"""Actual Frappe import/navigation regression tests on isolated sites only."""
import frappe
from pathlib import Path
from eup_administration.tests.base import AdministrationIntegrationTestCase
from eup_administration import navigation, workspaces

class TestWorkspaceNavigation(AdministrationIntegrationTestCase):
    def test_forced_import_preserves_existing_workspace_customization(self):
        from frappe.modules.import_file import import_file_by_path
        from frappe.model.sync import create_entity_file_map
        source_map = create_entity_file_map(['Workspace'])
        for name in workspaces.WORKSPACES:
            self.assertIn(name, source_map['Workspace'])
            doc = frappe.get_doc('Workspace', name)
            original = doc.content
            try:
                frappe.db.set_value('Workspace', name, 'content', '[{"id":"qa-preserve","type":"header","data":{"text":"Synthetic custom content","col":12}}]')
                before = workspaces.semantic_payload(frappe.get_doc('Workspace', name).as_dict())
                slug = name.lower().replace(' ', '_')
                source = Path(workspaces.__file__).parent/'eup_administration'/'workspace'/slug/(slug+'.json')
                for unused in range(2):
                    import_file_by_path(str(source), force=True, reset_permissions=False)
                    self.assertEqual(workspaces.semantic_payload(frappe.get_doc('Workspace', name).as_dict()), before)
            finally:
                frappe.db.set_value('Workspace', name, 'content', original)

    def test_single_navigation_retains_contents_and_one_visible_icon(self):
        old = frappe.conf.get('adm_single_navigation')
        frappe.conf.adm_single_navigation = 1
        self.addCleanup(frappe.conf.update, {'adm_single_navigation': old})
        before = {name: frappe.db.get_value('Workspace', name, 'content') for name in workspaces.WORKSPACES}
        navigation.configure()
        navigation.configure()
        icons = frappe.get_all('Desktop Icon', filters={'label': ['like', 'EuP Administration%'], 'hidden': 0}, pluck='name')
        self.assertEqual(icons, ['EuP Administration'])
        for name, content in before.items():
            self.assertEqual(frappe.db.get_value('Workspace', name, 'content'), content)
            self.assertEqual(frappe.db.get_value('Workspace', name, 'is_hidden'), 1)
