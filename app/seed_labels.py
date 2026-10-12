"""One-time, guarded renaming of the original sample accounts and catalog labels."""
from db import execute, one


ACCOUNTS = [
    (1, 1, 'QUAN_LY_KHO', 'demo_quanly', 'quanly'),
    (2, 2, 'NHAN_VIEN', 'demo_nhanvien', 'nhanvien'),
    (3, 3, 'NHAN_VIEN', 'demo_khac', 'nhanvien_khac'),
    (4, 4, 'ADMIN', 'demo_admin', 'admin'),
]
PRODUCTS = [
    (1, 'CPU-DEMO', 'CPU-001', 'CPU demo', 'CPU'),
    (2, 'RAM-DEMO', 'RAM-001', 'RAM demo', 'RAM'),
    (3, 'PC-DEMO', 'PC-001', 'PC demo - 1 CPU va 2 RAM', 'PC · 1 CPU + 2 RAM'),
]
LEGACY_TEXT_LABELS = [
    ('NHAN_VIEN', 'MaNV', 3, 'HoTen', 'Nhan vien khac', 'Nhân viên khác'),
    ('LOAI_SAN_PHAM', 'MaLoai', 1, 'TenLoai', 'Linh kien PC', 'Linh kiện PC'),
    ('LOAI_SAN_PHAM', 'MaLoai', 2, 'TenLoai', 'PC lap rap', 'PC lắp ráp'),
    ('VI_TRI_KHO', 'MaViTri', 1, 'KhuVuc', 'Nguyen lieu', 'Nguyên liệu'),
    ('VI_TRI_KHO', 'MaViTri', 2, 'KhuVuc', 'Thanh pham', 'Thành phẩm'),
    ('VI_TRI_KHO', 'MaViTri', 3, 'KhuVuc', 'Hang loi', 'Hàng lỗi'),
]


def normalize_seed_labels(c):
    """Preserve IDs, hashes, quantities and issued documents; never rename user data."""
    c.begin()
    try:
        accounts, products = [], []
        for ident, employee, role, old, new in ACCOUNTS:
            account = one(c, 'SELECT * FROM TAI_KHOAN WHERE MaTK=%s FOR UPDATE', (ident,))
            if not account or (account['MaNV'], account['VaiTro'], account['TenDangNhap']) != (employee, role, old):
                continue
            if one(c, 'SELECT MaTK FROM TAI_KHOAN WHERE TenDangNhap=%s', (new,)):
                raise RuntimeError(f'Ten dang nhap {new} da duoc su dung; chua doi nhan du lieu.')
            accounts.append((new, ident, old))
        for ident, old, new, old_name, new_name in PRODUCTS:
            product = one(c, 'SELECT SKU FROM SAN_PHAM WHERE MaSP=%s FOR UPDATE', (ident,))
            if not product or product['SKU'] != old:
                continue
            if one(c, 'SELECT MaSP FROM SAN_PHAM WHERE SKU=%s', (new,)):
                raise RuntimeError(f'SKU {new} da duoc su dung; chua doi nhan du lieu.')
            products.append((ident, old, new, old_name, new_name))
        for new, ident, old in accounts:
            execute(c, 'UPDATE TAI_KHOAN SET TenDangNhap=%s WHERE MaTK=%s AND TenDangNhap=%s', (new, ident, old))
        for ident, old, new, old_name, new_name in products:
            execute(c, 'UPDATE SAN_PHAM SET SKU=%s,TenSP=IF(TenSP=%s,%s,TenSP) WHERE MaSP=%s AND SKU=%s',
                    (new, old_name, new_name, ident, old))
        for ident, old, new in [(1, 'Quan ly demo', 'Quản lý kho'), (2, 'Nhan vien lap rap demo', 'Nhân viên lắp ráp'),
                                (4, 'Admin demo', 'Quản trị viên')]:
            execute(c, 'UPDATE NHAN_VIEN SET HoTen=%s WHERE MaNV=%s AND HoTen=%s', (new, ident, old))
        execute(c, 'UPDATE NHA_CUNG_CAP SET TenNCC=%s WHERE MaNCC=1 AND TenNCC=%s', ('Nhà cung cấp linh kiện', 'NCC demo'))
        text_changes = 0
        with c.cursor() as cursor:
            for table, key, ident, field, old, new in LEGACY_TEXT_LABELS:
                cursor.execute(f'UPDATE {table} SET {field}=%s WHERE {key}=%s AND CAST({field} AS BINARY)=CAST(%s AS BINARY)', (new, ident, old))
                text_changes += cursor.rowcount
        c.commit()
        return text_changes
    except Exception:
        c.rollback()
        raise
