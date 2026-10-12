"""Session cookies, frozen notes and exact seed-label migrations on real MySQL."""
import unittest
import unicodedata
from pathlib import Path
from unittest.mock import patch

import pymysql
import migrations
from db import connect, execute, one, rows, sql_statements
from manage import SCHEMA, database_snapshot
from seed_labels import LEGACY_TEXT_LABELS, normalize_seed_labels
from test_integration import WarehouseTests


class AuditFixes(WarehouseTests):
    def test_authenticated_reads_do_not_reissue_login_cookie(self):
        self.assertFalse(self.app.config['SESSION_REFRESH_EACH_REQUEST'])
        for client, urls in [(self.admin, ['/api/session', '/api/state']),
                             (self.manager, ['/api/session', '/api/state', '/api/report?from=2026-01-01&to=2027-01-01'])]:
            for url in urls:
                with self.subTest(url=url):
                    response = client.get(url)
                    self.assertEqual(response.status_code, 200, response.json)
                    self.assertEqual(response.headers.getlist('Set-Cookie'), [])
        old_response = self.admin.get('/api/state')
        self.mutate(self.admin, 'logout')
        csrf = self.admin.get('/api/session').json['csrf']
        response = self.admin.post('/api/login', json=dict(username='nhanvien', password='Demo@12345'), headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(old_response.headers.getlist('Set-Cookie'), [])
        self.assertEqual(self.admin.get('/api/session').json['user']['VaiTro'], 'NHAN_VIEN')

    def test_old_unauthorized_response_does_not_delete_new_login_cookie(self):
        self.mutate(self.admin, 'accounts/1', dict(VaiTro='QUAN_LY_KHO', TrangThai='HOAT_DONG', password='Changed@12345'), method='PUT')
        old_response = self.manager.get('/api/state')
        self.assertEqual(old_response.status_code, 401)
        self.assertEqual(old_response.headers.getlist('Set-Cookie'), [])
        csrf = self.manager.get('/api/session').json['csrf']
        response = self.manager.post('/api/login', json=dict(username='quanly', password='Changed@12345'), headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.manager.get('/api/state').status_code, 200)

    def assert_note_frozen(self, c, table, key, ident):
        before = one(c, f'SELECT * FROM {table} WHERE {key}=%s', (ident,))
        values = ['Ghi chú sửa trái trạng thái', None, '']
        if before['GhiChu']:
            original = before['GhiChu']
            unaccented = ''.join(ch for ch in unicodedata.normalize('NFD', original) if not unicodedata.combining(ch))
            values.extend([original.swapcase(), unaccented, original+' '])
        for value in values:
            if value == before['GhiChu']:
                continue
            with self.assertRaises(pymysql.MySQLError) as error:
                execute(c, f'UPDATE {table} SET GhiChu=%s WHERE {key}=%s', (value, ident))
            self.assertEqual(error.exception.args[0], 1644)
            c.rollback()
            self.assertEqual(one(c, f'SELECT * FROM {table} WHERE {key}=%s', (ident,)), before)

    def test_final_notes_are_frozen_for_app_account(self):
        c = connect(database=self.database)
        self.addCleanup(c.close)
        for table, key, ident in [('PHIEU_NHAP', 'MaPN', 1), ('PHIEU_XUAT', 'MaPX', 2), ('KET_QUA_LAP_RAP', 'MaKQ', 1)]:
            with self.subTest(table=table):
                self.assert_note_frozen(c, table, key, ident)

    def test_draft_notes_and_rejection_remain_supported(self):
        c = connect(database=self.database)
        self.addCleanup(c.close)
        incoming = self.create('incoming', dict(MaNCC=1, NgayChungTu='2026-10-11', lines=[dict(MaSP=1, MaViTri=1, SoLuongNhan=1, SoLuongLoi=0, DonGiaNhap=1)]))
        execute(c, 'UPDATE PHIEU_NHAP SET GhiChu=%s WHERE MaPN=%s', ('Ghi chú nháp', incoming))
        self.action('incoming', incoming, 'commit')
        self.assert_note_frozen(c, 'PHIEU_NHAP', 'MaPN', incoming)
        outgoing = self.create('outgoing', dict(LoaiXuat='THANH_PHAM', TenNguoiNhan='Bộ phận kiểm thử', lines=[dict(MaSP=3, MaViTri=2, SoLuongXuat=1)]), self.employee)
        execute(c, 'UPDATE PHIEU_XUAT SET GhiChu=%s WHERE MaPX=%s', ('Ghi chú nháp', outgoing))
        self.action('outgoing', outgoing, 'send', self.employee)
        self.assert_note_frozen(c, 'PHIEU_XUAT', 'MaPX', outgoing)
        self.action('outgoing', outgoing, 'reject', reason='Không còn nhu cầu')
        self.assertEqual(one(c, 'SELECT LyDoTuChoi FROM PHIEU_XUAT WHERE MaPX=%s', (outgoing,))['LyDoTuChoi'], 'Không còn nhu cầu')
        self.assert_note_frozen(c, 'PHIEU_XUAT', 'MaPX', outgoing)
        job = self.job(qty=1)
        self.action('outgoing', self.allocate(job, cpu=1, ram=2), 'approve')
        result = self.create('results', dict(MaYC=job, SoLuongDat=1, SoLuongLoi=0, MaViTriDat=2), self.employee)
        execute(c, 'UPDATE KET_QUA_LAP_RAP SET GhiChu=%s WHERE MaKQ=%s', ('Ghi chú nháp', result))
        self.action('results', result, 'send', self.employee)
        self.assert_note_frozen(c, 'KET_QUA_LAP_RAP', 'MaKQ', result)
        self.action('results', result, 'reject', reason='Cần kiểm tra lại')
        self.assertEqual(one(c, 'SELECT GhiChu FROM KET_QUA_LAP_RAP WHERE MaKQ=%s', (result,))['GhiChu'], 'Cần kiểm tra lại')
        self.assert_note_frozen(c, 'KET_QUA_LAP_RAP', 'MaKQ', result)
        second = self.result(job, good=1, faulty=0)
        self.action('results', second, 'accept')
        self.assert_note_frozen(c, 'KET_QUA_LAP_RAP', 'MaKQ', second)

    def legacy_triggers(self, c):
        guard = migrations.FROZEN_NOTES_GUARD
        special = f" OR ({guard} AND NOT(OLD.TrangThai='CHO_TIEP_NHAN' AND NEW.TrangThai='TU_CHOI'))"
        statements = list(sql_statements(SCHEMA.read_text(encoding='utf-8')))
        for name in migrations.FROZEN_NOTES_TRIGGERS:
            source = next(sql for sql in statements if sql.startswith(f'CREATE TRIGGER {name} '))
            source = source.replace(' /* '+migrations.FROZEN_NOTES_MARKER+' */', '').replace(' OR '+guard, '').replace(special, '')
            self.assertNotIn('NEW.GhiChu', source)
            execute(c, f'DROP TRIGGER {name}')
            execute(c, source)
        return {name: one(c, f'SHOW CREATE TRIGGER {name}')['SQL Original Statement'] for name in migrations.FROZEN_NOTES_TRIGGERS}

    def cleanup_rollbacks(self):
        for path in (migrations.RUNTIME / 'migrations').glob(f'{self.database}_frozen_notes_*.sql'):
            path.unlink()

    def test_freeze_upgrade_preserves_rows_and_is_repeatable(self):
        self.addCleanup(self.cleanup_rollbacks)
        c = connect(admin=True, database=self.database)
        self.addCleanup(c.close)
        self.legacy_triggers(c)
        before = database_snapshot(c, self.database)
        result = migrations.upgrade_frozen_notes(c, self.database)
        self.assertTrue(result['changed'])
        self.assertEqual(result['triggers'], 3)
        self.assertTrue(Path(result['rollback']).is_file())
        self.assertEqual(database_snapshot(c, self.database), before)
        self.assertEqual(migrations.upgrade_frozen_notes(c, self.database), dict(changed=False))
        # A marker alone must not preserve a comparison that ignores case/accents.
        for name in migrations.FROZEN_NOTES_TRIGGERS:
            current = one(c, f'SHOW CREATE TRIGGER {name}')['SQL Original Statement']
            execute(c, f'DROP TRIGGER {name}')
            execute(c, current.replace(migrations.FROZEN_NOTES_GUARD, 'NOT(NEW.GhiChu<=>OLD.GhiChu)'))
        self.assertEqual(migrations.upgrade_frozen_notes(c, self.database)['triggers'], 3)
        self.assertEqual(database_snapshot(c, self.database), before)
        self.assertEqual(migrations.upgrade_frozen_notes(c, self.database), dict(changed=False))
        self.test_final_notes_are_frozen_for_app_account()

    def test_failed_freeze_upgrade_restores_every_touched_trigger(self):
        self.addCleanup(self.cleanup_rollbacks)
        c = connect(admin=True, database=self.database)
        self.addCleanup(c.close)
        originals = self.legacy_triggers(c)
        before = database_snapshot(c, self.database)
        def fail_second_replacement(connection, sql, args=()):
            if sql.startswith('CREATE TRIGGER trg_phieu_xuat_freeze ') and migrations.FROZEN_NOTES_MARKER in sql:
                raise RuntimeError('Simulated second trigger failure')
            return execute(connection, sql, args)
        with patch.object(migrations, 'execute', side_effect=fail_second_replacement):
            with self.assertRaisesRegex(RuntimeError, 'Simulated second trigger failure'):
                migrations.upgrade_frozen_notes(c, self.database)
        self.assertEqual({name: one(c, f'SHOW CREATE TRIGGER {name}')['SQL Original Statement'] for name in originals}, originals)
        self.assertEqual(database_snapshot(c, self.database), before)

    def test_freeze_upgrade_rejects_invalid_database_names(self):
        c = connect(admin=True, database=self.database)
        self.addCleanup(c.close)
        for name in ('', 'invalid-name', 'schema`; DROP DATABASE mysql'):
            with self.assertRaises(ValueError):
                migrations.upgrade_frozen_notes(c, name)

    def test_legacy_labels_upgrade_exact_values_once(self):
        c = connect(admin=True, database=self.database)
        self.addCleanup(c.close)
        for table, key, ident, field, old, new in LEGACY_TEXT_LABELS:
            execute(c, f'UPDATE {table} SET {field}=%s WHERE {key}=%s', (old, ident))
        before = {table: rows(c, f'SELECT * FROM {table} ORDER BY {key}') for table, key in [('NHAN_VIEN', 'MaNV'), ('LOAI_SAN_PHAM', 'MaLoai'), ('VI_TRI_KHO', 'MaViTri')]}
        snapshot = database_snapshot(c, self.database)
        self.assertEqual(normalize_seed_labels(c), 6)
        for table, key, ident, field, old, new in LEGACY_TEXT_LABELS:
            record = next(r for r in before[table] if r[key] == ident)
            record[field] = new
        for table, key in [('NHAN_VIEN', 'MaNV'), ('LOAI_SAN_PHAM', 'MaLoai'), ('VI_TRI_KHO', 'MaViTri')]:
            self.assertEqual(rows(c, f'SELECT * FROM {table} ORDER BY {key}'), before[table])
        after = database_snapshot(c, self.database)
        changed = {name for name in snapshot['tables'] if snapshot['tables'][name] != after['tables'][name]}
        self.assertEqual({name.upper() for name in changed}, {'NHAN_VIEN', 'LOAI_SAN_PHAM', 'VI_TRI_KHO'})
        self.assertEqual(normalize_seed_labels(c), 0)
        self.assertEqual(database_snapshot(c, self.database), after)

    def test_legacy_labels_preserve_custom_names_and_other_ids(self):
        c = connect(admin=True, database=self.database)
        self.addCleanup(c.close)
        for index, (table, key, ident, field, old, new) in enumerate(LEGACY_TEXT_LABELS):
            execute(c, f'UPDATE {table} SET {field}=%s WHERE {key}=%s', (old.upper() if index % 2 else 'Tên riêng của nhóm', ident))
        execute(c, "INSERT INTO LOAI_SAN_PHAM(TenLoai) VALUES('Linh kien PC')")
        before = database_snapshot(c, self.database)
        self.assertEqual(normalize_seed_labels(c), 0)
        self.assertEqual(database_snapshot(c, self.database), before)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(AuditFixes(name) for name in sorted(AuditFixes.__dict__) if name.startswith('test_'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
