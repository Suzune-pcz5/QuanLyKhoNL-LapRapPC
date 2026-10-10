"""Warehouse API. Business transitions delegate to the supplied MySQL procedures."""
import csv
import hashlib
import io
import secrets
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import pymysql
from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash
from waitress import serve

from db import BASE, call, connect, execute, insert, one, rows, settings, update

MANAGER = 'QUAN_LY_KHO'
EMPLOYEE = 'NHAN_VIEN'
ADMIN = 'ADMIN'
DOCS = {
    'incoming': ('PHIEU_NHAP', 'MaPN', MANAGER, 'MaNVLap', ['MaNCC', 'NgayChungTu', 'GhiChu']),
    'outgoing': ('PHIEU_XUAT', 'MaPX', EMPLOYEE, 'MaNVLap', ['LoaiXuat', 'MaYCLapRap', 'TenNguoiNhan', 'GhiChu']),
    'bom': ('BOM', 'MaBOM', MANAGER, 'MaNVLap', ['MaSPThanhPham', 'PhienBan', 'TenCauHinh']),
    'jobs': ('YEU_CAU_LAP_RAP', 'MaYC', MANAGER, 'MaNVGiao', ['MaBOM', 'SoLuongYeuCau', 'MaNVNhan', 'HanMongMuon']),
    'results': ('KET_QUA_LAP_RAP', 'MaKQ', EMPLOYEE, 'MaNVLap', ['SoLuongDat', 'SoLuongLoi', 'MaViTriDat', 'MaViTriLoi', 'GhiChu']),
}
DETAILS = {
    'incoming': ('CT_PHIEU_NHAP', ['MaSP', 'MaViTri', 'SoLuongNhan', 'SoLuongLoi', 'DonGiaNhap', 'KetQuaKiemTra']),
    'outgoing': ('CT_PHIEU_XUAT', ['MaSP', 'MaViTri', 'SoLuongXuat']),
    'bom': ('CT_BOM', ['MaSPLinhKien', 'DinhMuc']),
}
CATALOGS = {
    'products': ('SAN_PHAM', 'MaSP', ['MaLoai', 'SKU', 'TenSP', 'LoaiMatHang', 'DonViTinh', 'MoTa', 'TrangThai']),
    'categories': ('LOAI_SAN_PHAM', 'MaLoai', ['TenLoai', 'MoTa']),
    'suppliers': ('NHA_CUNG_CAP', 'MaNCC', ['TenNCC', 'SoDienThoai', 'DiaChi', 'TrangThai']),
    'locations': ('VI_TRI_KHO', 'MaViTri', ['MaViTriHienThi', 'KhuVuc', 'Ke', 'Tang', 'TrangThai']),
    'employees': ('NHAN_VIEN', 'MaNV', ['HoTen', 'ChucVu', 'SoDienThoai', 'TrangThai']),
}
ACTIONS = {
    'incoming': {'commit': ('sp_chot_nhap', MANAGER)},
    'outgoing': {'send': ('sp_gui_de_nghi_xuat', EMPLOYEE), 'approve': ('sp_duyet_xuat', MANAGER), 'reject': ('sp_tu_choi_xuat', MANAGER)},
    'bom': {'publish': ('sp_ban_hanh_bom', MANAGER)},
    'jobs': {'assign': ('sp_giao_yeu_cau', MANAGER), 'receive': ('sp_nhan_viec', EMPLOYEE), 'cancel': ('sp_huy_yeu_cau', MANAGER)},
    'results': {'send': ('sp_gui_ket_qua', EMPLOYEE), 'accept': ('sp_tiep_nhan_ket_qua', MANAGER), 'reject': ('sp_tu_choi_ket_qua', MANAGER)},
}


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def need(condition, message, status=400):
    if not condition:
        raise Problem(message, status)


def public_user(user):
    return {k: user[k] for k in ('MaTK', 'MaNV', 'HoTen', 'TenDangNhap', 'VaiTro')}


def stamp(user):
    return hashlib.sha256(user['MatKhauBam'].encode()).hexdigest()[:24]


def integer(value, name, minimum=1, optional=False):
    if optional and value in ('', None):
        return None
    try:
        v = int(value)
        need(not isinstance(value, bool) and str(v) == str(value) and minimum <= v <= 2147483647, f'{name} phải là số nguyên từ {minimum}.')
        return v
    except (TypeError, ValueError):
        raise Problem(f'{name} phải là số nguyên từ {minimum}.')


def text(value, name, limit=255, required=False):
    need(value is None or isinstance(value, str), f'{name} phải là văn bản.')
    value = (value or '').strip()
    need(len(value) <= limit and (value or not required), f'{name} không hợp lệ (tối đa {limit} ký tự).')
    return value or None


def active(c, table, key, ident, state='HOAT_DONG'):
    r = one(c, f'SELECT * FROM {table} WHERE {key}=%s', (ident,))
    need(r is not None and ('TrangThai' not in r or r['TrangThai'] == state), f'{table} #{ident} không hoạt động hoặc không tồn tại.')
    return r


def product(c, ident, kind):
    p = active(c, 'SAN_PHAM', 'MaSP', ident)
    need(p['LoaiMatHang'] == kind, f"{p['SKU']}: loại mặt hàng không phù hợp.")
    return p


def normalized(obj):
    if isinstance(obj, dict): return {k: normalized(v) for k, v in obj.items()}
    if isinstance(obj, (tuple, list)): return [normalized(v) for v in obj]
    if isinstance(obj, (date, datetime)): return obj.isoformat(sep=' ') if isinstance(obj, datetime) else obj.isoformat()
    if isinstance(obj, Decimal): return int(obj) if obj == obj.to_integral_value() else str(obj)
    return obj


def create_app(test_config=None):
    app = Flask(__name__, static_folder='static', static_url_path='/static')
    x = settings()
    app.config.update(SECRET_KEY=x['secret_key'], SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=512*1024,
                      DATABASE=x['database'], TESTING=False)
    if test_config: app.config.update(test_config)
    rate = {}
    rate_lock = threading.Lock()
    backup_lock = threading.Lock()

    @app.before_request
    def authorize():
        if not request.path.startswith('/api/'):
            return
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('Origin')
            need(not origin or origin == request.host_url.rstrip('/'), 'Nguồn yêu cầu không hợp lệ.', 403)
            need(secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), session.get('csrf', '?')), 'Phiên thao tác hết hạn. Tải lại trang.', 403)
        if request.path in ('/api/session', '/api/login'):
            return
        need(session.get('account'), 'Vui lòng đăng nhập.', 401)
        g.c = connect(database=app.config['DATABASE'])
        g.user = one(g.c, 'SELECT t.*,n.HoTen,n.TrangThai NhanVienTrangThai FROM TAI_KHOAN t JOIN NHAN_VIEN n ON n.MaNV=t.MaNV WHERE t.MaTK=%s', (session['account'],))
        if not g.user or g.user['TrangThai'] != 'HOAT_DONG' or g.user['NhanVienTrangThai'] != 'DANG_LAM' or session.get('stamp') != stamp(g.user):
            session.clear()
            raise Problem('Tài khoản bị khóa, ngừng làm hoặc mật khẩu đã đổi. Đăng nhập lại.', 401)

    @app.teardown_request
    def cleanup(_error):
        c = g.pop('c', None)
        if c:
            c.rollback()
            c.close()

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(Problem)
    def problem(error): return jsonify(error=str(error)), error.status

    @app.errorhandler(pymysql.MySQLError)
    def database_error(error):
        code = error.args[0] if error.args else 0
        if code == 1644: message = str(error.args[1])
        elif code == 1062: message = 'Dữ liệu bị trùng. Kiểm tra SKU, phiên bản BOM hoặc phiếu cấp đang có hiệu lực.'
        elif code in (1451, 1452): message = 'Dữ liệu đã được tham chiếu hoặc đối tượng liên quan không tồn tại. Hãy ngừng sử dụng thay vì xóa lịch sử.'
        elif code in (3819, 1264, 1366): message = 'Giá trị không thỏa quy tắc dữ liệu. Kiểm tra số lượng, nguồn phiếu và vị trí.'
        elif code in (1213, 1205): message = 'Dữ liệu đang được xử lý đồng thời. Thử lại trên cùng mã phiếu.'
        else:
            app.logger.exception('Database operation failed')
            message = 'Không thể xử lý dữ liệu. Xem log backend hoặc thử lại.'
        return jsonify(error=message), 409

    @app.errorhandler(HTTPException)
    def http_error(error): return jsonify(error='Yêu cầu không hợp lệ hoặc đường dẫn không tồn tại.'), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception('Unexpected operation failure')
        return jsonify(error='Không thể hoàn tất thao tác. Xem log backend để kiểm tra.'), 500

    def role(expected):
        need(g.user['VaiTro'] == expected, 'Tài khoản không có quyền thực hiện thao tác này.', 403)

    def body():
        b = request.get_json(silent=True)
        need(isinstance(b, dict), 'Cần dữ liệu JSON hợp lệ.')
        return b

    @app.get('/')
    def home(): return send_from_directory(BASE / 'static', 'index.html')

    @app.get('/api/session')
    def current_session():
        session.setdefault('csrf', secrets.token_urlsafe(32))
        user = None
        if session.get('account'):
            c = connect(database=app.config['DATABASE'])
            try:
                u = one(c, 'SELECT t.*,n.HoTen,n.TrangThai NvState FROM TAI_KHOAN t JOIN NHAN_VIEN n ON n.MaNV=t.MaNV WHERE t.MaTK=%s', (session['account'],))
                if u and u['TrangThai'] == 'HOAT_DONG' and u['NvState'] == 'DANG_LAM' and stamp(u) == session.get('stamp'):
                    user = public_user(u)
            finally: c.close()
        return jsonify(csrf=session['csrf'], user=user)

    @app.post('/api/login')
    def login():
        b = body()
        ip = request.remote_addr
        with rate_lock:
            attempts = [t for t in rate.get(ip, []) if t > time.time()-60]
            need(len(attempts) < 15, 'Đăng nhập quá nhiều lần. Chờ một phút rồi thử lại.', 429)
            attempts.append(time.time()); rate[ip] = attempts
        c = connect(database=app.config['DATABASE'])
        try:
            u = one(c, 'SELECT t.*,n.HoTen,n.TrangThai NvState FROM TAI_KHOAN t JOIN NHAN_VIEN n ON n.MaNV=t.MaNV WHERE TenDangNhap=%s', (text(b.get('username'), 'Tên đăng nhập', 100, True),))
            password = text(b.get('password'), 'Mật khẩu', 255, True)
            need(u and u['TrangThai'] == 'HOAT_DONG' and u['NvState'] == 'DANG_LAM' and check_password_hash(u['MatKhauBam'], password), 'Tên đăng nhập, mật khẩu không đúng hoặc tài khoản bị khóa.', 401)
            session.clear(); session.permanent = True
            session.update(account=u['MaTK'], stamp=stamp(u), csrf=secrets.token_urlsafe(32))
            return jsonify(user=public_user(u), csrf=session['csrf'])
        finally: c.close()

    @app.post('/api/logout')
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/state')
    def state():
        c, u = g.c, g.user
        result = {'user': public_user(u), 'database': 'MySQL 8.4 · 17 bảng', 'now': one(c, 'SELECT NOW() n')['n']}
        for name, (table, key, _fields) in CATALOGS.items():
            result[name] = rows(c, f'SELECT * FROM {table} ORDER BY {key}')
        result['employees'] = rows(c, 'SELECT n.*,t.MaTK,t.VaiTro,t.TrangThai TaiKhoanTrangThai FROM NHAN_VIEN n LEFT JOIN TAI_KHOAN t ON t.MaNV=n.MaNV ORDER BY MaNV')
        if u['VaiTro'] == EMPLOYEE:
            result['employees'] = [n for n in result['employees'] if n['MaNV'] == u['MaNV']]
        result['accounts'] = rows(c, 'SELECT MaTK,MaNV,TenDangNhap,VaiTro,TrangThai,NgayTao FROM TAI_KHOAN ORDER BY MaTK') if u['VaiTro'] == ADMIN else []
        result['inventory'] = rows(c, 'SELECT v.*,s.TrangThai SanPhamTrangThai,k.TrangThai ViTriTrangThai FROM V_TON_KHO v JOIN SAN_PHAM s ON s.MaSP=v.MaSP JOIN VI_TRI_KHO k ON k.MaViTri=v.MaViTri ORDER BY SKU,MaViTri')
        for kind, (table, key, _role, _owner, _fields) in DOCS.items():
            where, args = '', ()
            if u['VaiTro'] == EMPLOYEE:
                if kind == 'incoming': result[kind] = []; continue
                if kind == 'jobs': where, args = ' WHERE MaNVNhan=%s', (u['MaNV'],)
                elif kind in ('results', 'outgoing'): where, args = ' WHERE MaNVLap=%s', (u['MaNV'],)
            docs = rows(c, f'SELECT * FROM {table}{where} ORDER BY {key} DESC', args)
            for d in docs:
                if kind in DETAILS:
                    detail_table, _fields = DETAILS[kind]
                    d['lines'] = rows(c, f'SELECT * FROM {detail_table} WHERE {key}=%s', (d[key],))
                if kind == 'jobs':
                    d['needs'] = rows(c, 'SELECT * FROM V_NHU_CAU_LAP_RAP WHERE MaYC=%s', (d[key],))
                    d['materials'] = rows(c, 'SELECT * FROM V_VAT_LIEU_LAP_RAP WHERE MaYC=%s', (d[key],))
                    d['accepted'] = one(c, "SELECT COALESCE(SUM(SoLuongDat+SoLuongLoi),0) n FROM KET_QUA_LAP_RAP WHERE MaYC=%s AND TrangThai='DA_TIEP_NHAN'", (d[key],))['n']
                    d['pending'] = one(c, "SELECT COALESCE(SUM(SoLuongDat+SoLuongLoi),0) n FROM KET_QUA_LAP_RAP WHERE MaYC=%s AND TrangThai='CHO_TIEP_NHAN'", (d[key],))['n']
            result[kind] = docs
        result['ledger'] = rows(c, 'SELECT b.*,s.SKU,s.TenSP,v.MaViTriHienThi,n.HoTen FROM BIEN_DONG_KHO b JOIN SAN_PHAM s ON s.MaSP=b.MaSP JOIN VI_TRI_KHO v ON v.MaViTri=b.MaViTri JOIN NHAN_VIEN n ON n.MaNV=b.MaNV ORDER BY MaBienDong DESC') if u['VaiTro'] in (MANAGER, ADMIN) else []
        return jsonify(normalized(result))

    def document_values(kind, b):
        c = g.c
        if kind == 'incoming':
            ncc = integer(b.get('MaNCC'), 'Nhà cung cấp'); active(c, 'NHA_CUNG_CAP', 'MaNCC', ncc)
            try: day = date.fromisoformat(b.get('NgayChungTu', ''))
            except (TypeError, ValueError): raise Problem('Ngày chứng từ không hợp lệ.')
            return dict(MaNCC=ncc, NgayChungTu=day, GhiChu=text(b.get('GhiChu'), 'Ghi chú'))
        if kind == 'outgoing':
            typ = b.get('LoaiXuat'); need(typ in ('CAP_PHAT', 'THANH_PHAM'), 'Loại xuất không hợp lệ.')
            yc = integer(b.get('MaYCLapRap'), 'Yêu cầu', optional=True) if typ == 'CAP_PHAT' else None
            if typ == 'CAP_PHAT':
                job = one(c, 'SELECT * FROM YEU_CAU_LAP_RAP WHERE MaYC=%s', (yc,))
                need(job and job['MaNVNhan'] == g.user['MaNV'], 'Chỉ được cấp vật liệu cho việc của mình.', 403)
            return dict(LoaiXuat=typ, MaYCLapRap=yc, TenNguoiNhan=text(b.get('TenNguoiNhan'), 'Người nhận', 150, True) if typ == 'THANH_PHAM' else None, GhiChu=text(b.get('GhiChu'), 'Ghi chú', 500))
        if kind == 'bom':
            sp = integer(b.get('MaSPThanhPham'), 'Thành phẩm'); product(c, sp, 'THANH_PHAM')
            return dict(MaSPThanhPham=sp, PhienBan=integer(b.get('PhienBan'), 'Phiên bản'), TenCauHinh=text(b.get('TenCauHinh'), 'Tên cấu hình', 200, True))
        if kind == 'jobs':
            bom = integer(b.get('MaBOM'), 'BOM')
            need(one(c, "SELECT MaBOM FROM BOM WHERE MaBOM=%s AND TrangThai='DANG_AP_DUNG'", (bom,)), 'Cần BOM đang áp dụng.')
            nv = integer(b.get('MaNVNhan'), 'Nhân viên')
            need(one(c, "SELECT t.MaTK FROM TAI_KHOAN t JOIN NHAN_VIEN n ON n.MaNV=t.MaNV WHERE t.MaNV=%s AND t.VaiTro='NHAN_VIEN' AND t.TrangThai='HOAT_DONG' AND n.TrangThai='DANG_LAM'", (nv,)), 'Nhân viên chưa có tài khoản hoạt động.')
            due = b.get('HanMongMuon')
            try: due = datetime.fromisoformat(due) if due else None
            except (TypeError, ValueError): raise Problem('Hạn mong muốn không hợp lệ.')
            return dict(MaBOM=bom, SoLuongYeuCau=integer(b.get('SoLuongYeuCau'), 'Số PC'), MaNVNhan=nv, HanMongMuon=due)
        dat = integer(b.get('SoLuongDat', 0), 'Số đạt', 0); loi = integer(b.get('SoLuongLoi', 0), 'Số lỗi', 0)
        need(dat + loi > 0, 'Cần ít nhất một PC đạt hoặc lỗi.')
        result = dict(SoLuongDat=dat, SoLuongLoi=loi, GhiChu=text(b.get('GhiChu'), 'Ghi chú', 500))
        for key, amount in [('MaViTriDat', dat), ('MaViTriLoi', loi)]:
            ident = integer(b.get(key), 'Vị trí', optional=not amount)
            if ident: active(c, 'VI_TRI_KHO', 'MaViTri', ident)
            result[key] = ident
        return result

    def save_lines(kind, ident, b):
        table, fields = DETAILS[kind]; key = DOCS[kind][1]
        lines = b.get('lines')
        need(isinstance(lines, list) and 0 < len(lines) <= 100, 'Cần từ 1 đến 100 dòng chi tiết.')
        seen = set()
        for line in lines:
            need(isinstance(line, dict), 'Dòng chi tiết không hợp lệ.')
            data = {}
            for field in fields:
                value = line.get(field)
                if field == 'DonGiaNhap':
                    try: value = Decimal(str(value))
                    except (InvalidOperation, ValueError): raise Problem('Giá nhập không hợp lệ.')
                    need(value.is_finite() and 0 <= value <= Decimal('9999999999999.99') and value.as_tuple().exponent >= -2, 'Giá nhập phải không âm và có tối đa 2 chữ số thập phân.')
                elif field == 'KetQuaKiemTra': value = text(value, 'Kiểm nhận')
                else: value = integer(value if value is not None else 0, field, 0 if field == 'SoLuongLoi' else 1)
                data[field] = value
            product_key = 'MaSPLinhKien' if kind == 'bom' else 'MaSP'
            item_kind = 'THANH_PHAM' if kind == 'outgoing' and b['LoaiXuat'] == 'THANH_PHAM' else 'NGUYEN_LIEU'
            product(g.c, data[product_key], item_kind)
            if kind != 'bom': active(g.c, 'VI_TRI_KHO', 'MaViTri', data['MaViTri'])
            if kind == 'incoming': need(data['SoLuongLoi'] <= data['SoLuongNhan'], 'Số lỗi không được lớn hơn số thực nhận.')
            unique = (data[product_key], data.get('MaViTri'))
            need(unique not in seen, 'Gộp các dòng trùng sản phẩm và vị trí.'); seen.add(unique)
            insert(g.c, table, {key: ident, **data})

    @app.route('/api/documents/<kind>', methods=['POST'])
    @app.route('/api/documents/<kind>/<int:ident>', methods=['PUT', 'DELETE'])
    def documents(kind, ident=None):
        need(kind in DOCS, 'Loại chứng từ không hợp lệ.', 404)
        table, key, expected, owner, _fields = DOCS[kind]; role(expected)
        c = g.c; c.begin()
        try:
            if ident:
                old = one(c, f'SELECT * FROM {table} WHERE {key}=%s FOR UPDATE', (ident,))
                need(old, 'Không tìm thấy chứng từ.', 404)
                need(old[owner] == g.user['MaNV'], 'Chỉ được sửa nháp của mình.', 403)
                need(old['TrangThai'] == 'NHAP', 'Chứng từ đã gửi/chốt; chỉ được xem hoặc in.', 409)
                if kind == 'incoming': need(old['LoaiNhap'] == 'NCC', 'Nhập nội bộ do hệ thống quản lý.', 403)
                if kind in DETAILS: execute(c, f'DELETE FROM {DETAILS[kind][0]} WHERE {key}=%s', (ident,))
                if request.method == 'DELETE':
                    execute(c, f'DELETE FROM {table} WHERE {key}=%s', (ident,)); c.commit(); return jsonify(ok=True)
            b = body(); values = document_values(kind, b)
            if ident: update(c, table, key, ident, values)
            else:
                values[owner] = g.user['MaNV']
                if kind == 'incoming': values['LoaiNhap'] = 'NCC'
                if kind == 'results':
                    yc = integer(b.get('MaYC'), 'Yêu cầu')
                    job = one(c, 'SELECT * FROM YEU_CAU_LAP_RAP WHERE MaYC=%s FOR UPDATE', (yc,))
                    need(job and job['MaNVNhan'] == g.user['MaNV'], 'Chỉ được ghi kết quả việc của mình.', 403)
                    need(job['TrangThai'] in ('DA_CAP_VAT_LIEU', 'DANG_LAP_RAP'), 'Cần cấp vật liệu trước khi ghi kết quả.')
                    values['MaYC'] = yc
                ident = insert(c, table, values)
            if kind in DETAILS: save_lines(kind, ident, b)
            c.commit()
            return jsonify(id=ident, message='Đã lưu nháp. Tồn kho chưa thay đổi.')
        except Exception:
            c.rollback(); raise

    @app.post('/api/actions/<kind>/<int:ident>/<action>')
    def action_route(kind, ident, action):
        need(kind in ACTIONS and action in ACTIONS[kind], 'Thao tác không tồn tại.', 404)
        proc, expected = ACTIONS[kind][action]; role(expected)
        table, key, _expected, _owner, _fields = DOCS[kind]
        doc = one(g.c, f'SELECT * FROM {table} WHERE {key}=%s', (ident,))
        need(doc, 'Không tìm thấy chứng từ.', 404)
        if expected == EMPLOYEE:
            owner = 'MaNVNhan' if kind == 'jobs' else 'MaNVLap'
            need(doc[owner] == g.user['MaNV'], 'Không được thao tác chứng từ của người khác.', 403)
        args = [g.user['MaTK'], ident]
        if action in ('reject', 'cancel'): args.append(text(body().get('reason'), 'Lý do', 255, True))
        # No enclosing transaction. Public routines own BEGIN/COMMIT/ROLLBACK.
        for attempt in range(3):
            try:
                result = call(g.c, proc, args)
                break
            except pymysql.OperationalError as error:
                if error.args[0] not in (1213, 1205) or attempt == 2: raise
                g.c.rollback(); time.sleep(.05*(attempt+1))
        return jsonify(result=normalized(result), message='Đã xử lý trước đó; tồn không đổi.' if result and result[0].get('KetQua') == 'DA_XU_LY_TRUOC' else 'Thao tác thành công.')

    @app.route('/api/catalog/<kind>', methods=['POST'])
    @app.route('/api/catalog/<kind>/<int:ident>', methods=['PUT', 'DELETE'])
    def catalog(kind, ident=None):
        role(ADMIN); need(kind in CATALOGS, 'Danh mục không tồn tại.', 404)
        table, key, fields = CATALOGS[kind]; c = g.c; c.begin()
        try:
            old = one(c, f'SELECT * FROM {table} WHERE {key}=%s FOR UPDATE', (ident,)) if ident else None
            if ident: need(old, 'Không tìm thấy dữ liệu.', 404)
            if request.method == 'DELETE':
                execute(c, f'DELETE FROM {table} WHERE {key}=%s', (ident,)); c.commit(); return jsonify(ok=True)
            b = body(); data = {}
            required = {'MaLoai', 'SKU', 'TenSP', 'LoaiMatHang', 'DonViTinh', 'TenLoai', 'TenNCC', 'MaViTriHienThi', 'HoTen'}
            limits = {'SKU':50,'TenSP':200,'DonViTinh':20,'TenNCC':150,'MaViTriHienThi':50,'HoTen':100,'TenLoai':100,'SoDienThoai':20,'ChucVu':50,'KhuVuc':50,'Ke':50,'Tang':50}
            for field in fields:
                if field == 'MaLoai':
                    data[field] = integer(b.get(field), field); active(c, 'LOAI_SAN_PHAM', 'MaLoai', data[field])
                elif field == 'TrangThai':
                    options = ('DANG_LAM', 'NGUNG_LAM') if kind == 'employees' else ('HOAT_DONG', 'NGUNG')
                    data[field] = b.get(field, options[0]); need(data[field] in options, 'Trạng thái không hợp lệ.')
                elif field == 'LoaiMatHang':
                    data[field] = b.get(field); need(data[field] in ('NGUYEN_LIEU','THANH_PHAM'), 'Loại mặt hàng không hợp lệ.')
                else: data[field] = text(b.get(field), field, limits.get(field,255), field in required)
            if old and kind == 'products':
                used = one(c, 'SELECT (SELECT COUNT(*) FROM CT_PHIEU_NHAP WHERE MaSP=%s)+(SELECT COUNT(*) FROM CT_PHIEU_XUAT WHERE MaSP=%s)+(SELECT COUNT(*) FROM CT_BOM WHERE MaSPLinhKien=%s)+(SELECT COUNT(*) FROM BOM WHERE MaSPThanhPham=%s) n', (ident,)*4)['n']
                if used: need(all(data[f] == old[f] for f in ('SKU','LoaiMatHang','DonViTinh')), 'Sản phẩm đã có chứng từ: giữ nguyên SKU, loại và đơn vị tính.',409)
            if old and kind == 'employees' and data['TrangThai'] == 'NGUNG_LAM': need(ident != g.user['MaNV'], 'Không thể tự ngừng tài khoản đang dùng.')
            if old: update(c, table, key, ident, data)
            else: ident = insert(c, table, data)
            c.commit(); return jsonify(id=ident, message='Đã lưu danh mục.')
        except Exception: c.rollback(); raise

    @app.route('/api/accounts', methods=['POST'])
    @app.route('/api/accounts/<int:ident>', methods=['PUT','DELETE'])
    def accounts(ident=None):
        role(ADMIN); c = g.c; c.begin()
        try:
            old = one(c, 'SELECT * FROM TAI_KHOAN WHERE MaTK=%s FOR UPDATE', (ident,)) if ident else None
            if ident: need(old, 'Không tìm thấy tài khoản.',404)
            if request.method == 'DELETE':
                need(ident != g.user['MaTK'], 'Không thể xóa tài khoản đang dùng.')
                references = [('PHIEU_NHAP','MaNVLap'),('PHIEU_XUAT','MaNVLap'),('PHIEU_XUAT','MaNVDuyet'),('BOM','MaNVLap'),('YEU_CAU_LAP_RAP','MaNVGiao'),('YEU_CAU_LAP_RAP','MaNVNhan'),('KET_QUA_LAP_RAP','MaNVLap'),('KET_QUA_LAP_RAP','MaNVTiepNhan'),('BIEN_DONG_KHO','MaNV')]
                need(not any(one(c,f'SELECT COUNT(*) n FROM {t} WHERE {f}=%s',(old['MaNV'],))['n'] for t,f in references), 'Nhân viên đã có chứng từ. Khóa tài khoản để giữ lịch sử.',409)
                execute(c, 'DELETE FROM TAI_KHOAN WHERE MaTK=%s',(ident,)); c.commit(); return jsonify(ok=True)
            b = body(); data = {'VaiTro':b.get('VaiTro'),'TrangThai':b.get('TrangThai','HOAT_DONG')}
            need(data['VaiTro'] in (ADMIN, MANAGER, EMPLOYEE) and data['TrangThai'] in ('HOAT_DONG','KHOA'), 'Vai trò hoặc trạng thái không hợp lệ.')
            if old and ident == g.user['MaTK']: need(data['VaiTro']==ADMIN and data['TrangThai']=='HOAT_DONG', 'Không thể tự khóa hoặc bỏ quyền Admin.')
            pw = b.get('password')
            if pw or not old:
                pw = text(pw, 'Mật khẩu',255,True); need(len(pw)>=8, 'Mật khẩu cần ít nhất 8 ký tự.'); data['MatKhauBam']=generate_password_hash(pw)
            if old: update(c,'TAI_KHOAN','MaTK',ident,data)
            else:
                data['MaNV']=integer(b.get('MaNV'),'Nhân viên'); active(c,'NHAN_VIEN','MaNV',data['MaNV'],'DANG_LAM')
                data['TenDangNhap']=text(b.get('TenDangNhap'),'Tên đăng nhập',100,True)
                ident=insert(c,'TAI_KHOAN',data)
            c.commit(); return jsonify(id=ident,message='Đã lưu tài khoản.')
        except Exception: c.rollback(); raise

    @app.get('/api/report')
    def report():
        role(MANAGER)
        try:
            start = datetime.fromisoformat(request.args.get('from',''))
            end = datetime.fromisoformat(request.args.get('to',''))
        except ValueError: raise Problem('Chọn khoảng ngày báo cáo hợp lệ.')
        need(start.tzinfo is None and end.tzinfo is None and end > start, 'Mốc kết thúc phải sau mốc đầu, theo UTC+7.')
        data = call(g.c,'sp_bao_cao_kho',(g.user['MaTK'],start,end))
        typ = request.args.get('type'); loc = request.args.get('location'); q = request.args.get('q','').casefold()
        data = [r for r in data if (not typ or r['LoaiMatHang']==typ) and (not loc or str(r['MaViTri'])==loc) and (not q or q in (r['SKU']+' '+r['TenSP']).casefold())]
        if request.args.get('format') == 'csv':
            stream=io.StringIO(); writer=csv.writer(stream)
            keys=['SKU','TenSP','LoaiMatHang','DonViTinh','MaViTri','TonDauKy','NhapTrongKy','XuatTrongKy','TonCuoiKy','KhongBanCuoiKy','KhaDungCuoiKy']
            writer.writerow(keys)
            for r in data:
                writer.writerow([("'"+str(r[k])) if isinstance(r[k],str) and r[k].startswith(('=','+','-','@')) else r[k] for k in keys])
            response=app.response_class('\ufeff'+stream.getvalue(),mimetype='text/csv; charset=utf-8')
            response.headers['Content-Disposition']='attachment; filename="bao_cao_kho.csv"'
            return response
        return jsonify(rows=normalized(data),start=start.isoformat(),end=end.isoformat())

    @app.post('/api/backup')
    def backup_route():
        role(ADMIN)
        from manage import backup
        need(backup_lock.acquire(blocking=False), 'Đang có tác vụ sao lưu/khôi phục.',409)
        try: name = backup()
        finally: backup_lock.release()
        return jsonify(file=name,url='/api/backups/'+name,message='Đã sao lưu đầy đủ bảng, routine và trigger.')

    @app.get('/api/backups/<name>')
    def download_backup(name):
        role(ADMIN); need(name.startswith('mrp_') and name.endswith('.sql'),'Tên backup không hợp lệ.')
        return send_from_directory(BASE/'backups',name,as_attachment=True)

    @app.post('/api/restore-test')
    def restore_route():
        role(ADMIN)
        from manage import verify_restore
        need(backup_lock.acquire(blocking=False),'Đang có tác vụ sao lưu/khôi phục.',409)
        try: result=verify_restore(text(body().get('file'), 'Tên backup', 255, True))
        finally: backup_lock.release()
        return jsonify(result=result,message='Khôi phục thử nghiệm đạt; dữ liệu chính được giữ nguyên.')

    return app


if __name__ == '__main__':
    serve(create_app(), host='127.0.0.1', port=8765, threads=6)
