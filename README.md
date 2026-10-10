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

Runtime, MySQL data và thông tin kết nối nằm tại `%LOCALAPPDATA%/HTTTDN-Demo`, bên ngoài repository. MySQL chạy trên `127.0.0.1:3397`; backend chạy trên `127.0.0.1:8765`. Trên máy đã chạy project HTTTDN, ứng dụng sử dụng lại môi trường và dữ liệu hiện có.

Chỉ chạy một bản ứng dụng trên hai cổng này. Khi đổi thư mục source, dừng bằng launcher của bản đang chạy rồi khởi động bản mới. Launcher kiểm tra đúng đường dẫn `server.py`, gồm cả tiến trình Python con, và từ chối dừng ứng dụng thuộc thư mục khác.

## Nội dung repository

- `app/`: backend, giao diện, script cài đặt, kiểm thử và hướng dẫn.
- `docs/mrp/`: PRD, schema, ERD, SQL dữ liệu ban đầu và hướng dẫn MRP; giữ nguyên nội dung bộ gốc.
- Hai launcher CMD và `.gitignore`.

Xem [hướng dẫn sử dụng và nghiệp vụ](app/README.md) và [kết quả kiểm tra](app/VERIFICATION.md). Các bài tập môn học, thư mục lưu trữ, backup, dependency đã cài và credential runtime không được đưa vào repository.

## Kiểm thử

Sau khi khởi tạo ứng dụng:

```powershell
cd app
& "$env:LOCALAPPDATA\HTTTDN-Demo\venv\Scripts\python.exe" -m unittest test_integration test_lifecycle -v
```

Kiểm thử nghiệp vụ sử dụng CSDL tạm riêng, không reset dữ liệu chính. Kiểm tra giao diện giả lập và cách tạo fixture được mô tả trong `app/README.md`.

PRD gốc có một liên kết tài liệu trên máy người soạn; liên kết đó không hoạt động trên máy khác. Các liên kết nội bộ của bộ MRP giữ nguyên.
