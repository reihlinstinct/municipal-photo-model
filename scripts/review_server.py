"""Private, local human review. No remote requests, automatic approval or training."""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import ssl
import threading
from urllib.parse import urlsplit

LABELS = ('sidewalk_parking', 'red_white', 'crosswalk_obstruction')
APP = Path(__file__).resolve().parents[1] / 'review'

# Section: Entry point

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--candidates', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--cert', type=Path)
    parser.add_argument('--key', type=Path)
    args = parser.parse_args()
    if args.bind not in {'127.0.0.1', '::1', 'localhost'} and not (args.cert and args.key):
        parser.error('Phone/LAN access requires a trusted TLS certificate and key; no public hosting')
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.store = ReviewStore(args.root, args.candidates, args.work)
    server.token = secrets.token_urlsafe(32)
    if args.cert and args.key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.cert, args.key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    scheme = 'https' if args.cert and args.key else 'http'
    print(f'Private local review: {scheme}://{args.bind}:{server.server_port}/#{server.token}', flush=True)
    print('Keep this local address private. Ctrl-C stops the server. Drafts stay in --work.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# Section: Validation and local-file helpers

def stamp():
    return datetime.now(timezone.utc).isoformat()

def image_path(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('Image must be a relative path')
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or path.suffix.lower() not in {'.jpg', '.jpeg', '.png'}:
        raise ValueError('Unsafe image path')
    if not path.is_file():
        raise ValueError('Image not found')
    return path

def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def box_ok(box, width, height):
    return (isinstance(box, list) and len(box) == 4
            and all(type(x) in (int, float) and math.isfinite(x) for x in box)
            and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height)

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as output:
        os.chmod(temporary, 0o600)
        json.dump(data, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)

# Section: Review storage

class ReviewStore:
    def __init__(self, root, candidates, work):
        self.root, self.work = Path(root).resolve(), Path(work).resolve()
        # Data/state must never be written into the public source checkout.
        source = APP.parent.resolve()
        if self.work.is_relative_to(source) or self.root.is_relative_to(source):
            raise ValueError('Keep private data and work directory outside the code checkout')
        self.lock = threading.Lock()
        rows = json.loads(Path(candidates).read_text())
        if not isinstance(rows, list) or not rows:
            raise ValueError('Candidates must be a non-empty JSON list')
        # OCR/database proposals are not visible truth and must never reach UI or export.
        self.rows = [{k: copy.deepcopy(v) for k, v in row.items() if k != 'plate_text_candidate'}
                     if isinstance(row, dict) else row for row in rows]
        seen = set()
        hash_groups = {}
        source_groups = {}
        for row in self.rows:
            if not isinstance(row, dict):
                raise ValueError('Every candidate must be an object')
            if (not isinstance(row.get('review_status'), str) or not row['review_status'].strip()
                    or row.get('review_status') == 'approved_visual_event_and_target'
                    or not isinstance(row.get('candidate_labels'), list)
                    or any(k not in LABELS for k in row['candidate_labels'])
                    or not isinstance(row.get('label_state'), dict)
                    or set(row['label_state']) != set(LABELS)
                    or any(v != 'unknown' for v in row['label_state'].values())):
                raise ValueError('Expected unreviewed candidate schema; do not infer missing source metadata')
            name = row.get('image')
            path = image_path(self.root, name)
            if name in seen or not isinstance(row.get('group_id'), str) or not row['group_id'].strip():
                raise ValueError('Unique image and verified group_id required for every row')
            seen.add(name)
            actual = digest(path)
            if row.get('image_sha256') != actual:
                raise ValueError('Candidate image hash mismatch')
            if hash_groups.setdefault(actual, row['group_id']) != row['group_id']:
                raise ValueError('Identical images must share a group')
            source_id = row.get('local_source_id')
            if source_id is not None:
                if not isinstance(source_id, str) or not source_id.strip():
                    raise ValueError('Invalid source event identifier')
                if source_groups.setdefault(source_id, row['group_id']) != row['group_id']:
                    raise ValueError('One source event must share a group')
            from PIL import Image
            with Image.open(path) as image:
                # Prepared pilot photos must be pixel-oriented; never rotate silently.
                if image.getexif().get(274, 1) != 1:
                    raise ValueError('Normalize EXIF orientation before preparing candidates')
                row['width'], row['height'] = image.size
        self.fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        self.state = {'fingerprint': self.fingerprint, 'revision': 0, 'reviews': {}}
        self.state_path = self.work / 'review-state.json'
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            if state.get('fingerprint') != self.fingerprint:
                raise ValueError('State belongs to different candidates')
            self.state = state

    def data(self):
        return {'rows': self.rows, 'state': self.state, 'labels': LABELS}

    def validate(self, review, row, approval=False):
        if not isinstance(review, dict):
            raise ValueError('Invalid review')
        if not isinstance(review.get('label_state'), dict) or any(review['label_state'].get(k) not in {'present', 'absent', 'unknown'} for k in LABELS):
            raise ValueError('Invalid label state')
        if review.get('split') not in {'unassigned', 'train', 'val', 'test'}:
            raise ValueError('Invalid split')
        for key in ('target_vehicle_box', 'plate_box'):
            if review.get(key) is not None and not box_ok(review[key], row['width'], row['height']):
                raise ValueError('Invalid pixel xyxy box')
        if review.get('plate_status') not in {'unknown', 'readable', 'unreadable', 'not_visible'}:
            raise ValueError('Invalid plate status')
        for key in ('reviewer', 'municipal_category', 'plate_text', 'notes', 'exclusion_reason'):
            if not isinstance(review.get(key, ''), str) or len(review.get(key, '')) > 4000:
                raise ValueError('Invalid text')
        if approval:
            if row.get('review_status') == 'held_missing_group_data':
                raise ValueError('Source group data is missing; repair candidates before approval')
            if not review.get('reviewer', '').strip() or review.get('event_checked') is not True or review.get('visual_checked') is not True:
                raise ValueError('Human reviewer, visual and event checks required')
            if not review.get('municipal_category', '').strip():
                raise ValueError('Confirm municipality category from source evidence')
            if review.get('split') == 'unassigned' or review.get('target_vehicle_box') is None:
                raise ValueError('Target vehicle box and split required')
            if any(review['label_state'][k] == 'unknown' for k in LABELS):
                raise ValueError('Resolve all labels, including negatives')
            plate = review['plate_status']
            if plate == 'unknown':
                raise ValueError('Review plate or mark unreadable/not visible')
            if plate in {'readable', 'unreadable'} and review.get('plate_box') is None:
                raise ValueError('Visible plate needs a box')
            if plate == 'readable' and not review.get('plate_text', '').strip():
                raise ValueError('Readable plate needs text')
            if plate != 'readable' and review.get('plate_text', '').strip():
                raise ValueError('Do not invent text for an unreadable or invisible plate')
            if review.get('plate_box') is not None:
                p, t = review['plate_box'], review['target_vehicle_box']
                if not (t[0] <= p[0] < p[2] <= t[2] and t[1] <= p[1] < p[3] <= t[3]):
                    raise ValueError('Plate box must be inside the target vehicle box')
            if plate == 'not_visible' and review.get('plate_box') is not None:
                raise ValueError('Invisible plate cannot have a box')
        return review

    def save(self, payload):
        with self.lock:
            if payload.get('revision') != self.state['revision']:
                raise ValueError('Stale page. Reload before saving; no data overwritten')
            index = payload.get('index')
            if type(index) is not int or not 0 <= index < len(self.rows):
                raise ValueError('Invalid row')
            row = self.rows[index]
            allowed = {'label_state', 'target_vehicle_box', 'plate_box', 'plate_text', 'municipal_category',
                       'plate_status', 'split', 'reviewer', 'event_checked', 'visual_checked', 'notes', 'exclusion_reason'}
            incoming = payload.get('review')
            if not isinstance(incoming, dict) or set(incoming) - allowed:
                raise ValueError('Unexpected review fields')
            review = copy.deepcopy(incoming)
            decision = payload.get('decision')
            if decision not in {'draft', 'approved', 'excluded'}:
                raise ValueError('Invalid decision')
            self.validate(review, row, decision == 'approved')
            if decision == 'excluded' and not review.get('exclusion_reason', '').strip():
                raise ValueError('Exclusion reason required')
            review.update(decision=decision, reviewed_at=stamp())
            updated = copy.deepcopy(self.state)
            updated['reviews'][row['image']] = review
            updated['revision'] += 1
            (self.work / 'manifest.reviewed.json').unlink(missing_ok=True)
            atomic_json(self.state_path, updated)
            self.state = updated
            return self.state

    def export(self):
        with self.lock:
            (self.work / 'manifest.reviewed.json').unlink(missing_ok=True)
            output, groups = [], {}
            reviews = self.state['reviews']
            for row in self.rows:
                review = reviews.get(row['image'], {})
                if review.get('decision') == 'excluded':
                    continue
                if review.get('decision') != 'approved':
                    raise ValueError('Every image must be approved or explicitly excluded before export')
                self.validate(review, row, True)
                if digest(image_path(self.root, row['image'])) != row['image_sha256']:
                    raise ValueError('Image changed since review started')
                group = row['group_id']
                if groups.setdefault(group, review['split']) != review['split']:
                    raise ValueError('Group leakage: assign the same split to every image in a group')
                merged = copy.deepcopy(row)
                merged.update({k: v for k, v in review.items() if k not in {'decision', 'exclusion_reason'}})
                merged['review_status'] = 'approved_visual_event_and_target'
                # Review does not authorize any upload, publication or training execution.
                merged['upload_approved'] = False
                merged['box_format'] = 'xyxy_pixels'
                output.append(merged)
            if set(groups.values()) != {'train', 'val', 'test'}:
                raise ValueError('Non-empty train, val and test groups required')
            train = [r for r in output if r['split'] == 'train']
            if any(not 0 < sum(r['label_state'][k] == 'present' for r in train) < len(train) for k in LABELS):
                raise ValueError('Training requires positive and negative examples for each class')
            atomic_json(self.work / 'manifest.reviewed.json', output)
            atomic_json(self.work / 'review-audit.json', self.state)
            return output

# Section: HTTP handling

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not log plate text, image names, token or private paths.

    def reply(self, status, body, content_type='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        return secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.server.token)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in {'/', '/app.js', '/style.css'}:
            filename = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[path]
            kind = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8', '/style.css': 'text/css; charset=utf-8'}[path]
            self.reply(200, (APP / filename).read_bytes(), kind)
            return
        if not self.authorized():
            self.reply(401, b'{"error":"Unauthorized"}')
            return
        if path == '/api/data':
            with self.server.store.lock:
                self.reply(200, json.dumps(self.server.store.data(), ensure_ascii=False).encode())
        elif path.startswith('/api/image/'):
            try:
                index = int(path.rsplit('/', 1)[1])
                if not 0 <= index < len(self.server.store.rows):
                    raise ValueError()
                row = self.server.store.rows[index]
                file = image_path(self.server.store.root, row['image'])
                kind = 'image/png' if file.suffix.lower() == '.png' else 'image/jpeg'
                self.reply(200, file.read_bytes(), kind)
            except (ValueError, OSError):
                self.reply(404, b'{}')
        else:
            self.reply(404, b'{}')

    def do_POST(self):
        if not self.authorized():
            self.reply(401, b'{"error":"Unauthorized"}')
            return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= length <= 64000:
                raise ValueError('Request too large')
            payload = json.loads(self.rfile.read(length))
            path = urlsplit(self.path).path
            if path == '/api/save':
                result = self.server.store.save(payload)
            elif path == '/api/export':
                result = self.server.store.export()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Disposition', 'attachment; filename="manifest.reviewed.json"')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(json.dumps(result, ensure_ascii=False, indent=2).encode())
                return
            else:
                self.reply(404, b'{}')
                return
            self.reply(200, json.dumps(result, ensure_ascii=False).encode())
        except (ValueError, KeyError, TypeError, OSError) as exc:
            self.reply(400, json.dumps({'error': str(exc)}, ensure_ascii=False).encode())


if __name__ == '__main__':
    main()
