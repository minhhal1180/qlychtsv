# Danh mục 10 lỗi có chủ đích

Mặc định `TRAINING_BUGS=1`. Dừng server và đặt `TRAINING_BUGS=0` để đối chiếu hành vi chuẩn trên cùng mã nguồn. Có đúng **10 điểm gây lỗi chủ đích** trong `bugs.py`/`app.py`; không khẳng định phần mềm tuyệt đối không có lỗi ngoài danh mục. Testcase tự động luôn kiểm tra yêu cầu đúng, nên phải FAIL khi phát hiện lỗi.

Mỗi testcase nên dùng một yêu cầu mới để lỗi trước không làm sai tiền điều kiện của testcase sau. Dùng hai trình duyệt/cửa sổ ẩn danh cho `sv01` và `cb01`/`admin`. Mật khẩu chung `Demo@123`. Ghi lại mã yêu cầu khi tạo.

| ID / Testcase | Tiền điều kiện và bước thực hiện | Kết quả đúng | Kết quả bản có lỗi | Mức độ / Tham chiếu |
| --- | --- | --- | --- | --- |
| B01 / TC-01 | sv01 → Tạo yêu cầu; chọn loại đang hoạt động; tiêu đề nhập 3 dấu cách; nội dung hợp lệ; Gửi | Báo lỗi; không tạo yêu cầu; API 400 | API 201, tạo yêu cầu có tiêu đề trắng | Medium / F02 validation |
| B02 / TC-02 | sv01 mở sẵn form tạo, chọn Học vụ. Cửa sổ admin ngừng hoạt động Học vụ. Quay lại form cũ, nhập tiêu đề/nội dung và Gửi, không tải lại form | Server từ chối loại đã ngừng; API 400 | Vẫn tạo NEW; API 201 | High / AC-F05-01 |
| B03 / TC-03 | Tạo NEW bằng sv01. cb01 mở yêu cầu → Tiếp nhận. sv01 tải lại chi tiết → Hủy yêu cầu → xác nhận | Bị chặn 409, vẫn IN_PROGRESS | Đổi thành CANCELLED | High / AC-F02-03 |
| B04 / TC-04 | Tạo NEW; cb01 tiếp nhận. Để Nội dung xử lý trống → Hoàn tất | Bị chặn 400, vẫn IN_PROGRESS | Chuyển COMPLETED | High / AC-F03-02 |
| B05 / TC-05 | Tạo NEW. cb01 mở chi tiết, để Nội dung xử lý trống → Từ chối → xác nhận | Bị chặn 400, vẫn NEW | Chuyển REJECTED | High / F03 validation |
| B06 / TC-06 | Tạo NEW; cb01 tiếp nhận → nhập “Bổ sung bảng điểm” → Yêu cầu bổ sung. sv01 mở chi tiết, gửi “Đã bổ sung thông tin” | Lưu trao đổi và trở lại IN_PROGRESS | Có trao đổi, trạng thái vẫn WAITING_STUDENT | High / AC-F04-01 và giả định TBD |
| B07 / TC-07 | Tạo NEW; cb01 nhập lý do hợp lệ → Từ chối. sv01 tải chi tiết → Mở lại yêu cầu | Bị chặn 409, vẫn REJECTED | Chuyển IN_PROGRESS | Medium / TBD-09 đã chọn cho bản triển khai |
| B08 / TC-08 | sv01 tạo tiêu đề “Hỗ trợ HỌC PHÍ”. Trở lại danh sách, tìm “học phí” → Lọc | Có yêu cầu vừa tạo | Không tìm thấy yêu cầu đó | Medium / F02 tìm kiếm, quy tắc không phân biệt hoa/thường của bản triển khai |
| B09 / TC-09 | sv01 tạo NEW → Thông báo → chọn thông báo vừa tạo → Đánh dấu đã đọc → tải lại | Thông báo vẫn Đã đọc | Thông báo vẫn Chưa đọc | Medium / F05 |
| B10 / TC-10 | Tạo NEW; cb01 tiếp nhận → nhập “Đã cấp giấy xác nhận” → Hoàn tất. Xem Lịch sử xử lý | Có sự kiện COMPLETE, từ IN_PROGRESS đến COMPLETED, người/thời điểm | Trạng thái COMPLETED nhưng lịch sử chỉ đến ACCEPT | High / AC-F03-03 |

B04 và B10 là hai lỗi độc lập: TC-10 luôn nhập kết quả hợp lệ; TC-04 chỉ kiểm tra quy tắc bắt buộc nhập. Tương tự TC-07 luôn từ chối có lý do để không phụ thuộc B05.

B02 cũng tái hiện được bằng API gửi `type_id` của loại đã ngừng hoạt động. Các nút Hủy ở IN_PROGRESS và Mở lại ở REJECTED được giữ trên giao diện thực hành để thử TC-03/TC-07; ở chế độ chuẩn backend trả lỗi và bảo toàn dữ liệu.

## Ánh xạ sang test tự động

`tests/test_support.py`, lớp `DefectTests`: mỗi phương thức `test_B01_…` đến `test_B10_…` tương ứng một dòng trên. Lớp `GuardTests` kiểm tra phân quyền, file, phiên, retry, dữ liệu, đồng thời và những luồng không cố ý làm sai.

Chạy một testcase, ví dụ:

```powershell
$env:TRAINING_BUGS="1"
python -m unittest tests.test_support.DefectTests.test_B03_cancel_after_accept_is_rejected -v
```

Khi lập báo cáo thực hành, ghi Actual, Expected, trạng thái FAIL và ảnh chụp từ lần chạy của bạn; không đánh dấu testcase PASS chỉ vì lỗi là cố ý.
