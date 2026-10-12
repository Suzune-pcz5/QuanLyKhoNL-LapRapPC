# Bản MRP riêng cho môn HTTTDN — 17 bảng

Ngày chốt phạm vi: 10/10/2026. Tài liệu yêu cầu hiện hành: [PRD MRP 17 bảng](PRD_MRP_HTTTDN_17_bang.docx).

Đây là bản thay phạm vi của thiết kế 38 bảng trước đó: chỉ quản lý kho nguyên vật liệu và quá trình lắp ráp PC theo yêu cầu môn. Tạo schema riêng, không thay bảng, khóa, dữ liệu hoặc API của CNPM. Đề môn không quy định số bảng; 17 là lựa chọn thiết kế để chạy đủ nghiệp vụ với phạm vi gọn.

## 1. File sử dụng

- `schema_MRP_HTTTDN_17_bang.sql`: cấu trúc và procedure nghiệp vụ.
- `ERD_MRP_HTTTDN_17_bang.mmd`: Mermaid ERD đầy đủ, 17 bảng, 122 thuộc tính, 36 FK.
- `demo_MRP_17_bang.sql`: dữ liệu giả định và giao dịch minh họa, chạy một lần sau schema.

Bộ tài liệu trong repository dùng phạm vi 17 bảng. Bản schema gốc để đối chiếu nằm trong [reference](reference/README.md); ứng dụng khởi tạo từ schema hiện hành ở thư mục này. Không mô tả giữ hàng online, khuyến mãi, đơn bán, kiểm kê hay hoàn vật liệu như chức năng của bản 17 bảng.

## 2. Vì sao cần đúng những bảng này

| Nhóm | Bảng | Số lượng |
|---|---|---:|
| Nhân viên/tài khoản | NHAN_VIEN, TAI_KHOAN | 2 |
| Danh mục/tồn kho | LOAI_SAN_PHAM, SAN_PHAM, NHA_CUNG_CAP, VI_TRI_KHO, TON_KHO | 5 |
| Phiếu nhập/xuất | PHIEU_NHAP, CT_PHIEU_NHAP, PHIEU_XUAT, CT_PHIEU_XUAT | 4 |
| Công thức | BOM, CT_BOM | 2 |
| Giao việc/nhu cầu | YEU_CAU_LAP_RAP, CT_NHU_CAU_LAP_RAP | 2 |
| Ghi nhận thành phẩm | KET_QUA_LAP_RAP | 1 |
| Báo cáo/đối chiếu | BIEN_DONG_KHO | 1 |
| Tổng | | **17** |

Phiếu và chi tiết tách riêng vì một phiếu có nhiều mặt hàng/vị trí. SAN_PHAM dùng chung danh mục nhưng mỗi SKU thuộc một trong hai loại NGUYEN_LIEU hoặc THANH_PHAM; không có hàng thương mại hoặc nghiệp vụ bán lẻ nguyên liệu trong bản này.

CT_NHU_CAU_LAP_RAP chụp định mức khi giao việc. Ví dụ BOM V1 cần 2 RAM/PC, giao làm 3 PC thì chốt 6 RAM. Ban hành V2 cần 3 RAM/PC không làm việc đã giao tự tăng lên 9 RAM.

BIEN_DONG_KHO lưu tác động thực tế của từng dòng nhập/xuất để tính báo cáo theo kỳ và đối chiếu tồn. Từng MaCTPN hoặc MaCTPX xuất hiện tối đa một lần trong lịch sử. Không cần bảng báo cáo theo tháng/quý/năm: các báo cáo là truy vấn.

TAI_KHOAN chứa VaiTro ENUM(ADMIN, QUAN_LY_KHO, NHAN_VIEN), mỗi tài khoản một vai trò. Nếu nhóm đã có phân hệ Admin HTTTDN, thống nhất cách dùng chung tài khoản trong ứng dụng sau; bản độc lập này không sửa phân hệ khác.

## 3. Đối chiếu với yêu cầu môn

| Yêu cầu từ đề | Dữ liệu/thao tác hỗ trợ |
|---|---|
| Quản lý nhập kho tăng nguyên liệu | PHIEU_NHAP/CT_PHIEU_NHAP loại NCC; sp_chot_nhap |
| Quản lý phê duyệt xuất nguyên liệu | PHIEU_XUAT/CT_PHIEU_XUAT loại CAP_PHAT; sp_duyet_xuat |
| Quản lý phê duyệt xuất thành phẩm | Cùng hai bảng phiếu xuất, loại THANH_PHAM; sp_duyet_xuat |
| Tồn/nhập/xuất theo tháng, quý, năm | TON_KHO, BIEN_DONG_KHO; sp_bao_cao_kho |
| Tạo công thức sản phẩm | BOM/CT_BOM; sp_ban_hanh_bom |
| Gửi số lượng thành phẩm cần cho nhân viên | YEU_CAU_LAP_RAP và nhu cầu chốt; sp_giao_yeu_cau |
| Nhân viên nhận yêu cầu, kiểm tra thiếu nguyên liệu | sp_nhan_viec; V_NHU_CAU_LAP_RAP hiển thị số cần/khả dụng/thiếu |
| Nhân viên lập đề nghị xuất vật liệu | Phiếu CAP_PHAT nháp; sp_gui_de_nghi_xuat |
| Nhân viên tạo thành phẩm từ vật liệu đã có | KET_QUA_LAP_RAP; sp_gui_ket_qua; quản lý tiếp nhận bằng sp_tiep_nhan_ket_qua |
| Nhân viên đề nghị xuất thành phẩm để bán | Phiếu THANH_PHAM nháp có TenNguoiNhan; sp_gui_de_nghi_xuat |
| Admin tài khoản và quyền | NHAN_VIEN/TAI_KHOAN, VaiTro; chức năng Admin thực hiện trong backend/UI |
| Admin xem/tìm/lọc danh mục | Các bảng danh mục và view tồn; backend/UI thực hiện tìm kiếm/lọc/sắp xếp |
| Phương án sao lưu/phục hồi | Quy trình tại mục 8; không cần thêm bảng backup |

MaYCLapRap chỉ có giá trị trên phiếu cấp phát. Phiếu xuất thành phẩm ghi người/bộ phận nhận ngay trên phiếu, không tham chiếu DON_BAN hoặc HOA_DON. Đây là chứng từ bàn giao thành phẩm ra khỏi kho để bán, không phải chức năng xử lý bán hàng.

## 4. Luồng nghiệp vụ và giới hạn

1. Quản lý lập nhập nguyên liệu, ghi số thực nhận và lỗi. Chốt mới tăng tồn; nháp không tăng.
2. Quản lý ban hành BOM một cấp rồi giao số lượng PC cho nhân viên.
3. Nhân viên nhận việc, tra nhu cầu và thiếu vật liệu. Nếu thiếu thì quản lý bổ sung nhập; nếu đủ thì lập đề nghị cấp phát toàn bộ nhu cầu.
4. Quản lý duyệt đồng thời bàn giao vật liệu. Toàn phiếu phải đủ tồn; thiếu một dòng thì rollback cả phiếu. Tồn nguyên liệu giảm đúng một lần.
5. Nhân viên ghi kết quả lắp ráp; cho phép nhiều đợt. Quản lý tiếp nhận, hệ thống tự tạo và chốt một nhập thành phẩm trong cùng giao dịch. Tổng đạt + lỗi không vượt số PC được giao. Không trừ nguyên liệu ở kệ lần hai.
6. Nhân viên đề nghị xuất thành phẩm, quản lý duyệt đồng thời bàn giao và giảm tồn thành phẩm.
7. Quản lý chọn kỳ báo cáo và xem tồn đầu, nhập, xuất, tồn cuối, lỗi và khả dụng.

Vật liệu ở khu lắp ráp được tính qua V_VAT_LIEU_LAP_RAP từ cấp phát đã thực hiện và kết quả đã tiếp nhận. Không tạo bảng VAT_LIEU_DA_CAP riêng. Cách này dùng được vì bản gọn cấp phát toàn bộ một lần, không hỗ trợ cấp bổ sung, thay vật tư, hoàn hoặc dừng việc sau khi cấp.

Yêu cầu chỉ được hủy trước cấp phát. Phiếu bị từ chối có thể lập phiếu mới, giữ lại lịch sử cũ. Đã chốt không được xóa, quay lùi trạng thái hay tự sửa số tồn. SKU lỗi nằm trong tồn thực tế nhưng không dùng được để cấp/xuất.

Một kho có nhiều vị trí; chưa có chuyển vị trí hoặc kiểm kê điều chỉnh. Không thêm giỏ hàng, khách hàng, thanh toán, vận chuyển, serial, giá thành hay khuyến mãi trong bản này.

## 5. Chạy SQL và ERD

MySQL 8.0.16 trở lên. Đã thử trên MySQL 8.0.46; không nhập nguyên file vào SQL Server/MariaDB.

Trong MySQL Workbench, tạo CSDL riêng:

```sql
CREATE DATABASE htttdn_mrp_17
 CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE htttdn_mrp_17;
```

Chọn CSDL đó làm mặc định, chạy toàn bộ `schema_MRP_HTTTDN_17_bang.sql`, giữ nguyên DELIMITER. Muốn thử nghiệp vụ thì chạy `demo_MRP_17_bang.sql` một lần tiếp theo. Mật khẩu demo là placeholder, backend phải tạo hash hợp lệ trước khi dùng đăng nhập.

File DDL không tự chọn CSDL và không chứa DROP. Nếu chạy DDL lỗi giữa chừng, tạo DB thử nghiệm khác sau khi sửa; MySQL không rollback nguyên file DDL.

Copy toàn bộ file .mmd vào [Mermaid Live](https://mermaid.live/), bắt đầu từ `erDiagram`. Có thể xuất SVG đưa vào báo cáo. PK/FK/UK đúng metadata SQL; UK trên một thuộc tính có thể là thành viên của khóa UNIQUE nhiều cột. CHECK và điều kiện theo trạng thái xem trong SQL, không suy diễn chỉ từ hình ERD.

## 6. Gọi nghiệp vụ trong backend

Cấu trúc mới: đa số routine là `CALL ten(MaTK, MaDoiTuong);`, **không còn tham số khóa thao tác** của bản 38 bảng. MaTK lấy từ session đã xác thực. Routine tự BEGIN/COMMIT/ROLLBACK, gọi ngoài transaction đang mở của backend.

| Routine | ID | Quyền/tham số thêm |
|---|---|---|
| sp_chot_nhap | MaPN | Quản lý; chỉ NCC |
| sp_ban_hanh_bom | MaBOM | Quản lý |
| sp_giao_yeu_cau | MaYC | Quản lý |
| sp_nhan_viec | MaYC | Nhân viên được giao |
| sp_gui_de_nghi_xuat | MaPX | Nhân viên lập |
| sp_duyet_xuat | MaPX | Quản lý khác người lập |
| sp_tu_choi_xuat | MaPX | Quản lý; thêm lý do |
| sp_gui_ket_qua | MaKQ | Nhân viên được giao |
| sp_tiep_nhan_ket_qua | MaKQ | Quản lý khác người lập |
| sp_tu_choi_ket_qua | MaKQ | Quản lý; thêm lý do |
| sp_huy_yeu_cau | MaYC | Quản lý; thêm lý do, trước cấp |
| sp_bao_cao_kho | Không theo mẫu trên | (MaTK, TuNgay, DenNgay), quản lý |

Ví dụ:

```sql
CALL sp_giao_yeu_cau(1,1);
CALL sp_nhan_viec(2,1);
CALL sp_duyet_xuat(1,1);
CALL sp_tiep_nhan_ket_qua(1,1);
CALL sp_bao_cao_kho(1,'2026-10-01','2026-11-01'); -- tháng
CALL sp_bao_cao_kho(1,'2026-10-01','2027-01-01'); -- quý IV
CALL sp_bao_cao_kho(1,'2026-01-01','2027-01-01'); -- năm
```

Khoảng báo cáo [TuNgay, DenNgay), không bao gồm đầu kỳ kế tiếp. Thời gian DATETIME theo UTC+7, mỗi kết nối đặt time_zone +07:00 và utf8mb4. Báo cáo dựa thời điểm chốt, không dựa ngày chứng từ nhập tay. Tồn cuối = tồn đầu + nhập − xuất; tách theo SKU/đơn vị tính/vị trí, không cộng CPU và RAM thành một tổng có ý nghĩa chung.

Gọi lại cùng phiếu/kết quả đã chốt trả DA_XU_LY_TRUOC, không đổi tồn. Backend cần tái dùng ID phiếu khi retry; không tạo một phiếu xuất thành phẩm mới cho cùng lần bàn giao rồi mong schema nhận ra đó là cùng giao dịch. Bản gọn không có cơ chế chống trùng request tạo phiếu của website.

Bốn routine hỗ trợ sp_kiem_tra_vai_tro, sp_ghi_bien_dong, sp_ap_dung_nhap_noi_bo, sp_kiem_tra_dong_xuat không cấp EXECUTE trực tiếp cho người dùng ứng dụng. Tài khoản DB backend không dùng root. Khi sửa nháp, backend kiểm tra quyền và chủ sở hữu, chỉ ghi các cột được phép. Không nhận từ client các giá trị trạng thái đã chốt, snapshot, tồn, lịch sử hoặc người duyệt. Khi gặp deadlock/timeout, retry có giới hạn sau rollback.

## 7. BFD/DFD sửa theo phạm vi mới

Không giữ bộ tám tiến trình cũ có kiểm kê/giữ hàng. Đề xuất bảy nhóm chức năng thống nhất:

1. Quản trị nhân viên, tài khoản và quyền.
2. Quản lý danh mục và tra cứu tồn.
3. Tiếp nhận, ghi nhận nhập nguyên liệu.
4. Quản lý BOM, giao và nhận yêu cầu lắp ráp.
5. Đề nghị/duyệt cấp vật liệu, ghi nhận và tiếp nhận thành phẩm.
6. Đề nghị/duyệt xuất thành phẩm.
7. Báo cáo kho theo tháng/quý/năm.

| Kho dữ liệu đề xuất | Bảng |
|---|---|
| D1 Nhân viên/tài khoản | NHAN_VIEN, TAI_KHOAN |
| D2 Danh mục/tồn | LOAI_SAN_PHAM, SAN_PHAM, NHA_CUNG_CAP, VI_TRI_KHO, TON_KHO |
| D3 Nhập | PHIEU_NHAP, CT_PHIEU_NHAP |
| D4 Xuất | PHIEU_XUAT, CT_PHIEU_XUAT |
| D5 Công thức | BOM, CT_BOM |
| D6 Lắp ráp | YEU_CAU_LAP_RAP, CT_NHU_CAU_LAP_RAP, KET_QUA_LAP_RAP |
| D7 Lịch sử kho | BIEN_DONG_KHO |

Tác nhân: Admin, Quản lý kho, Nhân viên, Nhà cung cấp, Bộ phận bán hàng/người nhận. Bộ phận bán hàng chỉ giao tiếp về bàn giao thành phẩm; không vẽ dữ liệu thanh toán/khuyến mãi của CNPM. Một kho dữ liệu DFD có thể gồm nhiều bảng SQL, không phải mỗi bảng tương ứng một tiến trình.

Đây là mapping thay thế của bản gọn, không dùng chung mã D1–D8 cũ nếu ý nghĩa đã thay. Cần cập nhật đồng bộ BFD, ngữ cảnh, DFD mức đỉnh, từ điển dữ liệu và báo cáo trước khi nộp.

## 8. Kiểm tra, sao lưu và phần còn phải làm

Đã nhập schema mới và chạy demo trên MySQL 8.0.46. 33 kiểm tra đạt: không có bảng CNPM; đúng tồn của chu trình demo; 3 PC cần 3 CPU + 6 RAM; tiếp nhận không trừ nguyên liệu lần hai; lặp duyệt không cộng/trừ thêm; quyền quản lý/nhân viên/Admin; khóa snapshot và chi tiết đã chốt; thay BOM không đổi việc cũ; thiếu RAM rollback CPU; từ chối lập lại; hủy trước cấp; chặn kết quả vượt kế hoạch; hai kết nối tranh 1 PC chỉ một thành công; tồn khớp lịch sử và công thức báo cáo.

SQL/ERD đáp ứng cấu trúc dữ liệu của phạm vi chọn, không tự hoàn thành phần mềm hoặc toàn bộ rubric. Nhóm vẫn cần làm đăng nhập/mật khẩu băm, Admin riêng (thêm/xóa/khóa/phân quyền account, xem/tìm/lọc/sắp xếp danh mục), màn hình quản lý/nhân viên, in/xuất báo cáo và hướng dẫn sử dụng. Không xóa nhân viên/tài khoản/danh mục đã có chứng từ; ngừng sử dụng để giữ lịch sử.

Phần báo cáo chung vẫn phải có giới thiệu doanh nghiệp, khảo sát ít nhất 15 câu và kết luận, mô tả bài toán, BFD/ngữ cảnh/DFD mức đỉnh, ERD và bảng mô tả thuộc tính, giao diện, cài đặt/sử dụng, kế hoạch nhóm 15 tuần và phân công theo đề.

Sao lưu: dùng mysqldump có routines/triggers/events; khôi phục vào DB thử nghiệm khác và ghi kết quả thực tế. Ví dụ:

```text
mysqldump -u tai_khoan_backup -p --routines --triggers --events --single-transaction --default-character-set=utf8mb4 --result-file=backup_mrp_17.sql htttdn_mrp_17
```

Tạo DB restore rỗng, mở backup trong Workbench và chạy vào DB đó; kiểm tra bảng, dữ liệu, routine, trigger rồi thử một nghiệp vụ. Bộ file này chưa tuyên bố đã chạy backup/restore trên môi trường triển khai của nhóm.
