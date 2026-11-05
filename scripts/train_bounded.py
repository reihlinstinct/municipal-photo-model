"""Bound one training process tree; does not allocate or release cloud sessions."""
from __future__ import annotations
import argparse
import json
import math
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required")

STAGES = {'setup': 600.0, 'train': 1800.0, 'evaluate': 300.0}

def supervise(command, *, total_seconds=2700.0, stage_seconds=None, idle_seconds=120.0):
    """Run one child, fail closed on deadlines, protocol errors or no progress."""
    budgets = dict(STAGES if stage_seconds is None else stage_seconds)
    if (set(budgets) != set(STAGES) or not 0 < total_seconds <= 2700
            or not 0 < idle_seconds <= 120
            or any(not 0 < budgets[k] <= STAGES[k] for k in STAGES)):
        raise ValueError('Invalid or excessive budget')
    if os.name != 'posix':
        raise RuntimeError('POSIX process groups required')
    events = queue.Queue(maxsize=128)
    start = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               start_new_session=True, text=False)
    def read_events():
        try:
            while True:
                line = process.stdout.readline(1025)
                if not line:
                    break
                try:
                    event = json.loads(line) if len(line) <= 1024 else None
                except (ValueError, UnicodeDecodeError):
                    event = None
                try:
                    events.put_nowait(event)
                except queue.Full:
                    break
        finally:
            process.stdout.close()
    reader = threading.Thread(target=read_events, daemon=True)
    reader.start()
    stage = 'setup'
    stage_start = last_progress = start
    last_step = 0
    heartbeat_progress = 0
    reason = 'worker_failed'
    order = list(STAGES)
    try:
        while True:
            now = time.monotonic()
            if now - start >= total_seconds:
                reason = 'total_timeout'; break
            if now - stage_start >= budgets[stage]:
                reason = 'stage_timeout'; break
            if now - last_progress >= idle_seconds:
                reason = 'no_progress'; break
            try:
                event = events.get(timeout=0.01)
            except queue.Empty:
                if process.poll() is not None and not reader.is_alive() and events.empty():
                    reason = 'ok' if process.returncode == 0 and stage == 'evaluate' else 'worker_failed'
                    break
                continue
            if not isinstance(event, dict):
                reason = 'invalid_event'; break
            if set(event) == {'stage'} and event['stage'] in STAGES:
                next_stage = event['stage']
                if order.index(next_stage) != order.index(stage) + 1:
                    reason = 'invalid_stage'; break
                stage = next_stage; stage_start = last_progress = now; heartbeat_progress = 0
            elif set(event) == {'heartbeat', 'progress'} and event['heartbeat'] == stage:
                progress = event['progress']
                if type(progress) is not int or progress <= heartbeat_progress:
                    reason = 'invalid_progress'; break
                heartbeat_progress = progress; last_progress = now
            elif set(event) == {'step', 'loss'} and stage == 'train':
                step, loss = event['step'], event['loss']
                if type(step) is not int or step != last_step + 1 or step > 100:
                    reason = 'step_limit'; break
                if type(loss) not in (int, float) or not math.isfinite(loss):
                    reason = 'nonfinite_loss'; break
                last_step = step; last_progress = now
            else:
                reason = 'invalid_event'; break
    finally:
        # Kill all descendants, even if the direct child has already exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            reason = 'cleanup_timeout'
            # Do not hide failure or block forever waiting for an unkillable child.
            threading.Thread(target=process.wait, daemon=True).start()
        reader.join(timeout=1)
    return reason

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, help='Approved reviewed dataset directory')
    args = parser.parse_args()
    reason = supervise([sys.executable, '-I', '-u', str(Path(__file__).with_name('training_worker.py')), '--root', args.root])
    print(json.dumps({'result': reason}), flush=True)
    return 0 if reason == 'ok' else 1

if __name__ == '__main__':
    raise SystemExit(main())
