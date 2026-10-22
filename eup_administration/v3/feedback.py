"""Requester feedback after completion; one response per source document and user."""
from hashlib import sha256
import frappe
from frappe.utils import now_datetime
from eup_administration.v3.registry import SUPPORTED


@frappe.whitelist(methods=["POST"])
def submit_feedback(reference_doctype, reference_name, rating, comments=None):
    if reference_doctype not in SUPPORTED:
        frappe.throw("Unsupported request type")
    try:
        value = int(rating)
    except (TypeError, ValueError):
        frappe.throw("Rating must be an integer between 1 and 5")
    if value not in (1, 2, 3, 4, 5):
        frappe.throw("Rating must be between 1 and 5")
    from eup_administration.v3.registry import registry_key
    ref = frappe.get_doc("ADM Request Registry", registry_key(reference_doctype, reference_name))
    ref.check_permission("read")
    if ref.requested_by != frappe.session.user:
        frappe.throw("Only the original requester can give feedback", frappe.PermissionError)
    if ref.source_status not in {"Completed", "Closed", "Fulfilled", "Returned"}:
        frappe.throw("Feedback is available only after completion")
    key = "ADMFB-" + sha256((reference_doctype + ":" + reference_name + ":" + frappe.session.user).encode()).hexdigest()[:32]
    if frappe.db.exists("ADM Request Feedback", key):
        frappe.throw("Feedback has already been submitted")
    return frappe.get_doc({
        "doctype": "ADM Request Feedback", "name": key,
        "reference_doctype": reference_doctype, "reference_name": reference_name,
        "submitted_by": frappe.session.user, "rating": value,
        "comments": (comments or "")[:1000], "submitted_at": now_datetime()
    }).insert(ignore_permissions=True).name
