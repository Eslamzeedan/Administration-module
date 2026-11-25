"""Opt-in single entry point; preserves legacy records and other apps' navigation."""
import json
from pathlib import Path
import frappe

APP = 'eup_administration'
TITLE = 'EuP Administration'


def configure():
    if not frappe.conf.get('adm_single_navigation'):
        return
    root = Path(__file__).resolve().parent
    for doctype, folder in [('Workspace Sidebar', 'workspace_sidebar'), ('Desktop Icon', 'desktop_icon')]:
        if frappe.db.exists(doctype, TITLE):
            if frappe.db.get_value(doctype, TITLE, 'app') != APP:
                raise RuntimeError('Canonical administration navigation belongs to another app')
        else:
            definition = json.loads((root / folder / 'eup_administration.json').read_text())
            frappe.get_doc(definition).insert(ignore_permissions=True)
    for row in frappe.get_all('Desktop Icon', filters={'app': APP, 'standard': 1}, fields=['name']):
        frappe.db.set_value('Desktop Icon', row.name, 'hidden', int(row.name != TITLE), update_modified=False)
    # Frappe may have generated nonstandard icons from the legacy Workspaces.
    # Match both exact labels and their own sidebar targets; never hide another app.
    for row in frappe.get_all('Desktop Icon', filters={'name': ['in', ['EuP Administration v2', 'EuP Administration v3']]},
                              fields=['name', 'app', 'link_type', 'link_to']):
        if row.app in (None, '', APP) and row.link_type == 'Workspace Sidebar' and row.link_to == row.name:
            frappe.db.set_value('Desktop Icon', row.name, 'hidden', 1, update_modified=False)
    # Legacy workspaces stay available by direct route, with original contents intact.
    for row in frappe.get_all('Workspace', filters={'module': 'EuP Administration'}, fields=['name']):
        frappe.db.set_value('Workspace', row.name, 'is_hidden', 1, update_modified=False)
    frappe.clear_cache()
