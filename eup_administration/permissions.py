"""Permission hooks deny access in addition to Frappe roles and User Permissions."""
import frappe

READ_TYPES = {"read", "select", "print", "email", "report", "export"}

def is_admin(user=None):
    user = user or frappe.session.user
    return user == "Administrator" or bool(set(frappe.get_roles(user)) & {"System Manager", "Administration Manager"})

def active_driver(user=None):
    user = user or frappe.session.user
    if "Administration Driver" not in frappe.get_roles(user):
        return None
    return frappe.db.get_value("ADM Driver", {"user": user, "enabled": 1}, "name")

def trip_query(user=None):
    user = user or frappe.session.user
    if is_admin(user):
        return ""
    own = "Administration User" in frappe.get_roles(user)
    parts = ["1=0"]
    if own:
        parts.append("`tabADM Trip`.requested_by = " + frappe.db.escape(user))
    driver = active_driver(user)
    if driver:
        parts.append("`tabADM Trip`.driver = " + frappe.db.escape(driver))
    return "(" + " OR ".join(parts) + ")"

def booking_query(user=None):
    if is_admin(user):
        return ""
    return "`tabADM Meeting Booking`.organizer = " + frappe.db.escape(user or frappe.session.user)

def trip_permission(doc, user=None, ptype=None, permission_type=None, **kwargs):
    user = user or frappe.session.user
    ptype = ptype or permission_type or "read"
    if is_admin(user):
        return True
    own = "Administration User" in frappe.get_roles(user) and doc.requested_by == user
    if doc.is_new():
        return "Administration User" in frappe.get_roles(user) and ptype in {"create", "write", "read"}
    assigned = doc.driver and doc.driver == active_driver(user)
    if ptype in READ_TYPES:
        return bool(own or assigned)
    if ptype == "write":
        return bool(own and doc.status == "Draft")
    return False

def booking_permission(doc, user=None, ptype=None, **kwargs):
    user = user or frappe.session.user
    if is_admin(user):
        return True
    if "Administration User" not in frappe.get_roles(user):
        return False
    own = doc.is_new() or doc.organizer == user
    return bool(own and ((ptype or "read") in READ_TYPES | {"create"} or (ptype == "write" and doc.status == "Confirmed")))

def driver_query(user=None):
    if is_admin(user):
        return ""
    return "`tabADM Driver`.user = " + frappe.db.escape(user or frappe.session.user)

def driver_permission(doc, user=None, ptype=None, **kwargs):
    user = user or frappe.session.user
    return is_admin(user) or ((ptype or "read") in READ_TYPES and doc.user == user)

def ledger_query(user=None):
    if is_admin(user):
        return ""
    # Owner applies to both ledgers, avoiding interpolated table identifiers.
    return "owner = " + frappe.db.escape(user or frappe.session.user)

def ledger_permission(doc, user=None, ptype=None, **kwargs):
    user = user or frappe.session.user
    if is_admin(user):
        return True
    ptype = ptype or "read"
    roles = set(frappe.get_roles(user))
    if not roles & {"Administration User", "Administration Driver"}:
        return False
    own = doc.is_new() or doc.owner == user
    return bool(own and (ptype in READ_TYPES or (ptype in {"create", "write"} and doc.docstatus == 0)))


def fuel_query(user=None):
    return ledger_query(user).replace('owner =', '`tabADM Fuel Log`.owner =')


def expense_query(user=None):
    return ledger_query(user).replace('owner =', '`tabADM Trip Expense`.owner =')
