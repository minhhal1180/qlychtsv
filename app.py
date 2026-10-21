"""Student support MVP: Flask, SQLite, one server, no frontend build step."""
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import click
from flask import Flask, abort, g, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from bugs import enabled

STATUSES = ("NEW", "IN_PROGRESS", "WAITING_STUDENT", "COMPLETED", "CANCELLED", "REJECTED")
ROLES = ("STUDENT", "STAFF", "ADMIN")
ALLOWED_FILES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".txt": "text/plain"}
MAX_FILE = 5 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def fail(message, code=400):
    abort(code, description=message)


def db():
    if "db" not in g:
        g.db = sqlite3.connect(g.app_db, timeout=15, isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def rows(sql, args=()):
    return [dict(row) for row in db().execute(sql, args).fetchall()]


def one(sql, args=()):
    row = db().execute(sql, args).fetchone()
    return dict(row) if row else None


def require(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not g.user:
                fail("Vui lòng đăng nhập.", 401)
            if roles and g.user["role"] not in roles:
                fail("Bạn không có quyền thực hiện thao tác này.", 403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def payload():
    value = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    if not isinstance(value, dict):
        fail("Dữ liệu phải là một đối tượng JSON hoặc biểu mẫu.")
    return value


def field(data, key, limit=10000, required=True):
    value = data.get(key, "")
    if not isinstance(value, str):
        fail(f"{key} phải là chuỗi.")
    if (required and not value.strip()) or len(value) > limit:
        fail(f"{key}: bắt buộc nhập, tối đa {limit} ký tự." if required else f"{key}: tối đa {limit} ký tự.")
    return value.strip()


def positive_id(value):
    try:
        if isinstance(value, bool) or str(int(value)) != str(value) or int(value) < 1:
            raise ValueError
        return int(value)
    except (TypeError, ValueError):
        fail("ID không hợp lệ.")


def flag(data, key, default=True):
    value = data.get(key, default)
    if type(value) is not bool:
        fail(f"{key} phải là true hoặc false.")
    return value


def ticket_for(ticket_id, writing=False):
    ticket = one("SELECT * FROM requests WHERE id=?", (ticket_id,))
    if not ticket:
        fail("Không tìm thấy yêu cầu.", 404)
    role = g.user["role"]
    if role == "ADMIN" or (role == "STUDENT" and ticket["student_id"] != g.user["id"]):
        fail("Bạn không có quyền truy cập yêu cầu này.", 403)
    if writing and role == "STAFF" and ticket["assignee_id"] != g.user["id"]:
        fail("Chỉ cán bộ phụ trách được xử lý yêu cầu.", 403)
    return ticket


def audit(ticket_id, action, old_status, new_status):
    db().execute("INSERT INTO history(request_id,action,from_status,to_status,actor_id,created_at) VALUES(?,?,?,?,?,?)",
                 (ticket_id, action, old_status, new_status, g.user["id"], now()))


def notify(ticket_id, recipient, event):
    if recipient:
        db().execute("INSERT INTO notifications(recipient_id,request_id,event_type,created_at) VALUES(?,?,?,?)",
                     (recipient, ticket_id, event, now()))


def transition(ticket, status, action):
    db().execute("UPDATE requests SET status=?,updated_at=? WHERE id=?", (status, now(), ticket["id"]))
    if not (action == "COMPLETE" and enabled(g.app, "B10")):
        audit(ticket["id"], action, ticket["status"], status)
    target = ticket["assignee_id"] if g.user["role"] == "STUDENT" else ticket["student_id"]
    notify(ticket["id"], target, action)


def attachments(ticket_id, message_id=None):
    files = request.files.getlist("files")
    if len(files) > 3:
        fail("Tối đa 3 tệp mỗi lần gửi.")
    for file in files:
        filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_FILES or len(filename) > 200:
            fail("Chỉ nhận PDF, PNG, JPG hoặc TXT; tên tối đa 200 ký tự.")
        content = file.read(MAX_FILE + 1)
        if not content or len(content) > MAX_FILE:
            fail("Mỗi tệp phải có dữ liệu và không quá 5 MB.")
        valid = {".pdf": content.startswith(b"%PDF-"), ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
                 ".jpg": content.startswith(b"\xff\xd8\xff"), ".jpeg": content.startswith(b"\xff\xd8\xff")}
        if extension in valid and not valid[extension]:
            fail("Nội dung tệp không khớp định dạng.")
        if extension == ".txt":
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                fail("Tệp TXT phải dùng UTF-8.")
        db().execute("INSERT INTO attachments(request_id,message_id,filename,mime_type,content,size) VALUES(?,?,?,?,?,?)",
                     (ticket_id, message_id, filename, ALLOWED_FILES[extension], content, len(content)))


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    secret_file = Path(app.instance_path) / "secret.key"
    if not secret_file.exists():
        secret_file.write_text(secrets.token_hex(32), encoding="utf-8")
    app.config.update(SECRET_KEY=os.getenv("SECRET_KEY") or secret_file.read_text(encoding="utf-8"),
                      DATABASE=os.getenv("DATABASE", str(Path(app.instance_path) / "support.db")),
                      TRAINING_BUGS=os.getenv("TRAINING_BUGS", "1") == "1",
                      MAX_CONTENT_LENGTH=16 * 1024 * 1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    if config:
        app.config.update(config)

    @app.before_request
    def prepare():
        g.app, g.app_db, g.user = app, app.config["DATABASE"], None
        if not request.path.startswith("/api/"):
            return
        if request.method in ("POST", "PATCH", "DELETE"):
            db().execute("BEGIN IMMEDIATE")
        if session.get("user_id"):
            user = one("SELECT id,username,name,role,active,session_version FROM users WHERE id=?", (session["user_id"],))
            if user and user["active"] and user["session_version"] == session.get("version"):
                g.user = user
            else:
                session.clear()
        if request.method in ("POST", "PATCH", "DELETE") and request.path != "/api/login":
            if not g.user:
                fail("Phiên hết hạn. Vui lòng đăng nhập.", 401)
            if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf", "")) or not session.get("csrf"):
                fail("Mã bảo vệ phiên không hợp lệ. Vui lòng tải lại trang.", 403)
            key = request.headers.get("Idempotency-Key")
            if key:
                if len(key) > 100:
                    fail("Idempotency-Key quá dài.")
                if request.mimetype == "multipart/form-data":
                    # Boundaries differ on retry; fingerprint logical fields and files.
                    fingerprint = hashlib.sha256(json.dumps(sorted(request.form.lists()), ensure_ascii=False).encode())
                    for name, file in request.files.items(multi=True):
                        fingerprint.update(json.dumps([name, file.filename], ensure_ascii=False).encode())
                        content = file.read()
                        fingerprint.update(hashlib.sha256(content).digest())
                        file.stream.seek(0)
                    digest = fingerprint.hexdigest()
                else:
                    digest = hashlib.sha256(request.get_data(cache=True)).hexdigest()
                g.retry = (g.user["id"], request.method, request.path, key, digest)
                previous = one("SELECT * FROM idempotency WHERE user_id=? AND method=? AND path=? AND key=?", g.retry[:4])
                if previous:
                    if previous["digest"] != digest:
                        fail("Khóa retry đã được dùng cho dữ liệu khác.", 409)
                    g.replayed = True
                    return app.response_class(previous["body"], status=previous["status"], mimetype="application/json")

    @app.after_request
    def finish(response):
        connection = g.get("db")
        if connection and connection.in_transaction:
            if response.status_code < 400:
                if g.get("retry") and not g.get("replayed"):
                    connection.execute("INSERT INTO idempotency(user_id,method,path,key,digest,body,status) VALUES(?,?,?,?,?,?,?)",
                                       (*g.retry, response.get_data(as_text=True), response.status_code))
                connection.commit()
            else:
                connection.rollback()
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.teardown_appcontext
    def close(_error):
        connection = g.pop("db", None)
        if connection:
            connection.close()

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(sqlite3.IntegrityError)
    def integrity_error(_error):
        return jsonify(error="Dữ liệu trùng hoặc tham chiếu không hợp lệ."), 409

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/api/login")
    def login():
        data = payload()
        username = field(data, "username", 80)
        password = field(data, "password", 200)
        user = one("SELECT * FROM users WHERE username=?", (username,))
        # Always perform a password hash check, even for an unknown account.
        valid = check_password_hash(user["password_hash"] if user else app.config["DUMMY_HASH"], password)
        if not user or not valid or not user["active"]:
            fail("Tài khoản hoặc mật khẩu không hợp lệ.", 401)
        session.clear()
        session.permanent = True
        session.update(user_id=user["id"], version=user["session_version"], csrf=secrets.token_hex(24))
        return jsonify(ok=True)

    @app.post("/api/logout")
    @require()
    def logout():
        # Invalidate copied cookies as well as the browser's current cookie.
        db().execute("UPDATE users SET session_version=session_version+1 WHERE id=?", (g.user["id"],))
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    @require()
    def me():
        return jsonify(user={k: g.user[k] for k in ("id", "username", "name", "role")}, csrf=session["csrf"])

    @app.get("/api/types")
    @require()
    def types():
        return jsonify(items=rows("SELECT * FROM request_types" + ("" if g.user["role"] == "ADMIN" else " WHERE active=1") + " ORDER BY id"))

    @app.post("/api/types")
    @require("ADMIN")
    def create_type():
        data = payload()
        cursor = db().execute("INSERT INTO request_types(code,name,description,active) VALUES(?,?,?,?)",
                              (field(data, "code", 30), field(data, "name", 120), field(data, "description", 1000, False), flag(data, "active")))
        return jsonify(id=cursor.lastrowid), 201

    @app.patch("/api/types/<int:type_id>")
    @require("ADMIN")
    def edit_type(type_id):
        old = one("SELECT * FROM request_types WHERE id=?", (type_id,))
        if not old:
            fail("Không tìm thấy loại yêu cầu.", 404)
        data = {**old, "active": bool(old["active"]), **payload()}
        db().execute("UPDATE request_types SET code=?,name=?,description=?,active=? WHERE id=?",
                     (field(data, "code", 30), field(data, "name", 120), field(data, "description", 1000, False), flag(data, "active", bool(old["active"])), type_id))
        return jsonify(ok=True)

    @app.get("/api/users")
    @require("ADMIN")
    def users():
        return jsonify(items=rows("SELECT id,username,name,role,active FROM users ORDER BY id"))

    @app.post("/api/users")
    @require("ADMIN")
    def create_user():
        data = payload()
        role = data.get("role")
        if role not in ROLES:
            fail("Vai trò không hợp lệ.")
        password = field(data, "password", 200)
        if len(password) < 8:
            fail("Mật khẩu cần ít nhất 8 ký tự.")
        cursor = db().execute("INSERT INTO users(username,name,password_hash,role,active) VALUES(?,?,?,?,?)",
                              (field(data, "username", 80), field(data, "name", 120), generate_password_hash(password), role, flag(data, "active")))
        return jsonify(id=cursor.lastrowid), 201

    @app.patch("/api/users/<int:user_id>")
    @require("ADMIN")
    def edit_user(user_id):
        old = one("SELECT * FROM users WHERE id=?", (user_id,))
        if not old:
            fail("Không tìm thấy tài khoản.", 404)
        data = payload()
        role, active = data.get("role", old["role"]), flag(data, "active", bool(old["active"]))
        if role not in ROLES:
            fail("Vai trò không hợp lệ.")
        if user_id == g.user["id"] and (role != "ADMIN" or not active):
            fail("Không thể tự khóa hoặc tự bỏ quyền quản trị.")
        if role != "STAFF" and one("SELECT id FROM requests WHERE assignee_id=? AND status IN ('IN_PROGRESS','WAITING_STUDENT')", (user_id,)):
            fail("Cán bộ cần hoàn tất các yêu cầu đang phụ trách trước khi đổi vai trò.", 409)
        db().execute("UPDATE users SET name=?,role=?,active=?,session_version=session_version+1 WHERE id=?",
                     (field({**old, **data}, "name", 120), role, active, user_id))
        if "password" in data:
            password = field(data, "password", 200)
            if len(password) < 8:
                fail("Mật khẩu cần ít nhất 8 ký tự.")
            db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(password), user_id))
        return jsonify(ok=True)

    @app.get("/api/requests")
    @require("STUDENT", "STAFF")
    def list_requests():
        where, args = [], []
        if g.user["role"] == "STUDENT":
            where.append("r.student_id=?")
            args.append(g.user["id"])
        if request.args.get("mine") == "1" and g.user["role"] == "STAFF":
            where.append("r.assignee_id=?")
            args.append(g.user["id"])
        base = " WHERE " + " AND ".join(where) if where else ""
        counts = {s: 0 for s in STATUSES}
        counts.update({r["status"]: r["total"] for r in rows("SELECT r.status,COUNT(*) total FROM requests r" + base + " GROUP BY r.status", args)})
        status, query = request.args.get("status", ""), request.args.get("q", "").strip()
        if status:
            if status not in STATUSES:
                fail("Trạng thái không hợp lệ.")
            where.append("r.status=?")
            args.append(status)
        if query:
            if len(query) > 200:
                fail("Từ khóa tối đa 200 ký tự.")
            if enabled(app, "B08"):
                where.append("(instr(r.title,?)>0 OR instr(r.code,?)>0)")
            else:
                where.append("(instr(casefold(r.title),casefold(?))>0 OR instr(casefold(r.code),casefold(?))>0)")
            args.extend([query, query])
        db().create_function("casefold", 1, lambda value: value.casefold())
        sql = "SELECT r.*,t.name type_name,u.name student_name,a.name assignee_name FROM requests r JOIN request_types t ON t.id=r.type_id JOIN users u ON u.id=r.student_id LEFT JOIN users a ON a.id=r.assignee_id"
        sql += " WHERE " + " AND ".join(where) if where else ""
        return jsonify(items=rows(sql + " ORDER BY r.updated_at DESC,r.id DESC", args), counts=counts)

    @app.post("/api/requests")
    @require("STUDENT")
    def create_request():
        data = payload()
        if enabled(app, "B01"):
            title = data.get("title", "")
            if not isinstance(title, str) or not title or len(title) > 200:
                fail("Tiêu đề bắt buộc nhập, tối đa 200 ký tự.")
        else:
            title = field(data, "title", 200)
        content = field(data, "content")
        type_id = positive_id(data.get("type_id"))
        request_type = one("SELECT * FROM request_types WHERE id=?", (type_id,))
        if not request_type or (not request_type["active"] and not enabled(app, "B02")):
            fail("Loại yêu cầu không tồn tại hoặc đã ngừng hoạt động.")
        timestamp = now()
        cursor = db().execute("INSERT INTO requests(code,student_id,type_id,title,content,status,created_at,updated_at) VALUES(NULL,?,?,?,?, 'NEW',?,?)",
                              (g.user["id"], type_id, title, content, timestamp, timestamp))
        ticket_id = cursor.lastrowid
        code = f"HT-{ticket_id:05d}"
        db().execute("UPDATE requests SET code=? WHERE id=?", (code, ticket_id))
        attachments(ticket_id)
        audit(ticket_id, "CREATE", None, "NEW")
        notify(ticket_id, g.user["id"], "CREATE")
        return jsonify(id=ticket_id, code=code), 201

    @app.get("/api/requests/<int:ticket_id>")
    @require("STUDENT", "STAFF")
    def detail(ticket_id):
        ticket_for(ticket_id)
        ticket = one("SELECT r.*,t.name type_name,u.name student_name,a.name assignee_name FROM requests r JOIN request_types t ON t.id=r.type_id JOIN users u ON u.id=r.student_id LEFT JOIN users a ON a.id=r.assignee_id WHERE r.id=?", (ticket_id,))
        return jsonify(item=ticket,
                       messages=rows("SELECT m.*,u.name sender_name,u.role sender_role FROM messages m JOIN users u ON u.id=m.sender_id WHERE request_id=? ORDER BY m.id", (ticket_id,)),
                       history=rows("SELECT h.*,u.name actor_name FROM history h JOIN users u ON u.id=h.actor_id WHERE request_id=? ORDER BY h.id", (ticket_id,)),
                       attachments=rows("SELECT id,message_id,filename,size FROM attachments WHERE request_id=? ORDER BY id", (ticket_id,)))

    @app.post("/api/requests/<int:ticket_id>/action")
    @require("STUDENT", "STAFF")
    def action(ticket_id):
        data = payload()
        action_name = data.get("action")
        ticket = ticket_for(ticket_id)
        status, role = ticket["status"], g.user["role"]
        body = field(data, "body", required=False)
        if action_name == "cancel" and role == "STUDENT":
            allowed = ("NEW", "IN_PROGRESS") if enabled(app, "B03") else ("NEW",)
            if status not in allowed:
                fail("Chỉ được hủy yêu cầu chưa tiếp nhận.", 409)
            transition(ticket, "CANCELLED", "CANCEL")
        elif action_name == "reopen" and role == "STUDENT":
            allowed = ("COMPLETED", "REJECTED") if enabled(app, "B07") else ("COMPLETED",)
            if status not in allowed:
                fail("Chỉ được mở lại yêu cầu đã hoàn tất.", 409)
            assignee = one("SELECT id FROM users WHERE id=? AND role='STAFF' AND active=1", (ticket["assignee_id"],))
            if not assignee:
                db().execute("UPDATE requests SET assignee_id=NULL WHERE id=?", (ticket_id,))
                ticket["assignee_id"] = None
            transition(ticket, "IN_PROGRESS" if assignee else "NEW", "REOPEN")
        elif action_name == "accept" and role == "STAFF":
            if status != "NEW" or ticket["assignee_id"]:
                fail("Yêu cầu đã được nhận hoặc đã kết thúc.", 409)
            db().execute("UPDATE requests SET assignee_id=? WHERE id=?", (g.user["id"], ticket_id))
            transition(ticket, "IN_PROGRESS", "ACCEPT")
        elif action_name in ("ask", "complete", "reject") and role == "STAFF":
            if action_name == "reject" and status == "NEW":
                db().execute("UPDATE requests SET assignee_id=? WHERE id=?", (g.user["id"], ticket_id))
            else:
                ticket_for(ticket_id, writing=True)
            valid_statuses = ("NEW", "IN_PROGRESS") if action_name == "reject" else ("IN_PROGRESS",)
            if status not in valid_statuses:
                fail("Thao tác không hợp lệ với trạng thái hiện tại.", 409)
            allow_empty = (action_name == "complete" and enabled(app, "B04")) or (action_name == "reject" and enabled(app, "B05"))
            if not body and not allow_empty:
                fail("Phải nhập nội dung yêu cầu bổ sung, kết quả hoặc lý do từ chối.")
            if body:
                db().execute("INSERT INTO messages(request_id,sender_id,body,created_at) VALUES(?,?,?,?)", (ticket_id, g.user["id"], body, now()))
            target = {"ask": "WAITING_STUDENT", "complete": "COMPLETED", "reject": "REJECTED"}[action_name]
            transition(ticket, target, {"ask": "ASK", "complete": "COMPLETE", "reject": "REJECT"}[action_name])
        else:
            fail("Thao tác không hợp lệ hoặc không đúng vai trò.", 403)
        return jsonify(ok=True)

    @app.post("/api/requests/<int:ticket_id>/messages")
    @require("STUDENT", "STAFF")
    def message(ticket_id):
        ticket = ticket_for(ticket_id, writing=True)
        role = g.user["role"]
        if (role == "STUDENT" and ticket["status"] != "WAITING_STUDENT") or (role == "STAFF" and ticket["status"] not in ("IN_PROGRESS", "WAITING_STUDENT")):
            fail("Không thể gửi trao đổi ở trạng thái này.", 409)
        body = field(payload(), "body", required=False)
        if not body and not request.files.getlist("files"):
            fail("Cần nhập nội dung hoặc đính kèm tệp.")
        cursor = db().execute("INSERT INTO messages(request_id,sender_id,body,created_at) VALUES(?,?,?,?)", (ticket_id, g.user["id"], body, now()))
        attachments(ticket_id, cursor.lastrowid)
        if role == "STUDENT":
            target = "WAITING_STUDENT" if enabled(app, "B06") else "IN_PROGRESS"
            transition(ticket, target, "SUPPLEMENT")
        else:
            db().execute("UPDATE requests SET updated_at=? WHERE id=?", (now(), ticket_id))
            audit(ticket_id, "MESSAGE", ticket["status"], ticket["status"])
            notify(ticket_id, ticket["student_id"], "MESSAGE")
        return jsonify(id=cursor.lastrowid), 201

    @app.get("/api/attachments/<int:attachment_id>")
    @require("STUDENT", "STAFF")
    def download(attachment_id):
        attachment = one("SELECT * FROM attachments WHERE id=?", (attachment_id,))
        if not attachment:
            fail("Không tìm thấy tệp.", 404)
        ticket_for(attachment["request_id"])
        from io import BytesIO
        from flask import send_file
        return send_file(BytesIO(attachment["content"]), mimetype=attachment["mime_type"], as_attachment=True, download_name=attachment["filename"])

    @app.get("/api/notifications")
    @require()
    def notifications():
        return jsonify(items=rows("SELECT n.*,r.code,r.title FROM notifications n JOIN requests r ON r.id=n.request_id WHERE recipient_id=? ORDER BY n.id DESC", (g.user["id"],)))

    @app.post("/api/notifications/<int:notification_id>/read")
    @require()
    def read_notification(notification_id):
        if not one("SELECT id FROM notifications WHERE id=? AND recipient_id=?", (notification_id, g.user["id"])):
            fail("Không tìm thấy thông báo.", 404)
        if not enabled(app, "B09"):
            db().execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))
        return jsonify(ok=True)

    app.config["DUMMY_HASH"] = generate_password_hash(secrets.token_hex(16))

    @app.cli.command("init-db")
    @click.option("--demo", is_flag=True, help="Create demo accounts and requests on a new database.")
    def init_command(demo):
        initialize(app, demo=demo)
        click.echo("Đã khởi tạo SQLite. Chạy: python app.py")

    return app


def initialize(app, demo=False):
    with app.app_context():
        g.app_db = app.config["DATABASE"]
        db().execute("PRAGMA journal_mode=WAL")
        db().executescript((Path(__file__).parent / "schema.sql").read_text(encoding="utf-8"))
        if demo and not one("SELECT id FROM users LIMIT 1"):
            db().execute("BEGIN IMMEDIATE")
            password_hash = generate_password_hash("Demo@123")
            for username, name, role in [("sv01", "Nguyễn Minh Anh", "STUDENT"), ("sv02", "Trần Quốc Bảo", "STUDENT"), ("cb01", "Lê Thu Hà", "STAFF"), ("cb02", "Phạm Đức Long", "STAFF"), ("admin", "Quản trị viên", "ADMIN")]:
                db().execute("INSERT INTO users(username,name,password_hash,role) VALUES(?,?,?,?)", (username, name, password_hash, role))
            for code, name, description in [("HOCVU", "Học vụ", "Đăng ký học phần, bảng điểm và lịch học"), ("HOCPHI", "Học phí", "Học phí, miễn giảm và xác nhận thanh toán"), ("GIAYTO", "Giấy tờ & xác nhận", "Xác nhận sinh viên và các giấy tờ liên quan")]:
                db().execute("INSERT INTO request_types(code,name,description) VALUES(?,?,?)", (code, name, description))
            samples = [(1, 3, "Xin giấy xác nhận sinh viên", "Em cần giấy xác nhận để bổ sung hồ sơ học bổng.", "NEW"),
                       (1, 2, "Kiểm tra học phí học kỳ I", "Em đã thanh toán nhưng chưa thấy cập nhật.", "IN_PROGRESS"),
                       (1, 1, "Đề nghị kiểm tra điểm học phần", "Em cần kiểm tra điểm quá trình môn Cơ sở dữ liệu.", "WAITING_STUDENT"),
                       (1, 3, "Xác nhận lịch học", "Em cần xác nhận thời khóa biểu hiện tại.", "COMPLETED"),
                       (2, 1, "Hỗ trợ đăng ký học phần", "Em chưa đăng ký được học phần tự chọn.", "NEW")]
            for i, (student_id, type_id, title, content, status) in enumerate(samples, 1):
                stamp = now()
                assigned = 3 if status != "NEW" else None
                db().execute("INSERT INTO requests(code,student_id,type_id,title,content,status,assignee_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (f"HT-{i:05d}", student_id, type_id, title, content, status, assigned, stamp, stamp))
                db().execute("INSERT INTO history(request_id,action,from_status,to_status,actor_id,created_at) VALUES(?,'CREATE',NULL,'NEW',?,?)", (i, student_id, stamp))
                if assigned:
                    db().execute("INSERT INTO history(request_id,action,from_status,to_status,actor_id,created_at) VALUES(?,'ACCEPT','NEW','IN_PROGRESS',3,?)", (i, stamp))
                if status in ("WAITING_STUDENT", "COMPLETED"):
                    body, action_name = ("Em vui lòng gửi ảnh bảng điểm để đối chiếu.", "ASK") if status == "WAITING_STUDENT" else ("Đã xác nhận thời khóa biểu của em.", "COMPLETE")
                    db().execute("INSERT INTO messages(request_id,sender_id,body,created_at) VALUES(?,3,?,?)", (i, body, stamp))
                    db().execute("INSERT INTO history(request_id,action,from_status,to_status,actor_id,created_at) VALUES(?,?,'IN_PROGRESS',?,3,?)", (i, action_name, status, stamp))
                db().execute("INSERT INTO notifications(recipient_id,request_id,event_type,created_at) VALUES(?,?,?,?)", (student_id, i, "CREATE" if status == "NEW" else status, stamp))
            db().commit()


if __name__ == "__main__":
    application = create_app()
    if not Path(application.config["DATABASE"]).exists():
        initialize(application, demo=True)
    application.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")), debug=False)
