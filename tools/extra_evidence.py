"""Record ten additional seeded defects against the same baseline/training build.

Correct-behavior assertions remain FAIL in training. The wrapper returns zero
only for 10 PASS baseline and exactly 10 FAIL training, with no setup errors.
"""
import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app, initialize
from playwright.sync_api import expect, sync_playwright
from training_extras import EXTRA_BUGS
from werkzeug.serving import WSGIRequestHandler, make_server


class Quiet(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--output", default=str(ROOT / "submission/evidence/additional"))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = []
    infrastructure_errors = []
    browser_errors = []
    started = datetime.now(timezone.utc).isoformat()

    def record(mode, bug_id, expected, actual, check, steps, files):
        try:
            check()
        except AssertionError as error:
            status, message = "FAIL", str(error)
        else:
            status, message = "PASS", "The intended behavior assertion passed."
        result = {"id": bug_id, **EXTRA_BUGS[bug_id], "mode": mode, "training_bugs": mode == "training",
                  "status": status, "expected": expected, "actual": actual, "assertion_message": message,
                  "steps": steps, "evidence_files": files}
        results.append(result)
        (output / f"{bug_id}-{mode}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{mode}: {bug_id} {status}", flush=True)

    def equal(actual, expected, message):
        assert actual == expected, f"{message}; expected={expected!r}, actual={actual!r}"

    def at_most(actual, limit, message):
        assert actual <= limit, f"{message}; actual={actual}, limit={limit}"

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel)
        browser_version = browser.version
        try:
            for bugs_enabled, mode in [(False, "baseline"), (True, "training")]:
                with tempfile.TemporaryDirectory(prefix=f"studentcare-{mode}-") as temp:
                    app = create_app({"DATABASE": str(Path(temp) / "support.db"), "TRAINING_BUGS": bugs_enabled})
                    initialize(app, demo=True)
                    server = make_server("127.0.0.1", 0, app, threaded=True, request_handler=Quiet)
                    thread = Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh")
                    page = context.new_page()
                    page.on("pageerror", lambda error: browser_errors.append({"mode": mode, "error": str(error)}))
                    base = f"http://127.0.0.1:{server.server_port}"
                    try:
                        response = page.goto(base)
                        assert response.status == 200
                        source = response.text()
                        assert ("/static/training.js" in source) == bugs_enabled, "Conditional training assets are not integrated correctly."
                        page.locator("#login-form [name=username]").fill("sv01")
                        page.locator("#login-form [name=password]").fill("Demo@123")
                        page.locator("#login-form button[type=submit]").click()
                        expect(page.locator("#workspace")).to_be_visible()
                        expect(page.locator("#main tbody tr")).to_have_count(4)
                        me = context.request.get(base + "/api/me").json()
                        csrf = me["csrf"]

                        # Use a known unambiguous day/month so C03 is reproducible on any run date.
                        with app.app_context():
                            from flask import g
                            from app import db
                            g.app_db = app.config["DATABASE"]
                            db().execute("UPDATE requests SET created_at='2026-10-21T03:00:00+00:00',updated_at='2026-10-21T03:00:00+00:00' WHERE id=4")
                        page.reload()
                        expect(page.locator("#main tbody tr")).to_have_count(4)

                        completed_row = page.locator("tbody tr").filter(has=page.locator('[data-ticket="4"]')).first
                        completed_label = completed_row.locator(".status.COMPLETED").text_content()
                        page.screenshot(path=str(output / f"C01-{mode}.png"), full_page=True)
                        record(mode, "C01", "COMPLETED phải hiển thị 'Hoàn tất'.", {"api_status": "COMPLETED", "display_label": completed_label},
                               lambda: equal(completed_label, "Hoàn tất", "Incorrect completed status wording"),
                               ["Đăng nhập sv01.", "Mở danh sách và xem nhãn yêu cầu HT-00004 có trạng thái COMPLETED."], [f"C01-{mode}.png"])

                        created_date = completed_row.locator("td").nth(3).evaluate("el => [...el.childNodes].find(n => n.nodeType === Node.TEXT_NODE).textContent.trim()")
                        page.screenshot(path=str(output / f"C03-{mode}.png"), full_page=True)
                        record(mode, "C03", "Ngày 21/10/2026 phải trình bày theo dd/mm/yyyy.",
                               {"source_timestamp": "2026-10-21T03:00:00+00:00", "display_date": created_date},
                               lambda: equal(created_date, "21/10/2026", "Incorrect day/month ordering"),
                               ["Dùng dữ liệu mẫu có created_at=2026-10-21.", "Đăng nhập sv01; xem cột Ngày tạo của HT-00004."], [f"C03-{mode}.png"])

                        page.locator('[data-ticket="4"]').first.click()
                        expect(page.locator("#main .page-heading h2")).to_be_visible()
                        title_box = page.locator("#main .page-heading h2").evaluate("el => ({text:el.textContent,client:el.clientWidth,scroll:el.scrollWidth,white_space:getComputedStyle(el).whiteSpace,overflow:getComputedStyle(el).overflow})")
                        page.screenshot(path=str(output / f"V01-{mode}.png"), full_page=True)
                        record(mode, "V01", "Tiêu đề chi tiết phải hiển thị đầy đủ, không bị cắt im lặng ở desktop.", title_box,
                               lambda: at_most(title_box["scroll"], title_box["client"], "Detail title is clipped"),
                               ["Viewport 1440×1000.", "Đăng nhập sv01; mở chi tiết HT-00004.", "Quan sát phần tiêu đề đầy đủ."], [f"V01-{mode}.png"])

                        page.locator("#back-list").click()
                        page.locator("#new-request").click()
                        expect(page.locator("#create-dialog")).to_be_visible()
                        upload_help = page.locator("#create-form .help").text_content()
                        page.screenshot(path=str(output / f"C02-{mode}.png"), full_page=True)
                        record(mode, "C02", "Hướng dẫn phải ghi đúng giới hạn 5 MB/tệp của backend.", {"display_help": upload_help, "backend_limit_mb": 5},
                               lambda: equal("50 MB" in upload_help, False, "Upload help misstates the limit as 50 MB"),
                               ["Đăng nhập sv01; mở Tạo yêu cầu.", "Đọc dòng hướng dẫn dung lượng tệp và đối chiếu giới hạn 5 MB."], [f"C02-{mode}.png"])

                        page.set_viewport_size({"width": 375, "height": 812})
                        dialog_box = page.locator("#create-dialog").evaluate("el => ({viewport:innerWidth,width:el.getBoundingClientRect().width,left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right})")
                        page.screenshot(path=str(output / f"V02-{mode}.png"), full_page=False)
                        record(mode, "V02", "Hộp thoại tạo yêu cầu không được rộng hơn viewport 375px.", dialog_box,
                               lambda: at_most(dialog_box["width"], dialog_box["viewport"], "Create dialog exceeds the mobile viewport"),
                               ["Đặt viewport 375×812.", "Đăng nhập sv01 và mở Tạo yêu cầu.", "Đối chiếu chiều rộng hộp thoại và màn hình."], [f"V02-{mode}.png"])
                        page.keyboard.press("Escape")
                        expect(page.locator("#create-dialog")).not_to_be_visible()
                        mobile_status = page.locator("tbody .status").first.evaluate("el => ({text:el.textContent,visibility:getComputedStyle(el).visibility,display:getComputedStyle(el).display})")
                        page.screenshot(path=str(output / f"V03-{mode}.png"), full_page=True)
                        record(mode, "V03", "Nhãn trạng thái trong danh sách vẫn phải nhìn thấy trên mobile.", mobile_status,
                               lambda: equal(mobile_status["visibility"], "visible", "Mobile status badge is hidden"),
                               ["Đặt viewport 375×812.", "Đăng nhập sv01; xem cột Trạng thái của bảng danh sách."], [f"V03-{mode}.png"])

                        for bug_id, path, limit in [("P01", "/api/requests?q=XIN", 800), ("P02", "/api/notifications", 900)]:
                            measurements = []
                            statuses = []
                            for sample in range(5):
                                before = time.perf_counter()
                                measured = context.request.get(base + path)
                                measured.body()
                                measurements.append(round((time.perf_counter() - before) * 1000, 3))
                                statuses.append(measured.status)
                            assert statuses == [200] * 5, statuses
                            p95 = sorted(measurements)[math.ceil(0.95 * len(measurements)) - 1]
                            record(mode, bug_id, f"Một người dùng, 5 mẫu tuần tự: p95 không quá {limit} ms.",
                                   {"endpoint": path, "samples_ms": measurements, "p95_ms": p95,
                                    "threshold_ms": limit, "http_statuses": statuses, "users": 1, "concurrent_requests": 1},
                                   lambda: at_most(p95, limit, "Measured p95 exceeds the response time criterion"),
                                   ["Đăng nhập sv01.", f"Gửi 5 GET {path} tuần tự, một người dùng, không chạy tải.",
                                    "Đo hết thời gian nhận response body bằng perf_counter; tính p95 nearest-rank."], [f"{bug_id}-{mode}.json"])

                        before_count = len(context.request.get(base + "/api/requests").json()["items"])
                        empty_response = context.request.post(base + "/api/requests", headers={"X-CSRF-Token": csrf}, multipart={
                            "type_id": "1", "title": "Kiểm tra tệp rỗng R01", "content": "Nội dung hợp lệ",
                            "files": {"name": "empty.txt", "mimeType": "text/plain", "buffer": b""}})
                        actual_empty = {"endpoint": "POST /api/requests", "filename": "empty.txt", "file_size_bytes": 0,
                                        "http_status": empty_response.status, "response_body": empty_response.json(),
                                        "request_count_before": before_count,
                                        "request_count_after": len(context.request.get(base + "/api/requests").json()["items"])}
                        record(mode, "R01", "Upload tệp rỗng trả HTTP 400 và không lưu yêu cầu.", actual_empty,
                               lambda: equal(empty_response.status, 400, "Invalid empty file caused server error"),
                               ["Đăng nhập sv01, lấy CSRF từ /api/me.", "POST multipart /api/requests với dữ liệu hợp lệ và empty.txt 0 byte.",
                                "Kiểm tra HTTP status và số yêu cầu trước/sau."], [f"R01-{mode}.json"])
                        absent = context.request.get(base + "/api/attachments/999999")
                        record(mode, "R02", "ID tệp không tồn tại trả HTTP 404, không trả HTTP 500.",
                               {"endpoint": "GET /api/attachments/999999", "http_status": absent.status, "response_body": absent.json()},
                               lambda: equal(absent.status, 404, "Missing file caused server error"),
                               ["Đăng nhập sv01.", "GET /api/attachments/999999 (ID không có trong dữ liệu mẫu).", "Quan sát HTTP status."], [f"R02-{mode}.json"])
                    except Exception as error:
                        infrastructure_errors.append({"mode": mode, "error": f"{type(error).__name__}: {error}"})
                    finally:
                        context.close()
                        server.shutdown()
                        server.server_close()
                        thread.join(timeout=5)
        finally:
            browser.close()

    expected_ids = set(EXTRA_BUGS)
    baseline = [r for r in results if r["mode"] == "baseline"]
    training = [r for r in results if r["mode"] == "training"]
    verified = (len(baseline) == len(training) == 10 and {r["id"] for r in baseline} == expected_ids
                and all(r["status"] == "PASS" for r in baseline) and all(r["status"] == "FAIL" for r in training)
                and not infrastructure_errors and not browser_errors)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    sources = ["app.py", "templates/index.html", "training_extras.py", "static/training.css", "static/training.js", "tools/extra_evidence.py"]
    report = {"started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_revision": revision, "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
              "browser": {"channel": args.channel, "version": browser_version},
              "performance_method": "Five sequential authenticated HTTP calls, one local browser user, complete body timing, nearest-rank p95; training sleeps are bounded at 1.1/1.2 seconds.",
              "summary": {"baseline": {"tests": len(baseline), "pass": sum(r["status"] == "PASS" for r in baseline)},
                          "training": {"tests": len(training), "fail": sum(r["status"] == "FAIL" for r in training)},
                          "verification": "PASS" if verified else "FAIL"},
              "infrastructure_errors": infrastructure_errors, "page_errors": browser_errors, "results": results}
    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrapper PASS: baseline 10/10 PASS; training exactly 10 FAIL." if verified else "Wrapper FAIL: inspect results.json infrastructure/outcomes.")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
