import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]

class TestWorkspacePreservation(TestCase):
    def subject(self, importing=True):
        payload = {'name': 'EuP Administration', 'doctype': 'Workspace', 'content': 'custom site content',
                   'roles': [{'role': 'Custom Reviewer', 'name': 'existing-child'}],
                   'custom_setting': 'keep', '_user_tags': 'important'}
        fake = SimpleNamespace(flags=SimpleNamespace(in_import=importing),
            db=SimpleNamespace(exists=Mock(return_value=True)),
            get_doc=Mock(return_value=SimpleNamespace(as_dict=lambda: payload)))
        spec = importlib.util.spec_from_file_location('workspace_test_subject', ROOT/'eup_administration/workspaces.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': fake}): spec.loader.exec_module(module)
        return module, fake, payload

    def test_all_workspaces_have_unique_source_names_without_standard(self):
        module, fake, payload = self.subject()
        for name in module.WORKSPACES:
            data = module.definition(name)
            self.assertEqual(data['name'], name)
            self.assertNotIn('standard', data)
            self.assertEqual(data['modified'], '2000-01-01 00:00:00')

    def test_forced_import_keeps_custom_content_roles_and_fields(self):
        module, fake, payload = self.subject()
        updates = {}
        doc = SimpleNamespace(name='EuP Administration', set=lambda k,v: updates.update({k:v}))
        module.preserve_on_import(doc)
        self.assertEqual(updates['content'], payload['content'])
        self.assertEqual(updates['roles'], payload['roles'])
        self.assertEqual(updates['custom_setting'], 'keep')
        self.assertEqual(updates['_user_tags'], 'important')
        self.assertNotIn('doctype', updates)
        updates['roles'][0]['role'] = 'Changed'
        self.assertEqual(payload['roles'][0]['role'], 'Custom Reviewer')

    def test_normal_user_save_does_not_adopt_existing_fields(self):
        module, fake, payload = self.subject(False)
        doc=SimpleNamespace(name='EuP Administration',set=Mock())
        module.preserve_on_import(doc)
        doc.set.assert_not_called()
        fake.get_doc.assert_not_called()

    def test_setup_never_recreates_existing_workspaces(self):
        module, fake, payload = self.subject()
        module.ensure_workspaces()
        fake.get_doc.assert_not_called()
