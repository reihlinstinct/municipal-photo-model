"""Static checks for worker/photo-labeler.mjs (Cloudflare Worker labeling UI).

The Worker is JavaScript; CI runs Python unittest only, so these tests verify
structure, wiring and privacy invariants without executing the Worker.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKER = ROOT / 'worker'
SOURCE = WORKER / 'photo-labeler.mjs'


class PhotoLabelerWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text(encoding='utf-8')

    def test_files_present(self):
        for name in ('photo-labeler.mjs', 'mark-page.mjs', 'wrangler.toml', 'README.md'):
            self.assertTrue((WORKER / name).is_file(), name)

    def test_mark_page_module(self):
        mark = (WORKER / 'mark-page.mjs').read_text(encoding='utf-8')
        self.assertLessEqual(len(mark.splitlines()), 400)
        self.assertIn('some_illegal', mark)
        self.assertIn('mark-page', mark)
        main = self.text
        self.assertIn('from "./mark-page.mjs"', main)
        self.assertIn('/api/mark-state', main)
        self.assertIn('/api/mark', main)

    def test_source_under_line_cap(self):
        self.assertLessEqual(len(self.text.splitlines()), 400)

    def test_mcp_tools_wired(self):
        for tool in ('get_next_unlabeled', 'submit_label', 'get_progress'):
            self.assertIn(tool, self.text)
        self.assertIn('/mcp', self.text)

    def test_per_source_label_keys(self):
        # Human and bot labels must never overwrite each other.
        self.assertRegex(self.text, r'label:\$\{set\}:\$\{source\}:\$\{id\}')

    def test_bearer_auth_required(self):
        self.assertIn('unauthorized', self.text)
        self.assertIn('authorization', self.text.lower())

    def test_mcp_cannot_write_as_human(self):
        # A bot over MCP must never write or queue as source 'human' (review finding).
        self.assertIn('BOT_SOURCES', self.text)
        self.assertIn("MCP callers must not use source 'human'", self.text)
        self.assertNotIn('enum: SOURCES, description', self.text)

    def test_page_label_route_forces_human(self):
        # The browser page always writes as 'human'; a page caller cannot pose as a bot.
        self.assertIn('submitLabel(env, b.set, "human"', self.text)
        self.assertNotIn('b.source || "human"', self.text)

    def test_query_key_rejected_for_mcp_and_export(self):
        # ?key= is for the browser page only; /mcp and /api/export need the header.
        m = re.search(r'function okAuth.*?\n}', self.text, re.S)
        self.assertIsNotNone(m)
        body = m.group(0)
        self.assertIn('"/mcp"', body)
        self.assertIn('"/api/export"', body)

    def test_no_long_numeric_identifiers(self):
        for path in WORKER.iterdir():
            if path.is_file():
                self.assertIsNone(
                    re.search(r'(?<![0-9])[0-9]{7,}(?![0-9])', path.read_text(encoding='utf-8')),
                    f'{path.name}: long numeric identifier')

    def test_wrangler_toml_has_placeholders_only(self):
        toml = (WORKER / 'wrangler.toml').read_text(encoding='utf-8')
        self.assertIn('REPLACE_WITH_ACCOUNT_ID', toml)
        self.assertIn('REPLACE_WITH_KV_NAMESPACE_ID', toml)


if __name__ == '__main__':
    unittest.main()
