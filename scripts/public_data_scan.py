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
        if p.suffix.lower() in {'.jpg','.jpeg','.png','.heic','.webp','.gif','.bmp','.tif','.tiff','.mp4','.svg','.mov','.webm','.avi','.jfif','.wav','.mp3','.pdf','.zip','.csv','.parquet'}:
            problems.append(str(rel)+': prohibited data/media file');continue
        try:
            text=p.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            problems.append(str(rel)+': unreadable UTF-8 text file');continue
        # Case numbers, long plate-shaped standalone digits, keys and secrets.
        if re.search(r'(?<![0-9])[0-9]{7,}(?![0-9])',text):problems.append(str(rel)+': long numeric identifier')
        if re.search(r'(?<![0-9])[0-9]{2}-[0-9]{3}-[0-9]{2}(?![0-9])|(?<![0-9])[0-9]{3}-[0-9]{2}-[0-9]{3}(?![0-9])',text):problems.append(str(rel)+': hyphenated plate-like identifier')
        if re.search(r'(?<![0-9])[0-9]{3}-[0-9]{3}-[0-9]{4}(?![0-9])',text):problems.append(str(rel)+': phone-like identifier')
        if re.search(r'(?<![0-9])(?:[0-9]{2}[ -][0-9]{3}[ -][0-9]{4}|[0-9]{3}[ -][0-9]{3}[ -][0-9]{4,5})(?![0-9])',text):problems.append(str(rel)+': separated phone-like identifier')
        if re.search(r'\b[0-9]{4}-[0-9]{6,}(?:/[0-9]+)?\b',text):problems.append(str(rel)+': case-like identifier')
        if re.search(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|(?:AKIA|ASIA)[A-Z0-9]{16}|(?:xox[bp]|xapp)-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|' + '-'*5 + r'BEGIN .*PRIVATE KEY)',text):problems.append(str(rel)+': secret-like token')
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
