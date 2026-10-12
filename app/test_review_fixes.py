"""Regression checks for revocable sessions, uncertain saves and frozen headers."""
import json
import secrets
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pymysql
import migrations
from db import connect, execute, one
from manage import database_snapshot, SCHEMA
from server import create_app
from test_integration import WarehouseTests


class ReviewFixes(WarehouseTests):
    def receipt(self):
        return dict(MaNCC=1, NgayChungTu='2026-10-11', GhiChu='Thử lưu lại', lines=[dict(MaSP=1, MaViTri=1, SoLuongNhan=1, SoLuongLoi=0, DonGiaNhap=1)])

    def save(self, client, token, data=None, kind='incoming'):
        csrf = client.get('/api/session').json['csrf']
        return client.post('/api/documents/' + kind, json=data or self.receipt(), headers={'X-CSRF-Token': csrf, 'Idempotency-Key': token})

    def test_logout_revokes_cookie_and_login_rotates_it(self):
        old = self.manager.get_cookie('session').value
        self.mutate(self.manager, 'logout')
        replay = self.app.test_client()
        replay.set_cookie('session', old)
        self.assertEqual(replay.get('/api/state').status_code, 401)
        csrf = self.manager.get('/api/session').json['csrf']
        anonymous = self.manager.get_cookie('session').value
        response = self.manager.post('/api/login', json=dict(username='quanly', password='Demo@12345'), headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(self.manager.get_cookie('session').value, anonymous)
        replay.set_cookie('session', anonymous)
        self.assertEqual(replay.get('/api/state').status_code, 401)
        replay.set_cookie('session', old)
        self.assertEqual(replay.get('/api/state').status_code, 401)

    def test_account_switch_revokes_previous_account_cookie(self):
        old = self.admin.get_cookie('session').value
        csrf = self.admin.get('/api/session').json['csrf']
        response = self.admin.post('/api/login', json=dict(username='nhanvien', password='Demo@12345'), headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 200)
        replay = self.app.test_client(); replay.set_cookie('session', old)
        self.assertEqual(replay.get('/api/state').status_code, 401)
        self.assertEqual(self.admin.get('/api/session').json['user']['VaiTro'], 'NHAN_VIEN')

    def test_sessions_survive_backend_restart_and_expire_on_server(self):
        cookie = self.manager.get_cookie('session').value
        restarted = create_app({'TESTING': True, 'DATABASE': self.database}).test_client()
        restarted.set_cookie('session', cookie)
        self.assertEqual(restarted.get('/api/state').status_code, 200)
        with patch('web_state.time.time', return_value=time.time() + 9 * 3600):
            self.assertEqual(restarted.get('/api/state').status_code, 401)

    def test_stale_session_save_cannot_resurrect_logged_out_account(self):
        from flask import request
        interface = self.app.session_interface
        cookie = self.manager.get_cookie('session').value
        with self.app.test_request_context('/api/session', headers={'Cookie': 'session=' + cookie}):
            old = interface.open_session(self.app, request)
        self.mutate(self.manager, 'logout')
        old['csrf'] = 'stale-response'
        response = self.app.response_class()
        interface.save_session(self.app, old, response)
        self.assertEqual(response.headers.getlist('Set-Cookie'), [])
        replay = self.app.test_client(); replay.set_cookie('session', cookie)
        self.assertEqual(replay.get('/api/state').status_code, 401)

    def test_retry_returns_same_draft_even_after_restart_or_finalization(self):
        token = secrets.token_hex(16); before = self.state()
        first = self.save(self.manager, token)
        self.assertEqual(first.status_code, 200, first.json)
        restarted = create_app({'TESTING': True, 'DATABASE': self.database}).test_client()
        restarted.set_cookie('session', self.manager.get_cookie('session').value)
        second = self.save(restarted, token)
        self.assertEqual(second.json['id'], first.json['id'])
        self.assertTrue(second.json['replayed'])
        self.assertEqual(len(self.state()['incoming']), len(before['incoming']) + 1)
        self.assertEqual(self.state()['inventory'], before['inventory'])
        self.action('incoming', first.json['id'], 'commit')
        stock = self.state()['inventory']
        self.assertEqual(self.save(self.manager, token).json['id'], first.json['id'])
        self.assertEqual(self.state()['inventory'], stock)
        changed = self.receipt(); changed['GhiChu'] = 'Nội dung khác'
        self.assertEqual(self.save(self.manager, token, changed).status_code, 409)
        # The same token is scoped by kind/account, and retries must still work
        # after publishing, assignment and final acceptance change the source state.
        def twice(client, kind, data):
            first = self.save(client, token, data, kind)
            second = self.save(client, token, data, kind)
            self.assertEqual(first.status_code, 200, first.json)
            self.assertEqual(second.status_code, 200, second.json)
            self.assertEqual(first.json['id'], second.json['id'])
            return first.json['id']
        bom_data = dict(MaSPThanhPham=3, PhienBan=2, TenCauHinh='Kiểm tra thử lại BOM', lines=[dict(MaSPLinhKien=1, DinhMuc=1), dict(MaSPLinhKien=2, DinhMuc=2)])
        bom = twice(self.manager, 'bom', bom_data)
        self.action('bom', bom, 'publish')
        self.assertEqual(self.save(self.manager, token, bom_data, 'bom').json['id'], bom)
        job_data = dict(MaBOM=bom, SoLuongYeuCau=1, MaNVNhan=2)
        job = twice(self.manager, 'jobs', job_data)
        self.action('jobs', job, 'assign'); self.action('jobs', job, 'receive', self.employee)
        self.assertEqual(self.save(self.manager, token, job_data, 'jobs').json['id'], job)
        self.action('outgoing', self.allocate(job, cpu=1, ram=2), 'approve')
        result_data = dict(MaYC=job, SoLuongDat=1, SoLuongLoi=0, MaViTriDat=2)
        result = twice(self.employee, 'results', result_data)
        self.action('results', result, 'send', self.employee); self.action('results', result, 'accept')
        self.assertEqual(self.save(self.employee, token, result_data, 'results').json['id'], result)
        outgoing_data = dict(LoaiXuat='THANH_PHAM', TenNguoiNhan='Kiểm tra thử lại', lines=[dict(MaSP=3, MaViTri=2, SoLuongXuat=1)])
        outgoing = twice(self.employee, 'outgoing', outgoing_data)
        other_outgoing = twice(self.other, 'outgoing', outgoing_data)
        self.assertNotEqual(outgoing, other_outgoing)

    def test_concurrent_retries_create_exactly_one_draft(self):
        token = secrets.token_hex(16); gate = threading.Barrier(2)
        clients = [self.login('quanly'), self.login('quanly')]
        before = len(self.state()['incoming'])
        def attempt(client):
            gate.wait()
            return self.save(client, token)
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(attempt, clients))
        self.assertEqual([r.status_code for r in replies], [200, 200])
        self.assertEqual(replies[0].json['id'], replies[1].json['id'])
        self.assertEqual(len(self.state()['incoming']), before + 1)

    def test_pending_operation_recovers_commit_and_rollback(self):
        store = self.app.session_interface.store
        for committed in (True, False):
            token = secrets.token_hex(16); data = self.receipt()
            import hashlib
            fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            c = connect(database=self.database)
            try:
                c.begin()
                ident = execute(c, "INSERT INTO PHIEU_NHAP(LoaiNhap,MaNCC,MaNVLap,NgayChungTu,GhiChu) VALUES('NCC',1,1,'2026-10-11','Thử lưu lại')")
                if committed:
                    execute(c, 'INSERT INTO CT_PHIEU_NHAP(MaPN,MaSP,MaViTri,SoLuongNhan,SoLuongLoi,DonGiaNhap) VALUES(%s,1,1,1,0,1)', (ident,))
                store.reserve(1, 'incoming', token, fingerprint, ident)
                c.commit() if committed else c.rollback()
            finally: c.close()
            response = self.save(self.manager, token, data)
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(response.json['id'] == ident, committed)

    def test_invalid_or_deleted_operation_does_not_create_new_draft(self):
        self.assertEqual(self.save(self.manager, 'bad').status_code, 400)
        token = secrets.token_hex(16); saved = self.save(self.manager, token).json['id']
        self.mutate(self.manager, f'documents/incoming/{saved}', method='DELETE')
        before = len(self.state()['incoming'])
        self.assertEqual(self.save(self.manager, token).status_code, 409)
        self.assertEqual(len(self.state()['incoming']), before)

    def test_save_outcome_distinguishes_rollback_from_a_committed_operation(self):
        before = self.state()
        invalid = self.receipt(); invalid['lines'][0]['SoLuongLoi'] = 2
        rejected = self.save(self.manager, secrets.token_hex(16), invalid)
        self.assertEqual(rejected.status_code, 400, rejected.json)
        self.assertTrue(rejected.json.get('save_not_committed'))
        duplicate = dict(MaSPThanhPham=3, PhienBan=1, TenCauHinh='Phiên bản trùng', lines=[dict(MaSPLinhKien=1, DinhMuc=1)])
        rejected = self.save(self.manager, secrets.token_hex(16), duplicate, 'bom')
        self.assertEqual(rejected.status_code, 409, rejected.json)
        self.assertTrue(rejected.json.get('save_not_committed'))
        store = self.app.session_interface.store
        with patch.object(store, 'reserve', side_effect=RuntimeError('Failure before commit')), patch.object(self.app.logger, 'exception'):
            rejected = self.save(self.manager, secrets.token_hex(16))
        self.assertEqual(rejected.status_code, 500, rejected.json)
        self.assertTrue(rejected.json.get('save_not_committed'))
        self.assertEqual(self.state()['incoming'], before['incoming'])
        self.assertEqual(self.state()['bom'], before['bom'])
        token = secrets.token_hex(16)
        with patch.object(store, 'complete', side_effect=RuntimeError('Failure after commit')), patch.object(self.app.logger, 'exception'):
            ambiguous = self.save(self.manager, token)
        self.assertEqual(ambiguous.status_code, 500, ambiguous.json)
        self.assertNotIn('save_not_committed', ambiguous.json)
        replay = self.save(self.manager, token)
        self.assertEqual(replay.status_code, 200, replay.json)
        self.assertTrue(replay.json['replayed'])
        changed = self.receipt(); changed['GhiChu'] = 'Dữ liệu khác'
        conflict = self.save(self.manager, token, changed)
        self.assertEqual(conflict.status_code, 409, conflict.json)
        self.assertNotIn('save_not_committed', conflict.json)
        # A successful COMMIT whose acknowledgement is lost must remain ambiguous,
        # even if the following rollback command succeeds on the same connection.
        commit_token = secrets.token_hex(16)
        original_commit = pymysql.connections.Connection.commit
        def lost_commit_reply(c):
            original_commit(c)
            raise pymysql.OperationalError(2013, 'Simulated missing COMMIT acknowledgement')
        with patch.object(pymysql.connections.Connection, 'commit', lost_commit_reply), patch.object(self.app.logger, 'exception'):
            ambiguous = self.save(self.manager, commit_token)
        self.assertEqual(ambiguous.status_code, 409, ambiguous.json)
        self.assertNotIn('save_not_committed', ambiguous.json)
        replay = self.save(self.manager, commit_token)
        self.assertEqual(replay.status_code, 200, replay.json)
        self.assertTrue(replay.json['replayed'])
        self.assertEqual(len(self.state()['incoming']), len(before['incoming']) + 2)
        self.assertEqual(self.state()['inventory'], before['inventory'])

    def test_frozen_header_fields_block_case_accents_null_and_date(self):
        c = connect(database=self.database); self.addCleanup(c.close)
        trials = [
            ('PHIEU_XUAT', 'MaPX', 2, 'TenNguoiNhan', ['Bộ phận bán hàng demo', 'BO PHAN BAN HANG DEMO', None, '']),
            ('BOM', 'MaBOM', 1, 'TenCauHinh', ['Cấu hình PC demo', 'CAU HINH PC DEMO', None, '']),
            ('YEU_CAU_LAP_RAP', 'MaYC', 1, 'HanMongMuon', ['2030-01-01 12:00:00']),
        ]
        for table, key, ident, field, values in trials:
            before = one(c, f'SELECT * FROM {table} WHERE {key}=%s', (ident,))
            for value in values:
                with self.assertRaises(pymysql.MySQLError) as error:
                    execute(c, f'UPDATE {table} SET {field}=%s WHERE {key}=%s', (value, ident))
                self.assertEqual(error.exception.args[0], 1644)
                c.rollback()
                self.assertEqual(one(c, f'SELECT * FROM {table} WHERE {key}=%s', (ident,)), before)
        job = self.job(qty=1)
        with self.assertRaises(pymysql.MySQLError):
            execute(c, 'UPDATE YEU_CAU_LAP_RAP SET HanMongMuon=%s WHERE MaYC=%s', ('2030-01-01', job))
        self.action('jobs', job, 'cancel', reason='Kiểm tra chuyển trạng thái hợp lệ')

    def legacy_headers(self, c):
        originals = {}
        for name, guard in migrations.FROZEN_HEADER_GUARDS.items():
            sql = one(c, f'SHOW CREATE TRIGGER {name}')['SQL Original Statement']
            sql = sql.replace(migrations.FROZEN_HEADERS_MARKER, '')
            if name == 'trg_yeu_cau_lap_rap_freeze': sql = sql.replace(' OR ' + guard, '')
            else:
                field = 'TenNguoiNhan' if name == 'trg_phieu_xuat_freeze' else 'TenCauHinh'
                sql = sql.replace(guard, f'NOT(NEW.{field}<=>OLD.{field})')
            execute(c, f'DROP TRIGGER {name}'); execute(c, sql)
            originals[name] = one(c, f'SHOW CREATE TRIGGER {name}')['SQL Original Statement']
        self.addCleanup(lambda: [p.unlink() for p in (migrations.RUNTIME/'migrations').glob(self.database+'_frozen_headers_*.sql')])
        return originals

    def test_header_migration_preserves_data_and_is_repeatable(self):
        c = connect(admin=True, database=self.database); self.addCleanup(c.close)
        self.legacy_headers(c); before = database_snapshot(c, self.database)
        result = migrations.upgrade_frozen_headers(c, self.database)
        self.assertEqual(result['triggers'], 3)
        self.assertTrue(Path(result['rollback']).is_file())
        self.assertEqual(database_snapshot(c, self.database), before)
        self.assertEqual(migrations.upgrade_frozen_headers(c, self.database), {'changed': False})

    def test_header_migration_restores_all_touched_triggers_on_failure(self):
        c = connect(admin=True, database=self.database); self.addCleanup(c.close)
        originals = self.legacy_headers(c); before = database_snapshot(c, self.database)
        def fail(connection, sql, args=()):
            if sql.startswith('CREATE TRIGGER trg_bom_freeze ') and migrations.FROZEN_HEADERS_MARKER in sql:
                raise RuntimeError('Simulated header upgrade failure')
            return execute(connection, sql, args)
        with patch.object(migrations, 'execute', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'Simulated header upgrade failure'):
                migrations.upgrade_frozen_headers(c, self.database)
        self.assertEqual({name: one(c, f'SHOW CREATE TRIGGER {name}')['SQL Original Statement'] for name in originals}, originals)
        self.assertEqual(database_snapshot(c, self.database), before)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(ReviewFixes(name) for name in sorted(ReviewFixes.__dict__) if name.startswith('test_'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
