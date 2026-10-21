import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from app import create_app, initialize


class SupportCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / "test.db")
        self.app = create_app({"TESTING": True, "DATABASE": self.database,
                               "SECRET_KEY": "test-only-key", "TRAINING_BUGS": os.getenv("TRAINING_BUGS", "1") == "1"})
        initialize(self.app, demo=True)
        self.clients = {}

    def user(self, username):
        if username not in self.clients:
            client = self.app.test_client()
            response = client.post("/api/login", json={"username": username, "password": "Demo@123"})
            self.assertEqual(response.status_code, 200)
            token = client.get("/api/me").json["csrf"]
            self.clients[username] = (client, token)
        return self.clients[username]

    def get(self, username, path):
        return self.user(username)[0].get("/api" + path)

    def post(self, username, path, data=None, headers=None, multipart=None):
        client, csrf = self.user(username)
        kwargs = {"headers": {"X-CSRF-Token": csrf, **(headers or {})}}
        if multipart is not None:
            kwargs.update(data=multipart, content_type="multipart/form-data")
        else:
            kwargs["json"] = data or {}
        return client.post("/api" + path, **kwargs)

    def patch(self, path, data):
        client, csrf = self.user("admin")
        return client.patch("/api" + path, json=data, headers={"X-CSRF-Token": csrf})

    def create(self, username="sv01", **overrides):
        response = self.post(username, "/requests", {"type_id": 1, "title": "Hỗ trợ HỌC PHÍ", "content": "Nội dung cần hỗ trợ", **overrides})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json["id"]

    def act(self, ticket_id, action, body="", user="cb01", **kwargs):
        return self.post(user, f"/requests/{ticket_id}/action", {"action": action, "body": body}, **kwargs)

    def accepted(self):
        ticket_id = self.create()
        self.assertEqual(self.act(ticket_id, "accept").status_code, 200)
        return ticket_id

    def detail(self, ticket_id):
        return self.get("sv01", f"/requests/{ticket_id}").json

    def sql(self, statement, args=()):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute(statement, args).fetchall()


class DefectTests(SupportCase):
    """Always assert the specified CORRECT behavior. These must fail with defects on."""

    def test_B01_whitespace_title_is_rejected(self):
        response = self.post("sv01", "/requests", {"type_id": 1, "title": "   ", "content": "Cần hỗ trợ"})
        self.assertEqual(response.status_code, 400, "B01: tiêu đề chỉ khoảng trắng phải bị từ chối")

    def test_B02_inactive_type_is_rejected(self):
        self.assertEqual(self.patch("/types/1", {"active": False}).status_code, 200)
        response = self.post("sv01", "/requests", {"type_id": 1, "title": "Yêu cầu mới", "content": "Nội dung"})
        self.assertEqual(response.status_code, 400, "B02: loại đã ngừng hoạt động không được dùng tạo mới")

    def test_B03_cancel_after_accept_is_rejected(self):
        ticket_id = self.accepted()
        response = self.act(ticket_id, "cancel", user="sv01")
        self.assertEqual(response.status_code, 409, "B03: hủy sau tiếp nhận phải bị chặn")
        self.assertEqual(self.detail(ticket_id)["item"]["status"], "IN_PROGRESS")

    def test_B04_completion_requires_result(self):
        ticket_id = self.accepted()
        self.assertEqual(self.act(ticket_id, "complete").status_code, 400, "B04: hoàn tất bắt buộc kết quả")

    def test_B05_rejection_requires_reason(self):
        ticket_id = self.create()
        self.assertEqual(self.act(ticket_id, "reject").status_code, 400, "B05: từ chối bắt buộc lý do")

    def test_B06_supplement_resumes_processing(self):
        ticket_id = self.accepted()
        self.assertEqual(self.act(ticket_id, "ask", "Bổ sung bảng điểm").status_code, 200)
        self.assertEqual(self.post("sv01", f"/requests/{ticket_id}/messages", {"body": "Đã bổ sung thông tin"}).status_code, 201)
        self.assertEqual(self.detail(ticket_id)["item"]["status"], "IN_PROGRESS", "B06: gửi bổ sung phải quay lại đang xử lý")

    def test_B07_rejected_request_cannot_reopen(self):
        ticket_id = self.create()
        self.assertEqual(self.act(ticket_id, "reject", "Không thuộc phạm vi hỗ trợ").status_code, 200)
        self.assertEqual(self.act(ticket_id, "reopen", user="sv01").status_code, 409, "B07: chỉ được mở lại COMPLETED")

    def test_B08_search_ignores_case(self):
        ticket_id = self.create(title="Hỗ trợ HỌC PHÍ")
        items = self.get("sv01", "/requests?q=học%20phí").json["items"]
        self.assertIn(ticket_id, [item["id"] for item in items], "B08: tìm kiếm phải không phân biệt hoa/thường")

    def test_B09_read_notification_is_persisted(self):
        ticket_id = self.create()
        notification = next(n for n in self.get("sv01", "/notifications").json["items"] if n["request_id"] == ticket_id)
        self.assertEqual(self.post("sv01", f'/notifications/{notification["id"]}/read').status_code, 200)
        updated = next(n for n in self.get("sv01", "/notifications").json["items"] if n["id"] == notification["id"])
        self.assertEqual(updated["is_read"], 1, "B09: tải lại vẫn phải là đã đọc")

    def test_B10_completion_records_history(self):
        ticket_id = self.accepted()
        self.assertEqual(self.act(ticket_id, "complete", "Đã cấp giấy xác nhận").status_code, 200)
        history = self.detail(ticket_id)["history"]
        self.assertEqual(history[-1]["action"], "COMPLETE", "B10: hoàn tất phải có nhật ký")
        self.assertEqual(history[-1]["from_status"], "IN_PROGRESS")
        self.assertEqual(history[-1]["to_status"], "COMPLETED")


class GuardTests(SupportCase):
    def test_login_generic_error_and_locked_account(self):
        client = self.app.test_client()
        wrong = client.post("/api/login", json={"username": "sv01", "password": "wrong"})
        unknown = client.post("/api/login", json={"username": "unknown", "password": "wrong"})
        self.assertEqual((wrong.status_code, wrong.json), (unknown.status_code, unknown.json))
        self.assertEqual(wrong.status_code, 401)
        self.patch("/users/1", {"active": False})
        locked = client.post("/api/login", json={"username": "sv01", "password": "Demo@123"})
        self.assertEqual(locked.status_code, 401)
        self.assertEqual(locked.json, wrong.json)

    def test_student_cannot_access_other_request_or_attachment(self):
        response = self.post("sv01", "/requests", multipart={"type_id": "1", "title": "Bảng điểm", "content": "Nội dung", "files": (io.BytesIO(b"sample"), "notes.txt")})
        self.assertEqual(response.status_code, 201)
        ticket_id = response.json["id"]
        attachment_id = self.detail(ticket_id)["attachments"][0]["id"]
        self.assertEqual(self.get("sv02", f"/requests/{ticket_id}").status_code, 403)
        self.assertEqual(self.get("sv02", f"/attachments/{attachment_id}").status_code, 403)
        self.assertEqual(self.get("sv01", f"/attachments/{attachment_id}").data, b"sample")
        self.assertEqual(self.app.test_client().get(f"/api/attachments/{attachment_id}").status_code, 401)
        self.assertNotIn(ticket_id, [item["id"] for item in self.get("sv02", "/requests").json["items"]])

    def test_admin_and_student_wrong_role(self):
        ticket_id = self.create()
        self.assertEqual(self.get("admin", f"/requests/{ticket_id}").status_code, 403)
        self.assertEqual(self.act(ticket_id, "accept", user="sv01").status_code, 403)
        self.assertEqual(self.act(ticket_id, "accept", user="admin").status_code, 403)
        self.assertEqual(self.get("sv01", "/users").status_code, 403)
        self.assertEqual(self.post("cb01", "/requests", {"type_id": 1, "title": "a", "content": "b"}).status_code, 403)

    def test_only_assignee_can_process(self):
        ticket_id = self.accepted()
        self.assertEqual(self.act(ticket_id, "complete", "Đã xử lý", user="cb02").status_code, 403)
        self.assertEqual(self.post("cb02", f"/requests/{ticket_id}/messages", {"body": "test"}).status_code, 403)

    def test_logout_invalidates_cookie_and_missing_auth(self):
        client, _csrf = self.user("sv01")
        cookie = client.get_cookie("session").value
        self.assertEqual(self.post("sv01", "/logout").status_code, 200)
        client.set_cookie("session", cookie)
        self.assertEqual(client.get("/api/me").status_code, 401)
        self.assertEqual(self.app.test_client().post("/api/requests", json={}).status_code, 401)

    def test_expired_and_tampered_sessions(self):
        from datetime import timedelta
        client, _csrf = self.user("sv01")
        self.app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=-1)
        self.assertEqual(client.get("/api/me").status_code, 401)
        client.set_cookie("session", "tampered")
        self.assertEqual(client.get("/api/me").status_code, 401)

    def test_lock_revokes_existing_session(self):
        client, _csrf = self.user("sv01")
        self.patch("/users/1", {"active": False})
        self.assertEqual(client.get("/api/me").status_code, 401)

    def test_csrf_is_required(self):
        client, _csrf = self.user("sv01")
        self.assertEqual(client.post("/api/requests", json={}).status_code, 403)

    def test_create_retries_return_same_record(self):
        data = {"type_id": 1, "title": "Retry", "content": "Một yêu cầu"}
        first = self.post("sv01", "/requests", data, {"Idempotency-Key": "create-1"})
        second = self.post("sv01", "/requests", data, {"Idempotency-Key": "create-1"})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json, second.json)
        ticket_id = first.json["id"]
        self.assertEqual(len(self.sql("SELECT id FROM notifications WHERE request_id=?", (ticket_id,))), 1)
        self.assertEqual(len(self.detail(ticket_id)["history"]), 1)
        changed = self.post("sv01", "/requests", {**data, "title": "Changed"}, {"Idempotency-Key": "create-1"})
        self.assertEqual(changed.status_code, 409)

    def test_action_retry_does_not_duplicate_events(self):
        ticket_id = self.create()
        self.assertEqual(self.act(ticket_id, "accept", headers={"Idempotency-Key": "accept-1"}).status_code, 200)
        self.assertEqual(self.act(ticket_id, "accept", headers={"Idempotency-Key": "accept-1"}).status_code, 200)
        self.assertEqual(len(self.detail(ticket_id)["history"]), 2)
        self.assertEqual(len(self.sql("SELECT id FROM notifications WHERE request_id=?", (ticket_id,))), 2)

    def test_multipart_retry_ignores_boundary(self):
        def form():
            return {"type_id": "1", "title": "Retry file", "content": "Một yêu cầu", "files": (io.BytesIO(b"same file"), "notes.txt")}
        first = self.post("sv01", "/requests", headers={"Idempotency-Key": "multipart-1"}, multipart=form())
        second = self.post("sv01", "/requests", headers={"Idempotency-Key": "multipart-1"}, multipart=form())
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json, second.json)
        self.assertEqual(len(self.detail(first.json["id"])["attachments"]), 1)

    def test_two_staff_accept_atomically(self):
        ticket_id = self.create()
        clients = [self.user("cb01"), self.user("cb02")]
        barrier = Barrier(2)
        def accept(pair):
            client, token = pair
            barrier.wait(timeout=5)
            return client.post(f"/api/requests/{ticket_id}/action", json={"action": "accept"}, headers={"X-CSRF-Token": token}).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(accept, clients))
        self.assertEqual(sorted(outcomes), [200, 409])
        self.assertEqual(len(self.detail(ticket_id)["history"]), 2)

    def test_cancel_new_and_no_exchange_after_close(self):
        ticket_id = self.create()
        self.assertEqual(self.act(ticket_id, "cancel", user="sv01").status_code, 200)
        self.assertEqual(self.detail(ticket_id)["item"]["status"], "CANCELLED")
        self.assertEqual(self.detail(ticket_id)["history"][-1]["action"], "CANCEL")
        self.assertEqual(self.act(ticket_id, "accept").status_code, 409)
        self.assertEqual(self.post("sv01", f"/requests/{ticket_id}/messages", {"body": "test"}).status_code, 409)

    def test_completion_notification_and_reopen(self):
        ticket_id = self.accepted()
        self.assertEqual(self.act(ticket_id, "complete", "Kết quả đã xử lý").status_code, 200)
        self.assertEqual(self.act(ticket_id, "complete", "Kết quả đã xử lý").status_code, 409)
        self.assertEqual(self.act(ticket_id, "reopen", user="sv01").status_code, 200)
        item = self.detail(ticket_id)["item"]
        self.assertEqual((item["status"], item["assignee_id"]), ("IN_PROGRESS", 3))
        self.assertEqual(self.detail(ticket_id)["history"][-1]["action"], "REOPEN")
        self.assertTrue(any(n["event_type"] == "COMPLETE" for n in self.get("sv01", "/notifications").json["items"]))

    def test_reopen_returns_to_queue_when_assignee_inactive(self):
        ticket_id = self.accepted()
        self.act(ticket_id, "complete", "Đã xử lý")
        self.patch("/users/3", {"active": False})
        self.assertEqual(self.act(ticket_id, "reopen", user="sv01").status_code, 200)
        item = self.detail(ticket_id)["item"]
        self.assertEqual((item["status"], item["assignee_id"]), ("NEW", None))

    def test_notifications_are_private(self):
        ticket_id = self.create()
        notification_id = self.get("sv01", "/notifications").json["items"][0]["id"]
        self.assertEqual(self.post("sv02", f"/notifications/{notification_id}/read").status_code, 404)
        self.assertFalse(any(n["request_id"] == ticket_id for n in self.get("sv02", "/notifications").json["items"]))

    def test_file_validation_rolls_back_entire_request(self):
        before = self.sql("SELECT COUNT(*) FROM requests")[0][0]
        for name, content in [("run.exe", b"binary"), ("fake.pdf", b"not a pdf"), ("big.txt", b"a" * (5 * 1024 * 1024 + 1))]:
            response = self.post("sv01", "/requests", multipart={"type_id": "1", "title": "Test file", "content": "Test", "files": (io.BytesIO(content), name)})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM requests")[0][0], before)

    def test_categories_retain_old_references(self):
        ticket_id = self.create()
        self.assertEqual(self.patch("/types/1", {"active": False}).status_code, 200)
        self.assertEqual(self.get("sv01", f"/requests/{ticket_id}").status_code, 200)
        self.assertNotIn(1, [item["id"] for item in self.get("sv01", "/types").json["items"]])
        self.assertEqual(self.patch("/types/1", {"name": "Học vụ mới"}).status_code, 200)
        self.assertEqual(self.detail(ticket_id)["item"]["type_name"], "Học vụ mới")

    def test_admin_account_management(self):
        response = self.post("admin", "/users", {"username": "sv03", "name": "Sinh viên mới", "password": "Password@123", "role": "STUDENT"})
        self.assertEqual(response.status_code, 201)
        user_id = response.json["id"]
        self.assertEqual(self.patch(f"/users/{user_id}", {"role": "STAFF"}).status_code, 200)
        self.assertEqual(self.patch("/users/5", {"active": False}).status_code, 400)
        self.assertEqual(self.post("admin", "/users", {"username": "short", "name": "Test", "password": "123", "role": "STUDENT"}).status_code, 400)
        self.assertNotIn("Demo@123", self.sql("SELECT password_hash FROM users LIMIT 1")[0][0])

    def test_filters_counts_and_validation(self):
        self.assertEqual(self.get("cb01", "/requests?status=NEW").status_code, 200)
        self.assertTrue(all(item["status"] == "NEW" for item in self.get("cb01", "/requests?status=NEW").json["items"]))
        self.assertTrue(all(item["assignee_id"] == 3 for item in self.get("cb01", "/requests?mine=1").json["items"]))
        self.assertEqual(sum(self.get("sv01", "/requests").json["counts"].values()), 4)
        self.assertEqual(self.get("sv01", "/requests?status=unknown").status_code, 400)
        self.assertEqual(self.post("sv01", "/requests", {"type_id": "invalid", "title": "a", "content": "b"}).status_code, 400)
        self.assertEqual(self.post("sv01", "/requests", {"type_id": 1, "title": "a", "content": "   "}).status_code, 400)
        self.assertEqual(self.post("sv01", "/requests", {"type_id": 1, "title": "x" * 201, "content": "b"}).status_code, 400)

    def test_ask_requires_body_and_message_requires_content(self):
        ticket_id = self.accepted()
        self.assertEqual(self.act(ticket_id, "ask").status_code, 400)
        self.assertEqual(self.act(ticket_id, "ask", "Bổ sung thông tin").status_code, 200)
        self.assertEqual(self.post("sv01", f"/requests/{ticket_id}/messages", {"body": "  "}).status_code, 400)
        self.assertEqual(self.detail(ticket_id)["item"]["status"], "WAITING_STUDENT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
