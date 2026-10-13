"""Hosted session and retry metadata verified on isolated real MySQL databases."""
import secrets
import unittest
from unittest.mock import patch

from flask import Response, request
from db import connect, execute, one, settings
from manage import initialize, drop_temporary_database
from server import create_app
from web_state import MYSQL_STATE_SCHEMA, MySQLWebState


class CloudStateTests(unittest.TestCase):
    def setUp(self):
        self.business = 'mrp_test_' + secrets.token_hex(6)
        self.metadata = 'mrp_test_' + secrets.token_hex(6)
        self.addCleanup(self.cleanup)
        initialize(self.business)
        x = settings()
        c = connect(admin=True)
        try:
            execute(c, f'CREATE DATABASE `{self.metadata}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
            c.select_db(self.metadata)
            for sql in MYSQL_STATE_SCHEMA: execute(c, sql)
            who = c.escape(x['user']) + "@'localhost'"
            for table in ('sessions', 'operations'):
                execute(c, f'GRANT SELECT,INSERT,UPDATE,DELETE ON `{self.metadata}`.`{table}` TO {who}')
        finally:c.close()
        self.config = {**x, 'external':True, 'database':self.business, 'state_database':self.metadata,
                       'app_origin':'https://warehouse.example.test', 'backups_enabled':False}
        self.app = self.new_app()

    def cleanup(self):
        c = connect(admin=True)
        try:
            for database in (self.metadata, self.business):drop_temporary_database(c, database)
        finally:c.close()

    def new_app(self):
        # Use local encrypted-at-rest test credentials while exercising the cloud store.
        # TLS and environment validation are covered separately in test_cloud_config.
        with patch('server.settings', return_value=self.config):
            return create_app({'TESTING':True})

    def login(self):
        client = self.app.test_client()
        csrf = client.get('/api/session').json['csrf']
        response = client.post('/api/login', json={'username':'quanly','password':'Demo@12345'},
                               headers={'Origin':self.config['app_origin'],'X-CSRF-Token':csrf})
        self.assertEqual(response.status_code,200,response.json)
        return client

    def test_login_and_save_replay_survive_app_recreation(self):
        client = self.login()
        token = 'cloud-save-' + secrets.token_hex(8)
        body = dict(MaNCC=1,NgayChungTu='2026-10-13',lines=[dict(MaSP=1,MaViTri=1,SoLuongNhan=2,SoLuongLoi=0,DonGiaNhap=1)])
        csrf = client.get('/api/session').json['csrf']
        headers = {'Origin':self.config['app_origin'],'X-CSRF-Token':csrf,'Idempotency-Key':token}
        saved = client.post('/api/documents/incoming',json=body,headers=headers)
        self.assertEqual(saved.status_code,200,saved.json)
        restarted = self.new_app().test_client()
        restarted.set_cookie('session',client.get_cookie('session').value)
        self.assertEqual(restarted.get('/api/session').json['user']['TenDangNhap'],'quanly')
        repeated = restarted.post('/api/documents/incoming',json=body,headers=headers)
        self.assertEqual(repeated.status_code,200,repeated.json)
        self.assertTrue(repeated.json['replayed'])
        self.assertEqual(repeated.json['id'],saved.json['id'])
        c=connect(database=self.business)
        try:
            self.assertEqual(one(c,'SELECT COUNT(*) n FROM PHIEU_NHAP WHERE MaPN=%s',(saved.json['id'],))['n'],1)
            self.assertEqual(one(c,'SELECT COUNT(*) n FROM information_schema.tables WHERE table_schema=%s AND table_type=%s',(self.business,'BASE TABLE'))['n'],17)
        finally:c.close()

    def test_logout_cannot_be_reversed_by_stale_response(self):
        client=self.login()
        cookie=client.get_cookie('session').value
        interface=self.app.session_interface
        with self.app.test_request_context(headers={'Cookie':'session='+cookie}):
            logout=interface.open_session(self.app,request)
            stale=interface.open_session(self.app,request)
        logout.clear()
        interface.save_session(self.app,logout,Response())
        stale['csrf']='stale-response'
        response=Response()
        interface.save_session(self.app,stale,response)
        self.assertNotIn('Set-Cookie',response.headers)
        with interface.store.connection() as c:
            self.assertIsNone(c.execute('SELECT * FROM sessions WHERE sid=?',(stale.sid,)).fetchone())

    def test_metadata_rollback_and_case_sensitive_operation_tokens(self):
        store=MySQLWebState(self.metadata)
        with self.assertRaises(RuntimeError):
            with store.connection() as c:
                c.execute('INSERT INTO sessions VALUES (?,?,?,0)',('rollback','{}',9999999999))
                raise RuntimeError('rollback probe')
        with store.connection() as c:
            self.assertIsNone(c.execute('SELECT * FROM sessions WHERE sid=?',('rollback',)).fetchone())
        store.reserve(1,'incoming','Token-A','a'*64,1)
        store.reserve(1,'incoming','token-a','b'*64,2)
        store.complete(1,'incoming','Token-A')
        recovered=MySQLWebState(self.metadata)
        self.assertEqual(recovered.operation(1,'incoming','Token-A')['ident'],1)
        self.assertEqual(recovered.operation(1,'incoming','token-a')['ident'],2)
        self.assertEqual(recovered.operation(1,'incoming','Token-A')['completed'],1)


if __name__ == '__main__': unittest.main(verbosity=2)
