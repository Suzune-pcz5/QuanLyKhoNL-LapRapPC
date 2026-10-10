# Kết quả kiểm tra demo kho

Ngày kiểm tra: **10/10/2026**, UTC+7.

## Repository Quản lý kho nguyên liệu và lắp ráp PC

Source đã được đưa vào `D:/Projects/QuanLyKhoNL-LapRapPC` trên branch `feat/quan-ly-kho`.

- **28 test đạt** trong một lần chạy từ repository mới: 22 test MySQL và 6 test quản lý tiến trình.
- **66 kiểm tra DOM giả lập đạt**; Python, JavaScript và hai script PowerShell qua kiểm tra cú pháp.
- Năm tài liệu MRP gốc giữ nguyên hash; backup, runtime credential và dependency đã cài không được đưa vào Git.
- Khi backend cũ còn chạy, launcher mới từ chối khởi động trước khi khởi tạo CSDL vì đường dẫn source không khớp.
- Đã chuyển backend từ source cũ sang source mới. Kiểm tra quyền sở hữu HTTP listener thành công, gồm Python launcher và tiến trình con.
- Gọi start lần hai dùng lại đúng listener. Hai launcher CMD mới dừng hết cả backend và MySQL rồi khởi động lại thành công, sử dụng dữ liệu hiện có.

Giới hạn kiểm tra hiển thị bằng trình duyệt thật ở phần dưới vẫn áp dụng.

## Cập nhật giao diện và tên dữ liệu

Đã bỏ nhãn demo, khẩu hiệu, banner tổng quan, thông tin kỹ thuật ở thanh bên/chân trang và khối tài khoản điền sẵn. Trang hướng dẫn dùng quy trình thao tác theo vai trò. Tài khoản hiện tại: `quanly`, `nhanvien`, `nhanvien_khac`, `admin`; mật khẩu giữ nguyên. Các SKU ban đầu là `CPU-001`, `RAM-001`, `PC-001`.

- **22 test MySQL đạt trong một lần chạy**, bao gồm bảo toàn lịch sử/mật khẩu khi đổi nhãn và rollback khi trùng tên đăng nhập.
- **66 kiểm tra DOM giả lập đạt**, kiểm tra các trang và hộp thoại không còn chữ demo trong nội dung hiển thị.
- Đã đối chiếu với backup trước thay đổi `mrp_20261010_190355_235d50.sql`: số dòng 17 bảng, hash mật khẩu, vai trò, tồn kho và toàn bộ bảng nghiệp vụ/lịch sử giữ nguyên. CSDL đối chiếu tạm đã được dọn.
- Dừng/khởi động lại thành công; cả bốn tài khoản mới đăng nhập qua API đang chạy.
- Backup sau thay đổi `mrp_20261010_190538_677ce4.sql` khôi phục vào `mrp_restore_20261010_190539_73cda5`: dữ liệu khớp, đăng nhập và chốt nhập kiểm chứng thành công.

Các kết quả dưới đây là lần triển khai ban đầu. Giới hạn kiểm tra hiển thị bằng trình duyệt thật vẫn áp dụng.

## Môi trường thực tế

- MySQL Community Server **8.4.11**, loopback `127.0.0.1:3397`.
- Python **3.11**, Flask **3.1.3**, PyMySQL **1.2.3**, Waitress **3.0.2**.
- Dữ liệu demo chính ở `htttdn_mrp_demo`; mỗi kiểm thử tích hợp dùng một CSDL mới và tự dọn đúng CSDL đó.
- Schema, demo SQL và các tài liệu gốc không bị sửa.

## Kiểm thử MySQL

**20 test tích hợp đạt**: 18 test trong lần chạy đầy đủ và 2 test bổ sung chạy riêng sau đó. Source và lệnh chạy ở `test_integration.py`.

| Nhóm | Kết quả |
|---|---|
| Baseline 17 bảng và số dư demo | Đạt |
| Nhập nháp → chốt → cấp → tiếp nhận → xuất PC | Đạt |
| Gọi lại chốt nhập, duyệt xuất, tiếp nhận | Không đổi tồn lần hai |
| Đổi phiên bản BOM sau giao việc | Snapshot việc cũ giữ nguyên |
| CPU đủ, RAM thiếu | Rollback cả phiếu, không thêm ledger |
| Kết quả các đợt vượt số được giao | Bị chặn |
| Từ chối cấp và lập phiếu mới | Giữ tồn và lịch sử |
| Hủy yêu cầu trước/sau cấp | Chỉ trước cấp được hủy |
| Xuất PC lỗi | Bị chặn |
| Hai kết nối tranh PC tốt cuối cùng | Chỉ một thành công |
| Phiên đăng nhập, vai trò, CSRF, đổi ID người khác | Bị chặn đúng quyền |
| Khóa tài khoản đang đăng nhập | Phiên cũ mất quyền |
| Client giả trạng thái/người lập | Giá trị không được nhận |
| Sửa/xóa nháp và khóa khi chốt | Đạt |
| DB user sửa tồn/ledger/snapshot/trạng thái/helper | Không có quyền |
| Báo cáo, mốc đầu kỳ sau, CSV và ledger | Khớp số dư |
| Danh mục có lịch sử, Admin và xóa account | Bảo vệ lịch sử |
| Vị trí ngừng hoạt động | Không được xuất |
| Nháp có dòng chi tiết không hợp lệ | Rollback cả header và detail |
| Sửa nháp đồng thời gửi duyệt | Khóa cha giữ dữ liệu nhất quán |

## Kiểm tra mã giao diện

**44 kiểm tra DOM giả lập đạt** với `test_frontend.cjs`. Không dùng trình duyệt hoặc mạng; API được mock bằng dữ liệu từ MySQL demo.

Đã kiểm tra các trang, quyền điều hướng, bộ lọc từ khóa, tạo các loại chứng từ, thêm/xóa dòng, payload lưu phiếu nhập, form danh mục/tài khoản và các nút sao lưu. JavaScript qua `node --check`; Python qua `py_compile`.

**Giới hạn:** công cụ trình duyệt từ chối quyền mở `http://127.0.0.1:8765`. Vì vậy chưa kiểm tra trực tiếp bố cục, in bằng trình duyệt và thao tác toàn luồng qua trình duyệt thật. DOM giả lập không thay thế kiểm tra hiển thị. API/nghiệp vụ được kiểm thử trên MySQL thật.

## Dừng và khởi động lại

Đã dừng backend và MySQL riêng bằng `manage.py stop`, sau đó khởi động lại bằng `manage.py start`: cả hai lệnh thành công. Sau khi khởi động lại, đăng nhập `demo_quanly`, đọc trạng thái từ MySQL qua API có xác thực và tải HTML trang chính đều đạt. Demo đang chạy tại `http://127.0.0.1:8765`.

## Sao lưu và khôi phục thực tế

Backup: `mrp_20261010_183225_83a9d1.sql` trong thư mục local `app/backups`.

CSDL khôi phục: `mrp_restore_20261010_183225_13ea14`.

- **17 bảng, 4 view, 16 routine, 19 trigger**.
- Toàn bộ dữ liệu 17 bảng khớp bản chính trước giao dịch kiểm chứng.
- Xác thực hash tài khoản demo quản lý thành công.
- Tạo phiếu nhập mới và gọi `sp_chot_nhap` thành công ở CSDL khôi phục.
- CSDL demo chính giữ nguyên số dư.

Đây là kết quả kiểm tra lần triển khai ứng dụng này, tách biệt với thông tin “33 kiểm tra” trong tài liệu bàn giao gốc.
