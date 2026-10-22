"""Meeting-room check-ins and safe availability listing."""
import frappe
from frappe.utils import now_datetime, get_datetime
from eup_administration.v3.security import is_manager, active_employee, roles


@frappe.whitelist()
def room_availability(start, end, company=None):
    start, end = get_datetime(start), get_datetime(end)
    if end <= start or (end - start).days > 14:
        frappe.throw("Choose a valid window within 14 days")
    if not is_manager():
        e = active_employee()
        if not e or (company and e.company != company):
            frappe.throw("Company access denied", frappe.PermissionError)
        company = e.company
    if not company:
        frappe.throw("Select a company")
    rooms = frappe.get_list("ADM Meeting Room", filters={"company": company},
        fields=["name", "room_name", "capacity"], limit_page_length=200)
    bookings = frappe.get_list("ADM Meeting Booking", filters={
        "company": company, "status": "Confirmed", "starts_at": ["<", end],
        "ends_at": [">", start],
    }, fields=["room", "starts_at", "ends_at"], limit_page_length=0)
    # Do not expose other organizers' private meeting titles.
    return {"rooms": rooms, "occupied": bookings}


@frappe.whitelist(methods=["POST"])
def check_in(booking):
    if not frappe.db.sql("SELECT name FROM `tabADM Meeting Booking` WHERE name=%s FOR UPDATE", (booking,)):
        frappe.throw("Meeting not found")
    doc = frappe.get_doc("ADM Meeting Booking", booking)
    doc.check_permission("read")
    if not (is_manager() or doc.organizer == frappe.session.user):
        frappe.throw("Only organizer or Administration Manager can check in", frappe.PermissionError)
    if doc.status != "Confirmed":
        frappe.throw("Only confirmed meetings allow check-in")
    now = get_datetime(now_datetime())
    if not (get_datetime(doc.starts_at) <= now <= get_datetime(doc.ends_at)):
        frappe.throw("Check-in must occur during the booking")
    if frappe.db.exists("ADM Meeting Checkin", {"booking": booking}):
        frappe.throw("Meeting has already been checked in")
    frappe.flags.adm_v3_checkin = True
    try:
        record = frappe.get_doc({"doctype": "ADM Meeting Checkin", "booking": doc.name,
            "company": doc.company, "status": "Present", "checked_in_by": frappe.session.user,
            "checked_in_at": now_datetime()}).insert(ignore_permissions=True)
    finally:
        frappe.flags.adm_v3_checkin = False
    return {"checkin": record.name, "status": "Present"}
