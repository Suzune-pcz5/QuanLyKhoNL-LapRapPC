"""Isolated local runtime, database setup, verified backup and process control."""
import argparse
import json
import os
import secrets
import socket
import subprocess
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import pymysql
from werkzeug.security import generate_password_hash, check_password_hash

from db import BASE, ROOT, RUNTIME, connect, execute, one, rows, run_sql, settings
from seed_labels import normalize_seed_labels

MYSQL = RUNTIME / 'mysql-8.4.11-winx64'
SCHEMA = ROOT / 'docs/mrp/schema_MRP_HTTTDN_17_bang.sql'
PUBLIC = ['sp_chot_nhap', 'sp_ban_hanh_bom', 'sp_giao_yeu_cau', 'sp_nhan_viec',
          'sp_gui_de_nghi_xuat', 'sp_duyet_xuat', 'sp_tu_choi_xuat', 'sp_gui_ket_qua',
          'sp_tiep_nhan_ket_qua', 'sp_tu_choi_ket_qua', 'sp_huy_yeu_cau', 'sp_bao_cao_kho']
DRAFTS = ['PHIEU_NHAP', 'CT_PHIEU_NHAP', 'PHIEU_XUAT', 'CT_PHIEU_XUAT', 'BOM', 'CT_BOM', 'YEU_CAU_LAP_RAP', 'KET_QUA_LAP_RAP']
CATALOGS = ['NHAN_VIEN', 'TAI_KHOAN', 'LOAI_SAN_PHAM', 'SAN_PHAM', 'NHA_CUNG_CAP', 'VI_TRI_KHO']


def port_open(port):
    with socket.socket() as s:
        s.settimeout(.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


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


def grant_app(c, database):
    if not database.replace('_', '').isalnum():
        raise ValueError('Invalid database name')
    x = settings()
    execute(c, "CREATE USER IF NOT EXISTS %s@'localhost' IDENTIFIED BY %s", (x['user'], x['password']))
    execute(c, "ALTER USER %s@'localhost' IDENTIFIED BY %s", (x['user'], x['password']))
    who = "'" + x['user'] + "'@'localhost'"
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
    normalize_seed_labels(c)
    grant_app(c, database)
    c.close()
    return database


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
    finally:
        option.unlink(missing_ok=True)
    return name


def verify_restore(name):
    path = BASE / 'backups' / name
    if Path(name).name != name or not path.is_file() or not name.endswith('.sql'):
        raise ValueError('Backup khong hop le.')
    original = settings()['database']
    restored = 'mrp_restore_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + secrets.token_hex(3)
    c = connect(admin=True)
    execute(c, f'CREATE DATABASE `{restored}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
    c.select_db(restored)
    text = path.read_text(encoding='utf-8').replace(f'`{original}`.', f'`{restored}`.')
    run_sql(c, text)
    table_list = rows(c, 'SELECT TABLE_NAME FROM information_schema.tables WHERE table_schema=%s AND table_type=%s', (original, 'BASE TABLE'))
    for t in table_list:
        table = t['TABLE_NAME']
        a = rows(c, f'SELECT * FROM `{original}`.`{table}`')
        b = rows(c, f'SELECT * FROM `{restored}`.`{table}`')
        if sorted(map(repr, a)) != sorted(map(repr, b)):
            raise RuntimeError('Du lieu restore khong khop: ' + table)
    routine_count = one(c, 'SELECT COUNT(*) n FROM information_schema.routines WHERE routine_schema=%s', (restored,))['n']
    trigger_count = one(c, 'SELECT COUNT(*) n FROM information_schema.triggers WHERE trigger_schema=%s', (restored,))['n']
    view_count = one(c, 'SELECT COUNT(*) n FROM information_schema.views WHERE table_schema=%s', (restored,))['n']
    account = one(c, "SELECT * FROM TAI_KHOAN WHERE MaTK=1 AND MaNV=1 AND VaiTro='QUAN_LY_KHO' AND TenDangNhap IN ('quanly','demo_quanly')")
    if not account or not check_password_hash(account['MatKhauBam'], 'Demo@12345'):
        raise RuntimeError('Tai khoan quan ly da doi mat khau; chua kiem chung duoc dang nhap restore.')
    from db import call
    # A fresh draft and real transition in the restored database, not the original.
    product = one(c, "SELECT MaSP FROM SAN_PHAM WHERE LoaiMatHang='NGUYEN_LIEU' AND TrangThai='HOAT_DONG' LIMIT 1")
    loc = one(c, "SELECT MaViTri FROM VI_TRI_KHO WHERE TrangThai='HOAT_DONG' LIMIT 1")
    ncc = one(c, "SELECT MaNCC FROM NHA_CUNG_CAP WHERE TrangThai='HOAT_DONG' LIMIT 1")
    if not all([product, loc, ncc]):
        raise RuntimeError('Can danh muc hoat dong de kiem chung nghiep vu restore.')
    pn = execute(c, "INSERT INTO PHIEU_NHAP(LoaiNhap,MaNCC,MaNVLap,NgayChungTu) VALUES('NCC',%s,%s,CURRENT_DATE())", (ncc['MaNCC'], account['MaNV']))
    execute(c, 'INSERT INTO CT_PHIEU_NHAP(MaPN,MaSP,MaViTri,SoLuongNhan,DonGiaNhap) VALUES(%s,%s,%s,1,1)', (pn, product['MaSP'], loc['MaViTri']))
    call(c, 'sp_chot_nhap', (account['MaTK'], pn))
    c.close()
    return dict(database=restored, tables=len(table_list), routines=routine_count, triggers=trigger_count,
                views=view_count, data_matched=True, login_verified=True, transaction_verified=True)


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
    parser.add_argument('command', choices=['start', 'stop', 'init', 'backup', 'restore-test'])
    parser.add_argument('file', nargs='?')
    args = parser.parse_args()
    if args.command == 'start': start()
    elif args.command == 'stop': stop()
    elif args.command == 'init': print('Database:', initialize())
    elif args.command == 'backup': print('Backup:', backup())
    elif args.command == 'restore-test': print(json.dumps(verify_restore(args.file), ensure_ascii=False))
