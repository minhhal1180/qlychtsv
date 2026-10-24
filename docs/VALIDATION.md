# Kiểm chứng bản bàn giao

> Các phần ngày 21/10 dưới đây là lịch sử bản đầu. Bản hồ sơ 25/10 đã mở rộng: API verifier 35/35 PASS baseline, training đúng 14 API FAIL; 97 testcase chức năng cho 97 PASS baseline và 83 PASS/14 FAIL training. Sáu lỗi Visual/Content có bằng chứng trình duyệt riêng; ba phát hiện exploratory giữ riêng. SRS và bộ biểu mẫu hiện tại nằm trong `submission/public`; kết quả chi tiết gửi riêng giảng viên. GitHub Actions hiện đã được kích hoạt, khác hạn chế quyền workflow ở bản đầu.

Ngày chạy: 21/10/2026. Môi trường: Windows, Python 3.11; Chromium headless cho kiểm tra trình duyệt. Mỗi lần chạy dùng database tạm, không sửa dữ liệu thực hành trong `instance/`.

## Kiểm thử API tự động

Lệnh: `python verify_training.py`.

| Chế độ | Tổng | PASS | FAIL | ERROR / SKIP |
| --- | --- | --- | --- | --- |
| `TRAINING_BUGS=0` | 31 | 31 | 0 | 0 / 0 |
| `TRAINING_BUGS=1` | 31 | 21 | 10 (B01–B10) | 0 / 0 |

Verifier đối chiếu danh tính từng testcase lỗi với B01–B10, chặn cả trường hợp lỗi thừa, thiếu lỗi, lỗi hạ tầng hoặc test bị skip. Không sử dụng `expectedFailure` để che kết quả. 21 testcase bảo vệ bao gồm quyền theo vai trò/từng bản ghi, file, phiên hết hạn, thu hồi phiên, CSRF, validation, thông báo riêng tư, retry JSON/multipart, retry thao tác không trùng lịch sử, cạnh tranh hai cán bộ tiếp nhận, mở lại và quản trị tài khoản/danh mục.

## Kiểm tra trình duyệt

Lệnh: `python tools/browser_smoke.py`. PASS trên Chromium với viewport 1440×1000 và 390×844, không có JavaScript page error. Đã kiểm tra:

- Đăng nhập ba vai trò và đăng xuất.
- Sinh viên tạo yêu cầu có tệp, tải lại đúng nội dung; tiêu đề chứa HTML được hiển thị như văn bản.
- Mô phỏng backend đã lưu nhưng trình duyệt mất phản hồi; gửi lại form multipart chỉ tạo một yêu cầu.
- Cán bộ tiếp nhận; chặn kết quả trống; yêu cầu bổ sung; sinh viên gửi bổ sung; cán bộ hoàn tất có lịch sử.
- Mở lại yêu cầu hoàn tất, giữ cán bộ cũ; đánh dấu thông báo đã đọc và tải lại.
- Tìm kiếm Unicode không phân biệt hoa/thường ở chế độ chuẩn.
- Admin cấp tài khoản và sửa loại yêu cầu.
- Màn hình điện thoại không tràn chiều ngang toàn trang; bảng có vùng cuộn riêng.

Ảnh và JSON kết quả tự sinh dưới `test-results/`, được gitignore. Kiểm tra browser chạy chế độ chuẩn; 10 lỗi training được đối chiếu qua API và có testcase thủ công trong BUGS.md.

Chạy lại browser test (tùy chọn, không cần để sử dụng ứng dụng):

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python tools/browser_smoke.py
```

Đã kiểm tra cú pháp Python, JavaScript và khoảng trắng Git. Chưa kiểm thử tải/hiệu năng hoặc các trình duyệt ngoài Chromium. Bộ test xác nhận các tình huống đã nêu, không chứng minh toàn bộ phần mềm không có lỗi ngoài danh mục.

GitHub từ chối push workflow do OAuth token thiếu scope `workflow`; vì vậy lưu cấu hình trong `docs/github-actions-tests.yml` dưới dạng mẫu, chưa kích hoạt CI. Các kết quả bên trên được chạy cục bộ thực tế, không phải kết quả GitHub Actions.

## Bổ sung kiểm chứng VPS — 21/10/2026

Đã triển khai lên `student@192.168.2.213`, Ubuntu 24.04/Python 3.12.3, Flask 3.1.3/Gunicorn 26.2.0. Nginx phục vụ tên miền **https://sv23.bcse-vju.com**, dùng HTTPS sẵn có của hạ tầng lab. Service `qlychtsv` ở trạng thái `active` và `enabled`; đã kiểm tra cấu hình Nginx, cấu hình Gunicorn và khởi động lại dịch vụ thành công.

Chạy lại `verify_training.py` ngay trên VPS: 31/31 PASS khi tắt lỗi; 21 PASS, đúng 10 FAIL B01–B10 khi bật lỗi; verifier trả mã 0. Dữ liệu của bộ test nằm trong database tạm, không ảnh hưởng database demo đang chạy.

Kiểm tra trình duyệt bên ngoài bằng `tools/live_smoke.py`: PASS, đăng nhập `sv01`, `sv02`, `cb01`, `admin`; ba vai trò đúng; chặn sinh viên truy cập hồ sơ người khác, chặn admin xử lý hồ sơ; cookie Secure/HttpOnly/SameSite=Lax; giao diện desktop/mobile; không có JavaScript page error. Bản VPS giữ `TRAINING_BUGS=1` theo yêu cầu. Không thử reboot toàn bộ VPS.
