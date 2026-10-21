# Kiểm chứng bản bàn giao

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

Đã kiểm tra cú pháp Python, JavaScript và khoảng trắng Git. Chưa kiểm thử tải/hiệu năng, hosting HTTPS hoặc các trình duyệt ngoài Chromium. Bộ test xác nhận các tình huống đã nêu, không chứng minh toàn bộ phần mềm không có lỗi ngoài danh mục.

GitHub từ chối push workflow do OAuth token thiếu scope `workflow`; vì vậy lưu cấu hình trong `docs/github-actions-tests.yml` dưới dạng mẫu, chưa kích hoạt CI. Các kết quả bên trên được chạy cục bộ thực tế, không phải kết quả GitHub Actions.
