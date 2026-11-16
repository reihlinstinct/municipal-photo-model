"""Validate folder allow/forbid/required rules; unknown folders fail closed."""
from __future__ import annotations
import fnmatch
import json
import sys
from pathlib import Path
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required")

def check(root: Path) -> list[str]:
    spec = json.loads((root / 'STRUCTURE.json').read_text())
    problems = []
    rules = spec['folders']
    for path in root.rglob('*'):
        if not path.is_file() or '.git' in path.parts or '__pycache__' in path.parts:
            continue
        rel = path.relative_to(root)
        folder = str(rel.parent)
        rule = rules.get(folder)
        if rule is None:
            problems.append(str(rel) + ': unknown folder')
            continue
        if any(fnmatch.fnmatchcase(path.name, p) for p in rule['forbid']):
            problems.append(str(rel) + ': forbidden file')
        elif not any(fnmatch.fnmatchcase(path.name, p) for p in rule['allow']):
            problems.append(str(rel) + ': not allowed')
    for folder, rule in rules.items():
        for name in rule['required']:
            if not (root / folder / name).is_file():
                problems.append(str(Path(folder) / name) + ': required file missing')
    return problems

if __name__ == '__main__':
    errors = check(Path(sys.argv[1] if len(sys.argv) > 1 else '.'))
    print('\n'.join(errors) if errors else 'Structure checks passed')
    raise SystemExit(bool(errors))
