import frappe


def execute():
    from eup_administration.install import ensure_roles
    ensure_roles()
    # This workspace was runtime-created in v0.1.0 and has no standard source JSON.
    # Keep it site-owned before orphan cleanup; never replace its customized content.
    if frappe.db.exists('Workspace', 'EuP Administration') and frappe.get_meta('Workspace').has_field('standard'):
        frappe.db.set_value('Workspace', 'EuP Administration', 'standard', 0, update_modified=False)
