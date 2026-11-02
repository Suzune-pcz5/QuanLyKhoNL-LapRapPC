"""MySQL connections and the authoritative, delimiter-aware SQL loader."""
import json
import os
import re
import ssl
from pathlib import Path

import pymysql

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
RUNTIME = Path(os.environ.get('MRP_RUNTIME') or (Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'HTTTDN-Demo'))


def cloud_mode():
    return bool(os.environ.get('DB_HOST') or os.environ.get('MYSQL_HOST') or os.environ.get('RENDER'))


def settings():
    if cloud_mode():
        aliases = {'DB_HOST': 'MYSQL_HOST', 'DB_PORT': 'MYSQL_PORT',
                   'DB_NAME': 'MYSQL_DATABASE', 'DB_USER': 'MYSQL_USER',
                   'DB_PASSWORD': 'MYSQL_PASSWORD', 'DB_SSL_CA': 'MYSQL_SSL_CA',
                   'APP_SECRET_KEY': 'SECRET_KEY'}
        env = {key: os.environ.get(key) or os.environ.get(alias)
               for key, alias in aliases.items()}
        required = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD',
                    'DB_SSL_CA', 'APP_SECRET_KEY')
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise RuntimeError('Thieu cau hinh cloud: ' + ', '.join(missing))
        ca = Path(env['DB_SSL_CA'])
        if not ca.is_file():
            raise RuntimeError('Khong tim thay chung chi CA MySQL: ' + str(ca))
        return dict(host=env['DB_HOST'], port=int(env['DB_PORT']),
                    database=env['DB_NAME'], user=env['DB_USER'],
                    password=env['DB_PASSWORD'],
                    secret_key=env['APP_SECRET_KEY'], ssl_ca=str(ca))
    return json.loads((RUNTIME / 'runtime.json').read_text(encoding='utf-8'))


def connect(admin=False, database=None):
    x = settings()
    if cloud_mode() and admin:
        raise RuntimeError('Cloud database khong cho phep ket noi root qua app. Su dung tai khoan migration rieng.')
    secure = {'ssl': ssl.create_default_context(cafile=x['ssl_ca'])} if cloud_mode() else {}
    return pymysql.connect(
        host=x['host'], port=x['port'], user='root' if admin else x['user'],
        password=x['root_password'] if admin else x['password'],
        database=database if database is not None else x['database'],
        charset='utf8mb4', autocommit=True, cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5, read_timeout=30, write_timeout=30,
        init_command="SET time_zone='+07:00',sql_mode='STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'",
        **secure,
    )


def rows(c, sql, args=()):
    with c.cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())


def one(c, sql, args=()):
    result = rows(c, sql, args)
    return result[0] if result else None


def execute(c, sql, args=()):
    with c.cursor() as cur:
        cur.execute(sql, args)
        return cur.lastrowid


def insert(c, table, data):
    # table and keys are exclusively server-owned allowlists.
    keys = list(data)
    return execute(c, f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join(['%s'] * len(keys))})", tuple(data[k] for k in keys))


def update(c, table, key, ident, data):
    execute(c, f"UPDATE {table} SET {','.join(k+'=%s' for k in data)} WHERE {key}=%s", (*data.values(), ident))


def call(c, name, args):
    with c.cursor() as cur:
        cur.execute(f"CALL {name}({','.join(['%s']*len(args))})", args)
        result = list(cur.fetchall())
        while cur.nextset():
            if cur.description:
                extra = list(cur.fetchall())
                if extra:
                    result = extra
        return result


def sql_statements(text):
    """Used with trusted schema/dump files, retaining routine delimiters."""
    delimiter = ';'
    buffer = ''
    for line in text.splitlines():
        if line.lstrip().startswith('--') or not line.strip():
            continue
        match = re.match(r'\s*DELIMITER\s+(\S+)', line, re.I)
        if match:
            delimiter = match[1]
            continue
        buffer += line + '\n'
        if buffer.rstrip().endswith(delimiter):
            yield buffer.rstrip()[:-len(delimiter)]
            buffer = ''
    if buffer.strip():
        raise ValueError('File SQL chua ket thuc cau lenh.')


def run_sql(c, text):
    with c.cursor() as cur:
        for sql in sql_statements(text):
            cur.execute(sql)
            while cur.nextset():
                pass
