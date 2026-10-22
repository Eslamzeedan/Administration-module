import json
import frappe

ROLES = ('Administration Manager', 'Administration User', 'Administration Driver',
         'Administration Requester', 'Administration Runner', 'Administration Department Approver', 'Administration Storekeeper',
         'Administration Coordinator', 'Administration Auditor')

def ensure_roles():
    for role in ROLES:
        if not frappe.db.exists('Role', role):
            frappe.get_doc({'doctype': 'Role', 'role_name': role, 'desk_access': 1}).insert(ignore_permissions=True)


def setup():
    ensure_roles()
    # Preserve the site's original workspace content. The new v2 workspace has a checked-in
    # standard JSON, so Frappe's orphan-entity cleanup can resolve its source during migrate.
    if not frappe.db.exists('Workspace', 'EuP Administration'):
        shortcuts = [{'label': label, 'type': 'DocType', 'link_to': dt} for label, dt in (
            ('Vehicles', 'ADM Vehicle'), ('Drivers', 'ADM Driver'), ('Trips', 'ADM Trip'),
            ('Meeting Rooms', 'ADM Meeting Room'), ('Meetings', 'ADM Meeting Booking'))]
        content = [{'id': 'adm-title', 'type': 'header', 'data': {'text': 'EuP Administration', 'col': 12}}]
        content += [{'id': f'adm-{i}', 'type': 'shortcut', 'data': {'shortcut_name': item['label'], 'col': 4}}
            for i, item in enumerate(shortcuts)]
        frappe.get_doc({'doctype': 'Workspace', 'label': 'EuP Administration', 'title': 'EuP Administration',
            'module': 'EuP Administration', 'type': 'Workspace', 'standard': 0, 'public': 1,
            'content': json.dumps(content), 'shortcuts': shortcuts,
            'roles': [{'role': role} for role in (*ROLES, 'System Manager')]}).insert(ignore_permissions=True)
    frappe.clear_cache()
