# Kết quả kiểm thử

## Sửa triển khai Render — 13/10/2026

- Sửa import phụ thuộc `LOCALAPPDATA`, giữ cấu hình Windows local và bổ sung cấu hình MySQL online qua environment. Không khởi tạo/migrate DB khi web khởi động.
- Kiểm tra import trong process không có `LOCALAPPDATA`; cấu hình thiếu/không hợp lệ báo đúng tên biến, không lộ giá trị. TLS kiểm tra chứng chỉ/hostname; HTTPS origin và Secure cookie được kiểm chứng.
- **47 test Python khác nhau đạt**: 46 test trong lượt kết hợp (15 config, 3 metadata MySQL, 22 nghiệp vụ, 6 lifecycle), sau đó bổ sung và kiểm tra lại test export loại credential quản trị, tổng nhóm config là 16.
- **279 kiểm tra DOM đạt**: 94 giao diện chung, 37 PRD, 42 audit, 62 session, 44 recovery. Bao gồm 2 kiểm tra mới cho trạng thái sao lưu của bản online.
- Session/idempotency cloud được kiểm chứng bằng MySQL thật ở DB tạm: tồn tại khi tạo app instance mới; lặp lưu trả cùng ID; logout không bị response cũ phục hồi; rollback metadata và phân biệt hoa/thường của token đúng. Các DB/quyền test được dọn.
- Kết nối thực tế tới dịch vụ Aiven của người dùng bằng CA đã cung cấp thành công, MySQL **8.4.11**. Trước khởi tạo, DB nghiệp vụ và metadata không có đối tượng. Sau khởi tạo: 17 bảng nghiệp vụ và 2 bảng metadata ở database riêng.
- Tài khoản MySQL hạn chế trên Aiven đã chạy API đăng nhập của cả bốn vai trò, đọc tồn và báo cáo thành công. UPDATE trực tiếp tồn/trạng thái và DELETE ledger bị từ chối.
- Credential, CA và file environment thực tế giữ ngoài repository. File export cho Render không chứa credential quản trị Aiven hoặc mật khẩu tài khoản web ban đầu.

Đây là kiểm chứng code và kết nối Aiven. Chưa xác nhận service Render Live; cần đưa commit lên branch triển khai, nhập environment/CA vào Render rồi deploy. `/healthz` chỉ xác nhận tiến trình, không thay thế kiểm tra đăng nhập và dữ liệu.

Ngày rà soát đầy đủ: **11/10/2026**, UTC+7. Môi trường: Windows, Python 3.14.5, MySQL 8.4.11 và Microsoft Edge thật.

## Đối chiếu PRD — 12/10/2026

Căn cứ: `docs/mrp/PRD_MRP_HTTTDN_17_bang.docx`, phiên bản 1.0. Đã đọc lại yêu cầu, đối chiếu backend/UI/schema và chạy lại riêng nghiệm thu PRD. **Phần chức năng ứng dụng khớp FR01–FR13 trong phạm vi đã kiểm tra; chưa phát hiện thêm yêu cầu chức năng bị thiếu.** Không kết luận toàn bộ tài liệu/bộ nộp đã hoàn chỉnh. Hồ sơ bàn giao và báo cáo môn nằm ngoài phạm vi theo yêu cầu trước của người dùng.

| Yêu cầu | Đối chiếu triển khai và bằng chứng |
|---|---|
| FR01 | Xác thực, khóa tài khoản, ba vai trò, quyền/sở hữu ở backend; AT03 chạy lại đạt. |
| FR02 | Admin theo vai trò; CRUD/khóa/đổi vai trò tài khoản; tìm từ khóa kết hợp bộ lọc và sắp xếp danh mục. Đối chiếu `server.py`, `static/app.js` và hồi quy tìm kiếm/UI hiện có. |
| FR03 | Nhập NCC, thực nhận/lỗi/giá/kiểm nhận/vị trí, chốt một lần; AT01/AT05 đạt. |
| FR04 | BOM một cấp, sửa nháp, phiên bản, ban hành một bản áp dụng; AT02 đạt. |
| FR05 | Giao số PC/BOM/nhân viên/hạn, chụp nhu cầu; AT02 đạt. |
| FR06 | Việc thuộc nhân viên, nhận việc, nhu cầu/khả dụng/thiếu; AT03 và các bước chuẩn bị luồng cấp phát đạt. |
| FR07 | Phân bổ đủ nhu cầu theo SKU/vị trí, gửi duyệt chưa giảm tồn; luồng AT04/AT08 đạt. |
| FR08 | Duyệt/bàn giao hoặc từ chối có lý do; thiếu một dòng rollback toàn phiếu; AT04/AT08 đạt. |
| FR09 | Kết quả đạt/lỗi nhiều đợt, tiếp nhận sinh nhập nội bộ, không trừ linh kiện lần hai; AT05/AT06/AT07 đạt. |
| FR10 | Đề nghị xuất thành phẩm có người nhận/SKU/số lượng/vị trí; luồng AT09 đạt. |
| FR11 | Duyệt chỉ dùng tồn khả dụng, chặn ghi nhận lặp và cạnh tranh; AT05/AT09 đạt. |
| FR12 | Tháng/quý/năm, loại hàng/vị trí, in/CSV; đối chiếu UI, AT10 chạy lại đạt. |
| FR13 | Tra cứu tồn/chứng từ/nhu cầu/trạng thái, lỗi tiếng Việt và hướng dẫn cài đặt/sử dụng; đối chiếu mã và bằng chứng UI ngày 11/10. |

**Kết quả mới:** `python -B -m unittest -v test_prd_acceptance` đạt **12/12 AT01–AT12 trong 172,935 giây** trên MySQL thật, chạy tuần tự bằng CSDL tạm. AT11 kiểm tra khóa chứng từ/lịch sử; AT12 kiểm tra backup/restore đủ dữ liệu/routine/trigger, đăng nhập và nghiệp vụ sau khôi phục. Lượt này không chạy lại toàn bộ 106 test Python hoặc ma trận Edge; các kết quả 277 DOM/250 Edge bên dưới thuộc ngày 11/10.

Đối chiếu mới giữa SQL, ERD và CSDL đang dùng: **17 bảng, 122 thuộc tính, 36 khóa ngoại**, tên bảng/cột khớp; ERD có 36 quan hệ FK. Runtime có 4 view/16 routine/19 trigger; đủ 17 bảng InnoDB/utf8mb4; kết nối UTC+7/SQL strict và tài khoản nghiệp vụ không phải root. Sau test, dấu dữ liệu và quyền CSDL chính khớp mốc kiểm tra trong lượt; không còn CSDL hoặc quyền test dư. BT không được truy cập. Không sửa mã chức năng hoặc PRD trong lượt này.

**Điểm tài liệu chưa đồng bộ:** `docs/mrp/HUONG_DAN_MRP_17_BANG.md:157` vẫn ghi nhóm cần làm đăng nhập/Admin/UI/in báo cáo/hướng dẫn; dòng 167 vẫn ghi chưa tuyên bố chạy backup/restore. Đây là mô tả cũ của bộ SQL, không phản ánh ứng dụng và bằng chứng hiện tại. Bộ source có ERD và mapping BFD/DFD dạng văn bản; không có bộ sơ đồ BFD/ngữ cảnh/DFD hoàn chỉnh trong các file còn lại. Phần hồ sơ này được ghi nhận, không triển khai vì người dùng đã loại khỏi phạm vi.

Bằng chứng mới lưu ngoài project tại `C:/Users/AD/.codex/visualizations/2026/10/10/01a125cb-7959-7423-9f55-c7cdd9b84b25/cnpm-prd-review-20261012/`: `prd-acceptance.log`, `schema-audit.json`, `baseline.json`, `final-audit.json`.

## Dọn workspace và kiểm thử sau R3 — 11/10/2026

Đã rà file cần giữ, cập nhật tài liệu cũ và chạy lại kiểm thử. Phát hiện **một biến thể còn sót của lỗi phục hồi form**, đã sửa và kiểm chứng. Không còn vấn đề đã tái hiện chưa xử lý trong phạm vi lượt này; kết quả kiểm thử không phải cam kết đã bao phủ mọi tình huống có thể có.

### R4-01 — đã sửa: form vẫn khóa khi thử lại gặp BOM trùng phiên bản HTTP 409

Trên Edge, tạo BOM cho PC với phiên bản 1 đã tồn tại, cắt kết nối ở lần lưu đầu, rồi thử lại. Backend từ chối vì trùng phiên bản bằng HTTP 409 nhưng form vẫn giữ trạng thái chưa xác định và khóa ô phiên bản. Bản sửa R3 trước đó chỉ mở lại sau HTTP 400. Không có BOM mới hoặc biến động tồn trong ca lỗi.

Backend hiện trả `save_not_committed=true` khi đã rollback thành công **trước khi thử COMMIT** của thao tác tạo có mã idempotency. Giao diện dựa vào xác nhận này để mở lại form, giữ đúng trạng thái vô hiệu hóa ban đầu và cấp mã mới cho dữ liệu đã sửa. Không suy ra chưa lưu chỉ từ mã 409/500: xung đột mã/khóa hoặc lỗi sau khi đã thử COMMIT vẫn giữ nguyên mã và payload để thử lại an toàn.

Đã tái hiện lỗi trước sửa bằng Edge và hai hồi quy backend/DOM. Sau sửa, ca mất mạng → trùng phiên bản 409 → đổi sang phiên bản 2 lưu thành công **đúng một BOM**. Mô phỏng server đã lưu rồi mất phản hồi mạng hoặc nhận 409/500 chưa xác định: thử lại trả đúng ID cũ và chỉ có một phiếu. Test MySQL bổ sung thực hiện COMMIT thật rồi báo lỗi mất phản hồi, xác nhận không trả marker chưa lưu và không tạo phiếu trùng khi thử lại. Không cần đổi schema hoặc migration.

### Kết quả kiểm thử

- **106 ca Python đã được xác nhận qua lượt đầy đủ và ca chạy lại.** Lượt đầy đủ chạy 106 ca trong **782,394 giây**, có **105 đạt và một ca cleanup thất bại** do tôi chạy thêm test MySQL song song dùng chung tài khoản DB. Log cho thấy 27 quyền của một CSDL test khác bị thu hồi giữa hai lần so sánh toàn bộ quyền. Sau khi mọi test DB khác kết thúc, chạy riêng `test_failed_setup_cleans_database_and_grants` đạt trong **6,366 giây**. Không ghi nhận thất bại nghiệp vụ còn lại; không mô tả lượt đầy đủ này là một lượt 106/106 OK.
- Hồi quy mới phân biệt rollback/COMMIT được mở rộng và chạy riêng đạt trong **12,266 giây**, bao gồm mất phản hồi ngay sau COMMIT thật. Hướng dẫn đã ghi rõ chạy các lượt test DB lần lượt để tránh nhiễu phép đối chiếu quyền.
- **277/277 kiểm tra DOM đạt**: 92 + 37 + 42 + 62 + 44. Thêm 11 kiểm tra cho rollback xác định 409/500 và xung đột chưa xác định ngay từ lần lưu đầu.
- **250 kiểm tra đối chứng Edge đạt**: 25 kiểm tra luồng nghiệp vụ, 13 đối chứng kèm ca phát hiện R4-01, 181 kiểm tra ma trận giao diện và 31 kiểm tra bản sửa. Ca lỗi R4-01 được ghi riêng ở kết quả trước sửa, sau đó kiểm chứng đã khắc phục.
- Ma trận sau bản sửa: **117 tổ hợp trang/tài khoản/kích thước**, bốn tài khoản ở 320/768/1440 px; đủ năm form ở 320/390/768/1440 px, năm tab danh mục, sidebar/focus và bốn kiểu kỳ báo cáo. Không ghi nhận tràn toàn trang, giá trị undefined/NaN hoặc lỗi JavaScript chưa xử lý. Đã xem ảnh giao diện desktop/mobile và ảnh trước/sau lỗi BOM.
- Luồng UI trên QA chạy đủ nhập nguyên liệu có hàng lỗi → giao/nhận việc → gợi ý cấp và duyệt → ghi/tiếp nhận kết quả → xuất thành phẩm. Tồn cuối CPU 14, RAM 28 gồm 4 lỗi, PC đạt 2 và PC lỗi 2; không trừ linh kiện lần hai, báo cáo/CSV khớp và giữ đơn vị **cái**.
- Kiểm tra cú pháp 17 file Python và JavaScript đạt; 11 liên kết tài liệu nội bộ đều trỏ tới file hiện có; `git diff --check` không có lỗi khoảng trắng.

### Dọn dẹp và bảo toàn

Source không có cache Python hoặc dependency đã cài cần xóa. Giữ các test hồi quy, fixture, PRD, schema tham chiếu, hai backup và bốn file rollback cần thiết. Cập nhật README từ số test cũ lên 106 Python/277 DOM; hướng dẫn MRP trỏ tới PRD hiện có và bỏ mô tả các file thiết kế cũ không còn trong repository. Không sửa Word PRD hoặc làm hồ sơ bàn giao.

Lượt test đang chạy được dừng khi cần sửa R4-01, rồi chạy lại với mã mới; CSDL của lượt bị dừng và 27 mục quyền tương ứng đã được dọn trước khi chạy lại. Cuối lượt đã dừng đúng QA cổng 8766, xóa CSDL/metadata QA và thu hồi 27 mục quyền; không còn quyền test dư. Hai thư mục script/dependency TEMP được dọn sau khi lưu bằng chứng. Folder BT không được truy cập, không commit/push.

Đối chiếu cuối: dấu dữ liệu đủ **17 bảng**, tên **4 view/16 routine/19 trigger**, định nghĩa **19 trigger**, danh sách CSDL/quyền ứng dụng, hash **hai backup và bốn file rollback**, cùng danh sách metadata HTTP đều khớp mốc trước kiểm thử. App chính đã khởi động lại để nhận backend mới, vẫn trả HTTP 200 tại `http://127.0.0.1:8765`; JavaScript/CSS đang phục vụ khớp source.

Bằng chứng lưu ngoài project tại `C:/Users/AD/.codex/visualizations/2026/10/10/01a125cb-7959-7423-9f55-c7cdd9b84b25/cnpm-clean-retest-20261011/`: `final-verification.json`, baseline, log đầy đủ cùng log cleanup chạy lại, hồi quy mới, DOM, kết quả Edge, kiểm tra liên kết và ảnh trước/sau. Không lưu mật khẩu hoặc cookie trong bằng chứng.

## Khắc phục R3-01/R3-02 — 11/10/2026

**Đã sửa cả hai lỗi phục hồi giao diện** và kiểm chứng trên Edge thật. Các mô tả R3 ở lượt kiểm thử bên dưới được giữ để đối chiếu tình trạng trước sửa.

| Vấn đề | Bản sửa |
|---|---|
| R3-01: đóng tab đang đăng nhập làm tab khác kẹt | Khi nhận thông báo bắt đầu, tab còn lại chờ Web Lock rồi đọc lại phiên; không phụ thuộc thông báo hoàn tất từ tab đã đóng. Mỗi thao tác đang chờ đều được đếm, nên nút chỉ mở khi các lượt đồng bộ đã kết thúc. Đọc phiên thất bại cũng giải phóng trạng thái chờ và hiển thị lỗi tiếng Việt. |
| R3-02: thử lưu lại bị 400 nhưng form vẫn khóa | API giữ mã HTTP trong lỗi. Lỗi nhập liệu 400 xác nhận chưa lưu sẽ xóa trạng thái chưa xác định, mở lại các ô theo trạng thái ban đầu và cho lưu dữ liệu đã sửa bằng mã thao tác mới. Chỉ hiển thị lỗi nhập liệu rõ ràng. |
| An toàn khi kết quả chưa rõ | Lỗi mạng, phản hồi không đọc được hoặc HTTP 5xx giữ nguyên payload/mã thao tác và nút Thử lại lưu. Giữ trạng thái vô hiệu hóa ban đầu của các ô qua nhiều lần thử; các ô bị khóa tạm sẽ mở đúng khi đã có kết quả xác định. Trường hợp đã xác nhận POST thành công nhưng GET danh sách thất bại vẫn chỉ tải lại dữ liệu. |

### Kiểm chứng bản sửa R3

- Hai ca hồi quy mới đều **thất bại đúng tại lỗi trước sửa**, rồi đạt sau sửa: đóng tab chủ mà không có thông báo hoàn tất; thử lưu lại nhận 400 rồi sửa số lượng.
- **266/266 kiểm tra DOM đạt**, gồm toàn bộ 233 kiểm tra cũ và **33 kiểm tra phục hồi mới** trong `test_recovery_frontend.cjs`; đã thêm vào `npm test`. Bao phủ nhiều lượt đồng bộ đang chờ, đọc phiên lỗi, sửa form sau 400, giữ ô vốn đã vô hiệu hóa, HTTP 500/409, phản hồi lỗi định dạng và giữ đúng mã/dữ liệu khi thử lại.
- **4/4 test MySQL liên quan đạt**, **34,210 giây**: thu hồi cookie/đổi tài khoản, lưu lại đủ năm loại chứng từ sau khởi động lại hoặc đổi trạng thái, phục hồi cả COMMIT và rollback. Lượt sửa chỉ thay JavaScript, test và tài liệu; không chạy lại toàn bộ 105 test Python. Kết quả 105 test của lượt kiểm thử ngay trước sửa được ghi bên dưới.
- **67/67 kiểm tra Edge thật đạt**: đóng tab giữ phản hồi login; đọc phiên thất bại sau khi đóng tab; tiếp tục đăng nhập mà không tải lại; đăng nhập/đăng xuất đồng bộ ba tab; bootstrap bị giữ; cookie đã thu hồi trả 401.
- Edge kiểm chứng mất mạng → thử lại nhận **400 thật từ backend** → sửa số lỗi → lưu thành công **đúng một phiếu** với mã thao tác mới. Sau khi server đã COMMIT, mô phỏng mất phản hồi hoặc phản hồi 500: thử lại trả đúng ID cũ và vẫn chỉ có một phiếu. Lưu nháp không đổi tồn. POST đã xác nhận rồi GET danh sách lỗi không gửi thêm POST khi tải lại.
- Mở đủ năm form ở 320/390/768/1440 px; kiểm tra vùng nút thao tác, xem ảnh desktop/mobile. Không ghi nhận lỗi JavaScript chưa xử lý. App chính đọc được workspace quản lý và đơn vị **cái**.

Đối chiếu cuối: dữ liệu đủ **17 bảng**, tên **4 view/16 routine/19 trigger**, định nghĩa **19 trigger**, quyền ứng dụng, danh sách CSDL, backup và danh sách metadata HTTP giữ nguyên. App chính `http://127.0.0.1:8765` vẫn trả HTTP 200; JavaScript/CSS đang phục vụ khớp source. Người dùng tải lại trang đang mở để nhận JavaScript mới. Không cần migration DB.

Server QA cổng 8766 đã dừng; CSDL và metadata QA được xóa, **27 mục quyền** được thu hồi; không còn quyền test dư. Hai thư mục script/dependency TEMP được dọn sau khi lưu bằng chứng. Không truy cập folder BT, không commit/push.

Bằng chứng: `C:/Users/AD/.codex/visualizations/2026/10/10/01a125cb-7959-7423-9f55-c7cdd9b84b25/cnpm-r3-fixes-20261011/`, gồm `baseline-audit.json`, `final-verification.json`, log DOM/Python, `edge-results.json` và ba ảnh Edge. Không lưu mật khẩu/cookie trong bằng chứng.

## Kiểm thử lại sau bản sửa R2 — 11/10/2026

**Các bộ kiểm thử hiện có đạt, nhưng còn hai lỗi giao diện mới đã tái hiện trên Edge thật.** Lượt này kiểm thử và ghi báo cáo; chưa sửa R3-01/R3-02. Kết quả đạt của các ca cũ không đồng nghĩa mọi tình huống biên đã được bao phủ.

### Kết quả chạy lại

- **105/105 test Python đạt**, chạy toàn bộ trong **790,933 giây** trên MySQL thật. Bao gồm AT01–AT12, phân quyền/CSRF, giao dịch và rollback, cạnh tranh tồn, BOM snapshot, kết quả từng phần, khóa nội dung, phiên đăng nhập, chống tạo trùng, báo cáo và sao lưu/khôi phục.
- **233/233 kiểm tra DOM đạt**: 92 + 37 + 42 + 62.
- **242 kiểm tra đối chứng trên Edge thật đạt**: 27 kiểm tra quy trình nghiệp vụ; 165 kiểm tra trang/bố cục/phiên bình thường; 43 kiểm tra điều khiển nhỏ; bảy kiểm tra đối chứng đi kèm hai ca lỗi mới. Hai ca lỗi mới được ghi riêng bên dưới, không tính là đạt.
- Mở **117 tổ hợp trang/tài khoản/kích thước** trên app chính: 39 tổ hợp trang của bốn tài khoản, ở 320/768/1440 px. Kiểm tra quyền hiển thị, tiêu đề, giá trị render và tràn ngang toàn trang. Bảng rộng cuộn trong vùng bảng. Kiểm tra đóng/mở sidebar, Escape, trả focus và giữ lựa chọn thu gọn sau tải lại.
- Đủ năm form chứng từ trên CSDL QA được mở ở **320/390/768/1440 px**; dialog và vùng nút thao tác nằm trong viewport. Đã xem ảnh desktop/mobile, chụp ảnh mobile sau khi sidebar kết thúc chuyển động.
- Kiểm tra năm tab danh mục, form tạo/sửa danh mục, tìm kiếm không có kết quả, xóa từ khóa, lọc loại sản phẩm, form tạo/sửa tài khoản; chỉ mở form, không lưu lên dữ liệu chính. Báo cáo tháng/quý/năm/tùy chọn đều trả kết quả; khoảng ngày đảo ngược bị từ chối và hiển thị thông báo tiếng Việt.
- Luồng QA thao tác qua UI: nhập CPU/RAM có hàng lỗi → giao việc ba PC → nhận việc → gợi ý cấp → gửi/duyệt cấp → gửi/tiếp nhận hai PC đạt và một PC lỗi → gửi/duyệt xuất một PC đạt. Lưu nháp không đổi tồn; tiếp nhận kết quả không trừ nguyên liệu lần hai; yêu cầu hoàn thành và sinh phiếu nhập nội bộ. Tồn cuối và báo cáo khớp, CSV giữ BOM UTF-8 và đơn vị **cái**.
- Không ghi nhận lỗi JavaScript chưa xử lý trong các lượt Edge. Đăng nhập/đăng xuất nhiều tab theo luồng bình thường đồng bộ đúng; sau đăng xuất API dữ liệu trả 401.

### R3-01 — P2: đóng tab đang đăng nhập làm tab còn lại kẹt nút Đăng nhập

**Tái hiện:** mở hai tab chưa đăng nhập trong cùng browser context. Ở tab A, đăng nhập và giữ phản hồi POST sau khi server đã trả 200. Tab B nhận sự kiện bắt đầu nên khóa nút Đăng nhập. Đóng tab A trước khi phản hồi được áp dụng. Web Lock đã được giải phóng, nhưng tab B vẫn giữ `loginPending=true` và nút bị vô hiệu hóa; chỉ tải lại tab B mới dùng được.

**Nguyên nhân:** `app/static/app.js:10–26` chỉ mở khóa tab nhận khi có sự kiện `done`. Tab chủ đóng giữa thao tác không chạy được thông báo trong `finally`, trong khi tab nhận không có cơ chế tự phục hồi khi khóa được giải phóng. Đã kiểm chứng tab B lấy lại được Web Lock nhưng nút vẫn bị khóa. Không tái hiện việc phục hồi quyền của cookie đã thu hồi trong ca này.

**Hướng sửa:** cho tab nhận chờ Web Lock rồi đọc lại phiên và kết thúc trạng thái chờ, kể cả khi không nhận `done`; xử lý tab chủ bị đóng hoặc lỗi. Bổ sung hồi quy hai tab với phản hồi login bị giữ và tab chủ đóng. Cách phục hồi hiện tại: tải lại tab bị kẹt.

### R3-02 — P2: thử lưu lại gặp lỗi nhập liệu rõ ràng nhưng form vẫn bị khóa

**Tái hiện:** tạo phiếu nhập với thực nhận 1, số lỗi 2; cắt kết nối ở lần lưu đầu trước khi gửi tới server. Form chuyển sang **Thử lại lưu** và khóa dữ liệu. Cho lần thử lại đi tới server: nhận HTTP 400, **Số lỗi không được lớn hơn số thực nhận.** Form vẫn giữ trạng thái chưa xác định, khóa các ô và nút **Thử lại lưu**, nên không sửa được số lượng trên form đang mở.

**Nguyên nhân:** `app/static/app.js:54–61,366–371` không giữ mã HTTP trong lỗi API và không xóa `dataset.uncertain` khi lần thử lại nhận một từ chối xác định. Thông báo đồng thời nói kết quả chưa rõ và đưa lỗi nhập liệu, gây khó hiểu. Đã đối chiếu không có phiếu mới và tồn kho không thay đổi trong phép thử.

**Hướng sửa:** phân biệt lỗi mạng/kết quả còn mơ hồ với lỗi nhập liệu xác nhận chưa lưu; cho sửa form sau từ chối xác định và quản lý lại mã thao tác/payload phù hợp. Giữ cơ chế chống tạo trùng khi mất phản hồi hoặc chưa rõ kết quả. Bổ sung hồi quy mất mạng → thử lại bị 400 → sửa số lượng → lưu thành công một phiếu. Hiện người dùng phải đóng form và nhập lại sau khi kiểm tra phiếu chưa được tạo.

### Bảo toàn dữ liệu và bằng chứng

Đối chiếu sau kiểm thử: dấu dữ liệu đủ **17 bảng**, tên **4 view/16 routine/19 trigger**, định nghĩa của toàn bộ **19 trigger**, quyền ứng dụng, danh sách CSDL, hai file backup và danh sách metadata HTTP đều khớp trước kiểm thử. App chính tại `http://127.0.0.1:8765` vẫn trả HTTP 200; JavaScript và CSS đang phục vụ khớp source. Folder BT không được truy cập.

Đã dừng đúng server QA cổng 8766, xóa CSDL QA, thu hồi **27 mục quyền**, xóa metadata QA; không còn quyền test dư. Các script và dependency của lượt kiểm thử nằm trong TEMP và được dọn sau khi lưu bằng chứng. Không sửa mã nghiệp vụ hoặc dữ liệu chính trong lượt này.

Bằng chứng lưu ngoài project tại `C:/Users/AD/.codex/visualizations/2026/10/10/01a125cb-7959-7423-9f55-c7cdd9b84b25/cnpm-retest-r3-20261011/`: `final-audit.json`, log Python/DOM, bốn file kết quả Edge và ảnh giao diện/lỗi. Không lưu mật khẩu hoặc cookie trong bằng chứng.

## Khắc phục R2-01–R2-03 — 11/10/2026

Đã sửa ba nhóm vấn đề của lượt rà soát sau QA-01–QA-04 và áp dụng lên app chính tại `http://127.0.0.1:8765`. Các mục R2 bên dưới giữ nguyên mô tả lỗi trước sửa để đối chiếu.

| Vấn đề | Bản sửa |
|---|---|
| R2-01: cookie cũ và phiên nhiều tab | Cookie chỉ chứa mã phiên ký; dữ liệu phiên nằm ở server và bị thu hồi khi đăng xuất/đổi tài khoản. Login xoay mã phiên; bản ghi có phiên bản để phản hồi cũ không phục hồi phiên đã thu hồi. Edge trên localhost dùng Web Locks để tuần tự hóa bootstrap/login/logout giữa các tab, rồi thông báo để các tab đồng bộ tài khoản và xóa dữ liệu cũ. |
| R2-02: thử lưu lại tạo phiếu trùng | Mỗi form mới giữ một `Idempotency-Key`. Backend khóa thao tác theo CSDL/tài khoản/loại chứng từ/mã, lưu kết quả bền vững và trả lại ID cũ khi thử lại. Khôi phục được khi dừng giữa ghi metadata và COMMIT; chặn cùng mã nhưng dữ liệu khác hoặc phiếu đã xóa. |
| R2-02: thông báo lỗi mạng | Thông báo tiếng Việt giải thích kết quả lưu chưa xác định, nút **Thử lại lưu** gửi lại đúng dữ liệu/mã ban đầu. Form giữ dữ liệu, chặn sửa trong lúc kết quả chưa rõ. POST đã xác nhận nhưng GET danh sách lỗi vẫn chỉ **Tải lại dữ liệu**. Form cuộn phần nội dung, giữ nút thao tác và đưa thông báo lỗi vào vùng nhìn thấy. |
| R2-03: khóa nội dung DB | So sánh theo byte cho `PHIEU_XUAT.TenNguoiNhan` và `BOM.TenCauHinh`; khóa `YEU_CAU_LAP_RAP.HanMongMuon` khi đã giao. Migration chỉ thay ba trigger, có bản rollback và phục hồi toàn bộ trigger đã thay nếu cập nhật thất bại. |

Metadata phiên/mã thao tác nằm trong SQLite có sẵn của Python ở runtime ngoài repository, tách riêng mỗi CSDL; schema MySQL vẫn gồm 17 bảng nghiệp vụ. Giữ metadata qua các lần khởi động. Cookie phiên của bản cũ cần đăng nhập lại sau nâng cấp.

### Kiểm chứng R2

- **105/105 test Python đạt** khi chạy toàn bộ bộ kiểm thử trên MySQL thật, trong **1.237,702 giây**; gồm đủ AT01–AT12, phân quyền/CSRF, luồng nhập/lắp ráp/xuất, cạnh tranh, báo cáo, sao lưu/khôi phục, cleanup và 11 hồi quy R2. Ca thử lại mở rộng sau đó được chạy riêng như ghi dưới đây.
- **11/11 hồi quy mới đạt** trên MySQL thật trong **83,808 giây**: thu hồi cookie, đổi tài khoản, hết hạn ở server, khởi động lại, chặn ghi lại phiên cũ, thử lưu lại/cạnh tranh, phục hồi lưu chưa xác nhận, phiếu đã xóa và nâng cấp trigger có rollback.
- Ca thử lưu lại đã được mở rộng cho **đủ năm loại chứng từ**, tách phạm vi theo tài khoản/loại phiếu và thử lại sau ban hành/giao việc/tiếp nhận; chạy lại riêng đạt trong **36,828 giây**.
- **233/233 kiểm tra DOM đạt**: 92 + 37 + 42 + 62. Mười kiểm tra mới xác nhận mất phản hồi giữ nguyên mã thao tác/dữ liệu, thông báo Việt hóa, khóa nội dung form và thử lại thành công.
- **156/156 kiểm tra Edge thật đạt**: 23 kiểm tra phiên/lưu chậm, 88 kiểm tra trên app chính và 45 kiểm tra bố cục form. Xác nhận khóa thao tác giữa hai tab khi giữ phản hồi login/bootstrap, đồng bộ đổi tài khoản/đăng xuất, từ chối cookie cũ, chỉ có một phiếu sau hai lần lưu và tải lại danh sách không gửi lại POST. App chính đã mở **39 tổ hợp trang/tài khoản** của bốn tài khoản mà không sửa chứng từ. Đủ năm form và chi tiết chứng từ được kiểm tra ở 320/390/768/1440 px; thông báo lỗi và nút thao tác không che nhau. Không ghi nhận lỗi JavaScript chưa xử lý; đã xem ảnh desktop/mobile.
- **9/9 cập nhật trái trạng thái trên DB chính bị chặn** bằng lỗi 1644. Mọi phép thử đều rollback và đối chiếu lại dấu dữ liệu của đủ 17 bảng.

Trước áp dụng đã tạo backup có kiểm chứng `app/backups/mrp_20261011_135246_a05b57.sql`. Migration chỉ thay `trg_phieu_xuat_freeze`, `trg_bom_freeze`, `trg_yeu_cau_lap_rap_freeze`; chạy lại không đổi gì. Dữ liệu 17 bảng và quyền CSDL chính khớp trước sửa; các định nghĩa cũ được giữ trong `<runtime>/migrations/`.

Đối chiếu cuối xác nhận dữ liệu đủ 17 bảng, số lượng 4 view/16 routine/19 trigger, danh sách CSDL và quyền ứng dụng giữ nguyên; backup cũ được giữ cùng backup mới. Backend QA cổng 8766 đã dừng, CSDL QA bị xóa và 27 mục quyền tương ứng được thu hồi. Không còn CSDL/quyền test dư hoặc metadata HTTP tạm; hai thư mục script/dependency trong TEMP đã dọn. Chỉ giữ metadata HTTP của app chính ở runtime. App chính vẫn trả HTTP 200, JavaScript và CSS đang phục vụ khớp source.

Bằng chứng của bản sửa lưu ngoài project tại `C:/Users/AD/.codex/visualizations/2026/10/10/01a125cb-7959-7423-9f55-c7cdd9b84b25/cnpm-r2-fixes-20261011/`, gồm `final-verification.json`, kết quả Python/DOM/Edge, migration và ảnh Edge. Không lưu mật khẩu hoặc cookie. Folder BT không thuộc phạm vi sửa/kiểm thử.

## Rà soát sau bản sửa QA-01–QA-04 — 11/10/2026

**Còn ba nhóm vấn đề mới đã tái hiện**, gồm một lỗi phiên ở nhiều tab, tạo phiếu trùng khi mất phản hồi lưu và khóa nội dung DB chưa đầy đủ. Có thêm thông báo lỗi mạng chưa Việt hóa trong nhóm lưu phiếu. Lượt này rà soát và ghi báo cáo, chưa sửa các vấn đề mới.

### Phạm vi chạy lại

- **21/21 test Python đạt**, 257,145 giây: AT01–AT12 và chín hồi quy QA-01–QA-04 trên MySQL thật. Không chạy lại toàn bộ 94 test trong lượt này; kết quả 94 test ở phần trước vẫn là kết quả của lượt sửa.
- **223/223 kiểm tra DOM đạt**. Các test hiện có chưa bao phủ những tình huống mới dưới đây.
- Edge thật: ba ca mới tái hiện lỗi, cùng mười kiểm tra đối chứng đạt; không ghi nhận lỗi JavaScript chưa xử lý. Đã kiểm chứng trường hợp POST được xác nhận rồi GET danh sách thất bại vẫn chỉ tải lại, không tạo thêm phiếu.
- Tám phép thử khóa nội dung bằng `mrp_app`: ghi chú ở ba bảng đã khóa đúng; năm cập nhật thử trên ba trường khác còn lọt. Tất cả cập nhật SQL thử đã rollback và đối chiếu lại dữ liệu QA. Ba API sửa chứng từ tương ứng đều chặn bằng HTTP 409.

### R2-01 — P1: phản hồi đăng nhập ở tab cũ ghi đè phiên của tab mới

Mở hai tab cùng một browser context. Tab A đăng nhập Admin, giữ phản hồi POST `/api/login` sau khi server đã xử lý. Tab B đăng nhập `nhanvien`; `/api/session` xác nhận `NHAN_VIEN`. Thả phản hồi Admin của tab A: cookie chung quay về `ADMIN`, tab A hiển thị Admin, trong khi tab B vẫn hiển thị nhân viên. Đã tái hiện bằng cookie thật trên Edge, không sửa nội dung phản hồi.

Biến thể thứ hai: giữ phản hồi GET `/api/session` của tab chưa đăng nhập, đăng nhập Admin thành công ở tab khác, rồi thả phản hồi bootstrap cũ. Phiên Admin bị thay bằng phiên chưa đăng nhập. Biện pháp chặn bootstrap trong một tab không đồng bộ được các tab khác.

Kiểm tra backend bổ sung: sao chép cookie vào bộ nhớ, đăng xuất thành công, rồi dùng cookie cũ ở một client khác vẫn đọc được `/api/state` với HTTP 200 và vai trò quản lý. Không lưu giá trị cookie vào bằng chứng.

Nguồn: `app/server.py:226,253–260` tạo/xóa cookie phía client; server chưa có trạng thái thu hồi phiên. `authVersion` trong `app/static/app.js` chỉ thuộc từng trang. Việc bỏ phản hồi đọc cũ trong cùng tab đã hoạt động đúng nhưng chưa giải quyết các phản hồi thay cookie giữa nhiều tab.

Hướng sửa: quản lý và thu hồi phiên ở server, phối hợp thay đổi đăng nhập giữa các tab; bổ sung hồi quy cả cookie và giao diện. Chỉ bỏ qua JSON cũ bằng JavaScript không ngăn trình duyệt áp dụng `Set-Cookie`.

### R2-02 — P2: lưu lại sau mất phản hồi POST tạo hai phiếu nháp

Quản lý tạo phiếu nhập. Cho POST `/api/documents/incoming` chạy tới server và lưu thành công PN-4, sau đó cắt phản hồi tới trình duyệt. Form hiển thị lỗi, vẫn cho bấm **Lưu nháp**. Bấm lại tạo PN-5 có cùng dữ liệu, thay vì nhận lại PN-4. Đã đối chiếu hai ID và cùng ghi chú/dòng hàng trên CSDL QA. Cả hai vẫn là nháp nên tồn chưa bị thay đổi trong phép thử.

Nguồn: `app/static/app.js:344–345` chỉ đặt `form.dataset.saved` sau khi đã nhận phản hồi POST; khi phản hồi mất, lần bấm tiếp theo gửi POST mới. Endpoint tạo chứng từ ở `app/server.py:371–406` chưa có mã thao tác để nhận diện lần thử lại.

Form còn đưa nguyên thông báo tiếng Anh **Failed to fetch** cho người dùng, chưa khớp yêu cầu thông báo rõ ràng của FR13. Đây là lỗi hiển thị mức P3 trong cùng tình huống.

Hướng sửa: cấp mã thao tác cho mỗi lần tạo mới và giữ lại qua các lần thử lại, để backend trả về chứng từ đã tạo; Việt hóa thông báo mất kết nối và nêu rõ khi chưa xác định được kết quả lưu. Cần giữ riêng trường hợp POST đã được xác nhận nhưng GET danh sách thất bại: cơ chế **Tải lại dữ liệu** hiện tại đã hoạt động đúng, không gửi lại POST.

### R2-03 — P2: ba trường nội dung khác vẫn sửa được ở DB sau khi khóa

| Đối tượng QA | Trường | Phép thử còn được chấp nhận |
|---|---|---|
| PX-2 đã thực hiện | `TenNguoiNhan` | Thêm dấu hoặc đổi toàn bộ sang chữ hoa |
| BOM-1 đang áp dụng | `TenCauHinh` | Thêm dấu hoặc đổi toàn bộ sang chữ hoa |
| YC-1 hoàn thành | `HanMongMuon` | Đổi từ NULL thành `2030-01-01 12:00:00` |

Hai trường tên dùng `<=>` theo collation không phân biệt dấu/hoa/thường, nên trigger không phát hiện thay đổi. Trigger yêu cầu chưa so sánh `HanMongMuon`. Tài khoản ứng dụng có quyền UPDATE các cột này. API đã chặn đúng bằng HTTP 409; lỗi nằm ở tầng DB, tương tự khoảng trống ghi chú đã sửa trước đó.

Nguồn: `docs/mrp/schema_MRP_HTTTDN_17_bang.sql:626,629,632`; phạm vi quyền ở `app/manage.py:145–157`. Chưa khớp bất biến khóa nội dung chứng từ đã gửi/chốt trong mục 5 của PRD. Tất cả năm cập nhật thử đã rollback, không sửa dữ liệu chính.

Hướng sửa: so sánh theo byte cho hai trường tên, khóa thêm hạn mong muốn sau khi giao; migration đúng các trigger liên quan và giữ các chuyển trạng thái nghiệp vụ hợp lệ.

Bằng chứng của lượt này lưu ngoài project tại `C:/Users/AD/.codex/visualizations/2026/10/10/01a125cb-7959-7423-9f55-c7cdd9b84b25/cnpm-review-afterfix-20261011/`, gồm kết quả JSON và ảnh Edge. Không lưu mật khẩu hoặc cookie.

Đối chiếu sau rà soát: dữ liệu đủ **17 bảng**, danh sách 4 view/16 routine/19 trigger, quyền ứng dụng, danh sách CSDL và các file backup khớp trước kiểm thử. Đã dừng backend QA cổng 8766, xóa đúng CSDL QA, thu hồi 27 mục quyền và dọn hai thư mục script/dependency tạm; không còn quyền test dư. App chính cổng 8765 vẫn trả HTTP 200, JavaScript đang phục vụ khớp source. Folder BT không được truy cập. Kết quả bảo toàn và cleanup nằm trong `final-audit.json` cùng thư mục bằng chứng.

## Khắc phục QA-01–QA-04 — 11/10/2026

Đã sửa cả bốn nhóm vấn đề của lượt rà soát gần nhất và áp dụng lên app chính tại `http://127.0.0.1:8765`.

| Vấn đề | Bản sửa |
|---|---|
| QA-01: phản hồi cũ phục hồi tài khoản trước | Theo dõi thế hệ đăng nhập và lượt tải; bỏ thành công/lỗi thuộc phiên cũ, giữ lượt tải mới nhất. Chặn đăng nhập lặp và đăng nhập trước khi bootstrap hoàn tất. Backend không gia hạn cookie trên request đọc; phản hồi 401 không xóa cookie của một lần đăng nhập mới. |
| QA-02: ghi chú đã gửi/chốt còn sửa được qua DB | Cập nhật đúng ba trigger bằng migration có rollback. So sánh ghi chú theo byte để chặn cả đổi hoa/thường, bỏ dấu, thêm khoảng trắng hoặc đổi NULL/rỗng. Nháp vẫn sửa được; procedure từ chối kết quả vẫn ghi lý do khi chuyển sang `TU_CHOI`. |
| QA-03: đếm dư vị trí hàng lỗi | Đếm `MaViTri` khác nhau sau khi lọc tồn lỗi; nhiều SKU lỗi cùng vị trí chỉ tính một lần, tồn trống cho kết quả 0. |
| QA-04: sáu nhãn mẫu thiếu dấu | Sửa seed, fixture và runtime hiện có. Migration chỉ đổi đúng ID và chuỗi cũ khớp theo byte; giữ nguyên tên riêng, biến thể hoa/thường và nhãn trùng ở ID khác. |

### Kiểm chứng bản sửa

- **94/94 test Python đạt** khi chạy toàn bộ bộ kiểm thử trên MySQL thật, trong **1.104,586 giây**; gồm AT01–AT12, cạnh tranh, rollback, phân quyền, sao lưu/khôi phục và cleanup. Riêng chín hồi quy mới được chạy lại sau điều chỉnh khóa ghi chú cuối cùng như ghi dưới đây.
- **9/9 hồi quy Python mới đạt** trên MySQL thật; chạy lại sau khi bổ sung so sánh ghi chú theo byte đạt trong **93,316 giây**. Có kiểm tra cập nhật trigger cũ, chạy lặp, khôi phục toàn bộ trigger đã thay khi CREATE thất bại và bảo toàn dữ liệu khi migration.
- **223/223 kiểm tra DOM đạt**: 92 + 37 + 42 + 52. Bộ mới kiểm tra phản hồi thành công/401/lỗi mạng đến sau đăng xuất hoặc đổi tài khoản, tải đảo thứ tự, lưu form cũ, gửi đăng nhập lặp và đếm vị trí hàng lỗi.
- **207/207 kiểm tra Edge thật đạt**: 186 kiểm tra hồi quy và 21 kiểm tra bổ sung sau cập nhật trigger cuối. Gồm 93 tổ hợp trang/vai trò/chiều rộng ở 320/768/1440 px, sidebar, nhãn có dấu, bootstrap chậm, phản hồi đọc chậm, nhập nháp/sửa/chốt, cấp vật liệu, kết quả từ chối/lập lại/tiếp nhận, xuất từ chối/duyệt và CSV UTF-8. Không ghi nhận lỗi JavaScript chưa xử lý; đã xem ảnh desktop và mobile.
- Trường hợp 401 bổ sung dùng phản hồi thật sau đổi mật khẩu: giữ phản hồi cũ, đăng nhập nhân viên, mở form mới rồi thả phản hồi. Cookie, dữ liệu nhân viên và form mới giữ nguyên. Phản hồi thành công/401 đọc dữ liệu không mang `Set-Cookie`.

Migration chính chỉ sửa sáu nhãn trong ba bảng `NHAN_VIEN`, `LOAI_SAN_PHAM`, `VI_TRI_KHO`; dấu dữ liệu của 17 bảng khớp kết quả dự kiến chỉ có sáu sửa đổi này. Số lượng, chứng từ, lịch sử và mật khẩu được giữ nguyên. Chỉ ba trigger khóa ghi chú được cập nhật; chạy lại migration không thay đổi gì. Định nghĩa cũ được giữ trong `.mrp-runtime/migrations/`.

Đã dừng backend QA cổng 8766, xóa đúng CSDL QA và thu hồi 27 mục quyền của nó. Danh sách CSDL, quyền và backup khớp trước sửa; không còn CSDL tạm hoặc quyền test dư. Script và dependency kiểm thử tạm đã dọn ngoài project. App chính vẫn chạy, JavaScript đang phục vụ khớp source, folder BT giữ nguyên.

Bằng chứng của bản sửa ở `C:/Users/AD/.codex/visualizations/2026/10/10/01a125cb-7959-7423-9f55-c7cdd9b84b25/cnpm-fixes-20261011/`: `final-verification.json`, `edge-results.json`, `edge-final-guard.json`, ảnh phiên nhân viên sau phản hồi Admin cũ, thống kê vị trí lỗi và giao diện mobile. Không lưu mật khẩu hoặc cookie trong bằng chứng.

Các phần bên dưới lưu lịch sử các lượt rà soát trước bản sửa này.

## Kiểm thử nghiệp vụ

**81/81 test Python đạt** trong lần rà soát đầy đủ (954,528 giây). Ca số lượng không hữu hạn được mở rộng và chạy lại riêng đạt.

| Bộ kiểm thử | Số test |
|---|---:|
| `test_integration.py` — luồng nghiệp vụ, quyền DB, ledger | 22 |
| `test_lifecycle.py` — nhận diện và dừng đúng tiến trình | 6 |
| `test_regressions.py` — hồi quy, backup, phiên và quyền | 14 |
| `test_prd_fixes.py` — đồng bộ, thiếu tồn và migration | 5 |
| `test_audit_edges.py` — số, ngày, phiên, cạnh tranh và CSV | 9 |
| `test_prd_acceptance.py` — AT01–AT12 của PRD | 12 |
| `test_sidecases.py` — giới hạn, phân bổ và cạnh tranh | 13 |
| **Tổng** | **81** |

Các test nghiệp vụ sử dụng CSDL tạm, không reset dữ liệu chính. Sao lưu/khôi phục đã đối chiếu dữ liệu, 17 bảng, 4 view, 16 routine, 19 trigger và chạy giao dịch kiểm chứng trên CSDL khôi phục.

## Giao diện

**153 kiểm tra DOM đạt**: 74 trong `test_frontend.cjs`, 37 trong `test_prd_frontend.cjs`, 42 trong `test_audit_frontend.cjs`. Fixture mẫu nằm trong `tests/fixtures/state.json`; chạy bằng `npm install` rồi `npm test` tại `app`.

Lần rà soát trên Edge thật đạt 75 kịch bản nghiệp vụ/UI, thêm 7 assertion lưu chậm và 7 kiểm tra trên app chính. Đã kiểm tra 31 trang theo vai trò ở 320/360/390/768/1024/1440 px (186 tổ hợp) và 38 bố cục bổ sung cho biểu mẫu, chi tiết, dữ liệu trống và tên dài. Không ghi nhận lỗi JavaScript chưa xử lý trong các ca cuối.

Sau yêu cầu đổi đơn vị/sidebar: 21 kịch bản Edge bổ sung đạt, gồm đơn vị và CSV trên hai app, ba vai trò ở sáu chiều rộng và kiểm tra lỗi JavaScript. Đã xác nhận nút bật/tắt, ghi nhớ sidebar trên desktop, Escape/nền mờ/nút đóng trên điện thoại, focus bàn phím và cuộn menu khi ẩn thanh cuộn.

## Bảo toàn dữ liệu

Đã đối chiếu đủ 17 bảng trước/sau các lần kiểm thử. Thay đổi dữ liệu chính được yêu cầu gần nhất chỉ đổi `DonViTinh` từ `cai` thành `cái` ở ba sản phẩm; các trường khác, tồn kho, chứng từ và lịch sử giữ nguyên. Chuyển đổi chạy lại không phát sinh cập nhật.

Runtime CNPM ở `../.mrp-runtime`, bên ngoài repository. Giữ backup của CSDL chính trong `app/backups` và SQL rollback migration trong runtime. Folder BT không thuộc phạm vi kiểm tra hoặc dọn dẹp.

## Dọn workspace

Đã gom các bài kiểm thử có thể chạy lại vào project, kèm fixture DOM. Các script khảo sát/chạy thử một lần, ảnh chụp, profile trình duyệt, log QA và dependency cài tạm được loại khỏi workspace. Tài liệu MRP trùng được gom vào `docs/mrp`; bản SQL gốc khác schema hiện hành được giữ trong `docs/mrp/reference`.

Các con số kiểm thử đầy đủ ở trên là kết quả lượt rà soát trước khi dọn workspace. Kiểm tra sau khi dọn được ghi riêng dưới đây, không coi là chạy lại toàn bộ 81 test.

## Kiểm tra sau khi dọn ngày 11/10/2026

- Python nhận đủ 81 test, không lỗi import. Chạy lại 6 test vòng đời và 2 test chọn lọc từ bộ PRD/sidecase vừa chuyển vào project: **8/8 đạt**.
- `npm test` với fixture có sẵn: **153/153 kiểm tra DOM đạt**.
- Đối chiếu hash: 17 file ứng dụng/kiểm thử không thuộc phần cập nhật tài liệu, fixture và lệnh test giữ nguyên; các file Python qua kiểm tra cú pháp.
- Dữ liệu đủ 17 bảng khớp dấu đối chiếu trước khi dọn; không còn CSDL test/khôi phục tạm. Cả bốn tài khoản đăng nhập và đọc dữ liệu trên app chính thành công.
- App chính tiếp tục chạy tại `http://127.0.0.1:8765`. Đã xóa 2.455 file dư, giải phóng khoảng 62 MiB; giữ runtime, backup chính và folder BT.

## Đối chiếu lại PRD sau khi dọn workspace — cập nhật sau sửa 11/10/2026

Căn cứ: `docs/mrp/PRD_MRP_HTTTDN_17_bang.docx`, phiên bản 1.0. Đánh giá phần mềm đang có; hồ sơ bàn giao/báo cáo môn được loại khỏi phạm vi theo yêu cầu của người dùng.

**Hai tồn đọng được phát hiện đã xử lý:** tìm kiếm FR02 loại cột thao tác; quyền CSDL test cũ đã dọn và cleanup tự thu hồi quyền cho các lượt mới. Các luồng nghiệp vụ MRP và 12 tiêu chí nghiệm thu đã đạt trong lượt đối chiếu trước sửa.

| Yêu cầu | Đối chiếu hiện tại |
|---|---|
| FR01 — đăng nhập, vai trò và sở hữu | Khớp; kiểm tra lại quyền endpoint, CSRF và đổi ID bằng test thực |
| FR02 — Admin, tài khoản và danh mục | Có CRUD/quyền; tìm kiếm đã loại chữ trên nút thao tác, vẫn tìm đúng tên thật chứa “sửa/xóa” |
| FR03 — nhập NCC | Khớp số nhận/lỗi/giá, nháp và chốt một lần |
| FR04 — BOM | Khớp phiên bản, định mức và một bản đang áp dụng |
| FR05 — giao việc | Có chọn BOM, số PC, nhân viên, hạn và snapshot khi giao |
| FR06 — nhận việc, nhu cầu và thiếu vật liệu | Khớp quyền sở hữu và cách tính nhu cầu/khả dụng/thiếu |
| FR07 — đề nghị cấp | Có phân bổ SKU/vị trí, gửi duyệt; chưa giảm tồn khi nháp/gửi |
| FR08 — duyệt cấp | Khớp duyệt/bàn giao, lý do từ chối và rollback toàn phiếu |
| FR09 — kết quả lắp ráp | Khớp đạt/lỗi, nhiều đợt, giới hạn kế hoạch và nhập thành phẩm tự động |
| FR10 — đề nghị xuất thành phẩm | Có người/bộ phận nhận, SKU, số lượng, vị trí và gửi duyệt |
| FR11 — duyệt xuất thành phẩm | Khớp tồn khả dụng, chống lặp và xử lý cạnh tranh |
| FR12 — báo cáo | Có tháng/quý/năm, bộ lọc, in/CSV; số dư và mốc kỳ đạt test |
| FR13 — tra cứu, lỗi và hướng dẫn | Có màn hình tra cứu, hướng dẫn cài đặt/sử dụng và lỗi nghiệp vụ có chi tiết |

Trước khi sửa, lượt đối chiếu chạy lại **19/19 test backend đạt**: 12 AT PRD, 5 hồi quy PRD và 2 test xác thực/Admin. **153/153 kiểm tra DOM khi đó đạt**, nhưng hai phép kiểm tra bổ sung đã tái hiện lỗi tìm kiếm mà bộ test chưa bao phủ. Kết quả sau sửa được ghi riêng bên dưới.

CSDL thực tế và ERD khớp **17 bảng, 122 thuộc tính, 36 khóa ngoại**; bảng dùng InnoDB/utf8mb4, kết nối UTC+7/SQL strict và tài khoản `mrp_app` thay vì root. Đối chiếu đủ 17 bảng trước/sau không đổi; không còn CSDL QA sau test. App chính vẫn hoạt động.

### FR02 — tìm kiếm đã sửa

Lỗi trước sửa: ở Admin → Danh mục → Sản phẩm hoặc Nhà cung cấp, nhập từ khóa `sửa`. Dữ liệu mẫu có **0** đối tượng chứa từ này, nhưng UI vẫn hiện **3 sản phẩm** và **1 nhà cung cấp**. Nguyên nhân: `filterTable()` tìm trên toàn bộ `tr.textContent`, gồm nhãn nút `Sửa` và `Xóa`.

Đã sửa `filterTable()` chỉ tìm trong ô dữ liệu, bỏ ô chứa nhóm thao tác. Áp dụng thống nhất cho danh mục, tài khoản và chứng từ; vẫn kết hợp loại hàng, nhóm, trạng thái, vị trí và sắp xếp. Không loại từ “sửa/xóa” khỏi truy vấn: tên sản phẩm/NCC thực sự chứa các từ này vẫn tìm được.

Đã bổ sung 18 kiểm tra DOM, gồm từ khóa trùng nhãn nút, chữ hoa/thường, tên thật chứa “sửa/xóa”, truy vấn trống và kết hợp lọc/sắp xếp. **171/171 kiểm tra DOM đạt** (92 + 37 + 42). **15 kiểm tra Edge thật trên app chính đạt**, không ghi nhận lỗi JavaScript; không sửa dữ liệu chính trong các ca UI.

### Quyền CSDL test — đã dọn và ngăn tích tụ

Trước sửa, MySQL còn quyền của **303 CSDL test đã xóa**. `grant_app()` cấp quyền cho CSDL tạm, trong khi teardown chỉ `DROP DATABASE`, khiến quyền tương ứng vẫn tồn tại.

Đã thu hồi **8.181 mục GRANT** thuộc đúng 303 CSDL test cũ, bằng `REVOKE` cho từng phạm vi schema, bảng/cột và routine. Bộ dọn chỉ nhận tên test hợp lệ đã không còn tồn tại, bỏ qua CSDL chính và mọi schema đang hoạt động. Chạy lại trả 0. Tài liệu cơ chế MySQL: [DROP DATABASE](https://dev.mysql.com/doc/refman/8.4/en/drop-database.html), [REVOKE](https://dev.mysql.com/doc/refman/8.4/en/revoke.html).

Đã thêm `manage.py cleanup-test-grants` để bảo trì runtime cũ. Test nghiệp vụ đăng ký `addCleanup` trước khi khởi tạo CSDL, tự xóa CSDL và thu hồi quyền kể cả khi setUp thất bại; test backup cũng đăng ký hoàn nguyên cấu hình để cleanup không bị kẹt bởi override còn sót. Bộ mới `test_cleanup.py` có 4 bài hồi quy về phạm vi quyền, bảo vệ CSDL chính/còn tồn tại, khởi tạo thất bại và dọn lặp. Bộ Python hiện có tổng cộng 85 test.

### Xác nhận sau sửa

- **35/35 test Python đạt**: 12 AT PRD, 5 hồi quy PRD, 6 vòng đời tiến trình, 2 xác thực/Admin, 6 sao lưu/khôi phục và 4 cleanup. Các ca cleanup bao gồm lỗi khởi tạo ở cả test nghiệp vụ và test backup. Đây là phạm vi chạy lại sau sửa, không phải toàn bộ 85 test.
- **171/171 kiểm tra DOM và 15 kiểm tra Edge thật đạt**; JavaScript app chính khớp file đã sửa.
- Dấu đối chiếu dữ liệu của **17 bảng** và **27 mục quyền CSDL chính** giữ nguyên so với trước sửa. Không còn CSDL test/khôi phục tạm hoặc quyền test dư; chạy lại lệnh dọn trả `databases=0, grants=0`.
- Python nhận đủ 85 test, không lỗi import; các file Python qua kiểm tra cú pháp. Giữ bản sao lưu chính, app tại `http://127.0.0.1:8765` và folder BT. Dependency kiểm thử dùng tạm ngoài project được dọn sau xác nhận.

## Rà soát toàn bộ lần tiếp theo — 11/10/2026

**Lượt trước sửa đã tái hiện 4 nhóm vấn đề.** Các vấn đề dưới đây đã được xử lý trong phần khắc phục QA-01–QA-04 ở đầu báo cáo. Nội dung này lưu lại cách tái hiện và kết quả trước sửa.

### Phạm vi và kết quả

- Chạy lại toàn bộ **85/85 test Python đạt**, 966,158 giây, trên MySQL thật; gồm AT01–AT12, phân quyền, cạnh tranh, rollback, sao lưu/khôi phục và dọn quyền test.
- **171/171 kiểm tra DOM đạt**.
- Edge thật: **327 kiểm tra trang, biểu mẫu và sidebar đạt**, gồm 31 trang theo ba vai trò ở 320/360/390/768/1024/1440 px. Không phát hiện tràn ngang toàn trang hoặc tràn biểu mẫu trong các ca này; đã xem ảnh desktop/mobile.
- Thêm **64 kiểm tra UI nghiệp vụ**: 63 đạt, 1 sai số đếm vị trí hàng lỗi. Đã thao tác thật nhập nháp/sửa/chốt, BOM/ban hành, giao/nhận việc, gợi ý cấp/gửi/duyệt, kết quả đạt/lỗi/tiếp nhận, xuất thành phẩm, CRUD năm danh mục, tài khoản/khóa/xóa, xóa nháp, hủy có lý do, từ chối, quyền sở hữu và CSV. Đã kiểm tra CSS in chứng từ/báo cáo và xem ảnh.
- **5 phép tái hiện phản hồi chậm** xác nhận lỗi đăng xuất/đổi tài khoản; tách riêng trường hợp có và không có `Set-Cookie`. Không ghi nhận lỗi JavaScript chưa xử lý trong các ca Edge.
- Kiểm tra bổ sung bằng kết nối `mrp_app` trên 3 chứng từ QA đã chốt: ghi chú vẫn sửa được ở MySQL; cả 3 cập nhật đã rollback. API tương ứng đều chặn đúng bằng HTTP 409.

### QA-01 — P1: phản hồi cũ phục hồi dữ liệu và cookie của tài khoản trước

Tái hiện: đăng nhập Admin, nhấn Làm mới và trì hoãn phản hồi `/api/state` đã được server xử lý; đăng xuất, đăng nhập `nhanvien`, rồi cho phản hồi Admin cũ tới trình duyệt. Trước khi thả phản hồi, `/api/session` xác nhận `NHAN_VIEN`; sau đó, phiên trở lại `ADMIN`, giao diện và danh sách tài khoản Admin xuất hiện. Đăng xuất mà chưa đăng nhập lại cũng có thể bị phản hồi cũ phục hồi.

Hai phần nguyên nhân đã được tách kiểm chứng:

1. `app/static/app.js:64`: `reload()` áp dụng mọi phản hồi thành công vào `S.data`/`S.user`, không kiểm tra lượt tải hoặc phiên đã thay đổi. Khi bỏ `Set-Cookie` khỏi phản hồi trong phép thử riêng, phiên server vẫn là nhân viên/đã đăng xuất nhưng UI và dữ liệu Admin cũ vẫn hiện lại.
2. `app/server.py:128,253`: phiên permanent, còn `SESSION_REFRESH_EACH_REQUEST` dùng giá trị mặc định `True` của Flask cài trong runtime. Phản hồi đọc cũ mang `Set-Cookie` và ghi đè cookie đăng nhập mới. Chỉ bỏ qua dữ liệu cũ ở JavaScript chưa giải quyết phần cookie.

Hướng sửa: quản lý thế hệ phiên/lượt tải, hủy hoặc bỏ phản hồi không còn hợp lệ khi đăng xuất/đăng nhập; đồng thời ngăn phản hồi đọc cũ gia hạn/ghi lại cookie xác thực (hoặc dùng cơ chế phiên có thu hồi). Cần hồi quy cả UI và `/api/session` với phản hồi đến đảo thứ tự.

### QA-02 — P2: ghi chú chứng từ đã khóa chưa được khóa ở tầng MySQL

Kết nối bằng chính tài khoản `mrp_app` vẫn thực hiện được `UPDATE ... SET GhiChu=...` đối với `PHIEU_NHAP` đã `DA_GHI_NHAN`, `PHIEU_XUAT` đã `DA_THUC_HIEN` và `KET_QUA_LAP_RAP` đã `DA_TIEP_NHAN`. Đã thử trên PN-5, PX-4, KQ-3 của CSDL QA và rollback, xác nhận nội dung trở lại như trước.

API đã chặn sửa các chứng từ này bằng HTTP 409. Khoảng trống nằm ở các trigger `trg_phieu_nhap_freeze`, `trg_phieu_xuat_freeze`, `trg_ket_qua_lap_rap_freeze` trong `docs/mrp/schema_MRP_HTTTDN_17_bang.sql:623,626,635`: điều kiện khóa chưa gồm `GhiChu`, trong khi tài khoản ứng dụng có quyền UPDATE cột đó. Chưa khớp bất biến nội dung chứng từ đã gửi/chốt được khóa trong PRD.

Hướng sửa: khóa thay đổi ghi chú sau nháp ở trigger; riêng kết quả cần giữ việc procedure từ chối ghi lý do khi chuyển sang `TU_CHOI`. Áp dụng migration cho runtime đang có và kiểm thử bằng quyền ứng dụng, gồm cả các lần từ chối hợp lệ.

### QA-03 — P2: đếm dư vị trí có hàng lỗi

`app/static/app.js:91` đếm số dòng tồn có lỗi thay vì số `MaViTri` khác nhau. Với CPU lỗi và RAM lỗi cùng ở `LK-A1`, PC lỗi ở `LOI-A1`, Tổng quan hiển thị **3**, trong khi chỉ có **2 vị trí**. Tồn thực tế/không bán/khả dụng của từng dòng vẫn đúng.

Hướng sửa: lọc các dòng có hàng lỗi rồi đếm tập `MaViTri` duy nhất; bổ sung ca nhiều SKU lỗi cùng vị trí.

### QA-04 — P3: 6 nhãn dữ liệu mẫu còn thiếu dấu

Đã đối chiếu dữ liệu QA và nguồn seed `docs/mrp/demo_MRP_17_bang.sql:6,12,18`:

| Đang hiển thị | Nhãn cần sửa |
|---|---|
| `Linh kien PC` | Linh kiện PC |
| `PC lap rap` | PC lắp ráp |
| `Nhan vien khac` | Nhân viên khác |
| `Nguyen lieu` | Nguyên liệu |
| `Thanh pham` | Thành phẩm |
| `Hang loi` | Hàng lỗi |

Hướng sửa: cập nhật seed mới và migration chỉ khớp đúng ID/nhãn mẫu cũ, giữ tên do người dùng đã sửa. Đây là tồn đọng dữ liệu mẫu đã được ghi ở giới hạn trước, chưa xử lý trong lượt sửa FR02/cleanup.

### Bảo toàn và bằng chứng

Dấu đối chiếu của **17 bảng**, **27 mục quyền CSDL chính** và danh sách backup giữ nguyên so với trước lượt rà soát. Đã dừng app QA trên cổng 8766, xóa CSDL QA và thu hồi 27 mục quyền tương ứng; không còn CSDL test/khôi phục hoặc quyền test dư. App chính tiếp tục chạy tại `http://127.0.0.1:8765`; folder BT giữ nguyên. Dependency và script kiểm thử tạm được dọn ngoài project.

Ảnh và kết quả có cấu trúc của lượt này lưu tại `C:/Users/AD/.codex/visualizations/2026/10/10/01a125cb-7959-7423-9f55-c7cdd9b84b25/cnpm-audit-20261011/`: `audit-results.json`, `final-audit.json`, `finding-account-switch-race.png`, `finding-account-switch-ui-race.png`, `finding-faulty-locations.png`. Không lưu mật khẩu, cookie hoặc thông tin kết nối trong bằng chứng này.

## Giới hạn

DOM giả lập không thay thế kiểm tra bố cục bằng trình duyệt. Kết quả phản ánh các kịch bản đã chạy, không bao phủ mọi dữ liệu có thể nhập. Sáu nhãn mẫu thiếu dấu và đơn vị `cai` đã được sửa; tên riêng của người dùng được giữ nguyên.
