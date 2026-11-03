"""MySQL-backed management UI for the ERD's 18 tables."""
import hashlib
import os
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal

import pymysql
from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix
from flask.sessions import SecureCookieSessionInterface

from db import BASE, cloud_mode, connect, rows, one, execute, settings

TABLES = ('User', 'NV', 'KH', 'LoaiSP', 'SP', 'NCC', 'PNH', 'CTPNH',
          'VI_TRI_KHO', 'TON_KHO', 'HD', 'CTHD', 'KIEM_KE', 'CT_KIEM_KE',
          'CTKM', 'KMTheoHD', 'KMTheoVoucher', 'KMTheoSP')
CUSTOMER_READ = frozenset({'LoaiSP', 'SP'})
WAREHOUSE_TABLES = frozenset({'VI_TRI_KHO', 'TON_KHO', 'KIEM_KE', 'CT_KIEM_KE'})
# Named logins reference the existing ERD keys; no extra database columns.
LOGIN_ALIASES = {'admin': (1, 'ADMIN'), 'admincnpm': (2, 'ADMIN_CNPM'),
                 'nhanvien': (3, 'NHAN_VIEN')}


def readable_tables(user):
    if not user:
        return ()
    if user['LoaiUser'] == 'KH':
        return tuple(t for t in TABLES if t in CUSTOMER_READ)
    if user['role'] == 'ADMIN_CNPM':
        return tuple(t for t in TABLES if t not in WAREHOUSE_TABLES)
    return TABLES


def writable_tables(user):
    if not user or user['LoaiUser'] != 'NV':
        return ()
    if user['role'] in ('ADMIN', 'ADMIN_CNPM'):
        return readable_tables(user)
    if user['role'] == 'NHAN_VIEN':
        return tuple(t for t in readable_tables(user) if t != 'User')
    return ()


class ProxyAwareSessionInterface(SecureCookieSessionInterface):
    """Send Secure cookies when TLS terminates at the trusted local tunnel."""

    def get_cookie_secure(self, app):
        return app.config.get('SESSION_COOKIE_SECURE', False) or request.is_secure


class Problem(Exception):
    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


def require(condition, message, status=400):
    if not condition:
        raise Problem(message, status)


def normalize(value):
    if isinstance(value, dict):
        return {key: normalize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [normalize(val) for val in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat(sep=' ') if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def current_user(c):
    uid = session.get('uid')
    if not uid:
        return None
    user = one(c, 'SELECT * FROM `User` WHERE UserID=%s', (uid,))
    if not user or hashlib.sha256(user['pass'].encode()).hexdigest() != session.get('fingerprint'):
        session.clear()
        return None
    origin = 'NV' if user['LoaiUser'] == 'NV' else 'KH'
    key = 'MaNV' if origin == 'NV' else 'MaKH'
    reference = one(c, f'SELECT Ho,Ten FROM `{origin}` WHERE `{key}`=%s',
                    (user['MaThamChieu'],))
    if not reference:
        session.clear()
        return None
    user['HoTen'] = (reference['Ho'] + ' ' + reference['Ten']).strip()
    return user


def public_user(u):
    if u is None:
        return None
    result = {key: u[key] for key in ('UserID', 'role', 'LoaiUser', 'MaThamChieu', 'HoTen')}
    result['permissions'] = {'read': readable_tables(u), 'write': writable_tables(u)}
    return result


def table_columns(c, dbname, table):
    return rows(c, """
        SELECT COLUMN_NAME AS name, DATA_TYPE AS data_type, COLUMN_TYPE AS column_type,
               IS_NULLABLE AS nullable, COLUMN_DEFAULT AS default_value,
               COLUMN_KEY AS column_key, EXTRA AS extra
        FROM information_schema.columns
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION
    """, (dbname, table))


def create_app(test_config=None):
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    # Cloudflared forwards HTTPS scheme/host to the localhost-only web server.
    # Do not use this proxy setup if the web server is bound to a public port.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.session_interface = ProxyAwareSessionInterface()
    conf = settings()
    app.config.update(SECRET_KEY=conf['secret_key'],
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
        SESSION_COOKIE_SECURE=cloud_mode(),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=256 * 1024, DATABASE=conf['database'])
    if cloud_mode():
        hostname = os.environ.get('PUBLIC_HOST') or os.environ.get('RENDER_EXTERNAL_HOSTNAME')
        if hostname:
            app.config['TRUSTED_HOSTS'] = [hostname]
    if test_config:
        app.config.update(test_config)

    @app.before_request
    def prepare():
        if not request.path.startswith('/api/'):
            return
        g.c = connect(database=app.config['DATABASE'])
        g.user = current_user(g.c)
        session.setdefault('csrf', secrets.token_urlsafe(24))
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('Origin')
            require(not origin or origin == request.host_url.rstrip('/'),
                    'Nguồn yêu cầu không hợp lệ.', 403)
            if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), session['csrf']):
                raise Problem('Phiên đăng nhập đã thay đổi. Vui lòng thử lại.', 403, 'CSRF_EXPIRED')

    @app.after_request
    def prevent_api_cache(response):
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.teardown_request
    def cleanup(_):
        c = g.pop('c', None)
        if c:
            c.close()

    @app.errorhandler(Problem)
    def problem(e):
        body = {'error': str(e)}
        if e.code:
            body['code'] = e.code
        return jsonify(body), e.status

    @app.errorhandler(pymysql.IntegrityError)
    def integrity(e):
        return jsonify(error='Dữ liệu vi phạm khóa hoặc ràng buộc: ' + str(e.args[1])), 409

    @app.errorhandler(pymysql.OperationalError)
    def operational(e):
        if e.args and e.args[0] == 1644:
            return jsonify(error=str(e.args[1])), 409
        raise e

    @app.errorhandler(pymysql.DataError)
    def data_error(e):
        return jsonify(error='Giá trị không hợp lệ: ' + str(e.args[1])), 400

    @app.get('/')
    def index():
        return send_from_directory(BASE / 'static', 'index.html')

    @app.get('/healthz')
    def healthz():
        return jsonify(status='ok')

    @app.get('/api/session')
    def show_session():
        return jsonify(csrf=session['csrf'], user=public_user(g.user))

    @app.post('/api/login')
    def login():
        body = request.get_json(silent=True) or {}
        require(isinstance(body, dict), 'Dữ liệu đăng nhập không hợp lệ.')
        account = body.get('userID', '')
        require(isinstance(account, (str, int)) and not isinstance(account, bool),
                'Sai tài khoản hoặc mật khẩu.', 401)
        account = str(account).strip()
        alias = LOGIN_ALIASES.get(account.casefold())
        if alias:
            uid = alias[0]
        else:
            require(account.isascii() and account.isdecimal() and len(account) <= 10,
                    'Sai tài khoản hoặc mật khẩu.', 401)
            uid = int(account)
            require(0 < uid <= 2147483647, 'Sai tài khoản hoặc mật khẩu.', 401)
        password = body.get('password', '')
        require(isinstance(password, str), 'Mật khẩu không hợp lệ.')
        user = one(g.c, 'SELECT * FROM `User` WHERE UserID=%s', (uid,))
        require(bool(user) and (not alias or
                (user['role'] == alias[1] and user['LoaiUser'] == 'NV'))
                and check_password_hash(user['pass'], password),
                'Sai tài khoản hoặc mật khẩu.', 401)
        session.clear()
        session['uid'] = uid
        session['fingerprint'] = hashlib.sha256(user['pass'].encode()).hexdigest()
        session['csrf'] = secrets.token_urlsafe(24)
        g.user = current_user(g.c)
        require(g.user is not None, 'Tài khoản không tham chiếu đến người dùng hợp lệ.', 403)
        return jsonify(user=public_user(g.user), csrf=session['csrf'])

    @app.post('/api/logout')
    def logout():
        session.clear()
        session['csrf'] = secrets.token_urlsafe(24)
        return jsonify(ok=True, csrf=session['csrf'])

    def authorized(table, write=False):
        require(table in TABLES, 'Không có bảng này.', 404)
        require(g.user is not None, 'Bạn chưa đăng nhập.', 401)
        require(table in readable_tables(g.user), 'Không có quyền truy cập phần này.', 403)
        if write:
            require(table in writable_tables(g.user), 'Không có quyền sửa dữ liệu này.', 403)

    @app.get('/api/schema')
    def schema():
        require(g.user is not None, 'Bạn chưa đăng nhập.', 401)
        available = readable_tables(g.user)
        return jsonify(tables={table: table_columns(g.c, app.config['DATABASE'], table)
                               for table in TABLES if table in available})

    @app.get('/api/data/<table>')
    def list_data(table):
        authorized(table)
        try:
            limit = min(max(int(request.args.get('limit', 100)), 1), 500)
            offset = max(int(request.args.get('offset', 0)), 0)
        except (ValueError, TypeError):
            raise Problem('Phân trang không hợp lệ.')
        count = one(g.c, f'SELECT COUNT(*) AS n FROM `{table}`')['n']
        cols = table_columns(g.c, app.config['DATABASE'], table)
        pk = [col['name'] for col in cols if col['column_key'] == 'PRI']
        order_by = ','.join(f'`{key}`' for key in pk) or '1'
        records = rows(g.c, f'SELECT * FROM `{table}` ORDER BY {order_by} LIMIT %s OFFSET %s',
                       (limit, offset))
        if table == 'User':
            for record in records:
                record.pop('pass', None)
        return jsonify(rows=normalize(records), count=count)

    def clean_values(table, values, edit=False):
        require(isinstance(values, dict), 'Dữ liệu phải là object.')
        cols = table_columns(g.c, app.config['DATABASE'], table)
        allowed = {col['name'] for col in cols
                   if not edit or col['column_key'] != 'PRI'}
        require(bool(values) and set(values) <= allowed, 'Tên trường không hợp lệ.')
        require(all(not isinstance(v, (dict, list)) for v in values.values()),
                'Giá trị không hợp lệ.')
        result = dict(values)
        if table == 'User':
            if g.user['role'] == 'ADMIN_CNPM':
                require(result.get('role') != 'ADMIN',
                        'Chỉ admin chính được cấp quyền admin toàn quyền.', 403)
                if 'UserID' in result:
                    require(valid_user_id(result['UserID']) != 1,
                            'Không được thay đổi tài khoản admin chính.', 403)
            if 'pass' in result:
                require(isinstance(result['pass'], str) and len(result['pass']) >= 8,
                        'Mật khẩu cần ít nhất 8 ký tự.')
                result['pass'] = generate_password_hash(result['pass'])
            if 'role' in result:
                require(result['role'] in ('ADMIN', 'ADMIN_CNPM', 'NHAN_VIEN', 'KHACH_HANG', 'CHI_XEM'),
                        'Vai trò không hợp lệ.')
        return result

    def valid_user_id(value):
        require(isinstance(value, (str, int)) and not isinstance(value, bool),
                'Mã tài khoản không hợp lệ.')
        value = str(value).strip()
        require(value.isascii() and value.isdecimal() and len(value) <= 10,
                'Mã tài khoản không hợp lệ.')
        ident = int(value)
        require(0 < ident <= 2147483647, 'Mã tài khoản không hợp lệ.')
        return ident

    def protect_admin_account(ident):
        if g.user['role'] != 'ADMIN_CNPM':
            return
        # Keep the checked role locked until the following mutation commits.
        g.c.begin()
        account = one(g.c, 'SELECT UserID, `role` FROM `User` WHERE UserID=%s FOR UPDATE', (ident,))
        require(account is not None, 'Không tìm thấy tài khoản.', 404)
        require(account['UserID'] != 1 and account['role'] != 'ADMIN',
                'Không được thay đổi tài khoản admin toàn quyền.', 403)

    def key_condition(table, body):
        meta = table_columns(g.c, app.config['DATABASE'], table)
        keys = [c['name'] for c in meta if c['column_key'] == 'PRI']
        key_data = body.get('key')
        require(isinstance(key_data, dict) and keys and set(key_data) == set(keys),
                'Thiếu khóa chính.')
        if table == 'User':
            key_data['UserID'] = valid_user_id(key_data['UserID'])
        return ' AND '.join(f'`{k}`=%s' for k in keys), [key_data[k] for k in keys]

    @app.post('/api/data/<table>')
    def add_data(table):
        authorized(table, True)
        values = clean_values(table, request.get_json(silent=True) or {})
        fields = list(values)
        ident = execute(g.c,
            f'INSERT INTO `{table}` ({",".join(f"`{k}`" for k in fields)}) '
            f'VALUES ({",".join(["%s"] * len(fields))})',
            tuple(values[k] for k in fields))
        return jsonify(ok=True, id=ident), 201

    @app.put('/api/data/<table>')
    def edit_data(table):
        authorized(table, True)
        body = request.get_json(silent=True) or {}
        condition, args = key_condition(table, body)
        values = clean_values(table, body.get('values', {}), edit=True)
        if table == 'User' and body['key']['UserID'] == g.user['UserID'] and 'role' in values:
            require(values['role'] == g.user['role'], 'Không thể tự đổi vai trò.')
        if table == 'User':
            protect_admin_account(body['key']['UserID'])
        execute(g.c, f'UPDATE `{table}` SET ' +
                ','.join(f'`{k}`=%s' for k in values) + ' WHERE ' + condition,
                tuple(values.values()) + tuple(args))
        if table == 'User' and g.user['role'] == 'ADMIN_CNPM':
            g.c.commit()
        return jsonify(ok=True)

    @app.delete('/api/data/<table>')
    def delete_data(table):
        authorized(table, True)
        body = request.get_json(silent=True) or {}
        condition, args = key_condition(table, body)
        if table == 'User':
            require(body['key']['UserID'] != g.user['UserID'],
                    'Không thể xóa tài khoản đang đăng nhập.')
            protect_admin_account(body['key']['UserID'])
        execute(g.c, f'DELETE FROM `{table}` WHERE {condition}', tuple(args))
        if table == 'User' and g.user['role'] == 'ADMIN_CNPM':
            g.c.commit()
        return jsonify(ok=True)

    @app.get('/api/overview')
    def overview():
        require(g.user is not None, 'Bạn chưa đăng nhập.', 401)
        if g.user['LoaiUser'] == 'KH':
            return jsonify(products=one(g.c, 'SELECT COUNT(*) AS n FROM SP')['n'])
        result = {}
        for table in readable_tables(g.user):
            result[table] = one(g.c, f'SELECT COUNT(*) AS n FROM `{table}`')['n']
        return jsonify(result)

    return app


if __name__ == '__main__':
    serve(create_app(),
          host='0.0.0.0' if cloud_mode() else '127.0.0.1',
          port=int(os.environ.get('PORT', '8765')),
          threads=8,
          **({'trusted_proxy': '*',
              'trusted_proxy_headers': {'x-forwarded-proto', 'x-forwarded-host'}}
             if cloud_mode() else {}))
