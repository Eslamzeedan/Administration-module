"""Mobile meeting room search and booking on the same calendar as Desk."""
import frappe
from eup_administration import services

ROOM = "ADM Meeting Room"
BOOKING = "ADM Meeting Booking"
SERVICE_TYPES = ("Hospitality", "Equipment", "Other")


def positive(value):
    text = str(value)
    if not text.isascii() or not text.isdigit() or not 0 < int(text) <= 2147483647:
        frappe.throw("Enter a positive whole number")
    return int(text)


def criteria(starts_at, ends_at, attendees):
    services.period(starts_at, ends_at)
    return positive(attendees)


@frappe.whitelist(methods=["GET"])
def available(starts_at, ends_at, attendees):
    count = criteria(starts_at, ends_at, attendees)
    rooms = frappe.get_list(ROOM, filters={"enabled": 1, "capacity": [">=", count]},
        fields=["name", "room_name", "capacity", "branch", "floor", "equipment", "buffer_minutes"],
        order_by="capacity asc, room_name asc, name asc", limit_page_length=0)
    return {"rooms": [r for r in rooms if not services.room_availability(r.name, starts_at, ends_at)],
            "can_book": bool(frappe.has_permission(BOOKING, "create"))}


@frappe.whitelist(methods=["POST"])
def reserve(room, title, starts_at, ends_at, attendees, extras=None):
    frappe.has_permission(BOOKING, "create", throw=True)
    count = criteria(starts_at, ends_at, attendees)
    if not isinstance(title,str) or not title.strip():
        frappe.throw("Enter the meeting title")
    extras = frappe.parse_json(extras) if isinstance(extras,str) else extras
    if extras is None:
        extras = []
    if not isinstance(extras,list) or len(extras)>len(SERVICE_TYPES):
        frappe.throw("Invalid meeting services")
    rows=[]
    for row in extras:
        if not isinstance(row,dict) or row.get("service_type") not in SERVICE_TYPES:
            frappe.throw("Invalid meeting service")
        rows.append(dict(service_type=row["service_type"], details=str(row.get("details") or ""),
                         quantity=positive(row.get("quantity",1)), status="Requested"))
    frappe.get_doc(ROOM, room).check_permission("read")
    frappe.db.savepoint("mobile_room_booking")
    try:
        doc=frappe.get_doc(dict(doctype=BOOKING,room=room,title=title.strip(),starts_at=starts_at,
                               ends_at=ends_at,attendee_count=count,services=rows)).insert()
    except frappe.ValidationError as exc:
        if str(exc)!="Room is already booked, including preparation time":
            raise
        frappe.db.rollback(save_point="mobile_room_booking")
        frappe.clear_last_message()
        return {"conflict": True}
    return {"conflict": False, "name":doc.name}


@frappe.whitelist(methods=["GET"])
def details(name):
    doc=frappe.get_doc(BOOKING,name)
    doc.check_permission("read")
    can_cancel=doc.status=="Confirmed" and doc.has_permission("write")
    doc.apply_fieldlevel_read_permissions()
    return {**{key:doc.get(key) for key in ("name","room","title","status","starts_at","ends_at","attendee_count")},
            "can_cancel":bool(can_cancel),
            "services":[{key:row.get(key) for key in ("service_type","quantity","details","status")}
                        for row in doc.get("services") or []]}
