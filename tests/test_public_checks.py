import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

scanner = load('public_data_scan')
structure = load('check_structure')

class PrivacyTests(unittest.TestCase):
    def scan_text(self, text, name='sample.txt'):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / name).write_text(text)
            return scanner.scan(Path(d))

    def test_plain_plate(self):
        self.assertTrue(self.scan_text(''.join(['123', '4567'])))

    def test_long_identifiers_and_phones(self):
        for length in [7, 9, 10, 12, 20]:
            self.assertTrue(self.scan_text('1' * length))
        self.assertTrue(self.scan_text('-'.join(['054', '123', '4567'])))

    def test_token_families(self):
        tokens = [
            'github_' + 'pat_' + 'A' * 30,
            'AK' + 'IA' + 'A' * 16,
            'xox' + 'b-' + 'a' * 20,
            'xox' + 'p-' + 'a' * 20,
            's' + 'k-' + 'a' * 30,
            'ey' + 'J' + 'a' * 12 + '.' + 'b' * 12 + '.' + 'c' * 12,
        ]
        for token in tokens:
            self.assertTrue(self.scan_text(token))

    def test_space_separated_number_list_fails_closed(self):
        groups = ['80', '443', '8080']
        self.assertTrue(self.scan_text('ports: ' + ' '.join(groups)))
        self.assertEqual(self.scan_text('ports: ' + ', '.join(groups)), [])

    def test_separated_phones(self):
        for groups in [('02', '123', '4567'), ('054', '123', '4567'), ('054', '123', '45678')]:
            for separator in ['-', ' ']:
                self.assertTrue(self.scan_text(separator.join(groups)))

    def test_additional_tokens(self):
        for token in ['AS' + 'IA' + 'A' * 16, 'x' + 'app-' + 'a' * 24]:
            self.assertTrue(self.scan_text(token))

    def scan_workflow(self, text, name='w.yml'):
        with tempfile.TemporaryDirectory() as d:
            wf = Path(d) / '.github' / 'workflows'
            wf.mkdir(parents=True)
            (wf / name).write_text(text)
            return scanner.scan(Path(d))

    def test_pinned_sha_in_uses_line_allowed(self):
        sha = '0976a9cc34d3b34a5f8c65b459' + '53678bba92f0b2'
        self.assertEqual(self.scan_workflow('  - uses: org/repo/.github/workflows/w.yml@' + sha + ' # v1.0.9'), [])

    def test_digit_run_on_non_uses_line_still_flagged(self):
        sha = '0976a9cc34d3b34a5f8c65b459' + '53678bba92f0b2'
        ticket = '1234' + '567'
        flagged = self.scan_workflow('env:\n  TICKET: "' + ticket + '"\nsteps:\n  - uses: org/repo/w@' + sha)
        self.assertTrue(any('long numeric' in p for p in flagged))

    def test_non_hex_numeric_ref_in_uses_still_flagged(self):
        self.assertTrue(self.scan_workflow('  - uses: foo/bar@' + '1' * 7))

    def test_sha_outside_uses_line_still_flagged(self):
        sha = '0976a9cc34d3b34a5f8c65b459' + '53678bba92f0b2'
        self.assertTrue(self.scan_workflow('# see commit ' + sha))

    def test_sha_in_non_workflow_file_still_flagged(self):
        sha = '0976a9cc34d3b34a5f8c65b459' + '53678bba92f0b2'
        self.assertTrue(self.scan_text('  - uses: org/repo/w@' + sha))

    def test_non_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'sample.txt').write_bytes(bytes([255, 254, 253]))
            self.assertIn('unreadable UTF-8', scanner.scan(Path(d))[0])

    def test_additional_media(self):
        for extension in ['gif', 'bmp', 'tif', 'tiff', 'mp4', 'svg', 'mov', 'webm', 'avi', 'jfif', 'wav', 'mp3']:
            self.assertTrue(self.scan_text('synthetic', 'sample.' + extension))

    def test_hyphenated_plates(self):
        for pieces in [('12', '345', '67'), ('123', '45', '678')]:
            self.assertTrue(self.scan_text('-'.join(pieces)))

    def test_case_number(self):
        self.assertTrue(self.scan_text('-'.join(['2611', '123456'])))

    def test_secrets(self):
        self.assertTrue(self.scan_text('gh' + 'p_' + 'A' * 30))
        self.assertTrue(self.scan_text('-' * 5 + 'BEGIN RSA PRIVATE KEY' + '-' * 5))

    def test_notebook_outputs_and_execution_count(self):
        for outputs, count in [([{'output_type': 'stream', 'text': 'synthetic'}], None), ([], 1)]:
            self.assertTrue(self.scan_text(json.dumps({'cells': [{'cell_type': 'code', 'outputs': outputs, 'execution_count': count}]}), 'sample.ipynb'))
        self.assertEqual(self.scan_text(json.dumps({'cells': [{'cell_type': 'code', 'outputs': [], 'execution_count': None}]}), 'sample.ipynb'), [])

    def test_private_manifest_and_media(self):
        self.assertTrue(self.scan_text('{}', 'manifest.proposals.json'))
        self.assertTrue(self.scan_text('synthetic', 'sample.jpg'))

    def test_clean_tree(self):
        self.assertEqual(scanner.scan(ROOT), [])

class StructureTests(unittest.TestCase):
    def test_current_tree(self):
        self.assertEqual(structure.check(ROOT), [])

    def test_missing_required_unknown_folder_and_wrong_type(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            shutil.copytree(ROOT, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '.git'))
            (root / 'SECURITY.md').unlink()
            (root / 'scripts' / 'unexpected.txt').write_text('synthetic')
            (root / 'unexpected').mkdir()
            (root / 'unexpected' / 'file.py').write_text('')
            errors = structure.check(root)
            self.assertTrue(any('required file missing' in e for e in errors))
            self.assertTrue(any('not allowed' in e for e in errors))
            self.assertTrue(any('unknown folder' in e for e in errors))

if __name__ == '__main__':
    unittest.main()
