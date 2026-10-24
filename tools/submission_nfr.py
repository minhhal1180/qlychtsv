"""Assemble measured NFR checks; pending JMeter data stays NOT_RUN, never PASS."""
import io
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'submission/evidence/nonfunctional'
OUT.mkdir(parents=True,exist_ok=True)
os.environ['TRAINING_BUGS']='1'
from tests.test_support import GuardTests, DefectTests

rows=[]
def add(nfr,title,expected,actual,status,evidence,bug='',method='API / assertions',steps=None):
    rows.append({'id':f'TC-NFR{int(nfr.split("-")[1]):02d}-{sum(x["requirement"]==nfr for x in rows)+1:03d}',
                 'requirement':nfr,'title':title,'expected':expected,'actual':actual,'status':status,
                 'evidence':evidence,'bug_id':bug,'method':method,
                 'steps':steps or ['Chạy công cụ nêu trong cột phương pháp.','Mở bằng chứng gốc.','Đối chiếu ngưỡng của SRS.'],
                 'scope':'Local self-test, not independent partner testing'})

extras=json.loads((ROOT/'submission/evidence/additional/results.json').read_text(encoding='utf-8'))
for result in extras['results']:
    if result['mode']!='training':continue
    add(result['requirement'],result['title'],result['expected'],result['actual'],result['status'],
        'evidence/additional/'+result['id']+'-training.json',result['id'],
        'Edge DOM/screenshot' if result['category'] in ('Visual','Content') else 'Authenticated HTTP measurement',result['steps'])

checks=[
('NFR-06',GuardTests,'test_admin_and_student_wrong_role','API trái vai trò','0 lần xử lý thành công trong các phép thử cấm; HTTP403'),
('NFR-06',GuardTests,'test_student_cannot_access_other_request_or_attachment','Quyền từng bản ghi/tệp','Sinh viên khác403; ẩn danh401; chủ tải đúng dữ liệu'),
('NFR-06',GuardTests,'test_csrf_is_required','CSRF bắt buộc','Thiếu X-CSRF-Token→403'),
('NFR-07',GuardTests,'test_two_staff_accept_atomically','Hai cán bộ tiếp nhận đồng thời','Đúng1HTTP200 và1HTTP409, chỉ1ACCEPT'),
('NFR-07',GuardTests,'test_create_retries_return_same_record','Idempotency JSON','Cùng key/body trả cùng id;1hồ sơ1CREATE1notification'),
('NFR-07',GuardTests,'test_multipart_retry_ignores_boundary','Retry multipart','Boundary khác nhưng trường/tệp cùng→cùngid,1tệp'),
('NFR-09',GuardTests,'test_file_validation_rolls_back_entire_request','Tệp sai/quá5MiB không ghi một phần','EXE/fakePDF/file5242881byte bị400; tổng hồ sơ không tăng'),
('NFR-10',DefectTests,'test_B10_completion_records_history','Audit hoàn tất','Sau hoàn tất hợp lệ có COMPLETE,fromIN_PROGRESS,toCOMPLETED'),
]
for nfr,klass,name,title,expected in checks:
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite([klass(name)]))
    status='PASS' if result.wasSuccessful() else 'ERROR' if result.errors else 'FAIL'
    filename=name+'.txt';(OUT/filename).write_text(stream.getvalue(),encoding='utf-8')
    actual={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'runner':'unittest assertion trace'}
    add(nfr,title,expected,actual,status,'evidence/nonfunctional/'+filename,'B10' if nfr=='NFR-10' else '')

metrics_path=ROOT/'submission/evidence/tooling/summary.json'
metrics=json.loads(metrics_path.read_text(encoding='utf-8')) if metrics_path.exists() else None
add('NFR-03','Danh sách dưới tải bậc1→2→4','P95≤1000ms,errors<1%,mỗi bậc120s',
    'Chờ JMeter hoàn tất; xem báo cáo tooling.', 'NOT_RUN','evidence/tooling/jmeter-step/metrics.json',method='Apache JMeter5.6.3')
report={'executed_at':datetime.now(timezone.utc).isoformat(),'scope':'Self-test only; independent peer evidence pending',
        'total':len(rows),'cases':rows,'counts':{key:sum(r['status']==key for r in rows) for key in ['PASS','FAIL','ERROR','NOT_RUN']}}
(OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report['counts']),f'total={len(rows)}')
