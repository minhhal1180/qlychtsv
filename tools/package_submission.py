"""Package public handover and a separate private instructor dossier, without caches."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'submission'
TARGET=ROOT.parent/'qlychtsv-ho-so-23110193'
PRIVATE_REPO='https://github.com/minhhal1180/qlychtsv-ho-so-23110193'
parser=argparse.ArgumentParser();parser.add_argument('--draft',action='store_true');args=parser.parse_args()
if not TARGET.exists():
    subprocess.run(['git','clone',PRIVATE_REPO+'.git',str(TARGET)],check=True)
if not (TARGET/'.git').is_dir():raise SystemExit('Expected a separate instructor repository checkout.')

def copy_tree(source,destination):
    if not source.exists():return
    shutil.copytree(source,destination,dirs_exist_ok=True,
        ignore=shutil.ignore_patterns('node_modules','__pycache__','.pytest_cache','.venv','.env','*.pyc'))

nonfunctional=json.loads((BASE/'evidence/nonfunctional/results.json').read_text(encoding='utf-8'))
if not args.draft and nonfunctional['counts'].get('NOT_RUN',0):
    raise SystemExit('NFR evidence still pending; use --draft only for a clearly marked partial package.')
copy_tree(BASE/'private',TARGET)
copy_tree(BASE/'public',TARGET/'owner-handover')
copy_tree(BASE/'evidence',TARGET/'evidence')
copy_tree(BASE/'data',TARGET/'data')
copy_tree(BASE/'tooling',TARGET/'tooling')
scripts=TARGET/'runners';scripts.mkdir(exist_ok=True)
for name in ['submission_functional.py','submission_nfr.py','extra_evidence.py','functional_evidence.py',
             'exploratory_submission.py','run_submission_tooling.py','build_workbooks.py','build_submission.py',
             'capture_extra_reports.py','live_smoke.py']:
    source=ROOT/'tools'/name
    if source.exists():shutil.copy2(source,scripts/name)
source_inventory=ROOT/'test-results/template-reading/source-inventory.json'
if source_inventory.exists():shutil.copy2(source_inventory,TARGET/'source-inventory.json')
for source,name in [(ROOT/'test-results/baseline.json','baseline-api-verifier.json'),(ROOT/'test-results/training.json','training-api-verifier.json')]:
    if source.exists():shutil.copy2(source,TARGET/'evidence'/name)
private_readme='''# Hồ sơ StudentCare – chỉ gửi giảng viên

**Bùi Xuân Minh – 23110193**. Kho riêng tư, không gửi Bug Manifest hoặc các bug report này cho bạn cặp trước khi kiểm thử.

- [Mẫu 02 – Bug Manifest](Mau_02_Bug_Manifest_23110193.xlsx): 20 seed, đủ 5 nhóm, mỗi lỗi có yêu cầu/bước tái hiện/actual/ảnh.
- [Mẫu 03 – Workbook tự kiểm thử](self-test/Mau_03_Bo_bieu_mau_TU_KIEM_THU_23110193.xlsx): 7 sheet, 97 functional, 19 NFR, 23 bug report; công thức tính số liệu.
- [Mẫu 04 – Test Plan](self-test/Mau_04_Test_Plan_TU_KIEM_THU_23110193.pdf).
- [Mẫu 05 – Test Summary](self-test/Mau_05_Test_Summary_TU_KIEM_THU_23110193.pdf), có ảnh biểu đồ JMeter gốc.
- [Tài liệu bàn giao cho bạn cặp](owner-handover/README.md).
- [23 bug report trên Issues](https://github.com/minhhal1180/qlychtsv-ho-so-23110193/issues): 20 seed và 3 exploratory ngoài PDF gốc.
- [Công cụ](tooling/README.md): Postman/Newman, Puppeteer, JMX; kết quả trong [evidence](evidence).

Các bộ test là **tự kiểm thử chính hệ thống của sinh viên**, không phải kiểm thử độc lập hệ thống bạn cặp. Ngày chạy thực lấy raw ISO timestamp; đợt 24–25/10/2026 theo UTC+7. Không làm giả dữ liệu/điểm/chữ ký.

Phần tester chính thức còn chờ họ tên/mã SV, link hệ thống/repo, URD/SRS/API/tài khoản của bạn cặp. Biên bản số 2 chưa ký, chưa ghi kết quả giả cho hệ thống chưa được bàn giao. Cũng chưa gửi bài vào biểu mẫu vì người dùng mới cung cấp ảnh, chưa có URL form.

Để nộp link riêng tư, chủ kho cần cấp quyền cho tài khoản GitHub của giảng viên hoặc tải gói và gửi qua kênh riêng được phép. Chưa có thông tin giảng viên để cấp quyền thay người dùng. Không mặc định cho bạn cặp quyền kho này.

Giới hạn bí mật: danh sách 10 lỗi bản cũ đã từng có trong lịch sử public repo. Các tài liệu đó đã được gỡ khỏi nhánh hiện tại, nhưng không viết lại lịch sử Git và không khẳng định blind testing tuyệt đối. Báo rõ điều này nếu giảng viên yêu cầu.

Nguồn mẫu: 9 file Drive được xem công khai; owner khóa tải gốc. Biểu mẫu được tái dựng theo cấu trúc/sheet/cột đã đọc, không phải file gốc được tải/export. Danh sách link nguồn trong source-inventory.json.

Runners gốc nằm trong repo ứng dụng `qlychtsv/tools`. Folder runners ở đây là snapshot tham khảo: chạy từ checkout ứng dụng, cài dependencies tương ứng, không chạy độc lập folder này khi thiếu app/schema. JMeter được đo trên bản sao cục bộ, **không đại diện hiệu năng VPS**. Báo cáo không xác định điểm bão hòa ngoài 4 users và rate cap.
'''
(TARGET/'README.md').write_text(private_readme,encoding='utf-8')
links={'student_id':'23110193','student_name':'Bùi Xuân Minh','github':'https://github.com/minhhal1180/qlychtsv',
       'website':'https://sv23.bcse-vju.com','documents':'https://github.com/minhhal1180/qlychtsv/tree/main/submission/public',
       'bugs':PRIVATE_REPO+'/issues','instructor_dossier':PRIVATE_REPO,
       'status':'Owner documents and real self-test complete; independent paired-student test pending missing handover.',
       'form_submitted':False,'form_url_provided':False,'signatures_fabricated':False,
       'private_access':'Instructor account not provided; owner must grant access or privately deliver download.'}
(TARGET/'submission-links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2),encoding='utf-8')
(BASE/'private/submission-links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2),encoding='utf-8')
fingerprints={str(path.relative_to(TARGET)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
              for path in TARGET.rglob('*') if path.is_file() and '.git' not in path.parts and path.name!='SHA256SUMS.json'}
(TARGET/'SHA256SUMS.json').write_text(json.dumps(fingerprints,indent=2),encoding='utf-8')
packages=BASE/'packages';packages.mkdir(exist_ok=True)
for title,source in [('Tai_lieu_ban_giao_23110193',BASE/'public'),('Ho_so_giang_vien_RIENG_TU_23110193',TARGET)]:
    with zipfile.ZipFile(packages/(title+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
        for path in source.rglob('*'):
            if path.is_file() and '.git' not in path.parts:archive.write(path,path.relative_to(source))
print(f'Prepared {len(fingerprints)} files and two ZIPs; private checkout: {TARGET}')
