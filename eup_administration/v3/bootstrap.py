"""Explicit staging setup; no destructive installation hooks."""
import frappe
from eup_administration.install import ensure_roles

def configure():
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw("System Manager required", frappe.PermissionError)
    ensure_roles()
    if not frappe.db.get_single_value("ADM Settings", "default_sla_minutes"):
        frappe.db.set_single_value("ADM Settings", "default_sla_minutes", 1440)
    frappe.clear_cache()
    return {"v3": "configured", "external_integrations": "off by default"}
