"""Cache keys must change with shared content on both Desk and website pages."""
from hashlib import sha256
from pathlib import Path
import runpy
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]

class TestUIAssets(unittest.TestCase):
    def setUp(self):
        self.hooks = runpy.run_path(str(ROOT / "eup_administration" / "hooks.py"))

    def test_desk_and_website_use_the_same_revised_assets(self):
        for kind in ("js", "css"):
            self.assertEqual(self.hooks["app_include_" + kind], self.hooks["web_include_" + kind])

    def test_cache_keys_match_the_actual_shared_file_contents(self):
        for kind in ("js", "css"):
            urls = self.hooks["app_include_" + kind]
            self.assertEqual(len(urls), 1)
            asset = urlsplit(urls[0])
            self.assertFalse(asset.scheme or asset.netloc)
            prefix = "/assets/eup_administration/"
            self.assertTrue(asset.path.startswith(prefix))
            content = (ROOT / "eup_administration" / "public" / asset.path.removeprefix(prefix)).read_bytes()
            self.assertEqual(parse_qs(asset.query), {"v": [sha256(content).hexdigest()[:16]]})
