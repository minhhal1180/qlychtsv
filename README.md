# StudentCare — Quản lý yêu cầu hỗ trợ sinh viên

Bản MVP theo `dactadan.pdf`: sinh viên gửi yêu cầu, cán bộ tiếp nhận và xử lý, quản trị viên quản lý tài khoản/danh mục. Flask + SQLite + HTML/CSS/JavaScript thuần, không cần Node, Docker hay cài database riêng.

**Bản chạy trên VPS:** https://sv23.bcse-vju.com — [cấu hình và cách quản lý dịch vụ](docs/DEPLOYMENT.md).

**Bản thực hành bật lỗi có chủ đích**, đủ năm nhóm theo checklist. [Tài liệu URD, SRS, API và bàn giao](submission/public) được công khai; Bug Manifest và bằng chứng chi tiết gửi riêng giảng viên trong kho hồ sơ riêng tư.

## Chạy nhanh

Cần Python 3.11 trở lên và Git. Trên Windows:

```powershell
git clone https://github.com/minhhal1180/qlychtsv.git
cd qlychtsv
.\start.bat
```

Mở **http://127.0.0.1:5000**. Lần đầu tự tạo môi trường ảo, cài Flask, tạo database và dữ liệu mẫu. Các lần sau giữ nguyên dữ liệu. Đóng cửa sổ hoặc Ctrl+C để dừng.

Hoặc chạy thủ công trên Windows/macOS/Linux:

```sh
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
# macOS/Linux: dùng .venv/bin/python thay cho .venv\Scripts\python
```

| Vai trò | Tài khoản | Mật khẩu |
| --- | --- | --- |
| Sinh viên | `sv01`, `sv02` | `Demo@123` |
| Cán bộ | `cb01`, `cb02` | `Demo@123` |
| Quản trị | `admin` | `Demo@123` |

Dùng cửa sổ ẩn danh hoặc trình duyệt khác để đăng nhập hai vai trò cùng lúc. Tài khoản mẫu chỉ được tạo khi database mới chưa có dữ liệu.

## Kiểm chứng bản thực hành

Chạy trong thư mục dự án, sau khi đã cài dependencies:

```powershell
.venv\Scripts\python verify_training.py
```

Script chạy cùng bộ testcase trên **hai database tạm độc lập**:

- `TRAINING_BUGS=0`: tất cả testcase phải PASS.
- `TRAINING_BUGS=1`: đúng 14 testcase API đã định danh phải FAIL; các testcase bảo vệ còn lại phải PASS.

Script chỉ trả mã `0` nếu kết quả khớp cả hai điều kiện. Assertion luôn kiểm tra hành vi đúng; log training có 14 testcase FAIL theo danh mục. Sáu trường hợp hiển thị/nội dung được kiểm tra riêng bằng `python tools/extra_evidence.py`. JSON kết quả API ở `test-results/baseline.json` và `test-results/training.json`.

GitHub Actions được cấu hình ở `.github/workflows/tests.yml`; kết nối hiện tại đã có quyền workflow. CI kiểm chứng cả baseline và bản thực hành. Không cần CI để chạy ứng dụng.

Chạy riêng testcase theo yêu cầu nghiệp vụ:

```powershell
# Bản có lỗi: 14 API FAIL là kết quả dự kiến
$env:TRAINING_BUGS="1"
.venv\Scripts\python -m unittest discover -s tests -v

# Bản chuẩn: tất cả PASS
$env:TRAINING_BUGS="0"
.venv\Scripts\python -m unittest discover -s tests -v

# Khởi động giao diện bản chuẩn (dừng server cũ trước)
.venv\Scripts\python app.py
```

Để quay lại bản có lỗi: `$env:TRAINING_BUGS="1"`, rồi chạy lại server. Trên macOS/Linux dùng `TRAINING_BUGS=0 python app.py`. Việc tắt lỗi **không sửa dữ liệu đã tạo sai**; dùng database mới khi cần kiểm tra sạch.

## Chức năng

- Đăng nhập/đăng xuất, phiên 8 giờ; kiểm tra tài khoản và vai trò tại backend.
- Sinh viên: tạo, tìm kiếm/lọc, xem chi tiết, hủy NEW, bổ sung nội dung/tệp, mở lại yêu cầu hoàn tất.
- Cán bộ: hàng đợi chung, lọc yêu cầu mình phụ trách, nhận xử lý, yêu cầu bổ sung, hoàn tất/từ chối, trao đổi.
- Quản trị: tạo/sửa/khóa tài khoản, đổi vai trò, đặt lại mật khẩu; thêm/sửa/ngừng hoạt động loại yêu cầu.
- Thông báo nội bộ, lịch sử xử lý, tải tệp có xác thực.
- SQLite transaction bảo vệ nhận xử lý đồng thời. API ghi dữ liệu hỗ trợ `Idempotency-Key` để retry không tạo trùng.

## Tài liệu và cấu trúc

- [Bộ tài liệu bàn giao URD, SRS, API](submission/public)
- [Phạm vi, lựa chọn cho TBD, ma trận quyền](docs/SCOPE.md)
- [API và mã lỗi](docs/API.md)
- [Kết quả kiểm chứng](docs/VALIDATION.md)

Kết quả bản hồ sơ 25/10: API verifier **35/35 PASS** baseline, **21 PASS + 14 FAIL** training. Bộ chức năng mở rộng: **97/97 PASS** baseline, **83 PASS + 14 FAIL** training (nhiều E2E phát hiện lại cùng bug). Đây là số liệu tự kiểm thử, chưa thay kết quả kiểm thử chéo bạn cặp.

```text
app.py                 Backend, phân quyền, workflow và khởi tạo dữ liệu
bugs.py                Danh mục đúng 10 lỗi chủ đích
schema.sql             Database SQLite
templates/index.html   Khung giao diện
static/                CSS và JavaScript
tests/                 Testcase nghiệp vụ và bảo vệ
verify_training.py     Đối chiếu kết quả hai chế độ
instance/              Database + khóa phiên, tự sinh và không commit
```

## Dữ liệu và vận hành

Database ở `instance/support.db`, tệp đính kèm được lưu trong database để sao lưu đơn giản. Khóa ký phiên ở `instance/secret.key`; giữ kín file này. Để tạo bộ dữ liệu mới, dừng server rồi **đổi tên** `instance/support.db` thành một tên sao lưu; chạy lại server để tự tạo dữ liệu mẫu. Không đổi database khi server còn chạy. Có thể chọn đường dẫn database mới bằng biến `DATABASE` (thư mục cha phải tồn tại).

Các biến tùy chọn: `PORT` (mặc định 5000), `HOST` (127.0.0.1), `TRAINING_BUGS` (1), `SECRET_KEY`, `DATABASE`, `COOKIE_SECURE` (0 cho localhost, 1 trên VPS HTTPS). VPS sử dụng Gunicorn + Nginx + systemd, giữ lỗi và dữ liệu mẫu để thực hành. GitHub chứa mã nguồn; GitHub Pages không chạy backend Flask. Khi sử dụng nghiệp vụ thật cần tắt lỗi, thay tài khoản mẫu và xác định chính sách vận hành.
