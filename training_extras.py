"""Ten opt-in training defects covering visual/content/performance/request errors.

Install after the normal API routes and authentication hook. The module does not
change RBAC, terminate processes, or affect a baseline TRAINING_BUGS=0 instance.
"""
import re
import time

from flask import g, jsonify, request

EXTRA_BUGS = {
    "V01": {"category": "Visual", "requirement": "NFR-04", "title": "Tiêu đề chi tiết bị cắt ở desktop"},
    "V02": {"category": "Visual", "requirement": "NFR-04", "title": "Hộp thoại tạo yêu cầu tràn màn hình 375px"},
    "V03": {"category": "Visual", "requirement": "NFR-04", "title": "Nhãn trạng thái trong bảng bị ẩn ở màn hình 375px"},
    "C01": {"category": "Content", "requirement": "NFR-05", "title": "COMPLETED hiển thị sai thành Đang xử lý"},
    "C02": {"category": "Content", "requirement": "NFR-05", "title": "Hướng dẫn upload ghi nhầm giới hạn 50 MB"},
    "C03": {"category": "Content", "requirement": "NFR-05", "title": "Ngày tạo trong bảng bị đảo tháng/ngày"},
    "P01": {"category": "Performance", "requirement": "NFR-01", "title": "Tìm kiếm một người dùng vượt ngưỡng 800 ms"},
    "P02": {"category": "Performance", "requirement": "NFR-02", "title": "Tải thông báo một người dùng vượt ngưỡng 900 ms"},
    "R01": {"category": "Crash", "requirement": "NFR-08", "title": "Tệp rỗng gây HTTP 500 thay vì lỗi dữ liệu"},
    "R02": {"category": "Crash", "requirement": "NFR-08", "title": "Tải ID tệp không tồn tại gây HTTP 500"},
}
for _bug in EXTRA_BUGS.values():
    _bug["severity"] = "High" if _bug["category"] == "Crash" else "Medium"


def install_training_extras(app):
    """Register once, after app.prepare so authentication/CSRF still run first."""
    if app.extensions.get("training_extras"):
        return
    app.extensions["training_extras"] = {"manifest": EXTRA_BUGS}

    @app.context_processor
    def training_context():
        return {"training_extras": bool(app.config.get("TRAINING_BUGS"))}

    @app.before_request
    def extra_training_failures():
        if not app.config.get("TRAINING_BUGS") or not g.get("user"):
            return None
        role = g.user["role"]
        if request.method == "GET":
            if request.path == "/api/requests" and request.args.get("q", "").strip() and role in ("STUDENT", "STAFF"):
                time.sleep(1.1)  # P01: bounded per-request latency, not a load test.
            elif request.path == "/api/notifications":
                time.sleep(1.2)  # P02: bounded per-request latency, not a load test.
            elif role in ("STUDENT", "STAFF"):
                match = re.fullmatch(r"/api/attachments/(\d+)", request.path)
                if match and not g.db.execute("SELECT id FROM attachments WHERE id=?", (int(match.group(1)),)).fetchone():
                    # R02: an unhandled missing-row assumption represented safely.
                    return jsonify(error="Không thể xử lý yêu cầu tải tệp."), 500
        elif request.method == "POST" and request.path == "/api/requests" and role == "STUDENT":
            # R01: a first-byte parser assumes at least one byte exists. Keep the
            # failure local to this request and let the normal transaction roll back.
            for file in request.files.getlist("files"):
                prefix = file.stream.read(1)
                file.stream.seek(0)
                try:
                    prefix[0]
                except IndexError:
                    return jsonify(error="Không thể đọc thông tin đầu tệp."), 500
        return None
