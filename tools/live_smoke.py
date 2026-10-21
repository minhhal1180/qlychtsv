"""Check deployed HTTPS UI and access controls without creating or changing tickets."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="https://sv23.bcse-vju.com")
args = parser.parse_args()
base = args.url.rstrip("/")
artifacts = Path(__file__).resolve().parents[1] / "test-results"
artifacts.mkdir(exist_ok=True)
errors, results = [], []

with sync_playwright() as p:
    browser = p.chromium.launch()
    contexts = []
    pages = {}
    try:
        for username, role in [("sv01", "STUDENT"), ("sv02", "STUDENT"), ("cb01", "STAFF"), ("admin", "ADMIN")]:
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            contexts.append(context)
            page = context.new_page()
            pages[username] = page
            page.on("pageerror", lambda error: errors.append(str(error)))
            response = page.goto(base, wait_until="domcontentloaded")
            assert response.status == 200, response.status
            expect(page.locator("#login-screen")).to_be_visible()
            if username == "sv01":
                page.screenshot(path=str(artifacts / "live-login.png"), full_page=True)
            page.locator("#login-form [name=username]").fill(username)
            page.locator("#login-form [name=password]").fill("Demo@123")
            page.get_by_role("button", name="Đăng nhập", exact=True).click()
            expect(page.locator("#workspace")).to_be_visible(timeout=20000)
            expect(page.locator("#main h1")).to_be_visible()
            me = page.evaluate("async () => (await fetch('/api/me')).json()")
            assert me["user"]["role"] == role
            cookie = next(c for c in context.cookies() if c["name"] == "session")
            assert cookie["secure"] and cookie["httpOnly"] and cookie["sameSite"] == "Lax"
            results.append(f"{username}: {role}, HTTPS login, secure session")
            if username == "sv01":
                page.screenshot(path=str(artifacts / "live-student-desktop.png"), full_page=True)
                page.set_viewport_size({"width":390,"height":844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(artifacts / "live-student-mobile.png"), full_page=True)
        first = pages["sv01"].evaluate("async () => (await (await fetch('/api/requests')).json()).items[0]")
        assert first, "Demo data should have at least one request"
        status = pages["sv02"].evaluate("async id => (await fetch('/api/requests/'+id)).status", first["id"])
        assert status == 403, status
        status = pages["admin"].evaluate("async id => (await fetch('/api/requests/'+id)).status", first["id"])
        assert status == 403, status
        status = pages["sv01"].evaluate("async () => (await fetch('/api/users')).status")
        assert status == 403, status
        assert not errors, errors
        report = {"result":"PASS", "url":base, "users":results, "page_errors":errors,
                  "checks":["HTTPS","four-logins-three-roles","secure-cookies","ownership-and-admin-denials","desktop-mobile"]}
        (artifacts / "live.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("PASS: deployed HTTPS, three roles, secure cookies, access controls, desktop/mobile.")
    finally:
        for context in contexts:
            context.close()
        browser.close()
