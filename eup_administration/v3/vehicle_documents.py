"""Vehicle documents and expiry checks; attachments must be private."""
from contextvars import ContextVar
import frappe
from frappe.utils import getdate
from eup_administration.v3.security import is_manager

_verifying = ContextVar("adm_v3_doc_verify", default=False)


def validate(doc):
    vehicle_company = frappe.db.get_value("ADM Vehicle", doc.vehicle, "company")
    if not vehicle_company or vehicle_company != doc.company:
        frappe.throw("Vehicle document company mismatch")
    if doc.valid_from and doc.expiry_date and getdate(doc.expiry_date) < getdate(doc.valid_from):
        frappe.throw("Document expiration cannot precede its start")
    if doc.attachment:
        row = frappe.db.get_value("File", {"file_url": doc.attachment},
                                  ["name", "is_private"], as_dict=True)
        if not row or not row.is_private:
            frappe.throw("Vehicle documents must be private files")
    old = doc.get_doc_before_save()
    if not _verifying.get():
        if old and old.verified and any(doc.get(x) != old.get(x) for x in ("attachment", "document_number", "valid_from", "expiry_date", "vehicle", "company", "document_type")):
            frappe.throw("Verified vehicle documents are immutable; create a new revision")
        if old and (doc.verified != old.verified or doc.verified_by != old.verified_by):
            frappe.throw("Verify using the protected action", frappe.PermissionError)
        if not old:
            doc.verified = 0
            doc.verified_by = None


@frappe.whitelist(methods=["POST"])
def verify(name):
    if not is_manager():
        frappe.throw("Administration Manager required", frappe.PermissionError)
    doc = frappe.get_doc("ADM Vehicle Document", name)
    doc.check_permission("read")
    if not doc.attachment:
        frappe.throw("Attach a private document before verification")
    token = _verifying.set(True)
    try:
        doc.verified = 1
        doc.verified_by = frappe.session.user
        doc.save(ignore_permissions=True)
    finally:
        _verifying.reset(token)
    return {"document": doc.name, "verified": True}
