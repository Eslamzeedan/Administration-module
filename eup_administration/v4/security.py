"""Company-scoped visibility; shared masters never grant cross-company access."""
import frappe
from eup_administration.v3.security import active_employee, roles

MANAGERS = {"Administration Manager", "System Manager"}


def company_access(company, user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    employee = active_employee(user)
    return bool(employee and employee.company == company)


def manager(company, user=None):
    return bool(MANAGERS & roles(user)) and company_access(company, user)


def require_company(company):
    if not company_access(company):
        frappe.throw("Active employee in the same company required", frappe.PermissionError)


def operation_permission(doc, user=None, ptype=None, permission_type=None, **kwargs):
    user = user or frappe.session.user
    action = ptype or permission_type or "read"
    if not company_access(doc.company, user):
        return False
    if action == "create":
        return True  # Role permissions still apply.
    visible = manager(doc.company, user) or user in (doc.requested_by, doc.assigned_to, doc.get("recipient"))
    if action in {"read", "select", "report", "print"}:
        return visible
    if action == "write":
        return visible and not doc.workflow_policy and (manager(doc.company, user) or doc.requested_by == user)
    return False


def operation_query(user=None):
    # Frappe query hooks do not supply doctype: per-DocType closures below.
    raise NotImplementedError


def query_for(doctype, user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    employee = active_employee(user)
    if not employee:
        return "1=0"
    company = frappe.db.escape(employee.company)
    own = frappe.db.escape(user)
    table = "`tab" + doctype + "`"
    clause = f"{table}.`company` = {company}"
    if not manager(employee.company, user):
        clause += f" AND ({table}.`requested_by` = {own} OR {table}.`assigned_to` = {own}"
        if doctype == "ADM Parcel":
            clause += f" OR {table}.`recipient` = {own}"
        clause += ")"
    return clause


def adm_facility_ticket_query(user=None):
    return query_for("ADM Facility Ticket", user)


def adm_driver_checklist_query(user=None):
    return query_for("ADM Driver Checklist", user)


def adm_preventive_plan_query(user=None):
    return query_for("ADM Preventive Plan", user)


def adm_parcel_query(user=None):
    return query_for("ADM Parcel", user)


def adm_equipment_booking_query(user=None):
    return query_for("ADM Equipment Booking", user)


def adm_contract_register_query(user=None):
    return query_for("ADM Contract Register", user)


def adm_operational_incident_query(user=None):
    return query_for("ADM Operational Incident", user)


def adm_recurring_task_query(user=None):
    return query_for("ADM Recurring Task", user)


def adm_task_occurrence_query(user=None):
    return query_for("ADM Task Occurrence", user)


def master_permission(doc, user=None, ptype=None, permission_type=None, **kwargs):
    action = ptype or permission_type or "read"
    if not company_access(doc.company, user):
        return False
    return action in {"read", "select", "print", "report"} or manager(doc.company, user)


def master_query(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    emp = active_employee(user)
    return "company = " + frappe.db.escape(emp.company) if emp else "1=0"


def escalation_permission(doc, user=None, ptype=None, permission_type=None, **kwargs):
    action = ptype or permission_type or "read"
    return action in {"read", "select"} and company_access(doc.company, user) and (
        manager(doc.company, user) or doc.escalation_role in roles(user))


def escalation_query(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    emp = active_employee(user)
    if not emp:
        return "1=0"
    company = "company = " + frappe.db.escape(emp.company)
    if manager(emp.company, user):
        return company
    allowed = ", ".join(frappe.db.escape(r) for r in roles(user))
    return company + " AND escalation_role IN (" + (allowed or "''") + ")"
