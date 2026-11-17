"""Private manifest validation and class-specific evaluation, without torch."""
import hashlib
import json
from pathlib import Path

from independent_model import LABELS


def read_manifest(root, filename, progress=lambda: None):
    root = Path(root).resolve()
    manifest_path = (root / filename).resolve()
    if not manifest_path.is_relative_to(root):
        raise ValueError('Manifest outside root')
    rows = json.loads(manifest_path.read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError('No reviewed manifest')
    groups, hashes = {}, {}
    seen_images = set()
    for row in rows:
        _validate_row_shape(row)
        status = row['review_status']
        if status not in {'approved_visual_event_and_target', 'approved_image_level_human',
                          'approved_image_level_agent'}:
            raise ValueError('Unreviewed row')
        if status == 'approved_visual_event_and_target' and row.get('target_vehicle_box') is None:
            raise ValueError('Boxed review requires box')
        split = row['split']
        if split not in {'train', 'val', 'test'}:
            raise ValueError('Invalid split')
        if any(row['label_state'][label] not in {'present', 'absent', 'unknown'} for label in LABELS):
            raise ValueError('Invalid label state')
        path = (root / row['image']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Image outside root or missing')
        if path in seen_images:
            raise ValueError('Repeated image')
        seen_images.add(path)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha != row['image_sha256']:
            raise ValueError('SHA mismatch')
        group = row['group_id']
        if not isinstance(group, str) or not group:
            raise ValueError('Missing group')
        if groups.setdefault(group, split) != split or hashes.setdefault(sha, split) != split:
            raise ValueError('Cross-split leakage')
        progress()
    if {r['split'] for r in rows} != {'train', 'val', 'test'}:
        raise ValueError('Need all three splits')
    return rows


def _validate_row_shape(row):
    """Reject malformed structure before indexing or using hash-based checks."""
    if not isinstance(row, dict):
        raise ValueError('Malformed manifest row')
    string_fields = ('review_status', 'split', 'image', 'image_sha256', 'group_id')
    if any(not isinstance(row.get(key), str) or not row[key] for key in string_fields):
        raise ValueError('Missing or invalid manifest field')
    states = row.get('label_state')
    if not isinstance(states, dict) or any(not isinstance(states.get(label), str) for label in LABELS):
        raise ValueError('Missing or invalid label state')


def class_rows(rows, label, split):
    if label not in LABELS or split not in {'train', 'val', 'test'}:
        raise ValueError('Invalid class or split')
    return [r for r in rows if r['split'] == split and r['label_state'][label] != 'unknown']


def binary_metrics(truth, probabilities, threshold):
    import math
    if not truth or len(truth) != len(probabilities):
        raise ValueError('Empty or mismatched evaluation')
    if any(y not in (0, 1) for y in truth):
        raise ValueError('Invalid truth')
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities):
        raise ValueError('Invalid probability')
    predicted = [p >= threshold for p in probabilities]
    tp = sum(y == 1 and p for y, p in zip(truth, predicted))
    fp = sum(y == 0 and p for y, p in zip(truth, predicted))
    fn = sum(y == 1 and not p for y, p in zip(truth, predicted))
    return {'precision': tp / (tp + fp) if tp + fp else 0.,
            'recall': tp / (tp + fn) if tp + fn else 0.,
            'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.,
            'n_known': len(truth), 'support_pos': sum(truth)}


def select_threshold(val_truth, val_probabilities):
    if set(val_truth) != {0, 1}:
        raise ValueError('Validation needs positive and negative labels')
    candidates = [i / 100 for i in range(10, 91, 5)]
    return max(candidates, key=lambda t: (binary_metrics(val_truth, val_probabilities, t)['f1'], t))
