"""Explicit one-time setup of empty hosted databases; never run during web startup."""
import argparse
import json
import os
import re
from pathlib import Path

import pymysql
from werkzeug.security import generate_password_hash

from db import ROOT, ConfigurationError, connect, execute, insert, one, run_sql, settings
from manage import grant_app
from seed_labels import normalize_seed_labels
from migrations import normalize_unit_labels
from web_state import MYSQL_STATE_SCHEMA


def load_private_config(path):
    values = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    allowed = {'MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_DATABASE', 'MYSQL_STATE_DATABASE', 'MYSQL_USER', 'MYSQL_PASSWORD',
               'MYSQL_ADMIN_USER', 'MYSQL_ADMIN_PASSWORD', 'MYSQL_SSL_CA', 'SECRET_KEY', 'APP_ORIGIN', 'INITIAL_PASSWORD'}
    if not isinstance(values, dict) or any(key not in allowed or not isinstance(value, str) for key, value in values.items()):
        raise ConfigurationError('Private config must contain only supported environment names and string values.')
    os.environ.update(values)


def export_render_environment(path):
    x = settings()
    if not x.get('external'): raise ConfigurationError('Export requires explicit hosted MySQL settings.')
    values = dict(MYSQL_HOST=x['host'], MYSQL_PORT=str(x['port']), MYSQL_DATABASE=x['database'],
                  MYSQL_STATE_DATABASE=x['state_database'], MYSQL_USER=x['user'], MYSQL_PASSWORD=x['password'],
                  SECRET_KEY=x['secret_key'], MYSQL_SSL_CA='/etc/secrets/ca.pem')
    if x['app_origin'] != 'https://setup.invalid': values['APP_ORIGIN'] = x['app_origin']
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # JSON strings are valid quoted dotenv values, including embedded punctuation.
    target.write_text('\n'.join(f'{key}={json.dumps(value)}' for key, value in values.items())+'\n',encoding='utf-8')
    return target


def object_count(c, database):
    return sum(one(c, f'SELECT COUNT(*) n FROM information_schema.{table} WHERE {field}=%s', (database,))['n']
               for table, field in [('tables', 'table_schema'), ('routines', 'routine_schema'), ('triggers', 'trigger_schema')])


def initialize_cloud(seed=False):
    x = settings()
    if not x.get('external'):
        raise ConfigurationError('Cloud setup requires explicit MYSQL_* settings.')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{1,31}', x['user']) or x['user'] == x.get('admin_user'):
        raise ConfigurationError('MYSQL_USER must be a new dedicated application user, different from MYSQL_ADMIN_USER.')
    password = os.environ.get('INITIAL_PASSWORD', '')
    if len(password) < 12:
        raise ConfigurationError('INITIAL_PASSWORD must have at least 12 characters for the initial web accounts.')
    schema = (ROOT / 'docs/mrp/schema_MRP_HTTTDN_17_bang.sql').read_text(encoding='utf-8')
    seed_sql = (ROOT / 'docs/mrp/demo_MRP_17_bang.sql').read_text(encoding='utf-8') if seed else None
    c = connect(admin=True)
    try:
        # All nonempty/occupied targets are rejected before the first DDL statement.
        if object_count(c, x['database']) or object_count(c, x['state_database']):
            raise ConfigurationError('Setup only accepts empty business and metadata databases. Existing objects were not changed.')
        try:
            one(c, 'SHOW GRANTS FOR %s@%s', (x['user'], '%'))
        except pymysql.MySQLError as error:
            if error.args[0] != 1141: raise
        else:
            raise ConfigurationError('The application MySQL user already exists. Choose a new dedicated user; credentials were not changed.')
        run_sql(c, schema)
        if seed_sql:
            run_sql(c, seed_sql)
            execute(c, 'UPDATE TAI_KHOAN SET MatKhauBam=%s', (generate_password_hash(password),))
            normalize_seed_labels(c)
            normalize_unit_labels(c)
        else:
            employee = insert(c, 'NHAN_VIEN', dict(HoTen='Quản trị viên'))
            insert(c, 'TAI_KHOAN', dict(MaNV=employee, TenDangNhap='admin', MatKhauBam=generate_password_hash(password), VaiTro='ADMIN'))
        execute(c, f'CREATE DATABASE IF NOT EXISTS `{x["state_database"]}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
        c.select_db(x['state_database'])
        for sql in MYSQL_STATE_SCHEMA: execute(c, sql)
        execute(c, 'CREATE USER %s@%s IDENTIFIED BY %s', (x['user'], '%', x['password']))
        grant_app(c, x['database'], host='%', create_account=False)
        who = (c.escape(x['user']) + "@'%'").replace('%', '%%')
        for table in ('sessions', 'operations'):
            execute(c, f'GRANT SELECT,INSERT,UPDATE,DELETE ON `{x["state_database"]}`.`{table}` TO {who}')
        # Check the restricted account, not just the provider's admin account.
        app_connection = connect()
        try:
            one(app_connection, 'SELECT COUNT(*) n FROM TAI_KHOAN')
            one(app_connection, f'SELECT COUNT(*) n FROM `{x["state_database"]}`.sessions')
        finally:
            app_connection.close()
        return dict(business_tables=17, metadata_tables=2, seeded=seed)
    finally:
        c.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-file', help='Private JSON environment settings outside Git; never printed.')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--initialize-empty', action='store_true', help='Acknowledge creation in explicitly configured empty databases.')
    action.add_argument('--export-render-env', metavar='PATH', help='Write app-only dotenv settings; excludes provider admin and initial account passwords.')
    parser.add_argument('--seed', action='store_true', help='Load the sample stock and four role accounts with INITIAL_PASSWORD.')
    args = parser.parse_args()
    if args.config_file: load_private_config(args.config_file)
    if args.export_render_env:
        print('Render environment file written:',export_render_environment(args.export_render_env))
    else:
        print('Cloud setup verified:', initialize_cloud(args.seed))
