"""Run isolated binary classifiers sequentially using the existing watchdog."""
import argparse
import json
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    raise SystemExit('Python 3.11 or newer is required')

from independent_model import LABELS, FORMAT
from train_bounded import supervise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--manifest', default='manifest.reviewed.json')
    parser.add_argument('--output', default='independent-output')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    metrics = {}
    for label in LABELS:
        command = [sys.executable, '-I', '-u', str(Path(__file__).with_name('independent_worker.py')),
                   '--root', str(Path(args.root).resolve()), '--manifest', args.manifest,
                   '--label', label, '--output', str(output)]
        reason = supervise(command)
        print(json.dumps({'label': label, 'result': reason}), flush=True)
        if reason != 'ok':
            return 1
        metrics[label] = json.loads((output / (label + '.json')).read_text())
    (output / 'metrics.json').write_text(json.dumps({'format': FORMAT, 'classes': metrics}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
