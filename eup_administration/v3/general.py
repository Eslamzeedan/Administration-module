"""Service-request actions; all state transitions are server-authorized."""
from contextlib import contextmanager
from contextvars import ContextVar
import frappe
from frappe.utils import now_datetime, get_datetime
from eup_administration.v3.security import active_employee, is_manager, roles, REQUESTER

_allow_transition = ContextVar("adm_v3_general_action", default=False)


@contextmanager
def transition():
    token = _allow_transition.set(True)
    try:
        yield
    finally:
        _allow_transition.reset(token)


def validate(doc):
    old = doc.get_doc_before_save()
    if not old:
        if not (is_manager() or roles() & REQUESTER):
            frappe.throw("Requester role required", frappe.PermissionError)
        doc.requested_by = frappe.session.user
        employee = active_employee()
        if employee:
            doc.company = employee.company
            doc.department = employee.department
        elif not is_manager():
            frappe.throw("An active Employee linked to the login is required", frappe.PermissionError)
        doc.status = "Draft"
        if not doc.priority:
            doc.priority = "Normal"
    else:
        protected = (
            "requested_by", "department", "company", "status", "assigned_to",
            "started_at", "completed_at", "closed_at", "completion_notes",
        )
        if any(doc.get(key) != old.get(key) for key in protected) and not _allow_transition.get():
            frappe.throw("Protected fields require authorized actions", frappe.PermissionError)
        if old.status != "Draft" and not _allow_transition.get():
            frappe.throw("Only draft service requests may be edited directly", frappe.PermissionError)
    if doc.cost_center and frappe.db.get_value("Cost Center", doc.cost_center, "company") != doc.company:
        frappe.throw("Cost center belongs to another company")
    if not doc.subject or not doc.description or not doc.company:
        frappe.throw("Subject, description, and company are required")
    if doc.needed_by:
        get_datetime(doc.needed_by)


def locked_request(name):
    if not frappe.db.sql("SELECT name FROM `tabADM General Service Request` WHERE name=%s FOR UPDATE", (name,)):
        frappe.throw("Service request not found")
    return frappe.get_doc("ADM General Service Request", name)


def write_action(doc):
    with transition():
        doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def submit(name):
    doc = locked_request(name)
    if doc.status != "Draft" or (doc.requested_by != frappe.session.user and not is_manager()):
        frappe.throw("Only a draft requester can submit", frappe.PermissionError)
    from eup_administration.v3.approval import create_case
    case = create_case(doc)
    doc.status = "Pending Approval"
    result = write_action(doc)
    return {**result, "approval_case": case.name}


@frappe.whitelist(methods=["POST"])
def assign(name, assignee):
    if not is_manager():
        frappe.throw("Administration Manager required", frappe.PermissionError)
    doc = locked_request(name)
    if doc.status != "Approved":
        frappe.throw("Request must be approved before assignment")
    if not frappe.db.get_value("User", assignee, "enabled"):
        frappe.throw("Assignee must be an enabled user")
    employee = active_employee(assignee)
    if not employee or employee.company != doc.company:
        frappe.throw("Assignee must be an active employee of the same company")
    doc.assigned_to = assignee
    doc.status = "Assigned"
    return write_action(doc)


@frappe.whitelist(methods=["POST"])
def start(name):
    doc = locked_request(name)
    if doc.status != "Assigned" or doc.assigned_to != frappe.session.user:
        frappe.throw("Only the assigned employee can start an assigned request", frappe.PermissionError)
    doc.status = "In Progress"
    doc.started_at = now_datetime()
    return write_action(doc)


@frappe.whitelist(methods=["POST"])
def complete(name, notes):
    doc = locked_request(name)
    if doc.status != "In Progress" or doc.assigned_to != frappe.session.user:
        frappe.throw("Only the assigned employee can complete this request", frappe.PermissionError)
    if not (notes or "").strip():
        frappe.throw("Completion notes are mandatory")
    doc.completion_notes = notes.strip()
    doc.completed_at = now_datetime()
    doc.status = "Completed"
    return write_action(doc)


@frappe.whitelist(methods=["POST"])
def close(name):
    doc = locked_request(name)
    if doc.status != "Completed" or not (is_manager() or doc.requested_by == frappe.session.user):
        frappe.throw("Requester or Administration Manager must verify completion", frappe.PermissionError)
    doc.status = "Closed"
    doc.closed_at = now_datetime()
    return write_action(doc)


@frappe.whitelist(methods=["POST"])
def cancel(name):
    doc = locked_request(name)
    if doc.status not in {"Draft", "Pending Approval", "Approved"}:
        frappe.throw("Request cannot be cancelled in its current state")
    if not (is_manager() or doc.requested_by == frappe.session.user):
        frappe.throw("Requester or Administration Manager required", frappe.PermissionError)
    doc.status = "Cancelled"
    from eup_administration.v3.approval import cancel_case
    cancel_case(doc)
    return write_action(doc)
