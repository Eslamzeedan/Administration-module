import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]

class TestSingleNavigation(TestCase):
    def module(self, enabled=True, app='eup_administration'):
        writes = []
        db = SimpleNamespace(exists=lambda *a: True, get_value=lambda *a: app,
                             set_value=lambda *a, **kw: writes.append((a, kw)))
        def rows(doctype, filters, fields):
            if doctype == 'Desktop Icon' and 'name' in filters:
                return [SimpleNamespace(name='EuP Administration v2', app=None, link_type='Workspace Sidebar', link_to='EuP Administration v2'),
                        SimpleNamespace(name='EuP Administration v3', app='other_app', link_type='Workspace Sidebar', link_to='EuP Administration v3')]
            if doctype == 'Desktop Icon':
                self.assertEqual(filters, {'app': 'eup_administration', 'standard': 1})
                return [SimpleNamespace(name='EuP Administration'), SimpleNamespace(name='EuP Administration v3')]
            self.assertEqual(filters, {'module': 'EuP Administration'})
            return [SimpleNamespace(name='EuP Administration v2')]
        fake = SimpleNamespace(conf={'adm_single_navigation': enabled}, db=db,
                               get_all=rows, clear_cache=Mock())
        spec = importlib.util.spec_from_file_location('single_navigation_test_subject', ROOT / 'eup_administration/navigation.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': fake}):
            spec.loader.exec_module(module)
        return module, writes, fake

    def test_existing_sites_are_unchanged_without_opt_in(self):
        module, writes, fake = self.module(False)
        module.configure()
        self.assertEqual(writes, [])
        fake.clear_cache.assert_not_called()

    def test_only_app_navigation_is_hidden_and_repeat_has_same_result(self):
        module, writes, fake = self.module()
        module.configure()
        first = list(writes)
        module.configure()
        self.assertEqual(writes, first * 2)
        self.assertEqual([a[:4] for a, kw in first], [
            ('Desktop Icon', 'EuP Administration', 'hidden', 0),
            ('Desktop Icon', 'EuP Administration v3', 'hidden', 1),
            ('Desktop Icon', 'EuP Administration v2', 'hidden', 1),
            ('Workspace', 'EuP Administration v2', 'is_hidden', 1)])
        self.assertTrue(all(kw == {'update_modified': False} for a, kw in writes))

    def test_foreign_canonical_entry_is_not_overwritten(self):
        module, writes, fake = self.module(app='other_app')
        with self.assertRaisesRegex(RuntimeError, 'another app'):
            module.configure()
        self.assertEqual(writes, [])
