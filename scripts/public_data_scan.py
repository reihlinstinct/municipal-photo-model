"""Fail-closed public-tree hygiene check; supplements, never replaces review."""
from __future__ import annotations
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required")
import json,re,sys
from pathlib import Path

def scan(root: Path) -> list[str]:
    problems=[]
    for p in root.rglob('*'):
        if not p.is_file() or '.git' in p.parts or '__pycache__' in p.parts:continue
        rel=p.relative_to(root)
        if p.suffix.lower() in {'.jpg','.jpeg','.png','.heic','.webp','.pdf','.zip','.csv','.parquet'}:
            problems.append(str(rel)+': prohibited data/media file');continue
        text=p.read_text(encoding='utf-8')
        # Case numbers, long plate-shaped standalone digits, keys and secrets.
        if re.search(r'(?<![0-9])[0-9]{7,9}(?![0-9])',text):problems.append(str(rel)+': long numeric identifier')
        if re.search(r'(?<![0-9])[0-9]{2}-[0-9]{3}-[0-9]{2}(?![0-9])|(?<![0-9])[0-9]{3}-[0-9]{2}-[0-9]{3}(?![0-9])',text):problems.append(str(rel)+': hyphenated plate-like identifier')
        if re.search(r'\b[0-9]{4}-[0-9]{6,}(?:/[0-9]+)?\b',text):problems.append(str(rel)+': case-like identifier')
        if re.search(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|' + '-'*5 + r'BEGIN .*PRIVATE KEY)',text):problems.append(str(rel)+': secret-like token')
        if p.name=='manifest.proposals.json' or p.name=='source-index.json':problems.append(str(rel)+': private manifest')
        if p.suffix=='.ipynb':
            nb=json.loads(text)
            if any(c.get('outputs') or c.get('execution_count') is not None for c in nb['cells'] if c['cell_type']=='code'):problems.append(str(rel)+': notebook outputs')
    return problems
if __name__=='__main__':
    result=scan(Path(sys.argv[1] if len(sys.argv)>1 else '.'))
    for item in result:print(item)
    if result:raise SystemExit(1)
    print('Public-tree synthetic-data scan passed. Manual privacy review still required.')
