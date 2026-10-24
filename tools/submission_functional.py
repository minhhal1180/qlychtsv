"""Executable functional test dossier. Always assert the required correct behavior.

Run: python tools/submission_functional.py --mode both
Each case uses its own temporary SQLite database. Results are self-test evidence,
not a claim of independent testing by a paired student.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app, initialize

CASES = []
OUTPUT_BASE = ROOT / 'submission'
RESPONSIBLE_TESTER = 'Bùi Xuân Minh – 23110193'
RUN_SCOPE = 'Tự kiểm thử hệ thống StudentCare; chưa thay cho kiểm thử chéo bạn cặp.'
SOURCE_HASHES = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                 for name in ("app.py", "bugs.py", "schema.sql")}


def case(fr, title, expected, *, preconditions="Database mẫu mới; 5 tài khoản và 3 loại yêu cầu hoạt động.", data=None, steps=None, bug=None, kind="Positive", case_id=None, technique=None, requirements=None):
    def register(fn):
        CASES.append({"id": case_id or f"TC-F-{len(CASES)+1:03d}", "function_id": fr,
                      "title": title, "preconditions": preconditions, "data": data or {},
                      "steps": steps or ["Đăng nhập vai trò được nêu trong tiêu đề.", "Gọi API với dữ liệu của testcase.", "Đối chiếu HTTP và dữ liệu trả về với expected."],
                      "expected": expected, "bug_id": bug or "", "test_kind": kind,
                      "technique": technique or {"Boundary":"Boundary value analysis", "Permission":"Decision table / quyền", "State":"State transition", "Retry":"State transition"}.get(kind,"Equivalence partitioning"),
                      "requirements":requirements or [fr], "fn": fn})
        return fn
    return register


class Sandbox:
    def __init__(self, database, training):
        self.database = database
        self.app = create_app({"TESTING": True, "DATABASE": database, "SECRET_KEY": "self-test-only-not-server-key",
                               "TRAINING_BUGS": training, "SESSION_COOKIE_SECURE": False})
        self.clients = {}
        self.trace = []

    def capture(self, method, path, username, payload, response):
        if response.is_json:
            body = response.get_json()
            if isinstance(body, dict) and "csrf" in body:
                body = {**body, "csrf": "[redacted]"}
        else:
            body = {"bytes": len(response.data), "content_type": response.content_type,
                    "preview": response.data[:100].decode("utf-8", errors="replace")}
        if isinstance(payload, dict):
            payload = {k: "[redacted]" if k == "password" else v for k, v in payload.items()}
        self.trace.append({"method": method, "path": path, "actor": username,
                           "input": payload, "http_status": response.status_code, "response": body})
        return response

    def client(self, username):
        if username not in self.clients:
            client = self.app.test_client()
            response = client.post("/api/login", json={"username": username, "password": "Demo@123"})
            self.capture("POST", "/api/login", username, {"username": username, "password": "Demo@123"}, response)
            self.eq(response.status_code, 200, "Đăng nhập tiền điều kiện")
            response = client.get("/api/me")
            self.capture("GET", "/api/me", username, None, response)
            self.eq(response.status_code, 200, "Lấy phiên tiền điều kiện")
            self.clients[username] = (client, response.json["csrf"])
        return self.clients[username]

    def get(self, actor, path):
        client = self.client(actor)[0] if actor else self.app.test_client()
        return self.capture("GET", "/api" + path, actor or "anonymous", None, client.get("/api" + path))

    def request(self, actor, method, path, data=None, headers=None, multipart=None):
        client, token = self.client(actor) if actor else (self.app.test_client(), "")
        request_headers = {"X-CSRF-Token": token, **(headers or {})}
        if multipart is None:
            response = client.open("/api" + path, method=method, json=data if data is not None else {}, headers=request_headers)
            shown = data
        else:
            response = client.open("/api" + path, method=method, data=multipart,
                                   content_type="multipart/form-data", headers=request_headers)
            shown = {k: "[multipart file bytes]" if k == "files" else v for k, v in multipart.items()}
        return self.capture(method, "/api" + path, actor or "anonymous", shown, response)

    def post(self, actor, path, data=None, **kwargs):
        return self.request(actor, "POST", path, data, **kwargs)

    def patch(self, path, data):
        return self.request("admin", "PATCH", path, data)

    def login(self, username, password):
        client = self.app.test_client()
        response = client.post("/api/login", json={"username": username, "password": password})
        return self.capture("POST", "/api/login", "anonymous", {"username": username, "password": password}, response)

    def eq(self, actual, expected, label="Đối chiếu"):
        self.trace.append({"assertion": label, "expected": expected, "actual": actual, "passed": actual == expected})
        if actual != expected:
            raise AssertionError(f"{label}: expected={expected!r}, actual={actual!r}")

    def true(self, value, label="Điều kiện phải đúng"):
        self.eq(bool(value), True, label)

    def sql(self, statement, args=()):
        with closing(sqlite3.connect(self.database)) as connection:
            result = connection.execute(statement, args).fetchall()
            connection.commit()
        return result

    def create(self, actor="sv01", **override):
        response = self.post(actor, "/requests", {"type_id": 1, "title": "Hỗ trợ học vụ", "content": "Em cần hỗ trợ nội dung học vụ.", **override})
        self.eq(response.status_code, 201, "Tạo yêu cầu tiền điều kiện")
        return response.json["id"]

    def detail(self, ticket, actor="sv01"):
        response = self.get(actor, f"/requests/{ticket}")
        self.eq(response.status_code, 200, "Đọc chi tiết")
        return response.json

    def action(self, ticket, name, body="", actor="cb01"):
        return self.post(actor, f"/requests/{ticket}/action", {"action": name, "body": body})

    def accepted(self):
        ticket = self.create()
        self.eq(self.action(ticket, "accept").status_code, 200, "Tiếp nhận tiền điều kiện")
        return ticket

    def waiting(self):
        ticket = self.accepted()
        self.eq(self.action(ticket, "ask", "Bổ sung bảng điểm.").status_code, 200, "Yêu cầu bổ sung tiền điều kiện")
        return ticket


# FR-01: login validation and role-specific sessions.
for actor, role in [("sv01", "STUDENT"), ("cb01", "STAFF"), ("admin", "ADMIN")]:
    @case("FR-01", f"Đăng nhập hợp lệ {actor} trả đúng vai trò {role}", f"HTTP 200; role={role}.", data={"username":actor,"password":"Demo@123 (tài khoản mẫu)"})
    def login_valid(s, actor=actor, role=role):
        response = s.get(actor, "/me")
        s.eq(response.status_code, 200)
        s.eq(response.json["user"]["role"], role, "Vai trò phiên")

for username, password, status, label in [("sv01", "wrong-pass",401,"Sai mật khẩu"),("not-exists","wrong-pass",401,"Tài khoản không tồn tại"),("", "Demo@123",400,"Tên tài khoản rỗng"),("sv01","",400,"Mật khẩu rỗng")]:
    @case("FR-01", label, f"HTTP {status}; không tạo phiên.", data={"username":username,"password":"[test value]"}, kind="Negative")
    def login_invalid(s, username=username, password=password, status=status):
        s.eq(s.login(username,password).status_code, status)

@case("FR-01", "Tài khoản bị khóa không đăng nhập được", "HTTP 401; lỗi giống sai thông tin đăng nhập.", kind="Negative")
def locked_login(s):
    s.eq(s.patch("/users/1", {"active":False}).status_code,200)
    response = s.login("sv01","Demo@123")
    s.eq(response.status_code,401)
    s.eq(response.json,s.login("sv01","wrong").json,"Thông báo đăng nhập không tiết lộ trạng thái tài khoản")

# FR-02: logout and session invalidation.
@case("FR-02", "Đăng xuất kết thúc phiên hiện tại", "Logout HTTP 200; GET /me sau logout trả 401.")
def logout_current(s):
    client,_token=s.client("sv01")
    s.eq(s.post("sv01","/logout").status_code,200)
    s.eq(client.get("/api/me").status_code,401)

@case("FR-02", "Cookie sao chép bị thu hồi sau đăng xuất", "Cookie cũ không thể khôi phục phiên; HTTP 401.", kind="Negative")
def logout_copied(s):
    client,_token=s.client("sv01")
    cookie=client.get_cookie("session").value
    s.eq(s.post("sv01","/logout").status_code,200)
    client.set_cookie("session",cookie)
    s.eq(client.get("/api/me").status_code,401)

@case("FR-02", "Phiên quá hạn không dùng được", "GET /me trả HTTP 401 sau thời hạn phiên.", kind="Boundary")
def expired(s):
    client,_token=s.client("sv01")
    s.app.config["PERMANENT_SESSION_LIFETIME"]=timedelta(seconds=-1)
    s.eq(client.get("/api/me").status_code,401)

@case("FR-02", "Người chưa đăng nhập không xem yêu cầu", "GET /requests trả HTTP 401.",kind="Permission")
def anonymous_requests(s): s.eq(s.get(None,"/requests").status_code,401)

@case("FR-02", "API ghi dữ liệu cần token CSRF", "POST thiếu token CSRF trả HTTP 403; không tạo yêu cầu.",kind="Permission")
def csrf(s):
    client,_token=s.client("sv01")
    before=s.sql("SELECT COUNT(*) FROM requests")[0][0]
    response=client.post("/api/requests",json={"type_id":1,"title":"test","content":"test"})
    s.capture("POST","/api/requests","sv01",{"csrf":"missing"},response)
    s.eq(response.status_code,403)
    s.eq(s.sql("SELECT COUNT(*) FROM requests")[0][0],before)

# FR-03 / FR-04: account management.
@case("FR-03", "Admin tạo tài khoản sinh viên hợp lệ", "HTTP 201; tài khoản mới đăng nhập được, role STUDENT.")
def new_user(s):
    response=s.post("admin","/users",{"username":"sv03","name":"Sinh viên mới","password":"Demo@456","role":"STUDENT"})
    s.eq(response.status_code,201)
    s.eq(s.login("sv03","Demo@456").status_code,200)

@case("FR-03", "Tạo tài khoản trùng username", "HTTP 409; không tạo thêm bản ghi.",kind="Negative")
def duplicate_user(s):
    s.eq(s.post("admin","/users",{"username":"sv01","name":"Trùng","password":"Demo@456","role":"STUDENT"}).status_code,409)

@case("FR-03", "Mật khẩu cấp mới ít hơn 8 ký tự", "HTTP 400.",kind="Boundary",data={"password_length":7})
def short_password(s):
    s.eq(s.post("admin","/users",{"username":"sv03","name":"Test","password":"1234567","role":"STUDENT"}).status_code,400)

@case("FR-03", "Vai trò cấp mới không thuộc danh mục", "HTTP 400.",kind="Negative")
def invalid_role(s):
    s.eq(s.post("admin","/users",{"username":"sv03","name":"Test","password":"Demo@456","role":"OWNER"}).status_code,400)

@case("FR-03", "Admin đổi tên và đặt lại mật khẩu", "PATCH 200; mật khẩu mới đăng nhập được, mật khẩu cũ trả 401.")
def edit_password(s):
    s.eq(s.patch("/users/2",{"name":"Tên cập nhật","password":"Changed@123"}).status_code,200)
    s.eq(s.login("sv02","Changed@123").status_code,200)
    s.eq(s.login("sv02","Demo@123").status_code,401)
    s.true(any(u["name"]=="Tên cập nhật" for u in s.get("admin","/users").json["items"]))

@case("FR-04", "Sinh viên không quản trị tài khoản", "GET /users và POST /users đều trả HTTP 403.",kind="Permission")
def student_user_admin(s):
    s.eq(s.get("sv01","/users").status_code,403)
    s.eq(s.post("sv01","/users",{}).status_code,403)

@case("FR-04", "Khóa tài khoản thu hồi phiên đã đăng nhập", "Phiên sv01 trước khi khóa trả 401 ngay sau PATCH.",kind="Permission")
def lock_session(s):
    client,_token=s.client("sv01")
    s.eq(s.patch("/users/1",{"active":False}).status_code,200)
    s.eq(client.get("/api/me").status_code,401)

@case("FR-04", "Admin không được tự khóa mình", "PATCH /users/5 active=false trả HTTP 400; admin vẫn active.",kind="Negative")
def self_lock(s):
    s.eq(s.patch("/users/5",{"active":False}).status_code,400)
    s.eq(s.sql("SELECT active FROM users WHERE id=5")[0][0],1)

@case("FR-04", "Admin không được tự bỏ quyền admin", "PATCH /users/5 role=STUDENT trả HTTP 400.",kind="Negative")
def self_demote(s): s.eq(s.patch("/users/5",{"role":"STUDENT"}).status_code,400)

@case("FR-04", "Cán bộ có việc đang xử lý không đổi sang sinh viên", "PATCH /users/3 role=STUDENT trả HTTP 409; role vẫn STAFF.",kind="State")
def assignee_role(s):
    s.eq(s.patch("/users/3",{"role":"STUDENT"}).status_code,409)
    s.eq(s.sql("SELECT role FROM users WHERE id=3")[0][0],"STAFF")

# FR-05: category lifecycle.
@case("FR-05", "Admin tạo loại yêu cầu hợp lệ", "HTTP 201; loại mới xuất hiện trong danh mục sinh viên.")
def create_type(s):
    response=s.post("admin","/types",{"code":"KHAC","name":"Hỗ trợ khác","description":"Mô tả"})
    s.eq(response.status_code,201)
    s.true(any(x["id"]==response.json["id"] for x in s.get("sv01","/types").json["items"]))

@case("FR-05", "Mã danh mục trùng bị từ chối", "HTTP 409 khi code=HOCVU đã có.",kind="Negative")
def duplicate_type(s): s.eq(s.post("admin","/types",{"code":"HOCVU","name":"Trùng"}).status_code,409)

@case("FR-05", "Loại ngừng hoạt động không xuất hiện trong form mới", "Danh sách sinh viên không chứa type_id=1; admin vẫn thấy bản ghi.")
def inactive_type_list(s):
    s.eq(s.patch("/types/1",{"active":False}).status_code,200)
    s.true(1 not in [x["id"] for x in s.get("sv01","/types").json["items"]])
    s.true(1 in [x["id"] for x in s.get("admin","/types").json["items"]])

@case("FR-05", "Sửa tên loại giữ tham chiếu yêu cầu cũ", "PATCH 200; chi tiết yêu cầu cũ hiển thị tên loại mới.")
def rename_type(s):
    ticket=s.create()
    s.eq(s.patch("/types/1",{"name":"Học vụ mới"}).status_code,200)
    s.eq(s.detail(ticket)["item"]["type_name"],"Học vụ mới")

@case("FR-05", "Sinh viên không tạo hoặc sửa danh mục", "POST và PATCH /types trả HTTP 403.",kind="Permission")
def category_permissions(s):
    s.eq(s.post("sv01","/types",{"code":"X","name":"X"}).status_code,403)
    s.eq(s.request("sv01","PATCH","/types/1",{"active":False}).status_code,403)

# FR-06: creation and validation.
@case("FR-06", "Tạo yêu cầu hợp lệ có mã duy nhất và NEW", "HTTP 201; hai mã khác nhau; student_id=1, trạng thái NEW.")
def create_request(s):
    first=s.create(); second=s.create()
    a,b=s.detail(first)["item"],s.detail(second)["item"]
    s.eq(a["status"],"NEW");s.eq(a["student_id"],1);s.true(a["code"]!=b["code"])

for title,label in [("","Tiêu đề rỗng"),("T"*201,"Tiêu đề vượt 200 ký tự")]:
    @case("FR-06",label,"POST /requests trả HTTP 400.",kind="Boundary",data={"title_length":len(title)})
    def bad_title(s,title=title):
        s.eq(s.post("sv01","/requests",{"type_id":1,"title":title,"content":"Nội dung"}).status_code,400)

@case("FR-06", "Tiêu đề chỉ khoảng trắng không hợp lệ", "HTTP 400; không tạo yêu cầu.",kind="Negative",bug="B01",data={"title":"   "})
def whitespace_title(s): s.eq(s.post("sv01","/requests",{"type_id":1,"title":"   ","content":"Nội dung"}).status_code,400)

@case("FR-06", "Nội dung chỉ khoảng trắng không hợp lệ", "HTTP 400.",kind="Negative")
def whitespace_content(s): s.eq(s.post("sv01","/requests",{"type_id":1,"title":"Tiêu đề","content":"   "}).status_code,400)

@case("FR-06", "Loại không tồn tại không tạo yêu cầu", "HTTP 400.",kind="Negative")
def missing_category(s): s.eq(s.post("sv01","/requests",{"type_id":99999,"title":"Tiêu đề","content":"Nội dung"}).status_code,400)

@case("FR-06", "Loại bị ngừng sau khi mở form phải bị từ chối", "POST type_id=1 sau khi ngừng hoạt động trả HTTP 400.",kind="State",bug="B02")
def inactive_category_create(s):
    s.eq(s.patch("/types/1",{"active":False}).status_code,200)
    s.eq(s.post("sv01","/requests",{"type_id":1,"title":"Form cũ","content":"Nội dung"}).status_code,400)

@case("FR-06", "Cán bộ không được tạo yêu cầu sinh viên", "POST /requests với cb01 trả HTTP 403.",kind="Permission")
def staff_create(s): s.eq(s.post("cb01","/requests",{"type_id":1,"title":"Tiêu đề","content":"Nội dung"}).status_code,403)

@case("FR-06", "Gửi lại cùng Idempotency-Key không tạo trùng", "Hai POST cùng key/nội dung trả cùng id; đúng một history và thông báo.",kind="Retry")
def retry_create(s):
    body={"type_id":1,"title":"Retry","content":"Nội dung"}
    headers={"Idempotency-Key":"TC-F-create-retry"}
    first=s.post("sv01","/requests",body,headers=headers);second=s.post("sv01","/requests",body,headers=headers)
    s.eq(first.status_code,201);s.eq(second.status_code,201);s.eq(first.json,second.json)
    s.eq(len(s.detail(first.json["id"])["history"]),1)
    s.eq(s.sql("SELECT COUNT(*) FROM notifications WHERE request_id=?",(first.json["id"],))[0][0],1)

# FR-07: lists and filters.
@case("FR-07", "Danh sách sinh viên chỉ chứa yêu cầu của mình", "sv01 chỉ student_id=1; không thấy yêu cầu sv02.",kind="Permission")
def own_list(s):
    items=s.get("sv01","/requests").json["items"]
    s.eq(len(items),4);s.true(all(x["student_id"]==1 for x in items))

@case("FR-07", "Cán bộ thấy toàn bộ hàng đợi chung", "cb01 thấy cả student_id 1 và 2.")
def staff_list(s):
    items=s.get("cb01","/requests").json["items"]
    s.eq({x["student_id"] for x in items},{1,2})

@case("FR-07", "Lọc trạng thái NEW", "Danh sách chỉ có trạng thái NEW; số đếm vẫn theo toàn bộ dữ liệu được phép.")
def status_filter(s):
    response=s.get("sv01","/requests?status=NEW")
    s.eq(response.status_code,200);s.true(all(x["status"]=="NEW" for x in response.json["items"]))
    s.eq(sum(response.json["counts"].values()),4)

@case("FR-07", "Lọc Tôi phụ trách", "mine=1 chỉ trả assignee_id=3 cho cb01.")
def mine_filter(s):
    items=s.get("cb01","/requests?mine=1").json["items"]
    s.true(len(items)>0);s.true(all(x["assignee_id"]==3 for x in items))

@case("FR-07", "Tìm theo tiêu đề", "Tìm chuỗi con 'Xác nhận' trả yêu cầu xác nhận lịch học.")
def title_search(s):
    items=s.get("sv01","/requests?"+urlencode({"q":"Xác nhận"})).json["items"]
    s.true(any(x["id"]==4 for x in items))

@case("FR-07", "Tìm theo mã yêu cầu duy nhất", "Tìm đúng code mới tạo phải trả đúng id.",kind="Positive",bug="B08")
def code_search(s):
    ticket=s.create(title="Nội dung không chứa mã")
    code=s.detail(ticket)["item"]["code"]
    items=s.get("sv01","/requests?"+urlencode({"q":code})).json["items"]
    s.eq([x["id"] for x in items],[ticket])

@case("FR-07", "Bộ lọc trạng thái không hợp lệ", "status=INVALID trả HTTP 400.",kind="Negative")
def bad_status(s): s.eq(s.get("sv01","/requests?status=INVALID").status_code,400)

# FR-08: detail and access.
@case("FR-08", "Chủ yêu cầu xem đầy đủ nội dung và lịch sử", "Chi tiết chứa item, messages, history, attachments; CREATE có actor/time.")
def detail_shape(s):
    ticket=s.create();detail=s.detail(ticket)
    s.eq(set(detail),{"item","messages","history","attachments"})
    s.eq(detail["history"][0]["action"],"CREATE");s.eq(detail["history"][0]["actor_id"],1)
    s.true(bool(detail["history"][0]["created_at"]))

@case("FR-08", "Sinh viên khác không xem chi tiết dù biết ID", "sv02 GET yêu cầu sv01 trả 403.",kind="Permission")
def other_detail(s): s.eq(s.get("sv02",f"/requests/{s.create()}").status_code,403)

@case("FR-08", "Admin không gọi API xử lý nghiệp vụ", "Admin GET chi tiết trả 403.",kind="Permission")
def admin_detail(s): s.eq(s.get("admin",f"/requests/{s.create()}").status_code,403)

@case("FR-08", "ID yêu cầu không tồn tại", "GET /requests/99999 trả HTTP 404.",kind="Negative")
def missing_detail(s): s.eq(s.get("sv01","/requests/99999").status_code,404)

# FR-09 / FR-10: cancellation and assignment.
@case("FR-09", "Hủy NEW thuộc mình", "HTTP 200; CANCELLED; sự kiện CANCEL lưu actor=1.")
def cancel_new(s):
    ticket=s.create();s.eq(s.action(ticket,"cancel",actor="sv01").status_code,200)
    detail=s.detail(ticket);s.eq(detail["item"]["status"],"CANCELLED");s.eq(detail["history"][-1]["action"],"CANCEL")

@case("FR-09", "Chặn hủy sau khi cán bộ đã tiếp nhận", "HTTP 409; giữ IN_PROGRESS và assignee_id=3.",kind="State",bug="B03")
def cancel_accepted(s):
    ticket=s.accepted();s.eq(s.action(ticket,"cancel",actor="sv01").status_code,409)
    s.eq(s.detail(ticket)["item"]["status"],"IN_PROGRESS")

@case("FR-09", "Sinh viên không hủy yêu cầu người khác", "sv02 POST cancel yêu cầu sv01 trả 403.",kind="Permission")
def cancel_other(s): s.eq(s.action(s.create(),"cancel",actor="sv02").status_code,403)

@case("FR-10", "Cán bộ tiếp nhận NEW", "HTTP 200; assignee_id=3; IN_PROGRESS; lịch sử ACCEPT.")
def accept_new(s):
    ticket=s.accepted();detail=s.detail(ticket)
    s.eq(detail["item"]["assignee_id"],3);s.eq(detail["item"]["status"],"IN_PROGRESS");s.eq(detail["history"][-1]["action"],"ACCEPT")

@case("FR-10", "Cán bộ thứ hai không nhận lại hồ sơ", "cb02 nhận ticket đã được cb01 nhận trả 409; giữ assignee_id=3.",kind="State")
def second_accept(s):
    ticket=s.accepted();s.eq(s.action(ticket,"accept",actor="cb02").status_code,409);s.eq(s.detail(ticket)["item"]["assignee_id"],3)

@case("FR-10", "Sinh viên không tiếp nhận yêu cầu", "sv01 action accept trả 403; giữ NEW.",kind="Permission")
def student_accept(s):
    ticket=s.create();s.eq(s.action(ticket,"accept",actor="sv01").status_code,403);s.eq(s.detail(ticket)["item"]["status"],"NEW")

@case("FR-10", "Không tiếp nhận yêu cầu đã hủy", "Cán bộ accept CANCELLED trả HTTP 409.",kind="State")
def accept_cancelled(s):
    ticket=s.create();s.eq(s.action(ticket,"cancel",actor="sv01").status_code,200);s.eq(s.action(ticket,"accept").status_code,409)

# FR-11 / FR-12: information requests and response flow.
@case("FR-11", "Cán bộ yêu cầu bổ sung có nội dung", "WAITING_STUDENT; lưu message; có thông báo ASK tới sinh viên.")
def ask_valid(s):
    ticket=s.waiting();detail=s.detail(ticket)
    s.eq(detail["item"]["status"],"WAITING_STUDENT");s.eq(detail["messages"][-1]["body"],"Bổ sung bảng điểm.")
    s.true(any(x["request_id"]==ticket and x["event_type"]=="ASK" for x in s.get("sv01","/notifications").json["items"]))

@case("FR-11", "Yêu cầu bổ sung bắt buộc nội dung", "ASK với body rỗng trả 400, giữ IN_PROGRESS.",kind="Negative")
def ask_empty(s):
    ticket=s.accepted();s.eq(s.action(ticket,"ask").status_code,400);s.eq(s.detail(ticket)["item"]["status"],"IN_PROGRESS")

@case("FR-11", "Cán bộ không được gán không yêu cầu bổ sung", "cb02 action ask trả 403.",kind="Permission")
def ask_other_staff(s): s.eq(s.action(s.accepted(),"ask","Bổ sung",actor="cb02").status_code,403)

@case("FR-12", "Sinh viên bổ sung đưa hồ sơ lại IN_PROGRESS", "HTTP 201, lưu nội dung và sự kiện SUPPLEMENT; trạng thái IN_PROGRESS.",bug="B06",kind="State")
def supplement_resumes(s):
    ticket=s.waiting();s.eq(s.post("sv01",f"/requests/{ticket}/messages",{"body":"Đã gửi thông tin"}).status_code,201)
    detail=s.detail(ticket);s.eq(detail["messages"][-1]["body"],"Đã gửi thông tin");s.eq(detail["item"]["status"],"IN_PROGRESS")

@case("FR-12", "Không bổ sung khi NEW", "Sinh viên gửi message vào NEW trả 409.",kind="State")
def supplement_new(s): s.eq(s.post("sv01",f"/requests/{s.create()}/messages",{"body":"Bổ sung"}).status_code,409)

@case("FR-12", "Không gửi bổ sung rỗng và không có tệp", "HTTP 400; giữ WAITING_STUDENT.",kind="Negative")
def supplement_empty(s):
    ticket=s.waiting();s.eq(s.post("sv01",f"/requests/{ticket}/messages",{"body":"   "}).status_code,400);s.eq(s.detail(ticket)["item"]["status"],"WAITING_STUDENT")

@case("FR-12", "Sinh viên khác không bổ sung vào yêu cầu", "sv02 gửi vào WAITING_STUDENT của sv01 trả 403.",kind="Permission")
def supplement_other(s): s.eq(s.post("sv02",f"/requests/{s.waiting()}/messages",{"body":"Bổ sung"}).status_code,403)

# FR-13: exchanges and files.
@case("FR-13", "Cán bộ được gán gửi trao đổi", "HTTP 201; message sender_id=3, giữ IN_PROGRESS.")
def staff_message(s):
    ticket=s.accepted();s.eq(s.post("cb01",f"/requests/{ticket}/messages",{"body":"Đang đối chiếu hồ sơ."}).status_code,201)
    detail=s.detail(ticket);s.eq(detail["messages"][-1]["sender_id"],3);s.eq(detail["item"]["status"],"IN_PROGRESS")

@case("FR-13", "Upload TXT UTF-8 và tải đúng nội dung", "POST 201; GET file 200; nội dung download khớp bytes đã upload.")
def upload_download(s):
    content="Bảng điểm tham khảo".encode("utf-8")
    response=s.post("sv01","/requests",multipart={"type_id":"1","title":"Có tệp","content":"Nội dung","files":(io.BytesIO(content),"notes.txt")})
    s.eq(response.status_code,201);files=s.detail(response.json["id"])["attachments"];s.eq(len(files),1)
    downloaded=s.get("sv01",f'/attachments/{files[0]["id"]}');s.eq(downloaded.status_code,200);s.eq(downloaded.data,content)

@case("FR-13", "Chặn tải tệp của sinh viên khác", "sv02 tải file của sv01 trả 403; anonymous trả 401.",kind="Permission")
def download_other(s):
    response=s.post("sv01","/requests",multipart={"type_id":"1","title":"Có tệp","content":"Nội dung","files":(io.BytesIO(b"sample"),"notes.txt")})
    s.eq(response.status_code,201);file_id=s.detail(response.json["id"])["attachments"][0]["id"]
    s.eq(s.get("sv02",f"/attachments/{file_id}").status_code,403);s.eq(s.get(None,f"/attachments/{file_id}").status_code,401)

for filename,contents,label in [("bad.exe",b"sample","Đuôi EXE không được phép"),("fake.pdf",b"not pdf","PDF sai magic bytes"),("bad.txt",b"\xff\xfe\x00","TXT không phải UTF-8")]:
    @case("FR-13",label,"HTTP 400; toàn bộ tạo yêu cầu được rollback.",kind="Negative",data={"filename":filename})
    def invalid_file(s,filename=filename,contents=contents):
        before=s.sql("SELECT COUNT(*) FROM requests")[0][0]
        response=s.post("sv01","/requests",multipart={"type_id":"1","title":"File lỗi","content":"Nội dung","files":(io.BytesIO(contents),filename)})
        s.eq(response.status_code,400);s.eq(s.sql("SELECT COUNT(*) FROM requests")[0][0],before)

@case("FR-13", "Không upload quá 3 tệp mỗi lần", "Upload 4 tệp TXT trả 400 và rollback yêu cầu.",kind="Boundary")
def too_many_files(s):
    files=[(io.BytesIO(b"sample"),f"file-{i}.txt") for i in range(4)]
    response=s.post("sv01","/requests",multipart={"type_id":"1","title":"Nhiều tệp","content":"Nội dung","files":files})
    s.eq(response.status_code,400)

@case("FR-13", "Tệp vượt 5 MB bị chặn", "Upload TXT 5 MB + 1 byte trả 400.",kind="Boundary")
def file_too_large(s):
    response=s.post("sv01","/requests",multipart={"type_id":"1","title":"Tệp lớn","content":"Nội dung","files":(io.BytesIO(b"a"*(5*1024*1024+1)),"big.txt")})
    s.eq(response.status_code,400)

# FR-14: terminal staff operations.
@case("FR-14", "Hoàn tất với kết quả hợp lệ", "HTTP 200; COMPLETED; message kết quả được lưu.")
def complete_valid(s):
    ticket=s.accepted();s.eq(s.action(ticket,"complete","Đã cấp giấy xác nhận.").status_code,200)
    detail=s.detail(ticket);s.eq(detail["item"]["status"],"COMPLETED");s.eq(detail["messages"][-1]["body"],"Đã cấp giấy xác nhận.")

@case("FR-14", "Hoàn tất bắt buộc kết quả", "Body rỗng trả 400; giữ IN_PROGRESS.",bug="B04",kind="Negative")
def complete_empty(s): s.eq(s.action(s.accepted(),"complete").status_code,400)

@case("FR-14", "Hoàn tất phải có lịch sử COMPLETE", "History cuối: COMPLETE, IN_PROGRESS → COMPLETED, actor_id=3 và thời điểm.",bug="B10")
def complete_audit(s):
    ticket=s.accepted();s.eq(s.action(ticket,"complete","Đã xử lý").status_code,200)
    event=s.detail(ticket)["history"][-1]
    s.eq(event["action"],"COMPLETE");s.eq(event["from_status"],"IN_PROGRESS");s.eq(event["to_status"],"COMPLETED");s.eq(event["actor_id"],3);s.true(bool(event["created_at"]))

@case("FR-14", "Từ chối NEW có lý do", "HTTP 200; REJECTED; người từ chối được gán và lý do lưu.")
def reject_valid(s):
    ticket=s.create();s.eq(s.action(ticket,"reject","Không thuộc phạm vi.").status_code,200)
    detail=s.detail(ticket);s.eq(detail["item"]["status"],"REJECTED");s.eq(detail["messages"][-1]["body"],"Không thuộc phạm vi.")

@case("FR-14", "Từ chối bắt buộc lý do", "Body rỗng trả 400; giữ NEW.",bug="B05",kind="Negative")
def reject_empty(s): s.eq(s.action(s.create(),"reject").status_code,400)

@case("FR-14", "Không hoàn tất hai lần", "Lần complete thứ hai trả 409; trạng thái COMPLETED.",kind="State")
def complete_twice(s):
    ticket=s.accepted();s.eq(s.action(ticket,"complete","Đã xử lý").status_code,200);s.eq(s.action(ticket,"complete","Đã xử lý").status_code,409)

@case("FR-14", "Cán bộ khác không được hoàn tất", "cb02 complete hồ sơ của cb01 trả 403.",kind="Permission")
def complete_other(s): s.eq(s.action(s.accepted(),"complete","Đã xử lý",actor="cb02").status_code,403)

@case("FR-14", "Không trao đổi sau khi kết thúc", "Sinh viên/cán bộ gửi message vào COMPLETED đều trả 409.",kind="State")
def messages_closed(s):
    ticket=s.accepted();s.eq(s.action(ticket,"complete","Đã xử lý").status_code,200)
    for actor in ("sv01","cb01"): s.eq(s.post(actor,f"/requests/{ticket}/messages",{"body":"Trao đổi muộn"}).status_code,409)

# FR-15: reopening.
@case("FR-15", "Mở lại COMPLETED giữ cán bộ đang hoạt động", "HTTP 200; IN_PROGRESS, assignee_id=3; có REOPEN.")
def reopen_complete(s):
    ticket=s.accepted();s.eq(s.action(ticket,"complete","Đã xử lý").status_code,200);s.eq(s.action(ticket,"reopen",actor="sv01").status_code,200)
    detail=s.detail(ticket);s.eq(detail["item"]["status"],"IN_PROGRESS");s.eq(detail["item"]["assignee_id"],3);s.eq(detail["history"][-1]["action"],"REOPEN")

@case("FR-15", "Mở lại khi cán bộ cũ bị khóa trả hàng đợi", "HTTP 200; NEW; assignee_id=null.")
def reopen_inactive(s):
    ticket=s.accepted();s.eq(s.action(ticket,"complete","Đã xử lý").status_code,200);s.eq(s.patch("/users/3",{"active":False}).status_code,200)
    s.eq(s.action(ticket,"reopen",actor="sv01").status_code,200)
    item=s.detail(ticket)["item"];s.eq(item["status"],"NEW");s.eq(item["assignee_id"],None)

@case("FR-15", "Không mở lại REJECTED", "Sinh viên mở lại yêu cầu đã từ chối trả 409; giữ REJECTED.",bug="B07",kind="State")
def reopen_rejected(s):
    ticket=s.create();s.eq(s.action(ticket,"reject","Không thuộc phạm vi").status_code,200);s.eq(s.action(ticket,"reopen",actor="sv01").status_code,409)

@case("FR-15", "Không mở lại CANCELLED", "Sinh viên reopen yêu cầu đã hủy trả 409.",kind="State")
def reopen_cancelled(s):
    ticket=s.create();s.eq(s.action(ticket,"cancel",actor="sv01").status_code,200);s.eq(s.action(ticket,"reopen",actor="sv01").status_code,409)

@case("FR-15", "Sinh viên khác không mở lại yêu cầu", "sv02 reopen COMPLETED thuộc sv01 trả 403.",kind="Permission")
def reopen_other(s):
    ticket=s.accepted();s.eq(s.action(ticket,"complete","Đã xử lý").status_code,200);s.eq(s.action(ticket,"reopen",actor="sv02").status_code,403)

# FR-16: notifications.
@case("FR-16", "Tạo yêu cầu sinh thông báo CREATE cho chủ yêu cầu", "Danh sách thông báo của sv01 có CREATE của yêu cầu vừa tạo.")
def notification_create(s):
    ticket=s.create();items=s.get("sv01","/notifications").json["items"]
    s.true(any(x["request_id"]==ticket and x["event_type"]=="CREATE" and x["is_read"]==0 for x in items))

@case("FR-16", "Tiếp nhận sinh thông báo ACCEPT cho sinh viên", "Sau cb01 accept, sv01 có thông báo ACCEPT tương ứng.")
def notification_accept(s):
    ticket=s.accepted();items=s.get("sv01","/notifications").json["items"]
    s.true(any(x["request_id"]==ticket and x["event_type"]=="ACCEPT" for x in items))

@case("FR-16", "Đánh dấu đã đọc được lưu sau tải lại", "POST read 200; GET lại is_read=1.",bug="B09")
def notification_read(s):
    ticket=s.create();item=next(x for x in s.get("sv01","/notifications").json["items"] if x["request_id"]==ticket)
    s.eq(s.post("sv01",f'/notifications/{item["id"]}/read').status_code,200)
    updated=next(x for x in s.get("sv01","/notifications").json["items"] if x["id"]==item["id"]);s.eq(updated["is_read"],1)

@case("FR-16", "Không xem hoặc đánh dấu thông báo người khác", "sv02 không thấy thông báo sv01; POST read trả 404.",kind="Permission")
def notification_other(s):
    ticket=s.create();item=next(x for x in s.get("sv01","/notifications").json["items"] if x["request_id"]==ticket)
    s.true(not any(x["request_id"]==ticket for x in s.get("sv02","/notifications").json["items"]))
    s.eq(s.post("sv02",f'/notifications/{item["id"]}/read').status_code,404)

@case("FR-16", "ID thông báo không tồn tại", "POST read notification 99999 trả 404.",kind="Negative")
def notification_missing(s): s.eq(s.post("sv01","/notifications/99999/read").status_code,404)


# Three complete use-case groups, each with three distinct E2E scenarios.
@case("FR-14", "UC01-A: học vụ → tiếp nhận → trao đổi → hoàn tất", "NEW→IN_PROGRESS→COMPLETED; trao đổi/kết quả được lưu; lịch sử có CREATE, ACCEPT, COMPLETE.",
      case_id="TC-FLOW01-01",technique="Use case / E2E",requirements=["FR-06","FR-10","FR-13","FR-14","FR-16"],bug="B10",
      steps=["sv01 tạo yêu cầu Học vụ.","cb01 tiếp nhận.","cb01 gửi trao đổi rồi hoàn tất có kết quả.","sv01 đọc chi tiết, đối chiếu trạng thái, messages, history và thông báo COMPLETE."])
def flow_01a(s):
    ticket=s.create();s.eq(s.action(ticket,"accept").status_code,200)
    s.eq(s.post("cb01",f"/requests/{ticket}/messages",{"body":"Đang kiểm tra."}).status_code,201)
    s.eq(s.action(ticket,"complete","Đã cập nhật hồ sơ.").status_code,200)
    detail=s.detail(ticket);s.eq(detail["item"]["status"],"COMPLETED");s.eq(len(detail["messages"]),2)
    s.true(any(n["request_id"]==ticket and n["event_type"]=="COMPLETE" for n in s.get("sv01","/notifications").json["items"]))
    s.eq([h["action"] for h in detail["history"]],["CREATE","ACCEPT","MESSAGE","COMPLETE"])

@case("FR-14", "UC01-B: học phí có tệp → tiếp nhận → hoàn tất → tải tệp", "Yêu cầu học phí COMPLETED; chủ yêu cầu tải đúng tệp gốc sau hoàn tất.",
      case_id="TC-FLOW01-02",technique="Use case / E2E",requirements=["FR-06","FR-10","FR-13","FR-14"],
      steps=["sv01 tạo loại Học phí kèm notes.txt.","cb02 tiếp nhận và hoàn tất có kết quả.","sv01 xem kết quả và tải lại tệp gốc."])
def flow_01b(s):
    response=s.post("sv01","/requests",multipart={"type_id":"2","title":"Đối chiếu học phí","content":"Nhờ hỗ trợ","files":(io.BytesIO(b"GD12345"),"notes.txt")})
    s.eq(response.status_code,201);ticket=response.json["id"]
    s.eq(s.action(ticket,"accept",actor="cb02").status_code,200)
    s.eq(s.action(ticket,"complete","Đã đối chiếu GD12345.",actor="cb02").status_code,200)
    detail=s.detail(ticket);s.eq(detail["item"]["status"],"COMPLETED");s.eq(detail["item"]["assignee_id"],4)
    downloaded=s.get("sv01",f'/attachments/{detail["attachments"][0]["id"]}');s.eq(downloaded.status_code,200);s.eq(downloaded.data,b"GD12345")

@case("FR-12", "UC01-C: học vụ → chờ bổ sung → sinh viên bổ sung → hoàn tất", "Sau bổ sung quay IN_PROGRESS; cán bộ hoàn tất; kết quả cuối COMPLETED.",
      case_id="TC-FLOW01-03",technique="Use case / E2E",requirements=["FR-06","FR-10","FR-11","FR-12","FR-14"],bug="B06",
      steps=["sv01 tạo và cb01 tiếp nhận.","cb01 yêu cầu bổ sung.","sv01 gửi thông tin bổ sung.","Đối chiếu IN_PROGRESS rồi cb01 hoàn tất có kết quả."])
def flow_01c(s):
    ticket=s.waiting();s.eq(s.post("sv01",f"/requests/{ticket}/messages",{"body":"Bổ sung mã sinh viên SV123"}).status_code,201)
    s.eq(s.detail(ticket)["item"]["status"],"IN_PROGRESS")
    s.eq(s.action(ticket,"complete","Đã xử lý hồ sơ đầy đủ.").status_code,200);s.eq(s.detail(ticket)["item"]["status"],"COMPLETED")

@case("FR-09", "UC02-A: tạo → sinh viên hủy NEW → cán bộ nhận bị chặn", "Kết thúc CANCELLED; tiếp nhận sau đó trả409; lịch sử CREATE,CANCEL.",
      case_id="TC-FLOW02-01",technique="Use case / E2E",requirements=["FR-06","FR-09","FR-10"],
      steps=["sv01 tạo NEW.","sv01 hủy trước tiếp nhận.","cb01 thử tiếp nhận.","sv01 kiểm tra trạng thái cuối và lịch sử."])
def flow_02a(s):
    ticket=s.create();s.eq(s.action(ticket,"cancel",actor="sv01").status_code,200);s.eq(s.action(ticket,"accept").status_code,409)
    detail=s.detail(ticket);s.eq(detail["item"]["status"],"CANCELLED");s.eq([h["action"] for h in detail["history"]],["CREATE","CANCEL"])

@case("FR-14", "UC02-B: tạo → cán bộ từ chối NEW → chặn bổ sung sau kết thúc", "REJECTED; lưu lý do; student message sau kết thúc trả409.",
      case_id="TC-FLOW02-02",technique="Use case / E2E",requirements=["FR-06","FR-12","FR-14","FR-16"],
      steps=["sv01 tạo yêu cầu ngoài phạm vi.","cb02 từ chối NEW có lý do.","sv01 xem lý do và thử gửi bổ sung.","Đối chiếu REJECTED và thông báo REJECT."])
def flow_02b(s):
    ticket=s.create();s.eq(s.action(ticket,"reject","Không thuộc phạm vi hỗ trợ.",actor="cb02").status_code,200)
    detail=s.detail(ticket);s.eq(detail["item"]["status"],"REJECTED");s.eq(detail["messages"][-1]["body"],"Không thuộc phạm vi hỗ trợ.")
    s.eq(s.post("sv01",f"/requests/{ticket}/messages",{"body":"Gửi thêm"}).status_code,409)
    s.true(any(n["request_id"]==ticket and n["event_type"]=="REJECT" for n in s.get("sv01","/notifications").json["items"]))

@case("FR-15", "UC02-C: tạo → tiếp nhận → từ chối → chặn mở lại", "IN_PROGRESS→REJECTED; reopen trả409 và bảo toàn REJECTED.",
      case_id="TC-FLOW02-03",technique="Use case / E2E",requirements=["FR-06","FR-10","FR-14","FR-15"],bug="B07",
      steps=["sv01 tạo và cb01 tiếp nhận.","cb01 từ chối với lý do.","sv01 thử mở lại yêu cầu bị từ chối.","Đối chiếu HTTP409 và trạng thái cuối REJECTED."])
def flow_02c(s):
    ticket=s.accepted();s.eq(s.action(ticket,"reject","Không đủ điều kiện xử lý.").status_code,200)
    s.eq(s.action(ticket,"reopen",actor="sv01").status_code,409);s.eq(s.detail(ticket)["item"]["status"],"REJECTED")

@case("FR-15", "UC03-A: hoàn tất → mở lại giữ cán bộ cũ → hoàn tất lần hai", "Mở lại IN_PROGRESS với assignee3; vòng xử lý thứ hai kết thúc COMPLETED.",
      case_id="TC-FLOW03-01",technique="Use case / E2E",requirements=["FR-06","FR-10","FR-14","FR-15"],
      steps=["Tạo, tiếp nhận và hoàn tất lần một.","sv01 mở lại.","Đối chiếu cán bộ cũ rồi cb01 hoàn tất lần hai.","sv01 thấy kết quả cập nhật và COMPLETED."])
def flow_03a(s):
    ticket=s.accepted();s.eq(s.action(ticket,"complete","Kết quả lần một.").status_code,200)
    s.eq(s.action(ticket,"reopen",actor="sv01").status_code,200);item=s.detail(ticket)["item"];s.eq(item["status"],"IN_PROGRESS");s.eq(item["assignee_id"],3)
    s.eq(s.action(ticket,"complete","Kết quả lần hai.").status_code,200);detail=s.detail(ticket);s.eq(detail["item"]["status"],"COMPLETED");s.eq(detail["messages"][-1]["body"],"Kết quả lần hai.")

@case("FR-15", "UC03-B: hoàn tất → khóa cán bộ cũ → mở lại hàng đợi → cán bộ mới xử lý", "Mở lại NEW không assignee; cb02 tiếp nhận và hoàn tất; assignee_id=4.",
      case_id="TC-FLOW03-02",technique="Use case / E2E",requirements=["FR-04","FR-06","FR-10","FR-14","FR-15"],
      steps=["Tạo và cb01 hoàn tất lần một.","Admin khóa cb01.","sv01 mở lại; kiểm tra NEW không người phụ trách.","cb02 nhận và hoàn tất hồ sơ; kiểm tra kết quả."])
def flow_03b(s):
    ticket=s.accepted();s.eq(s.action(ticket,"complete","Đã xử lý lần đầu.").status_code,200);s.eq(s.patch("/users/3",{"active":False}).status_code,200)
    s.eq(s.action(ticket,"reopen",actor="sv01").status_code,200);item=s.detail(ticket)["item"];s.eq(item["status"],"NEW");s.eq(item["assignee_id"],None)
    s.eq(s.action(ticket,"accept",actor="cb02").status_code,200);s.eq(s.action(ticket,"complete","Đã xử lý tiếp.",actor="cb02").status_code,200)
    item=s.detail(ticket)["item"];s.eq(item["status"],"COMPLETED");s.eq(item["assignee_id"],4)

@case("FR-12", "UC03-C: mở lại → yêu cầu bổ sung → bổ sung chỉ tệp → hoàn tất", "File-only supplement lưu tệp, quay IN_PROGRESS; hoàn tất vòng mở lại.",
      case_id="TC-FLOW03-03",technique="Use case / E2E",requirements=["FR-11","FR-12","FR-13","FR-14","FR-15"],bug="B06",
      steps=["Tạo, tiếp nhận, hoàn tất rồi sv01 mở lại.","cb01 yêu cầu gửi tệp bổ sung.","sv01 gửi TXT UTF8, body rỗng.","Kiểm tra file và IN_PROGRESS; cb01 hoàn tất."])
def flow_03c(s):
    ticket=s.accepted();s.eq(s.action(ticket,"complete","Kết quả đầu.").status_code,200);s.eq(s.action(ticket,"reopen",actor="sv01").status_code,200)
    s.eq(s.action(ticket,"ask","Gửi tệp bổ sung.").status_code,200)
    s.eq(s.post("sv01",f"/requests/{ticket}/messages",multipart={"body":"","files":(io.BytesIO(b"supplement"),"supplement.txt")}).status_code,201)
    detail=s.detail(ticket);s.eq(len(detail["attachments"]),1);s.eq(detail["item"]["status"],"IN_PROGRESS")
    s.eq(s.action(ticket,"complete","Đã đọc tệp.").status_code,200);s.eq(s.detail(ticket)["item"]["status"],"COMPLETED")


def json_value(value):
    if isinstance(value, bytes): return {"bytes":len(value),"utf8":value.decode("utf-8",errors="replace")}
    if isinstance(value, set): return sorted(value)
    raise TypeError(type(value).__name__)


def run_mode(mode):
    output=OUTPUT_BASE/"evidence"/"functional"/mode
    output.mkdir(parents=True,exist_ok=True)
    results=[]
    training=mode=="training"
    with tempfile.TemporaryDirectory(prefix="studentcare-functional-") as temp:
        root=Path(temp)
        seed=root/"seed.db"
        app=create_app({"DATABASE":str(seed),"TESTING":True,"TRAINING_BUGS":False})
        initialize(app,demo=True)
        for definition in CASES:
            database=root/(definition["id"]+".db")
            with closing(sqlite3.connect(seed)) as source,closing(sqlite3.connect(database)) as target:
                source.backup(target)
            sandbox=Sandbox(str(database),training)
            row={k:v for k,v in definition.items() if k!="fn"}
            start=time.perf_counter()
            row.update(executed_at=datetime.now(timezone.utc).isoformat(),mode=mode,
                       tester=RESPONSIBLE_TESTER,scope=RUN_SCOPE,
                       execution_operator="Codex automation at user request; both applications AI-assisted, not blind testing",
                       environment={"runner":"Flask test_client","database":"isolated temporary SQLite","python":sys.version.split()[0]})
            try:
                definition["fn"](sandbox)
                row.update(status="PASS",actual="Tất cả assertion đạt; xem trace request/response và đối chiếu trong evidence.")
            except AssertionError as error:
                row.update(status="FAIL",actual=str(error))
            except Exception as error:
                row.update(status="ERROR",actual=f"{type(error).__name__}: {error}",traceback=traceback.format_exc())
            row["duration_ms"]=round((time.perf_counter()-start)*1000,3)
            row["trace"]=sandbox.trace
            operations=[step for step in sandbox.trace if "method" in step]
            row["executed_steps"]=[f"{step['actor']}: {step['method']} {step['path']} → HTTP {step['http_status']}"
                                   for step in operations]
            if not row["data"]:
                row["data"]={"actors":list(dict.fromkeys(step["actor"] for step in operations)),
                             "requests":[{"method":step["method"],"path":step["path"],"body":step["input"]}
                                         for step in operations if step["input"] is not None]}
            row["evidence"]=f"evidence/functional/{mode}/{row['id']}.json"
            (output/(row["id"]+".json")).write_text(json.dumps(row,ensure_ascii=False,indent=2,default=json_value),encoding="utf-8")
            results.append(row)
            print(f"{mode:8} {row['id']} {row['function_id']} {row['status']:5} {row['title']}",flush=True)
    report={"scope":RUN_SCOPE, "mode":mode,"responsible_tester":RESPONSIBLE_TESTER,
            "execution_operator":"Codex automation; both apps AI-assisted, not blind testing",
            "source_sha256":SOURCE_HASHES,
            "started_from":"Fresh seed copied into an independent database for each testcase",
            "executed_at":datetime.now(timezone.utc).isoformat(),"total":len(results),
            "counts":{status:sum(r["status"]==status for r in results) for status in ("PASS","FAIL","ERROR")},
            "cases":results}
    (output/"results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,default=json_value),encoding="utf-8")
    return report


def main():
    global OUTPUT_BASE, RESPONSIBLE_TESTER, RUN_SCOPE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("baseline","training","both"),default="both")
    parser.add_argument("--output-base",type=Path,default=OUTPUT_BASE)
    parser.add_argument("--responsible-tester",default=RESPONSIBLE_TESTER)
    parser.add_argument("--scope",default=RUN_SCOPE)
    args=parser.parse_args()
    OUTPUT_BASE=args.output_base.resolve();RESPONSIBLE_TESTER=args.responsible_tester;RUN_SCOPE=args.scope
    data=OUTPUT_BASE/"data"
    data.mkdir(parents=True,exist_ok=True)
    definitions=[{k:v for k,v in item.items() if k!="fn"} for item in CASES]
    (data/"functional_cases.json").write_text(json.dumps(definitions,ensure_ascii=False,indent=2),encoding="utf-8")
    reports=[run_mode(mode) for mode in (["baseline","training"] if args.mode=="both" else [args.mode])]
    baseline=next((report for report in reports if report["mode"]=="baseline"),None)
    baseline_rows={row["id"]:row for row in baseline["cases"]} if baseline else {}
    dossier=[]
    for row in reports[-1]["cases"]:
        entry={k:v for k,v in row.items() if k not in ("trace","traceback")}
        if row["id"] in baseline_rows:
            reference=baseline_rows[row["id"]]
            entry.update(baseline_status=reference["status"],baseline_actual=reference["actual"],baseline_evidence=reference["evidence"])
        dossier.append(entry)
    (data/"functional_cases.json").write_text(json.dumps(dossier,ensure_ascii=False,indent=2,default=json_value),encoding="utf-8")
    for report in reports:
        print(f"SUMMARY {report['mode']}: total={report['total']} counts={report['counts']}",flush=True)
    # Preserve genuine FAIL status in individual reports. Exit nonzero if any failed;
    # a caller can inspect evidence rather than silently relabel known defects PASS.
    return 1 if any(r["counts"]["FAIL"] or r["counts"]["ERROR"] for r in reports) else 0


if __name__=="__main__":
    raise SystemExit(main())
