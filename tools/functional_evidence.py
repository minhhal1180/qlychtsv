"""Capture B01-B10 as real browser screenshots plus authenticated HTTP evidence.

Each case starts from its own temporary demo database. Correct-behavior
assertions must fail for the ten intentionally seeded functional defects.
The wrapper succeeds only when exactly B01-B10 are reproduced without errors.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app, initialize
from bugs import BUGS
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import WSGIRequestHandler, make_server


class Quiet(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--output", default=str(ROOT / "submission/evidence/seeded_functional"))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    results, setup_errors, page_errors = [], [], []
    mappings = {"B01": "F02 validation", "B02": "AC-F05-01", "B03": "AC-F02-03",
                "B04": "AC-F03-02", "B05": "F03 validation", "B06": "AC-F04-01 / selected baseline rule",
                "B07": "AC-F02-04", "B08": "F02 search by code/title", "B09": "F05 read/unread",
                "B10": "AC-F03-03"}

    def equal(actual, expected, message):
        assert actual == expected, f"{message}; expected={expected!r}, actual={actual!r}"

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel)
        browser_version = browser.version
        try:
            for number in range(1, 11):
                bug_id = f"B{number:02d}"
                events = []
                contexts = []
                with tempfile.TemporaryDirectory(prefix=f"studentcare-{bug_id}-") as temp:
                    app = create_app({"DATABASE": str(Path(temp) / "case.db"), "TRAINING_BUGS": True})
                    initialize(app, demo=True)
                    server = make_server("127.0.0.1", 0, app, threaded=True, request_handler=Quiet)
                    thread = Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    base = f"http://127.0.0.1:{server.server_port}"
                    clients = {}
                    try:
                        def client(username):
                            if username not in clients:
                                context = browser.new_context(viewport={"width": 1440, "height": 1100}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
                                contexts.append(context)
                                login = context.request.post(base + "/api/login", data={"username": username, "password": "Demo@123"})
                                assert login.status == 200, login.text()
                                token = context.request.get(base + "/api/me").json()["csrf"]
                                clients[username] = {"context": context, "token": token}
                            return clients[username]

                        def capture(response, label, data=None):
                            event = {"label": label, "method": response.request.method if hasattr(response, "request") else None,
                                     "path": urlsplit(response.url).path, "query": urlsplit(response.url).query,
                                     "http_status": response.status, "request_data": data, "response_json": response.json()}
                            events.append(event)
                            return event

                        def api(username, method, path, data=None, label="setup/read"):
                            item = client(username)
                            response = item["context"].request.fetch(base + path, method=method,
                                headers={"X-CSRF-Token": item["token"]}, data=data)
                            event = capture(response, label, data)
                            event["method"] = method
                            return event

                        def page_for(username, path="requests"):
                            page = client(username)["context"].new_page()
                            page.on("pageerror", lambda error: page_errors.append({"id": bug_id, "error": str(error)}))
                            page.goto(base + "/#" + path)
                            expect(page.locator("#workspace")).to_be_visible()
                            expect(page.locator("#main h1")).to_be_visible()
                            return page

                        def create_ticket():
                            response = api("sv01", "POST", "/api/requests", {"type_id": 1,
                                "title": f"Yêu cầu độc lập {bug_id}", "content": f"Dữ liệu riêng cho testcase {bug_id}."}, "setup create independent request")
                            assert response["http_status"] == 201, response
                            return response["response_json"]["id"]

                        def action(ticket_id, action_name, body="", username="cb01"):
                            response = api(username, "POST", f"/api/requests/{ticket_id}/action", {"action": action_name, "body": body}, "setup action")
                            assert response["http_status"] == 200, response

                        def detail(ticket_id):
                            return api("sv01", "GET", f"/api/requests/{ticket_id}", label="read resulting state/history")["response_json"]

                        def click_post(page, selector, path, request_data, label):
                            with page.expect_response(lambda r: urlsplit(r.url).path == path and r.request.method == "POST") as pending:
                                page.locator(selector).click()
                            return capture(pending.value, label, request_data)

                        if bug_id in ("B01", "B02"):
                            page = page_for("sv01")
                            page.locator("#new-request").click()
                            expect(page.locator("#create-dialog")).to_be_visible()
                            page.locator("#create-type").select_option("1")
                            title = "   " if bug_id == "B01" else "B02 gửi lại form dùng loại đã ngừng"
                            content = f"Nội dung hợp lệ của {bug_id}."
                            page.locator("#create-form [name=title]").fill(title)
                            page.locator("#create-form [name=content]").fill(content)
                            if bug_id == "B02":
                                update = api("admin", "PATCH", "/api/types/1", {"active": False}, "disable type after form has loaded")
                                assert update["http_status"] == 200
                            observed = click_post(page, "#create-form button[type=submit]", "/api/requests",
                                {"type_id": 1, "title": title, "content": content}, "UI create trigger")
                            ticket_id = observed["response_json"]["id"]
                            expect(page.locator("#create-dialog")).not_to_be_visible()
                            expect(page.locator("#main .breadcrumb")).to_contain_text(observed["response_json"]["code"])
                            result = detail(ticket_id)
                            actual = {"create_http": observed["http_status"], "created_item": result["item"]}
                            expected = "HTTP 400, không tạo yêu cầu khi tiêu đề chỉ khoảng trắng." if bug_id == "B01" else "HTTP 400, không tạo yêu cầu với loại đã ngừng hoạt động sau khi mở form."
                            assertion = lambda: equal(observed["http_status"], 400, "Invalid create should be rejected")
                            steps = ["sv01 mở Tạo yêu cầu, chọn Học vụ.", "Nhập ba dấu cách vào tiêu đề, nội dung hợp lệ; bấm Gửi." if bug_id == "B01" else "Admin ngừng Học vụ; sv01 giữ form cũ, nhập nội dung và bấm Gửi.", "Quan sát hồ sơ mới vẫn được tạo."]
                        elif bug_id == "B08":
                            ticket_id = create_ticket()
                            item = detail(ticket_id)["item"]
                            page = page_for("sv01")
                            page.locator("#filter-form [name=q]").fill(item["code"])
                            with page.expect_response(lambda r: urlsplit(r.url).path == "/api/requests" and bool(urlsplit(r.url).query)) as pending:
                                page.locator("#filter-form button[type=submit]").click()
                            query_event = capture(pending.value, "UI search by exact unique request code")
                            expect(page.locator("#main .empty")).to_be_visible()
                            returned_ids = [row["id"] for row in query_event["response_json"]["items"]]
                            actual = {"query": item["code"], "expected_request_id": ticket_id, "returned_ids": returned_ids,
                                      "rendered_message": page.locator("#main .empty").text_content()}
                            expected = "Tìm đúng mã yêu cầu phải trả hồ sơ có mã đó, dù tiêu đề không chứa mã."
                            assertion = lambda: equal(ticket_id in returned_ids, True, "Search should include the exact code match")
                            steps = ["sv01 tạo yêu cầu có tiêu đề không chứa mã.", "Quay lại danh sách, tìm đúng mã HT-xxxxx vừa sinh.", "Bấm Lọc; quan sát danh sách rỗng."]
                        elif bug_id == "B09":
                            ticket_id = create_ticket()
                            notifications = api("sv01", "GET", "/api/notifications", label="notification before UI click")["response_json"]["items"]
                            notification = next(row for row in notifications if row["request_id"] == ticket_id)
                            page = page_for("sv01", "notifications")
                            observed = click_post(page, f'[data-read="{notification["id"]}"]',
                                f'/api/notifications/{notification["id"]}/read', {}, "UI mark read trigger")
                            expect(page.locator(".notification").first).to_contain_text("Chưa đọc")
                            page.reload()
                            expect(page.locator(".notification").first).to_contain_text("Chưa đọc")
                            after = api("sv01", "GET", "/api/notifications", label="notification after mark-read and reload")["response_json"]["items"]
                            updated = next(row for row in after if row["id"] == notification["id"])
                            actual = {"update_http": observed["http_status"], "before": notification, "after": updated}
                            expected = "Đánh dấu đã đọc phải lưu is_read=1 và còn Đã đọc sau tải lại."
                            assertion = lambda: equal(updated["is_read"], 1, "Notification read status must persist")
                            steps = ["sv01 tạo yêu cầu để có thông báo mới.", "Mở Thông báo; chọn Đánh dấu đã đọc ở đúng hồ sơ.", "Tải lại trang và quan sát Chưa đọc vẫn còn."]
                        else:
                            ticket_id = create_ticket()
                            if bug_id in ("B03", "B04", "B06", "B10"):
                                action(ticket_id, "accept")
                            if bug_id == "B06":
                                action(ticket_id, "ask", "Em vui lòng bổ sung bảng điểm.")
                            if bug_id == "B07":
                                action(ticket_id, "reject", "Nội dung nằm ngoài phạm vi hỗ trợ.")
                            role_user = "cb01" if bug_id in ("B04", "B05", "B10") else "sv01"
                            page = page_for(role_user, f"request/{ticket_id}")
                            expect(page.locator("#main .breadcrumb")).to_contain_text(f"HT-{ticket_id:05d}")
                            page.on("dialog", lambda dialog: dialog.accept())
                            if bug_id == "B06":
                                page.locator("#message-form [name=body]").fill("Em đã bổ sung đầy đủ thông tin.")
                                observed = click_post(page, "#message-form button[type=submit]", f"/api/requests/{ticket_id}/messages",
                                    {"body": "Em đã bổ sung đầy đủ thông tin."}, "UI student supplement trigger")
                                expect(page.locator("#main .status.WAITING_STUDENT")).to_be_visible()
                            else:
                                action_name = {"B03": "cancel", "B04": "complete", "B05": "reject", "B07": "reopen", "B10": "complete"}[bug_id]
                                body = "Đã cấp giấy xác nhận sinh viên." if bug_id == "B10" else ""
                                if page.locator("#action-body").count():
                                    page.locator("#action-body").fill(body)
                                observed = click_post(page, f'[data-action="{action_name}"]', f"/api/requests/{ticket_id}/action",
                                    {"action": action_name, "body": body}, "UI business action trigger")
                                resulting_status = {"B03": "CANCELLED", "B04": "COMPLETED", "B05": "REJECTED", "B07": "IN_PROGRESS", "B10": "COMPLETED"}[bug_id]
                                expect(page.locator(f"#main .status.{resulting_status}")).to_be_visible()
                            result = detail(ticket_id)
                            actual = {"action_http": observed["http_status"], "item": result["item"],
                                      "messages": result["messages"], "history": result["history"]}
                            if bug_id == "B03":
                                expected = "HTTP 409; yêu cầu đã tiếp nhận phải giữ IN_PROGRESS, không bị hủy."
                                assertion = lambda: equal(observed["http_status"], 409, "Cancel after accept must be rejected")
                                steps = ["sv01 tạo yêu cầu mới.", "cb01 tiếp nhận.", "sv01 mở chi tiết, Hủy yêu cầu và xác nhận."]
                            elif bug_id == "B04":
                                expected = "HTTP 400; cán bộ không thể hoàn tất khi bỏ trống kết quả."
                                assertion = lambda: equal(observed["http_status"], 400, "Completion must require a result")
                                steps = ["sv01 tạo yêu cầu, cb01 tiếp nhận.", "cb01 mở chi tiết, để trống Nội dung xử lý.", "Bấm Hoàn tất."]
                            elif bug_id == "B05":
                                expected = "HTTP 400; cán bộ không thể từ chối khi bỏ trống lý do."
                                assertion = lambda: equal(observed["http_status"], 400, "Rejection must require a reason")
                                steps = ["sv01 tạo yêu cầu NEW.", "cb01 mở chi tiết, để trống Nội dung xử lý.", "Bấm Từ chối và xác nhận."]
                            elif bug_id == "B06":
                                expected = "Gửi bổ sung phải lưu trao đổi và chuyển từ WAITING_STUDENT về IN_PROGRESS."
                                assertion = lambda: equal(result["item"]["status"], "IN_PROGRESS", "Supplement must resume processing")
                                steps = ["sv01 tạo yêu cầu; cb01 nhận và yêu cầu bổ sung có nội dung.", "sv01 mở chi tiết, nhập bổ sung hợp lệ.", "Bấm Gửi bổ sung; quan sát vẫn Chờ bổ sung."]
                            elif bug_id == "B07":
                                expected = "HTTP 409; chỉ COMPLETED được mở lại; REJECTED phải giữ nguyên."
                                assertion = lambda: equal(observed["http_status"], 409, "Rejected request must not reopen")
                                steps = ["sv01 tạo yêu cầu; cb01 từ chối với lý do hợp lệ.", "sv01 mở chi tiết của hồ sơ REJECTED.", "Bấm Mở lại yêu cầu."]
                            else:
                                expected = "Lịch sử phải có COMPLETE từ IN_PROGRESS đến COMPLETED, người và thời điểm."
                                assertion = lambda: equal(result["history"][-1]["action"], "COMPLETE", "Completion must be audited")
                                steps = ["sv01 tạo yêu cầu; cb01 tiếp nhận.", "cb01 nhập kết quả hợp lệ và Hoàn tất.", "Quan sát lịch sử bên phải không có sự kiện Hoàn tất."]

                        image_name = f"{bug_id}-ui.png"
                        page.screenshot(path=str(output / image_name), full_page=True)
                        try:
                            assertion()
                        except AssertionError as error:
                            status, assertion_message = "FAIL", str(error)
                        else:
                            status, assertion_message = "PASS", "The intended behavior passed; seeded defect was not reproduced."
                        record = {"id": bug_id, "title": BUGS[bug_id], "category": "Functional", "requirement": mappings[bug_id],
                                  "training_bugs": True, "database": "independent temporary demo database for this case",
                                  "status": status, "expected": expected, "actual": actual,
                                  "assertion_message": assertion_message, "steps": steps,
                                  "screenshot": image_name, "http_capture": events,
                                  "screenshot_sha256": hashlib.sha256((output / image_name).read_bytes()).hexdigest()}
                        results.append(record)
                        (output / f"{bug_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                        print(f"{bug_id}: {status}; captured UI screenshot and HTTP evidence", flush=True)
                    except Exception as error:
                        setup_errors.append({"id": bug_id, "error": f"{type(error).__name__}: {error}"})
                        print(f"{bug_id}: SETUP ERROR {type(error).__name__}: {error}", flush=True)
                    finally:
                        for context in contexts:
                            context.close()
                        server.shutdown()
                        server.server_close()
                        thread.join(timeout=5)
        finally:
            browser.close()
    expected_ids = {f"B{number:02d}" for number in range(1, 11)}
    verified = len(results) == 10 and {row["id"] for row in results if row["status"] == "FAIL"} == expected_ids and not setup_errors and not page_errors
    source_files = ["app.py", "bugs.py", "static/app.js", "static/training.js", "tools/functional_evidence.py"]
    report = {"started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_files},
              "browser": {"channel": args.channel, "version": browser_version, "viewport": {"width": 1440, "height": 1100}},
              "summary": {"total": len(results), "correct_behavior_assertions_failed": sum(row["status"] == "FAIL" for row in results), "verification": "PASS" if verified else "FAIL"},
              "setup_errors": setup_errors, "page_errors": page_errors, "results": results}
    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrapper PASS: exactly B01-B10 reproduced with actual UI/HTTP evidence." if verified else "Wrapper FAIL: inspect results.json.")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
