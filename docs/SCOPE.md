# Phạm vi triển khai

Nguồn nghiệp vụ: `dactadan.pdf`, “MVP Student Support | Business Analysis Draft v1.0”, 7 trang, do người dùng cung cấp. Tài liệu được dùng làm đặc tả tham chiếu; yêu cầu bổ sung trực tiếp của người dùng là triển khai đơn giản và có 10 lỗi để dùng testcase phát hiện. Các lỗi có chủ đích được ghi riêng trong BUGS.md.

## Đối chiếu chức năng

| Nhóm | Màn hình | Đã triển khai |
| --- | --- | --- |
| F01 | SCR-01, SCR-08 | Đăng nhập/xuất, quản trị tài khoản, khóa, vai trò, đặt lại mật khẩu |
| F02 | SCR-02, SCR-03, SCR-04 | Tạo, danh sách/lọc/tìm, chi tiết, hủy, mở lại |
| F03 | SCR-05, SCR-06 | Hàng đợi, tiếp nhận, bổ sung, hoàn tất, từ chối |
| F04 | SCR-04, SCR-06 | Trao đổi bất biến, tệp khi tạo/bổ sung, tải tệp có xác thực |
| F05 | SCR-07, SCR-09 | Danh mục, ngừng hoạt động, thông báo của người nhận |

SCR-04 và SCR-06 dùng chung trang chi tiết nhưng hành động thay đổi theo vai trò, trạng thái, người phụ trách. Dashboard chuyên sâu không nằm trong MVP; chỉ giữ số đếm theo trạng thái.

## Lựa chọn triển khai cho mục chưa chốt

Đây là **giả định kỹ thuật của bản thực hành**, không coi các mục TBD trong PDF là quyết định đã được phê duyệt.

| Mục | Lựa chọn |
| --- | --- |
| TBD-01 | Một bộ phận, hàng đợi chung, cán bộ tự nhận |
| TBD-02 | Mở lại trực tiếp, không có bước phê duyệt/REOPEN_REQUESTED |
| TBD-03 | Chưa giới hạn số lần/thời gian mở lại |
| TBD-04 | Giữ cán bộ cũ nếu còn hoạt động và có vai trò STAFF; nếu không trả NEW, bỏ người phụ trách |
| TBD-05 | Admin tạo thủ công; có tài khoản seed để thực hành |
| TBD-06 | Admin đặt lại mật khẩu; chưa làm tự khôi phục qua email/SMS |
| TBD-07 | Tối đa 3 tệp/lần, 5 MB/tệp; PDF/PNG/JPG/TXT UTF-8; request tối đa 16 MB |
| TBD-08 | Sinh viên gửi bổ sung khi WAITING_STUDENT; cán bộ được gán trao đổi khi IN_PROGRESS hoặc WAITING_STUDENT |
| TBD-09 | Không mở lại REJECTED trong chế độ chuẩn; tạo yêu cầu mới |
| TBD-10 | Số đếm theo dữ liệu người dùng có quyền xem, có áp dụng “Tôi phụ trách”; trước bộ lọc từ khóa và trạng thái |

## Quyền tại backend

| Thao tác | Sinh viên | Cán bộ | Admin |
| --- | --- | --- | --- |
| Tạo yêu cầu | Có | Không | Không |
| Xem danh sách/chi tiết/tệp | Chỉ của mình | Toàn bộ hàng đợi chung | Không |
| Hủy/mở lại | Chỉ của mình, đúng trạng thái | Không | Không |
| Nhận NEW/từ chối NEW | Không | Có, cập nhật nguyên tử | Không |
| Xử lý/trao đổi | Bổ sung của mình khi chờ | Chỉ người được gán | Không |
| Quản lý tài khoản/danh mục | Không | Không | Có |
| Thông báo | Chỉ của mình | Chỉ của mình | Chỉ của mình (không phát sinh sự kiện xử lý) |

Cán bộ khác có thể xem hồ sơ/tệp để tiếp nhận từ hàng đợi, nhưng không được sửa yêu cầu đã có người phụ trách. Đổi vai trò cán bộ đang có yêu cầu IN_PROGRESS/WAITING_STUDENT bị chặn. Admin không tự khóa hoặc tự bỏ quyền; thay đổi tài khoản thu hồi phiên cũ. Đăng xuất thu hồi tất cả phiên của tài khoản đó. Phiên hiện tại sẽ cần đăng nhập lại khi admin sửa chính tài khoản của mình.

## Luồng chuẩn

```text
NEW → IN_PROGRESS → WAITING_STUDENT → IN_PROGRESS → COMPLETED
 │        │                                          │
 │        └→ REJECTED                                └→ IN_PROGRESS (hoặc NEW nếu cán bộ cũ không còn hợp lệ)
 ├→ CANCELLED
 └→ REJECTED
```

COMPLETE và ASK chỉ từ IN_PROGRESS. REJECT chỉ từ NEW hoặc IN_PROGRESS. Hủy chỉ NEW. COMPLETED/CANCELLED/REJECTED không được gửi thêm trao đổi. Mọi chuyển trạng thái ghi người, thời điểm, trạng thái trước/sau. B01–B10 cố ý làm sai một số quy tắc khi bật chế độ lỗi.

## Giới hạn của MVP

Chưa có email/SMS, SSO/SIS, nhiều phòng ban, dashboard biểu đồ, SLA, Excel export, FAQ, tự đăng ký hoặc tự khôi phục mật khẩu. Không cấu hình workflow động. Tệp lưu dưới dạng BLOB, phù hợp bài tập và dữ liệu nhỏ; không có quét virus hoặc kho file riêng.

Thông báo ghi cùng giao dịch nghiệp vụ trong SQLite để đảm bảo dữ liệu nhất quán và dễ triển khai. Khác đề xuất tách lỗi thông báo trong PDF: nếu SQLite lỗi khi ghi thông báo, toàn bộ giao dịch rollback và client có thể retry; chưa có outbox/background worker. Chưa triển khai rate limit/khóa theo số lần sai, backup tự động, giám sát tập trung hoặc cam kết hiệu năng; cần bổ sung trước sử dụng thực tế. Password dùng Werkzeug scrypt; khóa phiên tự sinh cục bộ; CSRF kiểm tra trên API ghi dữ liệu đã đăng nhập.
