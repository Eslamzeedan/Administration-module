"""Read-only request registry: source documents retain their authoritative status."""
from hashlib import sha256
import frappe
from frappe.utils import now_datetime

SUPPORTED = {
    "ADM Trip": "Fleet",
    "ADM Service Request": "Runner",
    "ADM Supply Request": "Supplies",
    "ADM Meeting Booking": "Meeting",
    "ADM Admin Custody": "Custody",
    "ADM General Service Request": "General",
}


def registry_key(doctype, name):
    return "ADMREG-" + sha256((doctype + ":" + name).encode("utf-8")).hexdigest()[:32]


def sync_document(doc, method=None, *, emit_events=True, rebuild=False):
    if doc.doctype not in SUPPORTED or (getattr(frappe.flags, "in_migrate", False) and not rebuild):
        return
    if not frappe.db.exists("DocType", "ADM Request Registry"):
        return
    # Serialize both lifecycle hooks and rebuilds on the authoritative source row.
    # Identifiers are exclusively from the closed SUPPORTED allowlist above.
    frappe.db.sql("SELECT name FROM `tab" + doc.doctype + "` WHERE name=%s FOR UPDATE", (doc.name,))
    state = doc.get("status") or "Created"
    who = doc.get("requested_by") or doc.get("organizer")
    if doc.doctype == "ADM General Service Request":
        who = doc.get("requested_by")
    if not who and doc.doctype == "ADM Admin Custody":
        who = frappe.db.get_value("Employee", doc.get("assigned_to"), "user_id") if doc.get("assigned_to") else None
    summary = doc.get("subject") or doc.get("purpose") or doc.get("title") or doc.get("custody_title") or doc.name
    date = doc.get("needed_by") or doc.get("planned_end") or doc.get("ends_at")
    if not date and doc.get("return_due"):
        date = str(doc.return_due) + " 23:59:59"
    values = {
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "service_family": SUPPORTED[doc.doctype],
        "company": doc.get("company"),
        "department": doc.get("department"),
        "requested_by": who,
        "assigned_to": doc.get("assigned_runner") or (doc.get("driver") if doc.doctype == "ADM General Service Request" else None),
        "summary": str(summary)[:140],
        "source_status": state,
        "priority": doc.get("priority") or "Normal",
        "due_at": date,
        "last_event_at": now_datetime(),
    }
    if doc.doctype == "ADM General Service Request":
        values["assigned_to"] = doc.assigned_to
    key = registry_key(doc.doctype, doc.name)
    matches = frappe.get_all("ADM Request Registry", filters={
        "reference_doctype": doc.doctype, "reference_name": doc.name
    }, fields=["name", "source_status"], order_by="modified desc")
    old = matches[0].source_status if matches else None
    canonical = next((row for row in matches if row.name == key), None)
    if canonical:
        frappe.db.set_value("ADM Request Registry", key, values, update_modified=True)
    else:
        if frappe.db.exists("ADM Request Registry", key):
            frappe.throw("Registry identity conflict; administrator review required")
        # v16 hash autonaming ignores a supplied document.name unless set_name is explicit.
        frappe.get_doc({"doctype": "ADM Request Registry", **values}).insert(
            ignore_permissions=True, set_name=key)
    for row in matches:
        if row.name != key:
            # Only this rebuildable index is deduplicated. Source records, events,
            # approvals, feedback and notification history are never deleted.
            frappe.db.delete("ADM Request Registry", {
                "name": row.name, "reference_doctype": doc.doctype, "reference_name": doc.name
            })
    if emit_events and old != state:
        event = frappe.get_doc({
            "doctype": "ADM Request Event", "reference_doctype": doc.doctype,
            "reference_name": doc.name, "event_type": "Created" if old is None else "Status Changed",
            "actor": frappe.session.user or "Administrator", "occurred_at": now_datetime(),
            "old_status": old, "new_status": state,
        }).insert(ignore_permissions=True)
        from eup_administration.v3.notifications import prepare_event
        prepare_event(event, doc)


@frappe.whitelist()
def my_requests(limit=50):
    """Permission-filtered list, never ignore_permissions."""
    limit = max(1, min(100, int(limit)))
    return frappe.get_list("ADM Request Registry", fields=[
        "reference_doctype", "reference_name", "service_family", "summary",
        "source_status", "priority", "due_at", "last_event_at"
    ], order_by="last_event_at desc", limit_page_length=limit)


def rebuild_registry():
    """Administrator-only, idempotent backfill for records existing before v3."""
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw("Administrator or System Manager required", frappe.PermissionError)
    totals = {}
    for dt in SUPPORTED:
        count = 0
        for name in frappe.get_all(dt, pluck="name", limit_page_length=0):
            sync_document(frappe.get_doc(dt, name), emit_events=False, rebuild=True)
            count += 1
        totals[dt] = count
    return totals
