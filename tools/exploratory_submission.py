"""Reproduce three existing UI findings on isolated data, without seeding defects.

Usage: python tools/exploratory_submission.py
Assertions express the desired UX. A successful wrapper run means exactly X01,
X02 and X03 fail those assertions, while setup and workflow checks succeed.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app, initialize
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import WSGIRequestHandler, make_server


class QuietHandler(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", default="msedge", help="Installed browser channel (default: msedge).")
    parser.add_argument("--output", default=str(ROOT / "submission/evidence/exploratory"))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    page_errors = []
    findings = []
    infrastructure_error = None
    browser_version = None

    def assertion_finding(issue_id, title, criterion, actual, assertion, screenshots, steps):
        try:
            assertion()
        except AssertionError as error:
            status, message = "FAIL", str(error)
        else:
            status, message = "PASS", "Expected UX assertion passed; the old finding is no longer reproduced."
        findings.append({"id": issue_id, "title": title, "category": "Exploratory usability",
                         "source": "Exploratory UX criterion; not a requirement stated in dactadan.pdf",
                         "training_bugs": False, "status": status, "expected": criterion,
                         "actual": actual, "assertion_message": message, "screenshots": screenshots,
                         "steps": steps, "disposition": "OPEN" if status == "FAIL" else "NOT_REPRODUCED"})
        print(f"{issue_id}: {status} — {title}", flush=True)

    def must_equal(actual, expected, message):
        assert actual == expected, f"{message}; expected={expected!r}, actual={actual!r}"

    with tempfile.TemporaryDirectory(prefix="studentcare-exploratory-") as temp:
        app = create_app({"DATABASE": str(Path(temp) / "exploratory.db"), "TRAINING_BUGS": False})
        initialize(app, demo=True)
        server = make_server("127.0.0.1", 0, app, threaded=True, request_handler=QuietHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel=args.channel)
                browser_version = browser.version
                try:
                    context = browser.new_context(viewport={"width": 390, "height": 844}, locale="vi-VN")
                    page = context.new_page()
                    page.on("pageerror", lambda error: page_errors.append(str(error)))

                    def login(username):
                        page.locator("#login-form [name=username]").fill(username)
                        page.locator("#login-form [name=password]").fill("Demo@123")
                        page.locator("#login-form button[type=submit]").click()
                        expect(page.locator("#workspace")).to_be_visible()
                        expect(page.locator("#main h1")).to_be_visible()

                    page.goto(base)
                    login("sv01")
                    query = "TU_KHOA_CUA_SV01_X01"
                    page.locator("#filter-form [name=q]").fill(query)
                    page.locator("#filter-form button[type=submit]").click()
                    expect(page.locator("#main .empty")).to_be_visible()
                    page.screenshot(path=str(output / "X01-before-sv01-search.png"), full_page=True)
                    page.locator("#logout").click()
                    expect(page.locator("#login-screen")).to_be_visible()
                    login("sv02")
                    carried_query = page.locator("#filter-form [name=q]").input_value()
                    visible_rows = page.locator("#main tbody tr").count()
                    permitted_items = page.evaluate("async () => (await (await fetch('/api/requests')).json()).items.length")
                    page.screenshot(path=str(output / "X01-after-sv02-inherited-search.png"), full_page=True)
                    assertion_finding(
                        "X01", "Bộ lọc tìm kiếm của tài khoản trước giữ lại sau khi đổi tài khoản",
                        "Sau đăng xuất/đăng nhập tài khoản khác, bộ lọc cá nhân phải được đặt lại, không gây lọc nhầm danh sách.",
                        {"previous_user": "sv01", "current_user": "sv02", "previous_query": query,
                         "current_query": carried_query, "visible_rows": visible_rows,
                         "authorized_records_without_filter": permitted_items},
                        lambda: must_equal(carried_query, "", "Account switch must clear the previous account's filter"),
                        ["X01-before-sv01-search.png", "X01-after-sv02-inherited-search.png"],
                        ["Đăng nhập sv01.", f"Tìm '{query}' và bấm Lọc.", "Đăng xuất.",
                         "Đăng nhập sv02 trong cùng tab, không tải lại trang.", "Quan sát ô tìm kiếm và danh sách."])

                    page.locator("#filter-form [name=q]").fill("")
                    page.locator("#filter-form button[type=submit]").click()
                    expect(page.locator("#main tbody tr")).to_have_count(permitted_items)
                    page.locator("#new-request").click()
                    expect(page.locator("#create-dialog")).to_be_visible()
                    draft_title = "Bản nháp X02 cần được giữ lại"
                    draft_content = "Nội dung sinh viên đã nhập trước khi vô tình bấm Escape."
                    page.locator("#create-type").select_option("1")
                    page.locator("#create-form [name=title]").fill(draft_title)
                    page.locator("#create-form [name=content]").fill(draft_content)
                    page.screenshot(path=str(output / "X02-before-draft.png"), full_page=True)
                    dialogs = []

                    def dismiss_dialog(dialog):
                        dialogs.append({"type": dialog.type, "message": dialog.message})
                        dialog.dismiss()

                    page.on("dialog", dismiss_dialog)
                    page.keyboard.press("Escape")
                    expect(page.locator("#create-dialog")).not_to_be_visible()
                    page.locator("#new-request").click()
                    expect(page.locator("#create-dialog")).to_be_visible()
                    current_title = page.locator("#create-form [name=title]").input_value()
                    current_content = page.locator("#create-form [name=content]").input_value()
                    page.screenshot(path=str(output / "X02-after-draft-discarded.png"), full_page=True)
                    assertion_finding(
                        "X02", "Đóng biểu mẫu bằng Escape làm mất bản nháp mà không xác nhận",
                        "Nếu không có xác nhận bỏ bản nháp, mở lại biểu mẫu phải còn nội dung đã nhập trong cùng phiên.",
                        {"draft_title_before": draft_title, "draft_content_before": draft_content,
                         "title_after_reopen": current_title, "content_after_reopen": current_content,
                         "confirmation_dialogs": dialogs, "request_was_submitted": False},
                        lambda: must_equal(current_title, draft_title, "Draft title should survive an accidental Escape close"),
                        ["X02-before-draft.png", "X02-after-draft-discarded.png"],
                        ["Mở Tạo yêu cầu, chọn Học vụ.", "Nhập tiêu đề và nội dung, chưa gửi.",
                         "Bấm Escape để đóng hộp thoại.", "Mở Tạo yêu cầu lần nữa.",
                         "Quan sát dữ liệu bản nháp và việc không có hộp thoại xác nhận bỏ."])

                    page.locator("#close-create").click()
                    page.locator("[data-ticket]").first.click()
                    expect(page.locator("#main .page-heading h2")).to_be_visible()
                    before_dimensions = page.evaluate("({viewport:innerWidth,scroll:document.documentElement.scrollWidth})")
                    page.screenshot(path=str(output / "X03-before-normal-title.png"), full_page=False)
                    page.locator("#back-list").click()
                    page.locator("#new-request").click()
                    page.locator("#create-type").select_option("1")
                    long_title = "W" * 200
                    page.locator("#create-form [name=title]").fill(long_title)
                    page.locator("#create-form [name=content]").fill("Nội dung hợp lệ để kiểm tra bố cục tiêu đề dài.")
                    page.locator("#create-form button[type=submit]").click()
                    expect(page.locator("#main .page-heading h2")).to_have_text(long_title)
                    after_dimensions = page.evaluate("({viewport:innerWidth,scroll:document.documentElement.scrollWidth,title_width:document.querySelector('#main h2').getBoundingClientRect().width})")
                    page.screenshot(path=str(output / "X03-after-long-title-overflow.png"), full_page=False)

                    def no_page_overflow():
                        assert after_dimensions["scroll"] <= after_dimensions["viewport"], (
                            "Long valid title must wrap inside the mobile viewport; " + json.dumps(after_dimensions))

                    assertion_finding(
                        "X03", "Tiêu đề hợp lệ gồm 200 ký tự liền nhau làm trang chi tiết tràn ngang",
                        "Ở viewport 390px, tiêu đề hợp lệ phải xuống dòng để toàn trang không rộng hơn viewport.",
                        {"title_length": len(long_title), "title_character": "W", "before": before_dimensions,
                         "after": after_dimensions, "horizontal_overflow_px": after_dimensions["scroll"] - after_dimensions["viewport"]},
                        no_page_overflow,
                        ["X03-before-normal-title.png", "X03-after-long-title-overflow.png"],
                        ["Đặt viewport 390×844.", "Mở chi tiết một yêu cầu có tiêu đề bình thường để đối chiếu.",
                         "Tạo yêu cầu mới với tiêu đề gồm 200 chữ W liền nhau, nội dung/loại hợp lệ.",
                         "Quan sát chi tiết: tiêu đề không ngắt dòng, trang rộng hơn viewport.",
                         "Đối chiếu documentElement.scrollWidth với innerWidth."])
                    assert not page_errors, page_errors
                    context.close()
                finally:
                    browser.close()
        except Exception as error:
            infrastructure_error = f"{type(error).__name__}: {error}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unknown"
    expected_ids = {"X01", "X02", "X03"}
    reproduced = {item["id"] for item in findings if item["status"] == "FAIL"}
    verified = reproduced == expected_ids and len(findings) == 3 and not infrastructure_error and not page_errors
    sources = ["app.py", "bugs.py", "static/app.js", "static/style.css", "tools/exploratory_submission.py"]
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    screenshots = {path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
                   for path in sorted(output.glob("X*.png"))}
    report = {"title": "StudentCare exploratory UI findings", "started_at_utc": started,
              "finished_at_utc": datetime.now(timezone.utc).isoformat(), "source_revision": revision,
              "source_files_sha256": source_hashes, "screenshot_files": screenshots,
              "environment": {"database": "temporary, seeded demo, deleted after run", "training_bugs": False,
                              "browser_channel": args.channel, "browser_version": browser_version,
                              "viewport": {"width": 390, "height": 844}},
              "test_summary": {"total": len(findings), "failed_correct_behavior_assertions": len(reproduced),
                               "expected_findings": sorted(expected_ids), "verification": "PASS" if verified else "FAIL"},
              "infrastructure_error": infrastructure_error, "page_errors": page_errors, "findings": findings}
    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrapper: PASS — exactly X01/X02/X03 were reproduced; the three UX assertions remain FAIL."
          if verified else f"Wrapper: FAIL — {infrastructure_error or 'outcomes differ from expected findings'}")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
