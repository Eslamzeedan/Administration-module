"""Dual handover of operational custody; capitalized assets stay in ERPNext Assets."""
from contextlib import contextmanager
from contextvars import ContextVar
import frappe
from frappe.utils import now_datetime
from eup_administration.v3.security import is_manager, active_employee, roles
from eup_administration.consumables import internal_action

_change = ContextVar("adm_v3_handover_change", default=False)


@contextmanager
def allow_change():
    token = _change.set(True)
    try:
        yield
    finally:
        _change.reset(token)


def validate(doc):
    old = doc.get_doc_before_save()
    if not old:
        if not (is_manager() or "Administration Coordinator" in roles()):
            frappe.throw("Administration Coordinator required", frappe.PermissionError)
        custody = frappe.get_doc("ADM Admin Custody", doc.custody)
        custody.check_permission("read")
        if custody.status != "Issued":
            frappe.throw("Only issued custody can be transferred")
        doc.company = custody.company
        doc.from_employee = custody.assigned_to
        doc.issued_by = frappe.session.user
        doc.status = "Pending"
        doc.received_by = None
        doc.handover_at = None
        if not doc.to_employee or doc.to_employee == doc.from_employee:
            frappe.throw("Select a different receiving employee")
        if frappe.db.get_value("Employee", doc.to_employee, "company") != doc.company:
            frappe.throw("Receiving employee belongs to another company")
    elif not _change.get():
        frappe.throw("Custody handovers can only change through actions", frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def confirm(name):
    if not frappe.db.sql("SELECT name FROM `tabADM Custody Handover` WHERE name=%s FOR UPDATE", (name,)):
        frappe.throw("Handover not found")
    handover = frappe.get_doc("ADM Custody Handover", name)
    employee = active_employee()
    if handover.status != "Pending" or not employee or handover.to_employee != employee.name:
        frappe.throw("Only the receiving employee can confirm", frappe.PermissionError)
    if handover.issued_by == frappe.session.user:
        frappe.throw("Dual confirmation requires another person")
    if not frappe.db.sql("SELECT name FROM `tabADM Admin Custody` WHERE name=%s FOR UPDATE", (handover.custody,)):
        frappe.throw("Custody not found")
    custody = frappe.get_doc("ADM Admin Custody", handover.custody)
    if custody.status != "Issued" or custody.assigned_to != handover.from_employee or custody.company != handover.company:
        frappe.throw("Custody owner changed since handover was started")
    with internal_action():
        custody.assigned_to = handover.to_employee
        custody.save(ignore_permissions=True)
    handover.status = "Confirmed"
    handover.received_by = frappe.session.user
    handover.handover_at = now_datetime()
    with allow_change():
        handover.save(ignore_permissions=True)
    return {"handover": handover.name, "status": "Confirmed", "custody": custody.name}
