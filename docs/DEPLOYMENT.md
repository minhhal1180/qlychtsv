# VPS sv23

Bản cập nhật 25/10/2026 đã sao lưu database bằng SQLite backup, cập nhật mã và khởi động lại dịch vụ. Kiểm chứng trên VPS: baseline 35/35 PASS; training 21 PASS/14 API FAIL theo danh mục. Các phép đo tải của bộ hồ sơ thực hiện trên bản sao cục bộ, không ghi là hiệu năng VPS.

Địa chỉ ứng dụng: **https://sv23.bcse-vju.com**. Máy đích: Ubuntu 24.04, user `student`, IP nội bộ `192.168.2.213`. Mã nguồn tại `/home/student/qlychtsv`, database/tệp/khóa phiên trong `instance/` và không đưa lên GitHub. Không lưu mật khẩu SSH trong repo.

Luồng truy cập: HTTPS của portal/Cloudflare → Nginx cổng 80 theo Host `sv23.bcse-vju.com` → Gunicorn `127.0.0.1:8001` → Flask/SQLite. Giữ nguyên virtual host mặc định và các dịch vụ khác. Cookie phiên Secure/HttpOnly/SameSite=Lax. Ứng dụng chạy dưới user `student`, systemd tự khởi động khi máy boot và khởi động lại khi process lỗi.

## Cài đặt lại trên đúng VPS

Đăng nhập SSH theo thông tin portal hiện tại (gateway và VPS có thể hỏi hai mật khẩu). Tài khoản `student` cần sudo. Nếu chưa có venv: `sudo apt-get install python3.12-venv`. Sau đó:

```sh
git clone https://github.com/minhhal1180/qlychtsv.git /home/student/qlychtsv
cd /home/student/qlychtsv
bash deploy/install-vps.sh
```

Script dùng cấu hình cụ thể cho máy này, không ghi đè vhost mặc định, giữ database đang có. Khi chạy lại, các file dịch vụ/Nginx riêng của ứng dụng được sao lưu trước; `/etc/qlychtsv.env` chỉ tạo nếu chưa có.

## Quản lý dịch vụ

```sh
sudo systemctl status qlychtsv --no-pager
sudo systemctl restart qlychtsv
sudo journalctl -u qlychtsv -n 100 --no-pager
sudo nginx -t
```

Đổi chế độ lỗi: sửa `TRAINING_BUGS` trong `/etc/qlychtsv.env` rồi restart `qlychtsv`. Mặc định bằng `1` theo yêu cầu thực hành; `0` là chế độ chuẩn. Không đổi `COOKIE_SECURE=1` khi truy cập qua HTTPS. Thay đổi chế độ không tự sửa dữ liệu đã tạo.

## Cập nhật mã và kiểm thử

```sh
cd /home/student/qlychtsv
git pull --ff-only
.venv/bin/python -m pip install -r requirements-server.txt
.venv/bin/python verify_training.py
sudo systemctl restart qlychtsv
```

Nếu thay cấu hình triển khai, chạy lại `bash deploy/install-vps.sh`. Testcase chạy trên database tạm, không thay dữ liệu người dùng. Tài khoản mẫu xem README. Không commit thư mục `instance/` hoặc thông tin đăng nhập hạ tầng.

Kiểm tra từ máy ngoài đã cài dependencies trình duyệt trong `requirements-dev.txt` và Chromium:

```sh
python tools/live_smoke.py --url https://sv23.bcse-vju.com
```

Lệnh này chỉ đăng nhập và đọc dữ liệu, không tạo/sửa yêu cầu. Kết quả và ảnh tự lưu trong `test-results/` của máy chạy kiểm tra.

## Sao lưu dữ liệu

Dùng SQLite backup để có bản sao nhất quán cả khi WAL đang hoạt động:

```sh
cd /home/student/qlychtsv
install -d -m 700 /home/student/qlychtsv-backups
.venv/bin/python -c "import sqlite3; from datetime import datetime, timezone; from contextlib import closing; stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); source=sqlite3.connect('instance/support.db'); target=sqlite3.connect('/home/student/qlychtsv-backups/support-'+stamp+'.db'); source.backup(target); target.close(); source.close()"
```

Bản backup chứa tài khoản, hash mật khẩu và tệp đính kèm; giữ riêng tư. Khóa `instance/secret.key` cũng cần giữ nếu muốn bảo toàn phiên sau khôi phục. Chưa cấu hình lịch backup tự động.
