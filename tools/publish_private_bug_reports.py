"""Create/update reviewable private issue records from captured bug evidence."""
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
repo='minhhal1180/qlychtsv-ho-so-23110193'
catalog=json.loads((ROOT/'submission/data/bug_catalog.json').read_text(encoding='utf-8'))
mapping_path=ROOT/'submission/private/issue-links.json'
mapping=json.loads(mapping_path.read_text(encoding='utf-8')) if mapping_path.exists() else {}
existing=json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/issues?state=all&per_page=100'],encoding='utf-8'))
by_title={issue['title']:issue for issue in existing}

def publish(bug):
    title=f'{bug["id"]}: {bug["title"]}'
    body=f'''Tự kiểm thử của chủ hệ thống, không phải báo cáo phát hiện độc lập của bạn cặp.

| Trường | Nội dung |
| --- | --- |
| Loại | {bug['category']} |
| Mức độ | {bug['severity']} |
| Yêu cầu | {bug['requirement_quote']} |
| Vị trí | {bug['url']} |
| Môi trường | {bug['environment']} |
| Phạm vi | {bug['spec_relation']} |

Tiền điều kiện: {bug['preconditions']}

Các bước:

'''+ '\n'.join(f'{i}. {step}' for i,step in enumerate(bug['steps'],1))+f'''

Expected: {bug['expected']}

Actual (trích kết quả thực chạy):

```json
{json.dumps(bug['actual'],ensure_ascii=False,indent=2)}
```

Bằng chứng:

'''+ '\n'.join(f'- [{Path(path).name}](https://github.com/{repo}/blob/main/{path})' for path in bug['evidence'])+f'''

TC liên quan: {', '.join(bug['testcases'])}

Trạng thái: đã xác nhận nội bộ, giữ nguyên cho demo. Hồ sơ Bug Manifest riêng giảng viên; không chuyển danh sách này cho bạn cặp trước khi kiểm thử.
'''
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'issue.json'
        path.write_text(json.dumps({'title':title,'body':body},ensure_ascii=False),encoding='utf-8')
        if title in by_title:
            endpoint=f'repos/{repo}/issues/{by_title[title]["number"]}'
            method='PATCH'
        else:
            endpoint=f'repos/{repo}/issues'
            method='POST'
        result=json.loads(subprocess.check_output(['gh','api',endpoint,'--method',method,'--input',str(path)],encoding='utf-8'))
    return bug['id'],result['html_url']

with ThreadPoolExecutor(max_workers=3) as pool:
    mapping.update(dict(pool.map(publish,catalog)))
mapping_path.write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Created or retained {len(mapping)} private bug report links.')
