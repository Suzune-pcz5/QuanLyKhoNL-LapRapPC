"""Isolated local runtime, database setup, verified backup and process control."""
import argparse
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import time
import webbrowser
from datetime import datetime
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

import pymysql
from werkzeug.security import generate_password_hash

from db import BASE, ROOT, RUNTIME, call, connect, execute, insert, one, rows, run_sql, settings
from seed_labels import normalize_seed_labels
from migrations import upgrade_stock_diagnostics, upgrade_frozen_notes, upgrade_frozen_headers, normalize_unit_labels
from config import external_configured

MYSQL = RUNTIME / 'mysql-8.4.11-winx64'
SCHEMA = ROOT / 'docs/mrp/schema_MRP_HTTTDN_17_bang.sql'
PUBLIC = ['sp_chot_nhap', 'sp_ban_hanh_bom', 'sp_giao_yeu_cau', 'sp_nhan_viec',
          'sp_gui_de_nghi_xuat', 'sp_duyet_xuat', 'sp_tu_choi_xuat', 'sp_gui_ket_qua',
          'sp_tiep_nhan_ket_qua', 'sp_tu_choi_ket_qua', 'sp_huy_yeu_cau', 'sp_bao_cao_kho']
DRAFTS = ['PHIEU_NHAP', 'CT_PHIEU_NHAP', 'PHIEU_XUAT', 'CT_PHIEU_XUAT', 'BOM', 'CT_BOM', 'YEU_CAU_LAP_RAP', 'KET_QUA_LAP_RAP']
CATALOGS = ['NHAN_VIEN', 'TAI_KHOAN', 'LOAI_SAN_PHAM', 'SAN_PHAM', 'NHA_CUNG_CAP', 'VI_TRI_KHO']
MANIFEST_PREFIX = '-- MRP_BACKUP_MANIFEST_V1: '
TEMP_DATABASE = re.compile(r'mrp_(?:(?:test|ui)_[0-9a-f]{12}|restore_\d{8}_\d{6}_(?:[0-9a-f]{6}|[0-9a-f]{12}))\Z')


class BackupVerificationError(RuntimeError):
    pass


def local_only(function):
    @wraps(function)
    def checked(*args, **kwargs):
        if os.name != 'nt' or external_configured():
            raise RuntimeError('This command manages the local Windows runtime only. Use cloud_setup.py for hosted MySQL.')
        return function(*args, **kwargs)
    return checked


def database_snapshot(c, database):
    """Order-independent row hashes and schema names, captured from one dump."""
    tables = rows(c, 'SELECT TABLE_NAME FROM information_schema.tables WHERE table_schema=%s AND table_type=%s ORDER BY TABLE_NAME', (database, 'BASE TABLE'))
    data = {}
    for row in tables:
        table = row['TABLE_NAME']
        records = sorted(json.dumps(r, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':')) for r in rows(c, f'SELECT * FROM `{database}`.`{table}`'))
        data[table] = dict(rows=len(records), sha256=hashlib.sha256('\n'.join(records).encode('utf-8')).hexdigest())
    objects = {}
    for kind, table, schema, name in [('views','views','table_schema','TABLE_NAME'), ('routines','routines','routine_schema','ROUTINE_NAME'), ('triggers','triggers','trigger_schema','TRIGGER_NAME')]:
        objects[kind] = [r['name'] for r in rows(c, f'SELECT {name} name FROM information_schema.{table} WHERE {schema}=%s ORDER BY {name}', (database,))]
    return dict(tables=data, **objects)


def rebase_dump(sql, source, target):
    # Replace qualified identifiers only; a note containing `source`. is data.
    pattern = r"('(?:\\.|''|[^'\\])*'|\"(?:\\.|\"\"|[^\"\\])*\")|`" + re.escape(source) + r'`(?=\.)'
    return re.sub(pattern, lambda m: m.group(1) if m.group(1) is not None else f'`{target}`', sql)


@contextmanager
def restored_dump(sql, source):
    restored = 'mrp_restore_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + secrets.token_hex(6)
    c = connect(admin=True)
    created = False
    try:
        execute(c, f'CREATE DATABASE `{restored}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
        created = True
        c.select_db(restored)
        run_sql(c, rebase_dump(sql, source, restored))
        yield c, restored
    finally:
        try:
            if created:
                c.rollback()
                execute(c, f'DROP DATABASE `{restored}`')
        finally:
            c.close()


def restore_business_probe(c):
    """Exercise production authentication and a real stock transition in isolation."""
    from server import authenticate
    token, password = secrets.token_hex(6), secrets.token_urlsafe(24)
    employee = insert(c, 'NHAN_VIEN', dict(HoTen='Kiểm thử khôi phục', TrangThai='DANG_LAM'))
    username = 'restore_' + token
    account = insert(c, 'TAI_KHOAN', dict(MaNV=employee, TenDangNhap=username, MatKhauBam=generate_password_hash(password), VaiTro='QUAN_LY_KHO', TrangThai='HOAT_DONG'))
    if not authenticate(c, username, password):
        raise BackupVerificationError('Không đăng nhập được tài khoản kiểm thử trong bản khôi phục.')
    category = insert(c, 'LOAI_SAN_PHAM', dict(TenLoai='Kiểm thử ' + token))
    product = insert(c, 'SAN_PHAM', dict(MaLoai=category, SKU='RESTORE-' + token, TenSP='Vật liệu kiểm thử', LoaiMatHang='NGUYEN_LIEU', DonViTinh='cái', TrangThai='HOAT_DONG'))
    location = insert(c, 'VI_TRI_KHO', dict(MaViTriHienThi='RESTORE-' + token, TrangThai='HOAT_DONG'))
    supplier = insert(c, 'NHA_CUNG_CAP', dict(TenNCC='Kiểm thử ' + token, TrangThai='HOAT_DONG'))
    receipt = insert(c, 'PHIEU_NHAP', dict(LoaiNhap='NCC', MaNCC=supplier, MaNVLap=employee, NgayChungTu=datetime.now().date()))
    insert(c, 'CT_PHIEU_NHAP', dict(MaPN=receipt, MaSP=product, MaViTri=location, SoLuongNhan=1, SoLuongLoi=0, DonGiaNhap=1))
    call(c, 'sp_chot_nhap', (account, receipt))
    stock = one(c, 'SELECT SoLuongThucTe FROM V_TON_KHO WHERE MaSP=%s AND MaViTri=%s', (product, location))
    if not stock or stock['SoLuongThucTe'] != 1:
        raise BackupVerificationError('Giao dịch nhập kho kiểm thử không cập nhật tồn đúng.')


def port_open(port):
    with socket.socket() as s:
        s.settimeout(.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


@local_only
def start_mysql():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    data = RUNTIME / 'mysql-data'
    exe = MYSQL / 'bin/mysqld.exe'
    if not exe.exists():
        raise RuntimeError('Chay setup.ps1 truoc de cai MySQL.')
    if not (data / 'auto.cnf').exists():
        subprocess.run([str(exe), '--initialize-insecure', f'--basedir={MYSQL}', f'--datadir={data}', '--console'], check=True)
    if not port_open(3397):
        proc = subprocess.Popen([str(exe), f'--basedir={MYSQL}', f'--datadir={data}', '--port=3397',
                                 '--bind-address=127.0.0.1', '--mysqlx=0', f'--log-error={RUNTIME / "mysql-error.log"}'],
                                creationflags=subprocess.CREATE_NO_WINDOW)
        (RUNTIME / 'mysql.pid').write_text(str(proc.pid))
    for _ in range(60):
        if port_open(3397):
            break
        time.sleep(.5)
    else:
        raise RuntimeError('MySQL chua san sang. Xem mysql-error.log.')
    conf = RUNTIME / 'runtime.json'
    if not conf.exists():
        pw = secrets.token_urlsafe(32)
        c = pymysql.connect(host='127.0.0.1', port=3397, user='root', password='', autocommit=True)
        with c.cursor() as cur:
            cur.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (pw,))
        c.close()
        conf.write_text(json.dumps(dict(host='127.0.0.1', port=3397, root_password=pw,
                                       password=secrets.token_urlsafe(32), secret_key=secrets.token_hex(32),
                                       database='htttdn_mrp_demo', user='mrp_app')), encoding='utf-8')


def grant_app(c, database, host='localhost', create_account=True):
    if not database.replace('_', '').isalnum():
        raise ValueError('Invalid database name')
    x = settings()
    if create_account:
        execute(c, 'CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s', (x['user'], host, x['password']))
        execute(c, 'ALTER USER %s@%s IDENTIFIED BY %s', (x['user'], host, x['password']))
    who = (c.escape(x['user']) + '@' + c.escape(host)).replace('%', '%%')
    execute(c, f'GRANT SELECT ON `{database}`.* TO {who}')
    for table in DRAFTS + CATALOGS:
        execute(c, f'GRANT INSERT, DELETE ON `{database}`.{table} TO {who}')
    allowed = {
        'PHIEU_NHAP': 'MaNCC,NgayChungTu,GhiChu',
        'PHIEU_XUAT': 'LoaiXuat,MaYCLapRap,TenNguoiNhan,GhiChu',
        'BOM': 'MaSPThanhPham,PhienBan,TenCauHinh',
        'YEU_CAU_LAP_RAP': 'MaBOM,SoLuongYeuCau,MaNVNhan,HanMongMuon',
        'KET_QUA_LAP_RAP': 'SoLuongDat,SoLuongLoi,MaViTriDat,MaViTriLoi,GhiChu',
        'NHAN_VIEN': 'HoTen,ChucVu,SoDienThoai,TrangThai',
        'TAI_KHOAN': 'MatKhauBam,VaiTro,TrangThai',
        'LOAI_SAN_PHAM': 'TenLoai,MoTa',
        'SAN_PHAM': 'MaLoai,SKU,TenSP,LoaiMatHang,DonViTinh,MoTa,TrangThai',
        'NHA_CUNG_CAP': 'TenNCC,SoDienThoai,DiaChi,TrangThai',
        'VI_TRI_KHO': 'MaViTriHienThi,KhuVuc,Ke,Tang,TrangThai',
    }
    for table, cols in allowed.items():
        execute(c, f'GRANT UPDATE ({cols}) ON `{database}`.{table} TO {who}')
    for routine in PUBLIC:
        execute(c, f'GRANT EXECUTE ON PROCEDURE `{database}`.{routine} TO {who}')


def temporary_database(database):
    return bool(TEMP_DATABASE.fullmatch(database)) and database != settings()['database']


def app_grants(c):
    """Read grants for only the configured local application account."""
    user = settings()['user']
    if user.casefold() == 'root':
        raise ValueError('Không thu hồi quyền của root.')
    if not one(c, "SELECT User FROM mysql.user WHERE User=%s AND Host='localhost'", (user,)):
        return []
    return [next(iter(r.values())) for r in rows(c, "SHOW GRANTS FOR %s@'localhost'", (user,))]


def grant_database(grant):
    match = re.search(r' ON (?:PROCEDURE |FUNCTION )?`([^`]+)`\.', grant)
    return match.group(1) if match and grant.startswith('GRANT ') else None


def revoke_temporary_grants(c, database, grants=None):
    """Revoke schema/table/column/routine grants only after a temporary DB is gone."""
    if not temporary_database(database):
        raise ValueError('Chỉ thu hồi quyền của CSDL kiểm thử có tên hợp lệ.')
    if one(c, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (database,)):
        raise ValueError('CSDL vẫn tồn tại; chưa thu hồi quyền.')
    count = 0
    for grant in app_grants(c) if grants is None else grants:
        if grant_database(grant) != database:
            continue
        statement, _, grantee = grant.partition(' TO ')
        account, option, _ = grantee.partition(' WITH GRANT OPTION')
        execute(c, 'REVOKE ' + statement.removeprefix('GRANT ') + ' FROM ' + account)
        if option:
            target = statement.partition(' ON ')[2]
            execute(c, 'REVOKE GRANT OPTION ON ' + target + ' FROM ' + account)
        count += 1
    return count


def drop_temporary_database(c, database):
    if not temporary_database(database):
        raise ValueError('Chỉ xóa CSDL kiểm thử có tên hợp lệ.')
    execute(c, f'DROP DATABASE IF EXISTS `{database}`')
    return revoke_temporary_grants(c, database)


@local_only
def cleanup_test_grants():
    """Keep all live schemas and the main database; remove only stale test grants."""
    c = connect(admin=True)
    try:
        grants = app_grants(c)
        candidates = {grant_database(g) for g in grants}
        removed, statements = [], 0
        for database in sorted(name for name in candidates if name and temporary_database(name)):
            if one(c, 'SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s', (database,)):
                continue
            statements += revoke_temporary_grants(c, database, grants)
            removed.append(database)
        return dict(databases=len(removed), grants=statements)
    finally:
        c.close()


@local_only
def initialize(database=None):
    start_mysql()
    x = settings()
    database = database or x['database']
    c = pymysql.connect(host=x['host'], port=x['port'], user='root', password=x['root_password'],
                        autocommit=True, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
    execute(c, f'CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
    c.select_db(database)
    count = one(c, 'SELECT COUNT(*) n FROM information_schema.tables WHERE table_schema=%s AND table_type=%s', (database, 'BASE TABLE'))['n']
    if count == 0:
        run_sql(c, SCHEMA.read_text(encoding='utf-8'))
        run_sql(c, (ROOT / 'docs/mrp/demo_MRP_17_bang.sql').read_text(encoding='utf-8'))
        execute(c, 'UPDATE TAI_KHOAN SET MatKhauBam=%s', (generate_password_hash('Demo@12345'),))
    elif count != 17:
        raise RuntimeError('CSDL chua du 17 bang. Khong tu xoa hoac ghi de du lieu.')
    try:
        upgrade_stock_diagnostics(c, database)
        upgrade_frozen_notes(c, database)
        upgrade_frozen_headers(c, database)
        normalize_seed_labels(c)
        normalize_unit_labels(c)
        grant_app(c, database)
    finally:
        c.close()
    return database


@local_only
def migrate():
    """Run with the backend stopped: upgrade routines/triggers and exact seed labels."""
    c = connect(admin=True)
    try:
        database = settings()['database']
        return dict(stock=upgrade_stock_diagnostics(c, database), frozen_notes=upgrade_frozen_notes(c, database),
                    frozen_headers=upgrade_frozen_headers(c, database),
                    sample_text_labels=normalize_seed_labels(c), units=normalize_unit_labels(c))
    finally:
        c.close()


@local_only
def backup():
    x = settings()
    folder = BASE / 'backups'
    folder.mkdir(exist_ok=True)
    name = 'mrp_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + secrets.token_hex(3) + '.sql'
    target = folder / name
    # Credentials stay in a short-lived options file, never command arguments or logs.
    option = RUNTIME / ('backup_' + secrets.token_hex(8) + '.cnf')
    option.write_text('[client]\nuser=root\npassword=' + x['root_password'] + '\nhost=127.0.0.1\nport=3397\n', encoding='utf-8')
    try:
        result = subprocess.run([str(MYSQL / 'bin/mysqldump.exe'), f'--defaults-extra-file={option}',
                                 '--routines', '--triggers', '--events', '--single-transaction', '--no-tablespaces',
                                 '--set-gtid-purged=OFF', '--complete-insert', '--default-character-set=utf8mb4',
                                 f'--result-file={target}', x['database']], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('Sao luu that bai: ' + result.stderr)
        sql = target.read_text(encoding='utf-8')
        # Capture the dumped snapshot, never the live database after the dump.
        with restored_dump(sql, x['database']) as (c, restored):
            snapshot = database_snapshot(c, restored)
        manifest = dict(version=1, source_database=x['database'], sql_sha256=hashlib.sha256(sql.encode('utf-8')).hexdigest(), snapshot=snapshot)
        target.write_text(MANIFEST_PREFIX + json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n' + sql, encoding='utf-8', newline='\n')
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        option.unlink(missing_ok=True)
    return name


@local_only
def verify_restore(name):
    path = BASE / 'backups' / name
    if Path(name).name != name or not path.is_file() or not name.endswith('.sql'):
        raise ValueError('Bản sao lưu không hợp lệ hoặc không tồn tại.')
    sql = path.read_text(encoding='utf-8-sig')
    manifest = None
    if sql.startswith(MANIFEST_PREFIX):
        header, _, sql = sql.partition('\n')
        try:
            manifest = json.loads(header[len(MANIFEST_PREFIX):])
            if manifest['version'] != 1 or manifest['sql_sha256'] != hashlib.sha256(sql.encode('utf-8')).hexdigest():
                raise ValueError('checksum')
            source = manifest['source_database']
            expected = manifest['snapshot']
        except (ValueError, KeyError, TypeError):
            raise BackupVerificationError('Bản sao lưu đã bị thay đổi hoặc thông tin kiểm chứng không hợp lệ.')
    else:
        match = re.search(r'^-- Host:.*?Database:\s+(\w+)\s*$', sql, re.M)
        source = match[1] if match else settings()['database']
    if not isinstance(source, str) or not re.fullmatch(r'[A-Za-z0-9_]+', source):
        raise BackupVerificationError('Tên cơ sở dữ liệu trong bản sao lưu không hợp lệ.')
    with restored_dump(sql, source) as (c, restored):
        snapshot = database_snapshot(c, restored)
        if manifest and snapshot != expected:
            raise BackupVerificationError('Dữ liệu khôi phục không khớp với dấu kiểm chứng của bản sao lưu.')
        if len(snapshot['tables']) != 17 or len(snapshot['views']) != 4 or len(snapshot['routines']) != 16 or len(snapshot['triggers']) != 19:
            raise BackupVerificationError('Bản khôi phục thiếu bảng, view, routine hoặc trigger của ứng dụng.')
        restore_business_probe(c)
    return dict(tables=len(snapshot['tables']), routines=len(snapshot['routines']), triggers=len(snapshot['triggers']),
                views=len(snapshot['views']), data_matched=bool(manifest), legacy_backup=not bool(manifest),
                login_verified=True, transaction_verified=True, temporary_database_removed=True)


def process_command(action):
    pid_file = RUNTIME / 'server.pid'
    pid = int(pid_file.read_text()) if pid_file.exists() else 0
    return ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(BASE / 'process_control.ps1'),
            '-Action', action, '-ServerPath', str(BASE / 'server.py'), '-RecordedPid', str(pid)]


def backend_state():
    result = subprocess.run(process_command('Inspect'), capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def listeners_belong_to_launch(state, root_pid):
    parents = {p['pid']: p['parent'] for p in state['processes']}
    for listener in state['listeners']:
        pid, visited = listener, set()
        while pid != root_pid:
            if pid in visited or pid not in parents:
                return False
            visited.add(pid)
            pid = parents[pid]
    return bool(state['listeners'])


def show_address():
    print('Kho PC: http://127.0.0.1:8765')
    if not os.environ.get('MRP_NO_BROWSER'):
        webbrowser.open('http://127.0.0.1:8765')


@local_only
def start():
    state = backend_state()
    owned = {p['pid'] for p in state['processes']}
    if (state['recorded_present'] and not state['recorded_owned']) or any(p not in owned for p in state['listeners']):
        raise RuntimeError('Backend thuoc ung dung/thu muc khac. Dung bang launcher cua thu muc dang chay truoc.')
    if state['listeners']:
        show_address()
        return
    if owned:
        raise RuntimeError('Backend dang khoi dong hoac bi treo. Xem server.log, hoac dung roi khoi dong lai.')
    initialize()
    if port_open(8765):
        raise RuntimeError('Cong 8765 vua bi ung dung khac su dung. Chua khoi dong backend.')
    log = open(RUNTIME / 'server.log', 'ab')
    p = subprocess.Popen([os.sys.executable, str(BASE / 'server.py')], cwd=BASE,
                         stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    (RUNTIME / 'server.pid').write_text(str(p.pid))
    log.close()
    for _ in range(40):
        if port_open(8765):
            if not listeners_belong_to_launch(backend_state(), p.pid):
                raise RuntimeError('Cong 8765 khong thuoc backend vua khoi dong. Khong nhan tien trinh khac.')
            show_address()
            return
        if p.poll() is not None:
            raise RuntimeError('Backend dung khi khoi dong. Xem server.log.')
        time.sleep(.25)
    raise RuntimeError('Backend chua san sang. Xem server.log.')


@local_only
def stop():
    # Match exact script arguments and stop both the venv launcher and its Python child.
    pid_file = RUNTIME / 'server.pid'
    subprocess.run(process_command('Stop'), check=True)
    for _ in range(20):
        if not port_open(8765):
            break
        time.sleep(.25)
    else:
        raise RuntimeError('Backend chua dung het. Giu PID va MySQL de kiem tra.')
    pid_file.unlink(missing_ok=True)
    try:
        c = connect(admin=True)
        execute(c, 'SHUTDOWN')
        c.close()
    except pymysql.MySQLError:
        pass
    print('Da dung backend va MySQL rieng cua ung dung.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['start', 'stop', 'init', 'migrate', 'backup', 'restore-test', 'cleanup-test-grants'])
    parser.add_argument('file', nargs='?')
    args = parser.parse_args()
    if args.command == 'start': start()
    elif args.command == 'stop': stop()
    elif args.command == 'init': print('Database:', initialize())
    elif args.command == 'migrate': print(json.dumps(migrate(), ensure_ascii=False))
    elif args.command == 'backup': print('Backup:', backup())
    elif args.command == 'restore-test': print(json.dumps(verify_restore(args.file), ensure_ascii=False))
    elif args.command == 'cleanup-test-grants': print(json.dumps(cleanup_test_grants(), ensure_ascii=False))
