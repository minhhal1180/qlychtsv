"""Server-side extra defects; browser-only defects are tested by extra_evidence.py."""
import io
import time

from tests.test_support import SupportCase


class ExtraAPITests(SupportCase):
    def test_P01_search_response_under_800_ms(self):
        client, _csrf = self.user("sv01")
        started = time.perf_counter()
        response = client.get("/api/requests?q=H")
        duration = time.perf_counter() - started
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(duration, 0.8, f"P01: search took {duration * 1000:.1f} ms, limit 800 ms")

    def test_P02_notifications_response_under_900_ms(self):
        client, _csrf = self.user("sv01")
        started = time.perf_counter()
        response = client.get("/api/notifications")
        duration = time.perf_counter() - started
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(duration, 0.9, f"P02: notifications took {duration * 1000:.1f} ms, limit 900 ms")

    def test_R01_zero_byte_upload_returns_validation_error(self):
        before = self.sql("SELECT COUNT(*) FROM requests")[0][0]
        response = self.post("sv01", "/requests", multipart={"type_id": "1", "title": "Tệp rỗng R01",
                             "content": "Nội dung hợp lệ", "files": (io.BytesIO(b""), "empty.txt")})
        self.assertEqual(response.status_code, 400, "R01: empty file must return 400, not a server error")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM requests")[0][0], before)

    def test_R02_missing_attachment_returns_not_found(self):
        response = self.get("sv01", "/attachments/999999")
        self.assertEqual(response.status_code, 404, "R02: missing attachment must return 404, not a server error")
