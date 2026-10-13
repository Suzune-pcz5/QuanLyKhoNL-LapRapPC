# Chạy trên Render với MySQL online

Code local dùng MySQL portable và `runtime.json` trên Windows. Bản online đọc biến môi trường, xác minh chứng chỉ TLS và không chạy script cài/dừng MySQL của Windows.

## 1. Chuẩn bị MySQL

Cần MySQL 8.0.16 trở lên, hỗ trợ InnoDB, CHECK, procedure, trigger và named lock. Aiven cung cấp gói MySQL Free; xem [tạo dịch vụ](https://aiven.io/docs/products/mysql/get-started) và [gói Free](https://aiven.io/docs/products/mysql/concepts/mysql-free-tier).

Trong Aiven, chờ service Running, lấy Host, Port, Database, user quản trị và tải CA certificate. Database nghiệp vụ cần trống. Tài khoản khởi tạo phải có quyền tạo bảng/view/procedure/trigger, tạo database metadata, tạo user và cấp quyền.

## 2. Khởi tạo một lần từ máy cá nhân

Chạy từ checkout đầy đủ có `docs/mrp`. Render với Root Directory `app` không có các file ngoài thư mục đó; không chạy khởi tạo trong Build/Start Command.

Cấu hình riêng ngoài Git, ví dụ `%LOCALAPPDATA%/HTTTDN-Demo/cloud/aiven-warehouse.json`:

```json
{
  "MYSQL_HOST": "HOST_AIVEN",
  "MYSQL_PORT": "PORT_AIVEN",
  "MYSQL_DATABASE": "defaultdb",
  "MYSQL_STATE_DATABASE": "warehouse_web",
  "MYSQL_USER": "mrp_web_app",
  "MYSQL_PASSWORD": "MAT_KHAU_MYSQL_APP_RIENG",
  "MYSQL_ADMIN_USER": "avnadmin",
  "MYSQL_ADMIN_PASSWORD": "MAT_KHAU_QUAN_TRI_AIVEN",
  "MYSQL_SSL_CA": "DUONG_DAN_CA_PEM",
  "SECRET_KEY": "CHUOI_NGAU_NHIEN_IT_NHAT_32_KY_TU",
  "APP_ORIGIN": "https://setup.invalid",
  "INITIAL_PASSWORD": "MAT_KHAU_WEB_IT_NHAT_12_KY_TU"
}
```

`APP_ORIGIN` trong file khởi tạo có thể dùng địa chỉ tạm trên vì CLI không phục vụ HTTP. Không dùng địa chỉ tạm đó làm origin của web thật.

```powershell
cd app
$taskConfig=Join-Path $env:LOCALAPPDATA 'HTTTDN-Demo/cloud/aiven-warehouse.json'
$taskPython=Join-Path $env:LOCALAPPDATA 'HTTTDN-Demo/venv/Scripts/python.exe'
& $taskPython cloud_setup.py --config-file $taskConfig --initialize-empty --seed
& $taskPython cloud_setup.py --config-file $taskConfig --export-render-env (Join-Path $env:LOCALAPPDATA 'HTTTDN-Demo/cloud/render.env')
```

Lệnh đầu chỉ nhận database trống và user ứng dụng mới; không ghi đè, reset hay tự migrate database đã có. MySQL DDL tự commit: nếu khởi tạo lỗi giữa chừng, kiểm tra các đối tượng đã tạo trước khi chạy lại, không xóa dữ liệu để thử lại. Khi thành công, có 17 bảng nghiệp vụ và 2 bảng metadata trong **database riêng**. Tài khoản ứng dụng chỉ có quyền danh mục/nháp theo cột, thực thi 12 procedure public và CRUD metadata; không được sửa tồn/ledger/trạng thái trực tiếp.

`--seed` tạo tồn mẫu và bốn tài khoản `quanly`, `nhanvien`, `nhanvien_khac`, `admin`, dùng `INITIAL_PASSWORD`. Không dùng `--seed` thì tạo một tài khoản `admin` để nhập dữ liệu từ đầu. Mật khẩu được lưu bằng hash.

## 3. Cấu hình Render

| Ô | Giá trị |
|---|---|
| Runtime | Python |
| Branch | Branch có commit sửa cloud |
| Root Directory | `app` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `waitress-serve --call --listen=0.0.0.0:$PORT --threads=6 --url-scheme=https server:create_app` |
| Health Check Path | `/healthz` |

Trong **Environment → Add from .env**, nhập nội dung file `render.env` được tạo ở trên. File chỉ chứa user ứng dụng; không đưa `MYSQL_ADMIN_PASSWORD` hoặc `INITIAL_PASSWORD` vào Render. Trong **Secret Files**, thêm file `ca.pem` với nội dung chứng chỉ CA và đặt `MYSQL_SSL_CA=/etc/secrets/ca.pem`.

Các biến bắt buộc: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `SECRET_KEY`. Metadata dùng `MYSQL_STATE_DATABASE`, mặc định `<database>_web`, phải khớp lúc khởi tạo. HTTPS origin lấy từ `RENDER_EXTERNAL_URL`; nếu dùng domain riêng, đặt `APP_ORIGIN=https://domain-cua-ban` không có đường dẫn.

Render dùng `$PORT` cho HTTP. Cấu hình Secure cookie và origin cố định giữ CSRF hoạt động khi HTTPS được kết thúc ở proxy. Xem [Render port binding](https://render.com/docs/web-services#port-binding), [biến mặc định](https://render.com/docs/environment-variables) và [Waitress CLI](https://docs.pylonsproject.org/projects/waitress/en/latest/runner.html).

## 4. Kiểm tra sau deploy

`/healthz` là kiểm tra tiến trình, không phải kiểm tra kết nối DB. Sau khi service Live, mở trang đăng nhập, đăng nhập tài khoản đã khởi tạo và kiểm tra tồn kho/báo cáo. Lần deploy hoặc process mới tiếp tục sử dụng session và idempotency record ở MySQL; không phụ thuộc ổ đĩa tạm của Render Free.

Bản Windows giữ SQLite metadata và chức năng backup/restore hiện có. Bản online dùng công cụ sao lưu của nhà cung cấp MySQL; các API backup/restore local bị chặn rõ ràng, không gọi executable Windows trên Render.

## Kiểm thử

```powershell
cd app
& "$env:LOCALAPPDATA/HTTTDN-Demo/venv/Scripts/python.exe" -m unittest test_cloud_config test_cloud_state test_integration test_lifecycle -v
```

Kiểm thử có import không tồn tại `LOCALAPPDATA`, cấu hình thiếu/không hợp lệ, TLS, HTTPS origin, health không kết nối DB, bảo vệ chức năng local, dữ liệu session/chống lưu trùng bền vững và rollback metadata. Test MySQL dùng database tạm riêng và thu hồi đúng quyền test.
