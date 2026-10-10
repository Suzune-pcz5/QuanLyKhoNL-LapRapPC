-- DU LIEU GIA DINH DE DEMO MON HTTTDN, KHONG PHAI DU LIEU THUC TE.
-- Chay mot lan sau schema_MRP_HTTTDN_17_bang.sql trong CSDL demo rong.
-- MatKhauBam chi la placeholder, khong dung de dang nhap that.
SET NAMES utf8mb4;
SET time_zone='+07:00';
INSERT INTO NHAN_VIEN(MaNV,HoTen) VALUES(1,'Quan ly demo'),(2,'Nhan vien lap rap demo'),(3,'Nhan vien khac'),(4,'Admin demo');
INSERT INTO TAI_KHOAN(MaTK,MaNV,TenDangNhap,MatKhauBam,VaiTro) VALUES
(1,1,'demo_quanly','DEMO_ONLY_NOT_A_PASSWORD_HASH','QUAN_LY_KHO'),
(2,2,'demo_nhanvien','DEMO_ONLY_NOT_A_PASSWORD_HASH','NHAN_VIEN'),
(3,3,'demo_khac','DEMO_ONLY_NOT_A_PASSWORD_HASH','NHAN_VIEN'),
(4,4,'demo_admin','DEMO_ONLY_NOT_A_PASSWORD_HASH','ADMIN');
INSERT INTO LOAI_SAN_PHAM(MaLoai,TenLoai) VALUES(1,'Linh kien PC'),(2,'PC lap rap');
INSERT INTO SAN_PHAM(MaSP,MaLoai,SKU,TenSP,LoaiMatHang) VALUES
(1,1,'CPU-DEMO','CPU demo','NGUYEN_LIEU'),
(2,1,'RAM-DEMO','RAM demo','NGUYEN_LIEU'),
(3,2,'PC-DEMO','PC demo - 1 CPU va 2 RAM','THANH_PHAM');
INSERT INTO NHA_CUNG_CAP(MaNCC,TenNCC) VALUES(1,'NCC demo');
INSERT INTO VI_TRI_KHO(MaViTri,MaViTriHienThi,KhuVuc) VALUES(1,'LK-A1','Nguyen lieu'),(2,'TP-A1','Thanh pham'),(3,'LOI-A1','Hang loi');

-- Quan ly nhap 10 CPU, 20 RAM (trong do 2 RAM loi).
INSERT INTO PHIEU_NHAP(MaPN,LoaiNhap,MaNCC,MaNVLap,NgayChungTu) VALUES(1,'NCC',1,1,CURRENT_DATE());
INSERT INTO CT_PHIEU_NHAP(MaPN,MaSP,MaViTri,SoLuongNhan,SoLuongLoi,DonGiaNhap) VALUES(1,1,1,10,0,1800000),(1,2,1,20,2,400000);
CALL sp_chot_nhap(1,1);

-- BOM: 1 PC = 1 CPU + 2 RAM. Giao lam 3 PC.
INSERT INTO BOM(MaBOM,MaSPThanhPham,PhienBan,TenCauHinh,MaNVLap) VALUES(1,3,1,'Cau hinh PC demo',1);
INSERT INTO CT_BOM VALUES(1,1,1),(1,2,2);
CALL sp_ban_hanh_bom(1,1);
INSERT INTO YEU_CAU_LAP_RAP(MaYC,MaBOM,SoLuongYeuCau,MaNVGiao,MaNVNhan) VALUES(1,1,3,1,2);
CALL sp_giao_yeu_cau(1,1);
CALL sp_nhan_viec(2,1);
-- Nhan vien xem nhu cau va thieu nguyen lieu.
SELECT * FROM V_NHU_CAU_LAP_RAP WHERE MaYC=1;

-- Nhan vien de nghi; quan ly duyet dong thoi ban giao 3 CPU va 6 RAM.
INSERT INTO PHIEU_XUAT(MaPX,LoaiXuat,MaYCLapRap,MaNVLap) VALUES(1,'CAP_PHAT',1,2);
INSERT INTO CT_PHIEU_XUAT(MaPX,MaSP,MaViTri,SoLuongXuat) VALUES(1,1,1,3),(1,2,1,6);
CALL sp_gui_de_nghi_xuat(2,1);
CALL sp_duyet_xuat(1,1);

-- Hai dot ket qua: 2 PC dat, sau do 1 PC loi. Khong tru linh kien lan hai.
INSERT INTO KET_QUA_LAP_RAP(MaKQ,MaYC,MaNVLap,SoLuongDat,MaViTriDat) VALUES(1,1,2,2,2);
CALL sp_gui_ket_qua(2,1);
CALL sp_tiep_nhan_ket_qua(1,1);
INSERT INTO KET_QUA_LAP_RAP(MaKQ,MaYC,MaNVLap,SoLuongDat,SoLuongLoi,MaViTriLoi) VALUES(2,1,2,0,1,3);
CALL sp_gui_ket_qua(2,2);
CALL sp_tiep_nhan_ket_qua(1,2);

-- De nghi xuat 1 PC cho bo phan ban hang. Khong tao don ban/hoa don CNPM.
INSERT INTO PHIEU_XUAT(MaPX,LoaiXuat,TenNguoiNhan,MaNVLap) VALUES(2,'THANH_PHAM','Bo phan ban hang demo',2);
INSERT INTO CT_PHIEU_XUAT(MaPX,MaSP,MaViTri,SoLuongXuat) VALUES(2,3,2,1);
CALL sp_gui_de_nghi_xuat(2,2);
CALL sp_duyet_xuat(1,2);

-- Ket qua: CPU 7; RAM 14 gom 2 loi; PC dat con 1; PC loi 1.
SELECT * FROM V_TON_KHO ORDER BY MaSP,MaViTri;
SELECT * FROM V_VAT_LIEU_LAP_RAP WHERE MaYC=1;
SELECT MaYC,TrangThai FROM YEU_CAU_LAP_RAP;
-- Thu bao cao thang, quy va nam theo khoang [TuNgay,DenNgay).
CALL sp_bao_cao_kho(1,CAST(DATE_FORMAT(CURRENT_DATE(),'%Y-%m-01') AS DATETIME),
 DATE_ADD(CAST(DATE_FORMAT(CURRENT_DATE(),'%Y-%m-01') AS DATETIME),INTERVAL 1 MONTH));
