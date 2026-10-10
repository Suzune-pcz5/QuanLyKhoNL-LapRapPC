# Quản lý kho và lắp ráp PC

Ứng dụng local dùng **MySQL thật**, schema 17 bảng đã có trong `docs/mrp`. Backend Flask/PyMySQL, giao diện HTML/CSS/JavaScript tiếng Việt, server Waitress. Không cần Node để chạy ứng dụng; Node chỉ dùng cho kiểm tra mã giao diện.

## Chạy trên máy này

Nhấp đúp [`start-demo.cmd`](../start-demo.cmd), hoặc chạy từ thư mục project:

```powershell
.\start-demo.cmd
```

Mở **http://127.0.0.1:8765**. Dừng bằng [`stop-demo.cmd`](../stop-demo.cmd).

Lần đầu, script tạo venv, cài thư viện và tải MySQL 8.4.11 ZIP từ CDN chính thức của Oracle, kiểm tra checksum rồi tạo CSDL demo riêng. Máy hiện tại đã được cài và khởi tạo. Python 3.11+ là điều kiện để bootstrap; đã có trên máy này.

- HTTP: `127.0.0.1:8765`.
- MySQL: `127.0.0.1:3397`; CSDL `htttdn_mrp_demo`.
- Runtime, MySQL data, credential ngẫu nhiên và log: `%LOCALAPPDATA%/HTTTDN-Demo`.
- Source: thư mục `app`; schema/PRD gốc giữ nguyên trong `docs/mrp`.
- Chạy lại launcher giữ dữ liệu hiện có; không tự reset hoặc nhập demo lần hai.
- Runtime được dùng chung với bản trong thư mục HTTTDN. Khi đổi thư mục source, dừng bản đang chạy trước; launcher chỉ nhận diện đúng đường dẫn server của checkout hiện tại và dừng cả tiến trình Python con.

## Tài khoản đăng nhập

Mật khẩu chung **`Demo@12345`**. Đây là dữ liệu giả định cho demo local.

Tên đăng nhập đã được rút gọn: `quanly`, `nhanvien`, `nhanvien_khac`, `admin`. Các tên cũ có tiền tố `demo_` không còn dùng để đăng nhập. Mật khẩu giữ nguyên. Màn hình đăng nhập không điền sẵn hoặc hiển thị mật khẩu.

Khi khởi động, ứng dụng đổi đúng nhãn dữ liệu ban đầu bằng giao dịch có kiểm tra trùng tên. ID, mật khẩu, số lượng và lịch sử được giữ nguyên. Tên BOM và bộ phận nhận của chứng từ đã chốt được rút gọn khi hiển thị; nội dung gốc vẫn lưu trong CSDL.

| Tên đăng nhập | Vai trò |
|---|---|
| `quanly` | Quản lý kho |
| `nhanvien` | Nhân viên được giao việc |
| `nhanvien_khac` | Nhân viên khác để kiểm tra quyền sở hữu |
| `admin` | Quản trị tài khoản và danh mục |

Mật khẩu lưu bằng hash Werkzeug; không sử dụng placeholder trong SQL để xác thực. Quyền được đọc lại từ DB trên từng request, kể cả khi tài khoản vừa khóa/đổi vai trò. Đổi mật khẩu làm phiên cũ mất hiệu lực. Admin không duyệt kho.

## Chức năng đã triển khai

- Tổng quan, tồn theo SKU/vị trí, tách hàng lỗi/khả dụng; tìm kiếm, lọc và sắp xếp.
- Phiếu nhập nguyên liệu: tạo/sửa/xóa nháp, nhiều dòng, giá mua, thực nhận/lỗi, chốt nhập và in.
- BOM một cấp: tạo/sửa nháp, định mức, phiên bản và ban hành.
- Yêu cầu lắp ráp: tạo/giao/nhận/hủy trước cấp; xem định mức chốt, nhu cầu, thiếu nguyên liệu, vật liệu còn ở khu lắp ráp và tiến độ.
- Đề nghị xuất nguyên liệu/thành phẩm: tạo/sửa/xóa nháp, gợi ý phân bổ qua vị trí hoạt động, gửi, duyệt hoặc từ chối có lý do.
- Kết quả đạt/lỗi: tạo/sửa nháp, gửi, tiếp nhận hoặc từ chối; tự nhập thành phẩm và không trừ linh kiện lần hai.
- Báo cáo theo tháng/quý/năm hoặc khoảng tùy chọn, lọc loại hàng/vị trí, in và CSV UTF-8. Khoảng `[từ, đến)` theo UTC+7.
- Admin riêng: CRUD danh mục, tìm kiếm kết hợp bộ lọc; nhân viên, tài khoản, khóa, đổi quyền và mật khẩu. Không xóa tài khoản của nhân viên đã có chứng từ; ngừng/khóa để giữ lịch sử.
- Lịch sử biến động chỉ xem; backup đầy đủ và khôi phục thử ở CSDL mới, đối chiếu dữ liệu và chạy một giao dịch kiểm chứng.

## Kịch bản trình bày

Trang **Hướng dẫn sử dụng** trong ứng dụng có từng bước và vai trò cần dùng. Dữ liệu ban đầu đã chạy SQL demo:

| Mặt hàng/vị trí | Thực tế | Không bán | Khả dụng |
|---|---:|---:|---:|
| CPU / LK-A1 | 7 | 0 | 7 |
| RAM / LK-A1 | 14 | 2 | 12 |
| PC / TP-A1 | 1 | 0 | 1 |
| PC / LOI-A1 | 1 | 1 | 0 |

Để trình bày một lượt mới:

1. Quản lý nhập thêm 10 CPU và 20 RAM, gồm 2 RAM lỗi; lưu nháp rồi chốt để thấy khác biệt.
2. Quản lý giao 3 PC theo BOM có sẵn cho `nhanvien`.
3. Nhân viên nhận việc, xem nhu cầu 3 CPU + 6 RAM; đề nghị cấp và gửi duyệt.
4. Quản lý duyệt cấp đồng thời bàn giao.
5. Nhân viên ghi 2 PC đạt và 1 PC lỗi, gửi kết quả.
6. Quản lý tiếp nhận; chỉ tăng PC, không giảm nguyên liệu lần hai.
7. Nhân viên đề nghị xuất 1 PC tốt; quản lý duyệt và xem báo cáo.
8. Admin tạo backup, tải file và kiểm chứng khôi phục thử.

Kết thúc lượt này: CPU 14; RAM 28 gồm 4 lỗi; PC tốt 2; PC lỗi 2. Không cần xóa dữ liệu demo cũ.

## Kiểm thử và bằng chứng

Chạy kiểm thử tích hợp trên MySQL riêng của demo:

```powershell
cd app
& "$env:LOCALAPPDATA\HTTTDN-Demo\venv\Scripts\python.exe" -m unittest test_integration test_lifecycle -v
```

Mỗi test tạo CSDL `mrp_test_<ngẫu nhiên>`, rồi xóa đúng CSDL của test. Không reset CSDL demo chính. Các kiểm thử gồm luồng đầy đủ, nhập nháp/chốt, snapshot BOM, rollback khi thiếu nguyên liệu, xử lý lặp, vượt kế hoạch, từ chối/lập lại, hủy trước cấp, cạnh tranh PC cuối cùng, phân quyền/CSRF, khóa phiên đăng nhập, khóa nháp khi gửi, báo cáo theo mốc kỳ, đối chiếu ledger và quyền DB hạn chế.

Kiểm tra giao diện bằng DOM giả lập, không cần truy cập trình duyệt:

```powershell
cd app
npm install
node test_frontend.cjs DUONG_DAN_FRONTEND_FIXTURE_JSON
```

Fixture là JSON từ `/api/state` của quản lý. Lần triển khai này đã tạo fixture tại `%LOCALAPPDATA%/HTTTDN-Demo/frontend-fixture.json`; nếu cần tái tạo, dùng Flask test client hoặc xuất phản hồi API. Kiểm tra DOM không xác nhận bố cục thực tế trên trình duyệt.

Ngày 10/10/2026, chạy từ repository này: **28 test đạt** (22 test MySQL và 6 test quản lý tiến trình); **66 kiểm tra DOM giả lập đạt**. Xem [kết quả và giới hạn kiểm tra](VERIFICATION.md).

## Sao lưu và khôi phục

Admin dùng trang **Sao lưu dữ liệu**, hoặc chạy CLI:

```powershell
cd app
& "$env:LOCALAPPDATA\HTTTDN-Demo\venv\Scripts\python.exe" manage.py backup
& "$env:LOCALAPPDATA\HTTTDN-Demo\venv\Scripts\python.exe" manage.py restore-test TEN_BACKUP.sql
```

Backup ở `app/backups`, được bỏ qua bởi Git. Chức năng khôi phục thử chỉ nhận file backup trong thư mục này, tạo CSDL `mrp_restore_<thời gian>_<ngẫu nhiên>`, không ghi đè CSDL chính. CSDL khôi phục được giữ để xem bằng Workbench hoặc CLI.

Đối chiếu dữ liệu diễn ra trước giao dịch thử. Kiểm chứng đăng nhập dùng tài khoản `quanly` và mật khẩu demo; nếu đã đổi mật khẩu hoặc ngừng toàn bộ danh mục, cần điều chỉnh kịch bản kiểm chứng. Bộ schema gồm 17 bảng, 4 view, 16 procedure, 19 trigger.

## Các điểm kỹ thuật để nhóm nối vào dự án

- Các API thay đổi trạng thái gọi 12 procedure public bằng `MaTK` lấy từ phiên đã xác thực. Bốn helper nội bộ không được cấp EXECUTE cho DB user ứng dụng.
- DB user `mrp_app` chỉ có SELECT, DML danh mục/nháp theo cột và EXECUTE cần thiết; không được sửa tồn, ledger, snapshot hoặc cột chuyển trạng thái.
- Lưu/sửa nháp khóa cha bằng `FOR UPDATE` trong transaction. CALL nghiệp vụ chạy ngoài transaction của backend, đọc hết result set và retry deadlock có giới hạn trên cùng ID.
- Session ký, cookie HttpOnly/SameSite Strict, CSRF và kiểm tra quyền/sở hữu ở backend. Query được parameter hóa, không lấy người lập/duyệt hoặc tồn từ client.
- Credential của MySQL và secret session ở runtime ngoài source. Root chỉ phục vụ cài đặt, quản lý runtime và sao lưu/khôi phục trong máy local; request nghiệp vụ dùng DB user hạn chế.
- Gợi ý cấp vật liệu chỉ dùng sản phẩm/vị trí hoạt động. View nhu cầu gốc có thể bao gồm tồn ở vị trí đã ngừng; màn hình chi tiết ghi rõ điều này.
- Từ chối chứng từ giữ lại lịch sử; nhân viên lập phiếu mới. Chứng từ gửi/chốt chỉ xem/in, không sửa.
- API tạo nháp: `POST /api/documents/{incoming,outgoing,bom,jobs,results}`. Sửa/xóa nháp: `PUT/DELETE .../{id}`. Chuyển trạng thái: `POST /api/actions/{kind}/{id}/{action}`.
- API dữ liệu: `GET /api/state`; báo cáo: `GET /api/report?from=...&to=...&type=...&location=...`.

Đây là bản demo chạy local theo phạm vi MRP trong PRD; phần khảo sát doanh nghiệp, BFD/DFD và báo cáo đồ án chung vẫn cần nhóm hoàn thiện.
