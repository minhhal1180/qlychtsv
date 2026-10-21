"""Optional real-browser QA. Run: python tools/browser_smoke.py (uses temp data)."""
import json
import sys
import tempfile
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app, initialize
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server, WSGIRequestHandler


class QuietHandler(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


def main():
    artifacts = ROOT / "test-results"
    artifacts.mkdir(exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory() as temp:
        app = create_app({"DATABASE": str(Path(temp) / "browser.db"), "TRAINING_BUGS": False})
        initialize(app, demo=True)
        server = make_server("127.0.0.1", 0, app, threaded=True, request_handler=QuietHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                contexts = []
                def login(username, mobile=False):
                    context = browser.new_context(viewport={"width": 390 if mobile else 1440, "height": 844 if mobile else 1000})
                    contexts.append(context)
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base)
                    expect(page.locator('#login-screen')).to_be_visible()
                    if username == 'sv01' and not mobile:
                        page.screenshot(path=str(artifacts / "login-desktop.png"), full_page=True)
                    page.locator('[name=username]').first.fill(username)
                    page.locator('[name=password]').first.fill('Demo@123')
                    page.get_by_role('button', name='Đăng nhập').click()
                    expect(page.locator('#workspace')).to_be_visible()
                    expect(page.locator('#main h1')).to_be_visible()
                    return page
                student = login('sv01')
                expect(student.locator('tbody tr')).to_have_count(4)
                student.screenshot(path=str(artifacts / 'requests-desktop.png'), full_page=True)
                student.get_by_role('button', name='＋ Tạo yêu cầu').click()
                student.locator('#create-type').select_option('1')
                title = 'Kiểm tra HỌC PHÍ <img src=x onerror=alert(1)>'
                student.locator('#create-form [name=title]').fill(title)
                student.locator('#create-form [name=content]').fill('Em cần đối chiếu hồ sơ học phí.')
                student.locator('#create-form [name=files]').set_input_files({'name':'notes.txt','mimeType':'text/plain','buffer':b'Browser upload'})
                def lose_response(route):
                    route.fetch()  # Backend saves successfully, but the browser loses the response.
                    route.abort('failed')
                student.route('**/api/requests', lose_response)
                student.get_by_role('button', name='Gửi yêu cầu →').click()
                expect(student.locator('#create-error')).to_contain_text('Failed to fetch')
                student.unroute('**/api/requests', lose_response)
                # Retry the same form; a different multipart boundary must not create a duplicate.
                student.get_by_role('button', name='Gửi yêu cầu →').click()
                expect(student.locator('#main .page-heading h2')).to_have_text(title)
                expect(student.locator('#main img')).to_have_count(0)
                ticket_path = student.url.split('#')[1]
                expect(student.locator('.file-link')).to_contain_text('notes.txt')
                with student.expect_download() as download_info:
                    student.locator('.file-link').click()
                download = download_info.value
                assert Path(download.path()).read_bytes() == b'Browser upload'
                staff = login('cb01')
                staff.goto(base + '/#' + ticket_path)
                staff.get_by_role('button', name='Tiếp nhận yêu cầu').click()
                expect(staff.locator('#main .status')).to_have_text('Đang xử lý')
                # CSRF/server validation remains authoritative on the training UI.
                staff.get_by_role('button', name='Hoàn tất', exact=True).click()
                expect(staff.locator('#action-error')).to_contain_text('Phải nhập')
                staff.locator('#action-body').fill('Em bổ sung thông tin thanh toán nhé.')
                staff.get_by_role('button', name='Yêu cầu bổ sung', exact=True).click()
                expect(staff.locator('#main .status')).to_have_text('Chờ bổ sung')
                student.reload()
                student.locator('#message-form [name=body]').fill('Em gửi thêm mã thanh toán GD123.')
                student.get_by_role('button', name='Gửi bổ sung →').click()
                expect(student.locator('#main .status')).to_have_text('Đang xử lý')
                staff.reload()
                staff.locator('#action-body').fill('Đã đối chiếu thanh toán thành công.')
                staff.get_by_role('button', name='Hoàn tất', exact=True).click()
                expect(staff.locator('#main .status')).to_have_text('Hoàn tất')
                expect(staff.locator('.history-item').last).to_contain_text('Đã hoàn tất yêu cầu')
                staff.screenshot(path=str(artifacts / 'detail-desktop.png'), full_page=True)
                student.reload()
                student.get_by_role('button', name='Mở lại yêu cầu', exact=True).click()
                expect(student.locator('#main .status')).to_have_text('Đang xử lý')
                student.goto(base + '/#notifications')
                student.get_by_role('button', name='Đánh dấu đã đọc').first.click()
                expect(student.locator('.notification').first).to_contain_text('Đã đọc')
                student.reload()
                expect(student.locator('.notification').first).to_contain_text('Đã đọc')
                student.goto(base + '/#requests')
                student.get_by_role('textbox', name='Tìm theo mã hoặc tiêu đề').fill('học phí')
                student.get_by_role('button', name='Lọc', exact=True).click()
                expect(student.get_by_role('button', name=title, exact=True)).to_be_visible()
                admin = login('admin')
                admin.get_by_role('button', name='Tài khoản', exact=False).click()
                expect(admin.locator('#main h1')).to_have_text('Quản lý tài khoản')
                form = admin.locator('#user-form')
                form.locator('[name=name]').fill('Người dùng kiểm thử')
                form.locator('[name=username]').fill('smoke-user')
                form.locator('[name=password]').fill('Password@123')
                form.get_by_role('button', name='Lưu tài khoản').click()
                expect(admin.locator('tbody')).to_contain_text('smoke-user')
                admin.get_by_role('button', name='Loại yêu cầu', exact=False).click()
                admin.locator('[data-edit-type="1"]').click()
                admin.locator('#type-form [name=name]').fill('Học vụ cập nhật')
                admin.get_by_role('button', name='Lưu danh mục').click()
                expect(admin.locator('tbody')).to_contain_text('Học vụ cập nhật')
                mobile = login('sv01', mobile=True)
                expect(mobile.locator('tbody tr')).to_have_count(5)
                assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
                mobile.screenshot(path=str(artifacts / 'requests-mobile.png'), full_page=True)
                mobile.get_by_role('button', name='＋ Tạo yêu cầu').click()
                expect(mobile.locator('#create-dialog')).to_be_visible()
                mobile.locator('#close-create').click()
                student.get_by_role('button', name='Đăng xuất', exact=False).click()
                expect(student.locator('#login-screen')).to_be_visible()
                assert not errors, errors
                for context in contexts:
                    context.close()
                browser.close()
                report = {"result":"PASS", "console_errors":errors, "viewports":["1440x1000","390x844"],
                          "checks":["login-three-roles","create-upload-download","lost-response-multipart-retry","html-escaping","accept","required-result",
                                    "ask-supplement","complete-history","reopen","notifications-persist","search-unicode",
                                    "admin-create-user","admin-edit-type","mobile-no-page-overflow","logout"]}
                (artifacts / "browser.json").write_text(json.dumps(report, indent=2), encoding='utf-8')
                print('PASS: browser workflow, three roles, file, Unicode, desktop/mobile; no JavaScript errors.')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
