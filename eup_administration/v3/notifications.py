"""Feature-flagged outbox. Does not contact mail servers on installation."""
import frappe
from frappe.utils import now_datetime

def flag(name):
    try:
        return bool(frappe.db.get_single_value("ADM Settings", name))
    except Exception:
        return False


def prepare_event(event, source):
    """Use an outbox with a unique event/recipient/channel tuple."""
    if not flag("enable_email_notifications"):
        return
    recipients = {source.get("requested_by"), source.get("assigned_to"), source.get("assigned_runner")}
    for recipient in recipients - {None, ""}:
        if not frappe.db.exists("User", recipient):
            continue
        match = {"event": event.name, "recipient": recipient, "channel": "Email"}
        if frappe.db.exists("ADM Notification Outbox", match):
            continue
        frappe.get_doc({
            "doctype": "ADM Notification Outbox", **match,
            "status": "Pending", "attempts": 0, "next_attempt": now_datetime(),
        }).insert(ignore_permissions=True)


def process_outbox():
    if not flag("enable_email_notifications"):
        return {"status": "disabled"}
    processed = 0
    for record in frappe.get_all("ADM Notification Outbox",
        filters={"status": "Pending", "next_attempt": ["<=", now_datetime()]},
        fields=["name"], order_by="creation asc", limit_page_length=50):
        row = frappe.get_doc("ADM Notification Outbox", record.name)
        # Explicitly no outbound mail until recipients/templates have been accepted in staging.
        row.db_set("status", "Disabled")
        processed += 1
    return {"disabled_unconfigured": processed}


def daily_sla_digest():
    """Deliberately read-only until SLA policy and escalation routing are configured."""
    return {"status": "inactive", "note": "SLA escalation feature flag not enabled"}
