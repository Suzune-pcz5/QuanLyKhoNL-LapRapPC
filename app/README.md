# Quản lý kho và lắp ráp PC

Ứng dụng local dùng **MySQL thật**, schema 17 bảng đã có trong `docs/mrp`. Backend Flask/PyMySQL, giao diện HTML/CSS/JavaScript tiếng Việt, server Waitress. Không cần Node để chạy ứng dụng; Node chỉ dùng cho kiểm tra mã giao diện.

## Chạy trên máy này

Chạy trên Render/Linux: xem [hướng dẫn triển khai](../docs/DEPLOY_RENDER.md). Cấu hình MySQL được đọc từ biến môi trường; bản local tiếp tục dùng `runtime.json` và runtime hiện có.

Nhấp đúp [`start-demo.cmd`](../start-demo.cmd), hoặc chạy từ thư mục project:

```powershell
.\start-demo.cmd
```

Mở **http://127.0.0.1:8765**. Dừng bằng [`stop-demo.cmd`](../stop-demo.cmd).

Lần đầu, script tạo venv, cài thư viện và tải MySQL 8.4.11 ZIP từ CDN chính thức của Oracle, kiểm tra checksum rồi tạo CSDL demo riêng. Cần Python 3.11+ để bootstrap.

Trong workspace CNPM, dùng `../start-kho-local.cmd` / `../stop-kho-local.cmd` tính từ thư mục project để dùng runtime và dữ liệu hiện có ở `../.mrp-runtime`. Trước khi chạy các lệnh Python bên dưới tại `app`, đặt `$env:MRP_RUNTIME=(Resolve-Path '..\..\.mrp-runtime').Path`.

- HTTP: `127.0.0.1:8765`.
- MySQL: `127.0.0.1:3397`; CSDL `htttdn_mrp_demo`.
- Runtime, MySQL data, credential ngẫu nhiên và log: `%LOCALAPPDATA%/HTTTDN-Demo`.
- Source: thư mục `app`; PRD/ERD trong `docs/mrp`, SQL cấu trúc được cập nhật cùng routine của ứng dụng.
- Chạy lại launcher giữ dữ liệu hiện có; không tự reset hoặc nhập demo lần hai.
- Khi đổi thư mục source, dừng bản đang chạy trước; launcher chỉ nhận diện đúng đường dẫn server của checkout hiện tại và dừng cả tiến trình Python con.

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
$taskRuntime = if ($env:MRP_RUNTIME) { $env:MRP_RUNTIME } else { Join-Path $env:LOCALAPPDATA 'HTTTDN-Demo' }
& "$taskRuntime\venv\Scripts\python.exe" -B -m unittest discover -s . -p 'test_*.py' -v
```

Các test nghiệp vụ tạo CSDL `mrp_test_<ngẫu nhiên>`, rồi xóa đúng CSDL và thu hồi quyền tương ứng; cleanup vẫn chạy khi khởi tạo test thất bại. Test vòng đời tiến trình dùng mock. Tổng cộng 106 test, gồm 12 AT của PRD, 13 sidecase, 4 hồi quy cleanup, 9 hồi quy QA-01–QA-04 và 12 hồi quy phiên/lưu lại R2–R4. Không reset CSDL demo chính. Các kiểm thử gồm luồng đầy đủ, nhập nháp/chốt, snapshot BOM, rollback khi thiếu nguyên liệu, xử lý lặp, vượt kế hoạch, từ chối/lập lại, hủy trước cấp, cạnh tranh PC cuối cùng, phân quyền/CSRF, khóa phiên đăng nhập, khóa nháp khi gửi, báo cáo theo mốc kỳ, đối chiếu ledger và quyền DB hạn chế.

Chạy các lượt test MySQL lần lượt khi dùng chung runtime/tài khoản DB. Một số ca cleanup đối chiếu toàn bộ quyền ứng dụng; tiến trình test khác đang tạo hoặc xóa quyền có thể làm phép đối chiếu bị nhiễu.

Kiểm tra giao diện bằng DOM giả lập, không cần truy cập trình duyệt:

```powershell
cd app
npm install
npm test
```

Fixture mẫu đã có ở `tests/fixtures/state.json`, gồm dữ liệu demo và không chứa mật khẩu/hash. `npm test` chạy cả năm bộ kiểm tra DOM với tổng cộng 277 kiểm tra; có thể truyền JSON riêng cho từng file `test_*frontend.cjs`. Bộ phiên đăng nhập kiểm tra phản hồi thành công/lỗi đến muộn, đổi tài khoản, tải đảo thứ tự, lưu form cũ, đếm vị trí hàng lỗi và giữ nguyên mã thao tác/dữ liệu khi thử lưu lại. Bộ phục hồi bổ sung trường hợp tab giữ khóa bị đóng, nhiều lượt đồng bộ đang chờ, đọc phiên thất bại và sửa form sau lỗi nhập liệu/rollback xác định. Kiểm tra DOM không xác nhận bố cục thực tế trên trình duyệt.

Kết quả từng lượt rà soát, hồi quy và kiểm tra trên Edge thật được ghi trong [báo cáo kiểm thử](VERIFICATION.md).

Nếu runtime cũ còn quyền của CSDL test đã xóa, có thể dọn bằng CLI sau khi MySQL đã chạy:

```powershell
& "$taskRuntime\venv\Scripts\python.exe" -B manage.py cleanup-test-grants
```

Lệnh chỉ thu hồi quyền của tài khoản ứng dụng trên tên CSDL test hợp lệ đã không còn tồn tại; bỏ qua CSDL chính và mọi schema còn hoạt động. Dùng `REVOKE` cho từng quyền schema, bảng/cột và routine; không sửa trực tiếp bảng quyền hệ thống. MySQL không tự thu hồi quyền khi `DROP DATABASE` ([tài liệu MySQL 8.4](https://dev.mysql.com/doc/refman/8.4/en/drop-database.html)).

## Sao lưu và khôi phục

Admin dùng trang **Sao lưu dữ liệu**, hoặc chạy CLI:

```powershell
cd app
$taskRuntime = if ($env:MRP_RUNTIME) { $env:MRP_RUNTIME } else { Join-Path $env:LOCALAPPDATA 'HTTTDN-Demo' }
& "$taskRuntime\venv\Scripts\python.exe" manage.py backup
& "$taskRuntime\venv\Scripts\python.exe" manage.py restore-test TEN_BACKUP.sql
```

Backup ở `app/backups`, được bỏ qua bởi Git. Mỗi bản mới có dấu SHA-256 của SQL, số dòng và dấu dữ liệu từng bảng, cùng danh sách view/routine/trigger. Thông tin này được lấy bằng cách khôi phục chính dump vừa tạo vào CSDL tạm, tránh lệch với dữ liệu đang tiếp tục thay đổi.

Kiểm chứng khôi phục chỉ nhận file trong thư mục này, tạo CSDL `mrp_restore_<thời gian>_<ngẫu nhiên>`, đối chiếu với thông tin trong backup rồi thử xác thực và chốt nhập bằng tài khoản/danh mục kiểm thử riêng. Không phụ thuộc tên hay mật khẩu tài khoản demo. CSDL tạm được xóa cả khi thành công và khi thất bại; CSDL chính không bị ghi đè. Bản SQL cũ chưa có dấu kiểm chứng vẫn có thể được kiểm tra cấu trúc và giao dịch, nhưng kết quả sẽ ghi rõ chưa đối chiếu dữ liệu tại thời điểm sao lưu.

Admin không thể khóa tài khoản, bỏ vai trò nhân viên hoặc ngừng làm nhân viên đang có yêu cầu ở trạng thái đã giao, đã cấp vật liệu hoặc đang lắp ráp. Cần hoàn thành công việc, hoặc hủy hợp lệ trước khi cấp vật liệu. Nhu cầu hiển thị chỉ tính vật liệu có thể cấp từ sản phẩm và vị trí đang hoạt động; tồn vật lý vẫn được giữ để tra cứu.

Đối chiếu dữ liệu diễn ra trước giao dịch thử. Tài khoản và danh mục kiểm thử được tạo riêng trong CSDL khôi phục. Bộ schema gồm 17 bảng, 4 view, 16 procedure, 19 trigger.

## Đồng bộ form, xác nhận chứng từ và migration

Form lưu thành công chỉ đóng sau khi tải xong danh sách mới. Nếu ghi đã thành công nhưng tải danh sách lỗi, nút **Tải lại dữ liệu** chỉ tải lại danh sách, không gửi lại yêu cầu lưu. Trong lúc lưu/đồng bộ, form chặn đóng và lưu lặp; nếu đóng sau lỗi tải lại, cần **Làm mới** trước khi mở form tiếp theo.

Chốt nhập, duyệt xuất/bàn giao và tiếp nhận lắp ráp hiển thị mã chứng từ, nguồn/người nhận, SKU/vị trí và thay đổi tồn thực tế/hàng lỗi/khả dụng từng dòng. Thông tin chứng từ được tải mới trước khi mở xác nhận. Khi thiếu tồn, API trả HTTP 409 cùng `code=INSUFFICIENT_STOCK` và `details` gồm `sku`, `location`, `required`, `available`, `missing`; số lượng lấy ngay từ dòng tồn đã khóa trong giao dịch.

Khi khởi động backend, `initialize()` tự nâng cấp routine nội bộ `sp_ghi_bien_dong` của CSDL cũ; không tạo lại bảng hay nhập lại seed. Định nghĩa cũ được lưu ở `<runtime>/migrations/` để rollback. Nếu tạo routine mới thất bại sau khi DROP, migration thử khôi phục ngay định nghĩa cũ và báo lỗi. Chạy lại migration đã áp dụng không thay đổi gì.

Migration cũng cập nhật đúng ba trigger khóa ghi chú của phiếu nhập, phiếu xuất và kết quả lắp ráp. Ghi chú chỉ được sửa ở nháp; so sánh theo byte để chặn cả đổi hoa/thường hoặc bỏ dấu. Riêng procedure từ chối kết quả được ghi lý do khi chuyển từ chờ tiếp nhận sang từ chối. Các định nghĩa trigger cũ được lưu trước khi cập nhật; nếu cập nhật thất bại, toàn bộ trigger đã thay được phục hồi. Sáu nhãn mẫu thiếu dấu chỉ được đổi khi đúng ID và khớp chính xác nhãn cũ, kể cả hoa/thường; tên riêng của người dùng được giữ nguyên.

Migration khóa nội dung còn bổ sung so sánh theo byte cho tên người nhận phiếu xuất, tên cấu hình BOM và khóa hạn mong muốn của yêu cầu đã giao. Chỉ thay ba trigger liên quan, có rollback, không cập nhật dữ liệu chứng từ.

Khi tạo phiếu mới, giao diện gửi `Idempotency-Key` cho mỗi biểu mẫu. Nếu mất phản hồi lưu, nút **Thử lại lưu** gửi lại đúng mã và dữ liệu ban đầu; server trả lại ID đã tạo. Mã thao tác được lưu bền vững và thao tác được tuần tự hóa theo tài khoản/loại phiếu/mã, kể cả khi backend khởi động lại. Cùng mã nhưng dữ liệu khác hoặc phiếu đã xóa được báo lỗi, không tự tạo thêm. Client tích hợp nên luôn gửi header này khi POST tạo chứng từ.

Nếu thử lại nhận lỗi nhập liệu HTTP 400 hoặc backend xác nhận `save_not_committed=true`, form cho sửa dữ liệu và lần lưu sau dùng mã thao tác mới. Backend chỉ xác nhận sau rollback thành công trước khi thử COMMIT; áp dụng cả lỗi trùng BOM HTTP 409. Lỗi xung đột mã/khóa, lỗi máy chủ chưa rõ kết quả hoặc phản hồi không đọc được giữ nguyên dữ liệu/mã để thử lại an toàn. Không suy ra chưa lưu chỉ từ HTTP 409/500. Các tab chờ đăng nhập sẽ đọc lại phiên sau khi Web Lock được giải phóng, kể cả khi tab đang đăng nhập bị đóng trước lúc gửi thông báo hoàn tất.

Tại workspace CNPM, dùng `D:/Hojc/CNPM/start-kho-local.cmd` / `stop-kho-local.cmd`; runtime là `D:/Hojc/CNPM/.mrp-runtime`. Có thể chạy riêng migration khi backend đã dừng và MySQL vẫn chạy:

```powershell
$env:MRP_RUNTIME='D:\Hojc\CNPM\.mrp-runtime'
& "$env:MRP_RUNTIME\venv\Scripts\python.exe" manage.py migrate
```

Routine/trigger DDL của MySQL không nằm trong transaction. Dừng backend trước khi áp dụng/rollback; file rollback phải chạy với đúng CSDL ghi trong tên file, bằng tài khoản quản lý CSDL. Nên tạo backup đầy đủ trước khi cập nhật bản đang dùng. Launcher khi backend đang chạy chỉ mở lại địa chỉ; cần khởi động lại backend để nhận mã Python/routine mới.

## Các điểm kỹ thuật để nhóm nối vào dự án

- Các API thay đổi trạng thái gọi 12 procedure public bằng `MaTK` lấy từ phiên đã xác thực. Bốn helper nội bộ không được cấp EXECUTE cho DB user ứng dụng.
- DB user `mrp_app` chỉ có SELECT, DML danh mục/nháp theo cột và EXECUTE cần thiết; không được sửa tồn, ledger, snapshot hoặc cột chuyển trạng thái.
- Lưu/sửa nháp khóa cha bằng `FOR UPDATE` trong transaction. CALL nghiệp vụ chạy ngoài transaction của backend, đọc hết result set và retry deadlock có giới hạn trên cùng ID.
- Cookie chỉ chứa mã phiên ký, HttpOnly/SameSite Strict; trạng thái phiên ở server được thu hồi khi đăng xuất/đổi tài khoản và hết hạn sau 8 giờ. Request đọc không tự gia hạn hay ghi lại cookie. Edge trên localhost dùng Web Locks để tuần tự hóa bootstrap/đăng nhập/đăng xuất giữa các tab; thông báo thay đổi qua localStorage làm các tab tải lại tài khoản và loại bỏ dữ liệu cũ. CSRF và quyền/sở hữu vẫn được kiểm tra ở backend.
- Metadata phiên và mã thao tác nằm trong `<runtime>/web-state-<mã CSDL>.sqlite3`, dùng SQLite có sẵn của Python, tách riêng mỗi CSDL. Giữ file này qua các lần khởi động để bảo toàn khả năng thử lưu lại; không đưa vào source hoặc bản sao lưu SQL nghiệp vụ. MySQL vẫn giữ nguyên 17 bảng nghiệp vụ. Phiên cookie của bản cũ cần đăng nhập lại một lần sau nâng cấp. Query được parameter hóa, không lấy người lập/duyệt hoặc tồn từ client.
- Credential của MySQL và secret session ở runtime ngoài source. Root chỉ phục vụ cài đặt, quản lý runtime và sao lưu/khôi phục trong máy local; request nghiệp vụ dùng DB user hạn chế.
- Gợi ý cấp vật liệu chỉ dùng sản phẩm/vị trí hoạt động. View nhu cầu gốc có thể bao gồm tồn ở vị trí đã ngừng; màn hình chi tiết ghi rõ điều này.
- Từ chối chứng từ giữ lại lịch sử; nhân viên lập phiếu mới. Chứng từ gửi/chốt chỉ xem/in, không sửa.
- API tạo nháp: `POST /api/documents/{incoming,outgoing,bom,jobs,results}`. Sửa/xóa nháp: `PUT/DELETE .../{id}`. Chuyển trạng thái: `POST /api/actions/{kind}/{id}/{action}`.
- API dữ liệu: `GET /api/state`; báo cáo: `GET /api/report?from=...&to=...&type=...&location=...`.

Đây là bản demo chạy local theo phạm vi MRP trong PRD; phần khảo sát doanh nghiệp, BFD/DFD và báo cáo đồ án chung vẫn cần nhóm hoàn thiện.
