"""Portable local settings and explicit environment settings for hosted MySQL."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


class ConfigurationError(RuntimeError):
    pass


def runtime_path(env=None):
    env = os.environ if env is None else env
    if env.get('MRP_RUNTIME'):
        return Path(env['MRP_RUNTIME']).expanduser()
    if env.get('LOCALAPPDATA'):
        return Path(env['LOCALAPPDATA']) / 'HTTTDN-Demo'
    return Path(env.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'HTTTDN-Demo'


RUNTIME = runtime_path()


def external_configured(env=None):
    env = os.environ if env is None else env
    return bool(env.get('RENDER')) or any(key.startswith('MYSQL_') for key in env)


def database_name(value, variable):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', value):
        raise ConfigurationError(f'{variable} must contain only letters, digits and underscores, max 64 characters.')
    return value


def settings():
    if not external_configured():
        try:
            x = json.loads((RUNTIME / 'runtime.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            raise ConfigurationError('Local runtime is not initialized. Run start-demo.cmd, or configure MYSQL_* for hosted MySQL.') from None
        return {**x, 'external': False, 'backups_enabled': os.name == 'nt'}
    required = ('MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_DATABASE', 'MYSQL_USER', 'MYSQL_PASSWORD', 'SECRET_KEY')
    missing = [key for key in required if not os.environ.get(key)]
    origin_value = os.environ.get('APP_ORIGIN') or os.environ.get('RENDER_EXTERNAL_URL')
    if not origin_value: missing.append('APP_ORIGIN')
    if missing:
        raise ConfigurationError('Missing environment variables: ' + ', '.join(missing) + '. See docs/DEPLOY_RENDER.md.')
    try:
        port = int(os.environ['MYSQL_PORT'])
        if not 1 <= port <= 65535: raise ValueError()
    except ValueError:
        raise ConfigurationError('MYSQL_PORT must be an integer between 1 and 65535.') from None
    if len(os.environ['SECRET_KEY']) < 32:
        raise ConfigurationError('SECRET_KEY must have at least 32 characters.')
    try:
        origin = urlsplit(origin_value)
        origin.port
    except ValueError:
        raise ConfigurationError('APP_ORIGIN must be a valid HTTPS origin.') from None
    if origin.scheme != 'https' or not origin.hostname or origin.username or origin.password or origin.path not in ('', '/') or origin.query or origin.fragment:
        raise ConfigurationError('APP_ORIGIN must be an HTTPS origin without credentials, path, query or fragment.')
    database = database_name(os.environ['MYSQL_DATABASE'], 'MYSQL_DATABASE')
    state_database = database_name(os.environ.get('MYSQL_STATE_DATABASE', database + '_web'), 'MYSQL_STATE_DATABASE')
    if database.casefold() == state_database.casefold():
        raise ConfigurationError('MYSQL_STATE_DATABASE must differ from the seventeen-table business database.')
    admin_keys = ('MYSQL_ADMIN_USER', 'MYSQL_ADMIN_PASSWORD')
    if any(key in os.environ for key in admin_keys) and not all(os.environ.get(key) for key in admin_keys):
        raise ConfigurationError('Initialization requires both MYSQL_ADMIN_USER and MYSQL_ADMIN_PASSWORD.')
    return dict(host=os.environ['MYSQL_HOST'], port=port, database=database, user=os.environ['MYSQL_USER'],
                password=os.environ['MYSQL_PASSWORD'], secret_key=os.environ['SECRET_KEY'], external=True,
                state_database=state_database, app_origin=origin_value.rstrip('/'),
                ssl_ca=os.environ.get('MYSQL_SSL_CA'), admin_user=os.environ.get('MYSQL_ADMIN_USER'),
                admin_password=os.environ.get('MYSQL_ADMIN_PASSWORD'), backups_enabled=False)
