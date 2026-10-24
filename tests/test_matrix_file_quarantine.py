"""Exercise the real quarantine function on temporary files without Frappe installed."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from eup_administration.acceptance_rules import matrix_file_cleanup_plan


class MatrixQuarantineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.bench = Path(temporary.name).resolve()
        (self.bench / 'logs').mkdir()
        self.site = self.bench / 'sites' / 'clone'
        (self.site / 'private/files').mkdir(parents=True)
        (self.site / 'public/files').mkdir(parents=True)
        self.original = self.site / 'private/files/original.txt'
        self.original.write_bytes(b'existing document')
        self.data = {'records': {'File': [1, 'original']}, 'protected': {'GL Entry': [0, 'original']}}
        self.before = self.snapshot()
        self.references = set()
        source = Path(__file__).resolve().parents[1] / 'eup_administration/tests/clone_acceptance.py'
        tree = ast.parse(source.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'quarantine_matrix_files')
        namespace = {'Path': Path, 'hashlib': hashlib, 'json': json, 'tempfile': tempfile,
                     'BENCH': self.bench, 'CLONE': 'clone', 'guard': lambda: None,
                     'restore_snapshot': self.snapshot,
                     'matrix_file_cleanup_plan': matrix_file_cleanup_plan,
                     'frappe': SimpleNamespace(get_site_path=lambda: str(self.site),
                         db=SimpleNamespace(exists=lambda dt, filters:
                                            filters['file_url'] in self.references))}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        self.quarantine = namespace['quarantine_matrix_files']

    def snapshot(self):
        files = {}
        for folder in ('private/files', 'public/files'):
            for file in (self.site / folder).rglob('*'):
                if file.is_file():
                    files[str(file.relative_to(self.site)).replace('\\', '/')] = hashlib.sha256(
                        file.read_bytes()).hexdigest()
        return {'data': copy.deepcopy(self.data), 'files': files}

    def fixtures(self):
        private = self.site / ('private/files/ADM-CLONE-' + 'a' * 32 + '.txt')
        public = self.site / ('public/files/ADM-CLONE-' + 'c' * 32 + '.txt')
        private.write_bytes(b'Synthetic clone QA ' + b'b' * 32)
        public.write_bytes(b'Synthetic public QA ' + b'd' * 32)
        return private, public

    def test_exact_fixture_bytes_retained_and_original_snapshot_restored(self):
        private, public = self.fixtures()
        expected = {private.name: private.read_bytes(), public.name: public.read_bytes()}
        self.quarantine(self.before)
        self.assertEqual(self.snapshot(), self.before)
        evidence, = (self.bench / 'logs').glob('adm-clone-file-evidence-*')
        manifest = json.loads((evidence / 'manifest.json').read_text())
        self.assertEqual(len(manifest['files']), 2)
        self.assertEqual((evidence / ('private-' + private.name)).read_bytes(), expected[private.name])
        self.assertEqual((evidence / ('public-' + public.name)).read_bytes(), expected[public.name])
        self.assertEqual(self.original.read_bytes(), b'existing document')

    def test_referenced_fixture_blocks_entire_move(self):
        private, public = self.fixtures()
        self.references.add('/files/' + public.name)
        with self.assertRaisesRegex(AssertionError, 'referenced File'):
            self.quarantine(self.before)
        self.assertTrue(private.is_file())
        self.assertTrue(public.is_file())
        self.assertEqual(list((self.bench / 'logs').iterdir()), [])

    def test_changed_original_blocks_entire_move(self):
        private, public = self.fixtures()
        self.original.write_bytes(b'changed original')
        with self.assertRaisesRegex(AssertionError, 'pre-existing file'):
            self.quarantine(self.before)
        self.assertTrue(private.is_file())
        self.assertTrue(public.is_file())
        self.assertEqual(list((self.bench / 'logs').iterdir()), [])

    def test_symlink_fixture_is_refused_without_touching_target(self):
        outside = self.bench / 'outside.txt'
        outside.write_bytes(b'Synthetic clone QA ' + b'b' * 32)
        linked = self.site / ('private/files/ADM-CLONE-' + 'a' * 32 + '.txt')
        linked.symlink_to(outside)
        with self.assertRaisesRegex(AssertionError, 'symlink'):
            self.quarantine(self.before)
        self.assertTrue(linked.is_symlink())
        self.assertTrue(outside.is_file())
        self.assertEqual(list((self.bench / 'logs').iterdir()), [])
