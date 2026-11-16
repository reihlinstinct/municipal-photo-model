"""Synthetic validation, isolation and checkpoint-format coverage."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from independent_data import read_manifest, class_rows, select_threshold, binary_metrics
from independent_model import LABELS, FORMAT


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = []
        for index, split in enumerate(('train', 'val', 'test')):
            data = ('synthetic-' + split).encode()
            name = split + '.txt'
            (self.root / name).write_bytes(data)
            self.rows.append({'image': name, 'image_sha256': hashlib.sha256(data).hexdigest(),
                              'group_id': split, 'split': split,
                              'review_status': 'approved_image_level_agent',
                              'label_state': dict.fromkeys(LABELS, 'absent')})

    def read(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.rows))
        return read_manifest(self.root, 'manifest.json')

    def test_valid_and_unknown_filtered(self):
        self.rows[0]['label_state'][LABELS[0]] = 'unknown'
        rows = self.read()
        self.assertEqual(class_rows(rows, LABELS[0], 'train'), [])
        self.assertEqual(len(class_rows(rows, LABELS[1], 'train')), 1)

    def test_reject_sha_group_hash_and_path_leaks(self):
        original = copy.deepcopy(self.rows)
        self.rows[0]['image_sha256'] = 'bad'
        with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
            self.read()
        self.rows = copy.deepcopy(original)
        self.rows[1]['group_id'] = 'train'
        with self.assertRaisesRegex(ValueError, 'leakage'):
            self.read()
        self.rows = copy.deepcopy(original)
        data = (self.root / 'train.txt').read_bytes()
        (self.root / 'val.txt').write_bytes(data)
        self.rows[1]['image_sha256'] = self.rows[0]['image_sha256']
        with self.assertRaisesRegex(ValueError, 'leakage'):
            self.read()
        self.rows = copy.deepcopy(original)
        self.rows[0]['image'] = '../outside.txt'
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.read()

    def test_reject_unreviewed_and_missing_box(self):
        for status in ('proposed', 'approved_visual_event_and_target'):
            self.rows[0]['review_status'] = status
            with self.assertRaises(ValueError):
                self.read()

    def test_reject_duplicate_and_invalid_state(self):
        self.rows.append(copy.deepcopy(self.rows[0]))
        with self.assertRaisesRegex(ValueError, 'Repeated image'):
            self.read()
        self.rows.pop()
        self.rows[0]['label_state'][LABELS[0]] = 'maybe'
        with self.assertRaisesRegex(ValueError, 'Invalid label'):
            self.read()


class MetricsTests(unittest.TestCase):
    def test_val_threshold_and_tie(self):
        self.assertEqual(select_threshold([0, 1], [.1, .8]), .8)
        # No test input exists in the selection API.
        self.assertEqual(binary_metrics([0, 1, 1], [.1, .8, .2], .5)['f1'], 2 / 3)

    def test_unknown_empty_nonfinite_rejected(self):
        for truth, probs in [([], []), ([0], [.5]), ([0, 1], [float('nan'), .5])]:
            with self.assertRaises(ValueError):
                select_threshold(truth, probs)
        with self.assertRaises(ValueError):
            binary_metrics([1], [], .5)


@unittest.skipUnless(importlib.util.find_spec('torch') and importlib.util.find_spec('torchvision'),
                     'Optional model dependencies; run in the model environment too')
class ModelTests(unittest.TestCase):
    def test_parameters_buffers_and_optimizer_are_isolated(self):
        import torch
        from independent_model import build_model
        a, b = build_model(), build_model()
        self.assertEqual(a.fc.out_features, 1)
        a_ptrs = {p.data_ptr() for p in list(a.parameters()) + list(a.buffers())}
        b_ptrs = {p.data_ptr() for p in list(b.parameters()) + list(b.buffers())}
        self.assertFalse(a_ptrs & b_ptrs)
        before = b.fc.weight.detach().clone()
        opt = torch.optim.SGD(a.fc.parameters(), lr=.1)
        a.fc(torch.ones(1, a.fc.in_features)).sum().backward()
        opt.step()
        self.assertTrue(torch.equal(before, b.fc.weight))
        self.assertFalse(a.conv1.weight.requires_grad)
        self.assertTrue(a.layer4[0].conv1.weight.requires_grad)

    def test_roundtrip_reject_legacy_and_wrong_label(self):
        import torch
        from independent_model import build_model, load_checkpoint
        torch.set_num_threads(2)
        a = build_model().eval()
        x = torch.zeros(1, 3, 224, 224)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'model.pt'
            torch.save({'format': FORMAT, 'label': LABELS[0], 'threshold': .5,
                        'state_dict': a.state_dict()}, p)
            b, label, threshold = load_checkpoint(p, expected_label=LABELS[0])
            self.assertEqual(label, LABELS[0])
            self.assertEqual(threshold, .5)
            with torch.no_grad():
                self.assertTrue(torch.equal(a(x), b(x)))
            with self.assertRaisesRegex(ValueError, 'label mismatch'):
                load_checkpoint(p, expected_label=LABELS[1])
            torch.save(a.state_dict(), p)
            with self.assertRaisesRegex(ValueError, 'Not an independent'):
                load_checkpoint(p)


if __name__ == '__main__':
    unittest.main()
