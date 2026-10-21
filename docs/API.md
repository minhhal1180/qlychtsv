# API ngắn gọn

Base URL cục bộ: `http://127.0.0.1:5000/api`. JSON, cookie session. `POST /login` nhận `{"username":"sv01","password":"Demo@123"}`. Sau đăng nhập, `GET /me` trả `user` và `csrf`. Mọi POST/PATCH sau đăng nhập cần header `X-CSRF-Token` lấy từ `/me`.

| Method | Đường dẫn | Vai trò / dữ liệu |
| --- | --- | --- |
| POST | `/login` | `{username,password}` |
| POST | `/logout` | Thu hồi phiên |
| GET | `/me` | Người dùng hiện tại, CSRF |
| GET | `/types` | Tài khoản đã đăng nhập; admin thấy cả loại ngừng hoạt động |
| POST | `/types` | Admin; `{code,name,description?,active?}` |
| PATCH | `/types/:id` | Admin; sửa các trường danh mục |
| GET | `/users` | Admin; không trả password/hash |
| POST | `/users` | Admin; `{username,name,password,role,active?}` |
| PATCH | `/users/:id` | Admin; `{name?,role?,active?,password?}`; không đổi username |
| GET | `/requests` | Sinh viên/cán bộ; `?status=NEW&q=HT-&mine=1` |
| POST | `/requests` | Sinh viên; `{type_id,title,content}` hoặc multipart có trường `files` lặp lại |
| GET | `/requests/:id` | `item`, `messages`, `history`, `attachments` |
| POST | `/requests/:id/action` | `{action,body?}`; action: `accept`, `cancel`, `ask`, `complete`, `reject`, `reopen` |
| POST | `/requests/:id/messages` | `{body}` hoặc multipart `body`, `files`; nội dung hoặc tệp bắt buộc |
| GET | `/attachments/:id` | Download với cookie, kiểm tra quyền từng yêu cầu |
| GET | `/notifications` | Chỉ thông báo người nhận đăng nhập |
| POST | `/notifications/:id/read` | Đánh dấu đã đọc của chính người nhận |

`active` là boolean JSON, `role` là `STUDENT`, `STAFF` hoặc `ADMIN`. ID là số nguyên dương. Danh sách trả `{items:[...]}`; `/requests` trả thêm `counts`. Tạo mới trả 201; cập nhật 200. Tìm kiếm Unicode không phân biệt hoa/thường ở chế độ chuẩn, so khớp chuỗi con, không bỏ dấu. API không có chỉnh sửa/xóa trao đổi/lịch sử, xóa loại hoặc xóa yêu cầu.

Lỗi trả `{"error":"Thông báo tiếng Việt"}`: 400 validation, 401 chưa đăng nhập/hết phiên/đăng nhập sai, 403 sai quyền/CSRF, 404 không tìm thấy, 409 xung đột trạng thái/trùng dữ liệu, 413 body quá lớn.

## Retry

Gửi `Idempotency-Key` duy nhất (tối đa 100 ký tự) cho mỗi thao tác ghi. Khi bị timeout, gửi lại cùng khóa, cùng đường dẫn, cùng nội dung với tài khoản đó. Backend trả lại đúng kết quả đã ghi mà không thêm yêu cầu, lịch sử hoặc thông báo lần nữa. Dùng cùng khóa với dữ liệu khác trả 409. Các khóa được lưu trong SQLite, dùng cho bản thực hành chưa có cơ chế dọn định kỳ. Với multipart, hash theo trường và tệp thay vì HTTP boundary để retry qua trình duyệt hoạt động.

## Ví dụ trong DevTools của ứng dụng đã đăng nhập

```javascript
const me = await (await fetch('/api/me')).json();
const response = await fetch('/api/requests', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': me.csrf,
    'Idempotency-Key': crypto.randomUUID()
  },
  body: JSON.stringify({type_id: 1, title: 'Xin xác nhận sinh viên', content: 'Em cần bổ sung hồ sơ.'})
});
console.log(response.status, await response.json());
```
