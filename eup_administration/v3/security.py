"""Row-level permissions for the request hub. Never rely on hidden UI alone."""
import frappe

ADMIN = {"Administration Manager", "System Manager"}
REQUESTER = {"Administration User", "Administration Requester"}
TEAM = {"Administration Coordinator", "Administration Runner", "Administration Driver", "Administration Storekeeper"}


def roles(user=None):
    return set(frappe.get_roles(user or frappe.session.user))


def is_manager(user=None):
    return bool(ADMIN & roles(user))


def active_employee(user=None):
    return frappe.db.get_value(
        "Employee", {"user_id": user or frappe.session.user, "status": "Active"},
        ["name", "department", "company"], as_dict=True
    )


def general_query(user=None):
    user = user or frappe.session.user
    if is_manager(user):
        return ""
    quoted = frappe.db.escape(user)
    return f"(`tabADM General Service Request`.`requested_by` = {quoted} OR `tabADM General Service Request`.`assigned_to` = {quoted})"


def general_permission(doc, user=None, ptype=None, permission_type=None, **kwargs):
    user = user or frappe.session.user
    action = ptype or permission_type or "read"
    if is_manager(user):
        return True
    if action == "create":
        return bool(REQUESTER & roles(user))
    if action in {"read", "select", "print"}:
        return user in (doc.requested_by, doc.assigned_to)
    if action == "write":
        return doc.status == "Draft" and doc.requested_by == user and bool(REQUESTER & roles(user))
    return False


def registry_query(user=None):
    user = user or frappe.session.user
    if is_manager(user) or "Administration Auditor" in roles(user):
        return ""
    quoted = frappe.db.escape(user)
    return f"(`tabADM Request Registry`.`requested_by` = {quoted} OR `tabADM Request Registry`.`assigned_to` = {quoted})"


def registry_permission(doc, user=None, ptype=None, permission_type=None, **kwargs):
    user = user or frappe.session.user
    action = ptype or permission_type or "read"
    if action not in {"read", "select", "print", "report"}:
        return False
    return is_manager(user) or "Administration Auditor" in roles(user) or user in (doc.requested_by, doc.assigned_to)
