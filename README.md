# Quản lý kho nguyên liệu và lắp ráp PC

Ứng dụng quản lý nhập/xuất kho, tồn kho, BOM, giao việc lắp ráp, tiếp nhận thành phẩm, báo cáo, tài khoản và sao lưu. Giao diện tiếng Việt; backend Flask/Waitress kết nối MySQL, dùng bộ schema MRP 17 bảng trong `docs/mrp`.

## Chạy trên Windows

Cần Python 3.11 trở lên. Nhấp đúp [start-demo.cmd](start-demo.cmd) hoặc chạy:

```powershell
.\start-demo.cmd
```

Script tự tạo môi trường Python, cài thư viện và tải MySQL portable nếu chưa có. Sau đó mở **http://127.0.0.1:8765**. Dừng bằng [stop-demo.cmd](stop-demo.cmd).

| Tài khoản | Vai trò |
|---|---|
| `quanly` | Quản lý kho |
| `nhanvien` | Nhân viên lắp ráp |
| `nhanvien_khac` | Nhân viên khác |
| `admin` | Quản trị viên |

Mật khẩu ban đầu: **`Demo@12345`**. Màn hình đăng nhập không điền sẵn thông tin.

Runtime, MySQL data và thông tin kết nối mặc định nằm tại `%LOCALAPPDATA%/HTTTDN-Demo`, bên ngoài repository. MySQL chạy trên `127.0.0.1:3397`; backend chạy trên `127.0.0.1:8765`.

Riêng workspace CNPM đang dùng runtime `../.mrp-runtime`. Chạy bằng `../start-kho-local.cmd`, dừng bằng `../stop-kho-local.cmd` để dùng đúng dữ liệu hiện có. Hai launcher này nằm ngoài repository và không cần đưa vào bản source chia sẻ.

Chỉ chạy một bản ứng dụng trên hai cổng này. Khi đổi thư mục source, dừng bằng launcher của bản đang chạy rồi khởi động bản mới. Launcher kiểm tra đúng đường dẫn `server.py`, gồm cả tiến trình Python con, và từ chối dừng ứng dụng thuộc thư mục khác.

## Nội dung repository

Hướng dẫn chạy online trên Render với MySQL Aiven: [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md). Bản online dùng biến môi trường và TLS, giữ 17 bảng nghiệp vụ cùng database metadata riêng cho session/chống lưu trùng. Không dùng launcher Windows làm lệnh khởi động Render.

- `app/`: backend, giao diện, script cài đặt, kiểm thử và hướng dẫn.
- `docs/mrp/`: PRD, ERD, schema hiện hành, SQL dữ liệu ban đầu và hướng dẫn MRP. Schema gốc để đối chiếu nằm trong `docs/mrp/reference/`.
- Hai launcher CMD và `.gitignore`.

Xem [hướng dẫn sử dụng và nghiệp vụ](app/README.md) và [kết quả kiểm tra](app/VERIFICATION.md). Các bài tập môn học, thư mục lưu trữ, backup, dependency đã cài và credential runtime không được đưa vào repository.

## Kiểm thử

Sau khi khởi tạo ứng dụng:

Có 106 bài kiểm thử Python và 277 kiểm tra DOM. Kiểm thử nghiệp vụ sử dụng CSDL tạm riêng, tự dọn cả dữ liệu và quyền test, không reset dữ liệu chính. Lệnh chạy với từng runtime và fixture có sẵn được mô tả trong [app/README.md](app/README.md).

PRD gốc có một liên kết tài liệu trên máy người soạn; liên kết đó không hoạt động trên máy khác. Các liên kết nội bộ của bộ MRP giữ nguyên.
