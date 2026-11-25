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
    from eup_administration.workspaces import ensure_workspaces
    from eup_administration.navigation import configure
    ensure_workspaces()
    configure()
    frappe.clear_cache()
