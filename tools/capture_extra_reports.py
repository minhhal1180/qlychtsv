"""Screenshot four clearly labelled HTTP/measurement reports from existing JSON.

This helper does not run the application, send API requests, or repeat tests.
The images are reports of already captured measurements, not application UI.
"""
import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def escaped(value):
    return html.escape(str(value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", default="msedge")
    parser.add_argument("--directory", default=str(ROOT / "submission/evidence/additional"))
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    source_path = directory / "results.json"
    source_bytes = source_path.read_bytes()
    report = json.loads(source_bytes)
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    captured = []
    rendered_at = datetime.now(timezone.utc).isoformat()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel)
        try:
            page = browser.new_page(viewport={"width": 1120, "height": 960}, device_scale_factor=1)
            for bug_id in ("P01", "P02", "R01", "R02"):
                result = next(row for row in report["results"] if row["id"] == bug_id and row["mode"] == "training")
                case_path = directory / f"{bug_id}-training.json"
                case_bytes = case_path.read_bytes()
                case = json.loads(case_bytes)
                assert case["actual"] == result["actual"], f"Case and aggregate evidence disagree: {bug_id}"
                case_digest = hashlib.sha256(case_bytes).hexdigest()
                actual_json = json.dumps(result["actual"], ensure_ascii=False, indent=2)
                measurement_table = ""
                if result["category"] == "Performance":
                    measurements = result["actual"]["samples_ms"]
                    statuses = result["actual"]["http_statuses"]
                    measurement_table = "<table><thead><tr><th>Mẫu</th><th>Thời gian nhận hết body (ms)</th><th>HTTP</th></tr></thead><tbody>"
                    measurement_table += "".join(f"<tr><td>{i + 1}</td><td>{escaped(value)}</td><td>{escaped(statuses[i])}</td></tr>" for i, value in enumerate(measurements))
                    measurement_table += "</tbody></table>"
                    metric = f"p95 thực đo {result['actual']['p95_ms']} ms · ngưỡng {result['actual']['threshold_ms']} ms"
                else:
                    metric = f"HTTP thực nhận: {result['actual']['http_status']}"
                steps = "".join(f"<li>{escaped(step)}</li>" for step in result["steps"])
                document = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>{escaped(bug_id)} — Báo cáo bằng chứng đã ghi</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;padding:34px 40px;font:15px/1.55 Arial,sans-serif;color:#20322c;background:#f1f4f2}}
main{{max-width:1040px;margin:auto;background:white;border:1px solid #d7e2da;padding:30px 34px;border-radius:10px}}
.notice{{padding:12px 16px;background:#fff3dc;border:1px solid #e0bd6c;border-radius:5px;color:#67460c;font-size:17px;font-weight:bold}}
.small{{font-size:12px;color:#627269}}h1{{font-size:26px;line-height:1.3;margin:22px 0 12px}}h2{{font-size:17px;margin:22px 0 8px}}
.bad{{color:#a82424;font-weight:bold}}.metric{{background:#f0f5f1;padding:12px 16px;border-left:4px solid #287954;font-weight:bold}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #dde5df;padding:8px 12px;text-align:left}}th{{background:#f2f6f3}}
pre{{font:13px/1.5 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8f6;border:1px solid #e1e7e2;padding:14px}}
.source{{font-size:11px;overflow-wrap:anywhere;border-top:1px solid #dfe6e0;margin-top:22px;padding-top:12px;color:#5e6e64}}
ol{{font-size:13px;padding-left:22px}}p{{margin:8px 0}}
</style></head><body><main>
<div class="notice">Ảnh báo cáo HTTP/đo, không phải UI ứng dụng</div>
<p class="small">Bản tổng hợp chỉ đọc từ dữ liệu đã ghi. Không chạy lại testcase/API khi tạo ảnh này.</p>
<h1>{escaped(bug_id)} · {escaped(result['title'])}</h1>
<p>Loại: <strong>{escaped(result['category'])}</strong> · Yêu cầu: {escaped(result['requirement'])} · Chế độ: <strong>TRAINING_BUGS=1</strong> · Assertion: <span class="bad">{escaped(result['status'])}</span></p>
<div class="metric">{escaped(metric)}</div>
<h2>Kết quả cần có</h2><p>{escaped(result['expected'])}</p>
<h2>Dữ liệu thực tế đã ghi</h2>{measurement_table}<pre>{escaped(actual_json)}</pre>
<h2>Các bước của lần đo gốc</h2><ol>{steps}</ol>
<p class="small">{escaped(result['assertion_message'])}</p>
<div class="source">
<p>JSON từng testcase: <strong>{escaped(case_path.name)}</strong><br>SHA256: {case_digest}</p>
<p>JSON tổng hợp: <strong>{escaped(source_path.name)}</strong><br>SHA256: {source_digest}</p>
<p>Lần ghi gốc bắt đầu (UTC): {escaped(report['started_at_utc'])}<br>Kết thúc (UTC): {escaped(report['finished_at_utc'])}<br>Revision mã nguồn trong lần ghi: {escaped(report['source_revision'])}</p>
<p>Ảnh báo cáo tạo lúc (UTC): {escaped(rendered_at)}. Các giá trị trên được lấy nguyên từ JSON gốc.</p>
</div></main></body></html>"""
                html_path = directory / f"{bug_id}-report.html"
                image_path = directory / f"{bug_id}-report.png"
                html_path.write_text(document, encoding="utf-8")
                page.goto(html_path.as_uri(), wait_until="load")
                page.screenshot(path=str(image_path), full_page=True)
                captured.append({"id": bug_id, "image": image_path.name, "html": html_path.name,
                                 "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                                 "original_case": case_path.name, "original_case_sha256": case_digest})
                print(f"Captured {image_path.name} from {case_path.name}; no API calls.")
        finally:
            browser.close()
    manifest = {"rendered_at_utc": rendered_at, "purpose": "Clearly labelled reports from existing captured JSON, not application screenshots",
                "source": source_path.name, "source_sha256": source_digest, "reports": captured}
    (directory / "report-images.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
