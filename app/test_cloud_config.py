"""Hosted configuration, import and HTTP behavior without an external database."""
import json
import os
import ssl
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import cloud_setup
import db
import manage
import server
from web_state import WebState


ENV = dict(MYSQL_HOST='mysql.example.test', MYSQL_PORT='12345', MYSQL_DATABASE='warehouse',
           MYSQL_USER='mrp_web_app', MYSQL_PASSWORD='db-secret-for-tests', SECRET_KEY='s'*64,
           APP_ORIGIN='https://warehouse.example.test')


class CloudConfigTests(unittest.TestCase):
    def test_runtime_override_needs_no_windows_environment(self):
        self.assertEqual(config.runtime_path({'MRP_RUNTIME': '/tmp/mrp'}), Path('/tmp/mrp'))
        self.assertEqual(config.runtime_path({'XDG_DATA_HOME': '/tmp/data'}), Path('/tmp/data/HTTTDN-Demo'))
        self.assertEqual(config.runtime_path({'LOCALAPPDATA': 'C:/local'}), Path('C:/local/HTTTDN-Demo'))

    def test_import_without_localappdata_in_a_new_process(self):
        env = {k: v for k, v in os.environ.items() if k != 'LOCALAPPDATA' and not k.startswith('MYSQL_')}
        result = subprocess.run([sys.executable, '-c', 'import db,server; print("portable import passed")'],
                                cwd=Path(__file__).parent, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_partial_environment_does_not_read_local_credentials(self):
        with patch.dict(os.environ, {'MYSQL_HOST': 'private-host'}, clear=True), patch.object(config.json, 'loads') as read:
            with self.assertRaises(config.ConfigurationError) as error: config.settings()
            self.assertIn('MYSQL_PASSWORD', str(error.exception))
            self.assertNotIn('private-host', str(error.exception))
            read.assert_not_called()

    def test_render_requires_explicit_connection_settings(self):
        with patch.dict(os.environ, {'RENDER': 'true'}, clear=True):
            with self.assertRaises(config.ConfigurationError) as error: config.settings()
            self.assertIn('MYSQL_HOST', str(error.exception))

    def test_render_external_url_can_supply_the_https_origin(self):
        env={k:v for k,v in ENV.items() if k!='APP_ORIGIN'}
        with patch.dict(os.environ,{**env,'RENDER_EXTERNAL_URL':'https://service.onrender.com'},clear=True):
            self.assertEqual(config.settings()['app_origin'],'https://service.onrender.com')

    def test_environment_export_excludes_privileged_credentials(self):
        env={**ENV,'MYSQL_ADMIN_USER':'admin-private','MYSQL_ADMIN_PASSWORD':'admin-not-for-render','INITIAL_PASSWORD':'bootstrap-not-for-render'}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,env,clear=True):
            target=Path(folder)/'render.env'
            cloud_setup.export_render_environment(target)
            contents=target.read_text()
            self.assertNotIn('MYSQL_ADMIN',contents)
            self.assertNotIn('INITIAL_PASSWORD',contents)
            self.assertNotIn('admin-not-for-render',contents)
            self.assertNotIn('bootstrap-not-for-render',contents)
            self.assertIn('MYSQL_SSL_CA="/etc/secrets/ca.pem"',contents)

    def test_cloud_setup_rejects_existing_objects_before_changes(self):
        env={**ENV,'MYSQL_ADMIN_USER':'avnadmin','MYSQL_ADMIN_PASSWORD':'admin-test-secret','INITIAL_PASSWORD':'Bootstrap@12345'}
        with patch.dict(os.environ,env,clear=True), patch.object(cloud_setup,'connect'), \
             patch.object(cloud_setup,'object_count',return_value=1), patch.object(cloud_setup,'execute') as change:
            with self.assertRaises(config.ConfigurationError):cloud_setup.initialize_cloud(seed=True)
            change.assert_not_called()

    def test_cloud_setup_rejects_existing_application_user_before_changes(self):
        env={**ENV,'MYSQL_ADMIN_USER':'avnadmin','MYSQL_ADMIN_PASSWORD':'admin-test-secret','INITIAL_PASSWORD':'Bootstrap@12345'}
        with patch.dict(os.environ,env,clear=True), patch.object(cloud_setup,'connect'), \
             patch.object(cloud_setup,'object_count',return_value=0), patch.object(cloud_setup,'one',return_value={}), \
             patch.object(cloud_setup,'execute') as change:
            with self.assertRaises(config.ConfigurationError):cloud_setup.initialize_cloud(seed=True)
            change.assert_not_called()

    def test_local_json_fallback_preserves_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            data = dict(host='localhost', user='local_app', password='local-secret', database='local_db', secret_key='x'*64)
            (runtime/'runtime.json').write_text(json.dumps(data))
            with patch.dict(os.environ, {}, clear=True), patch.object(config, 'RUNTIME', runtime):
                loaded = config.settings()
            self.assertFalse(loaded['external'])
            self.assertEqual(loaded['password'], data['password'])

    def test_invalid_cloud_inputs_fail_without_secret_values(self):
        for changes in [dict(MYSQL_PORT='0'), dict(MYSQL_PORT='bad'), dict(SECRET_KEY='short-secret'),
                        dict(APP_ORIGIN='http://warehouse.example.test'), dict(APP_ORIGIN='https://user:secret@host'),
                        dict(APP_ORIGIN='https://host/path'), dict(MYSQL_DATABASE='bad;sql'),
                        dict(MYSQL_STATE_DATABASE='warehouse'), dict(MYSQL_ADMIN_USER='admin')]:
            with self.subTest(changes=changes), patch.dict(os.environ, {**ENV, **changes}, clear=True):
                with self.assertRaises(config.ConfigurationError) as error: config.settings()
                self.assertNotIn(ENV['MYSQL_PASSWORD'], str(error.exception))

    def test_tls_verifies_certificate_and_hostname(self):
        with patch.dict(os.environ, ENV, clear=True), patch.object(db.pymysql, 'connect') as connection:
            db.connect()
            args = connection.call_args.kwargs
            self.assertTrue(args['ssl'].check_hostname)
            self.assertEqual(args['ssl'].verify_mode, ssl.CERT_REQUIRED)
            self.assertEqual(args['user'], ENV['MYSQL_USER'])

    def test_invalid_ca_never_falls_back_to_plaintext(self):
        with patch.dict(os.environ, {**ENV, 'MYSQL_SSL_CA': '/not-existing/certificate.pem'}, clear=True), \
             patch.object(db.pymysql, 'connect') as connection:
            with self.assertRaises(config.ConfigurationError): db.connect()
            connection.assert_not_called()

    def test_admin_credentials_are_not_inferred_from_application_credentials(self):
        with patch.dict(os.environ, ENV, clear=True), patch.object(db.pymysql, 'connect') as connection:
            with self.assertRaises(config.ConfigurationError): db.connect(admin=True)
            connection.assert_not_called()

    def test_cloud_cannot_start_or_stop_local_services(self):
        with patch.dict(os.environ, ENV, clear=True), patch.object(manage.subprocess, 'run') as process:
            for function, args in [(manage.start_mysql, ()), (manage.initialize, ()), (manage.stop, ()),
                                   (manage.backup, ()), (manage.verify_restore, ('file.sql',)), (manage.cleanup_test_grants, ())]:
                with self.assertRaises(RuntimeError): function(*args)
            process.assert_not_called()

    def test_factory_and_health_do_not_connect_or_create_local_state(self):
        with patch.dict(os.environ, ENV, clear=True), patch.object(server, 'WebState') as local, \
             patch.object(db.pymysql, 'connect') as connection:
            app = server.create_app({'TESTING': True})
            client = app.test_client()
            token = app.session_interface.signer(app).dumps('signed-cookie-for-health')
            client.set_cookie('session', token)
            self.assertEqual(client.get('/healthz').json, {'status': 'ok'})
            client.delete_cookie('session')
            response = client.get('/')
            self.assertEqual(response.status_code, 200)
            response.close()
            local.assert_not_called()
            connection.assert_not_called()
            self.assertTrue(app.config['SESSION_COOKIE_SECURE'])

    def test_https_origin_behind_http_proxy_and_cloud_backup_guard(self):
        with tempfile.TemporaryDirectory() as folder, patch('web_state.RUNTIME', Path(folder)):
            store = WebState('cloud-http-test')
            with patch.dict(os.environ, ENV, clear=True), patch.object(server, 'MySQLWebState', return_value=store):
                app = server.create_app({'TESTING': True})
            client = app.test_client()
            csrf = client.get('/api/session').json['csrf']
            headers = {'X-CSRF-Token': csrf, 'Origin': ENV['APP_ORIGIN']}
            self.assertEqual(client.post('/api/login', json={}, headers={**headers, 'Origin': 'https://other.test'}).status_code, 403)
            user = dict(MaTK=1, MaNV=1, HoTen='Admin', TenDangNhap='admin', VaiTro='ADMIN', MatKhauBam='hash',
                        TrangThai='HOAT_DONG', NhanVienTrangThai='DANG_LAM')
            with patch.object(server, 'connect'), patch.object(server, 'authenticate', return_value=user), patch.object(server, 'one', return_value=user), \
                 patch.object(manage, 'backup') as backup:
                login = client.post('/api/login', json={'username':'admin','password':'test-pass'}, headers=headers)
                self.assertEqual(login.status_code, 200, login.json)
                self.assertIn('Secure', login.headers['Set-Cookie'])
                response = client.post('/api/backup', json={}, headers={**headers, 'X-CSRF-Token': login.json['csrf']})
                self.assertEqual(response.status_code, 409, response.json)
                backup.assert_not_called()


if __name__ == '__main__': unittest.main(verbosity=2)
