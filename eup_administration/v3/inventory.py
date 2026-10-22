"""Two-person administrative stock counts, using v2 locked adjustment API."""
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
import frappe
from frappe.utils import now_datetime
from eup_administration.consumables import _fetch_stock, reconcile_consumables, _lock
from eup_administration.v3.security import is_manager, active_employee, roles

_action = ContextVar("adm_v3_stock_count_action", default=False)


@contextmanager
def allow_action():
    token = _action.set(True)
    try:
        yield
    finally:
        _action.reset(token)


def validate_count(doc):
    old = doc.get_doc_before_save()
    if not old:
        if not (is_manager() or "Administration Coordinator" in roles()):
            frappe.throw("Administration Coordinator required", frappe.PermissionError)
        doc.status = "Draft"
        doc.counted_by = frappe.session.user
    elif not _action.get():
        if old.status != "Draft":
            frappe.throw("Only draft counts can be edited directly", frappe.PermissionError)
        if any(doc.get(f) != old.get(f) for f in ("status", "counted_by", "approved_by", "posted_at")):
            frappe.throw("Status changes require stock count actions", frappe.PermissionError)
    if not doc.company or not doc.location or frappe.db.get_value("ADM Consumable Location", doc.location, "company") != doc.company:
        frappe.throw("Stock count location must belong to the selected company")
    if not doc.get("lines"):
        frappe.throw("Stock count requires one or more items")
    item_names = [r.item for r in doc.lines]
    if len(item_names) != len(set(item_names)):
        frappe.throw("Duplicate items are not allowed in one count")
    for row in doc.lines:
        if frappe.db.get_value("ADM Consumable Item", row.item, "company") != doc.company:
            frappe.throw("Stock count item belongs to another company")
        try:
            value = Decimal(str(row.counted_qty))
        except Exception:
            frappe.throw("Invalid stock count quantity")
        if not value.is_finite() or value < 0:
            frappe.throw("Stock count quantity must be finite and nonnegative")
    if old and old.status != "Draft" and _action.get():
        if old.company != doc.company or old.location != doc.location:
            frappe.throw("Approved count company/location cannot change")


def locked_count(name):
    if not frappe.db.sql("SELECT name FROM `tabADM Stock Count` WHERE name=%s FOR UPDATE", (name,)):
        frappe.throw("Stock count not found")
    return frappe.get_doc("ADM Stock Count", name)


def _save(doc):
    with allow_action():
        doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def submit_count(name):
    doc = locked_count(name)
    if doc.status != "Draft" or not (is_manager() or doc.counted_by == frappe.session.user):
        frappe.throw("Only a draft count owner or manager can submit", frappe.PermissionError)
    for row in doc.lines:
        row.expected_qty = float(_fetch_stock(row.item, doc.location))
        row.difference = float(Decimal(str(row.counted_qty)) - Decimal(str(row.expected_qty)))
    doc.status = "Submitted"
    return _save(doc)


@frappe.whitelist(methods=["POST"])
def approve_count(name):
    if not is_manager():
        frappe.throw("Administration Manager required", frappe.PermissionError)
    doc = locked_count(name)
    if doc.status != "Submitted" or doc.counted_by == frappe.session.user:
        frappe.throw("Requires a different approving manager")
    doc.approved_by = frappe.session.user
    doc.status = "Approved"
    return _save(doc)


@frappe.whitelist(methods=["POST"])
def post_count(name):
    if not is_manager():
        frappe.throw("Administration Manager required", frappe.PermissionError)
    doc = locked_count(name)
    if doc.status != "Approved":
        frappe.throw("Only an approved count may be posted")
    if not (doc.reason or "").strip():
        frappe.throw("Physical count adjustment reason is required")
    # Lock in deterministic order to avoid races/deadlocks across stock counts.
    for item in sorted({r.item for r in doc.lines}):
        _lock("ADM Consumable Item", item)
    _lock("ADM Consumable Location", doc.location)
    # No partial posting on failure: the Frappe POST transaction rolls back.
    for row in doc.lines:
        current = Decimal(str(_fetch_stock(row.item, doc.location)))
        if current != Decimal(str(row.expected_qty)):
            frappe.throw("Stock changed since count submission; recount required")
        reconcile_consumables(row.item, doc.location, row.counted_qty, doc.reason)
    doc.status = "Posted"
    doc.posted_at = now_datetime()
    return _save(doc)
