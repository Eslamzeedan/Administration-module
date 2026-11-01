"""Permission-scoped employee/driver trip view; no elevated trip reads or writes."""
import frappe
from eup_administration.permissions import active_driver, is_admin
from eup_administration.v3.security import active_employee
from eup_administration import services
from eup_administration.trip_stops import next_visit

CREATE_FIELDS = {"purpose", "origin", "destination", "planned_start", "planned_end", "passenger_count", "stops"}
STOP_FIELDS = {"location", "purpose", "expected_wait_minutes"}


def login():
    if frappe.session.user == "Guest":
        frappe.throw("Please sign in", frappe.PermissionError)


def serialize(doc):
    doc.check_permission("read")
    operate = bool(is_admin() or (doc.driver and doc.driver == active_driver()))
    row = next_visit(doc)
    return {
        **{key: doc.get(key) for key in (
            "name", "purpose", "origin", "destination", "planned_start", "planned_end",
            "status", "vehicle", "driver", "requested_by", "passenger_count",
            "actual_start", "actual_end", "start_odometer", "end_odometer", "distance_km",
            "destination_arrived_at", "rejection_reason", "modified")},
        "driver_name": frappe.db.get_value("ADM Driver", doc.driver, "driver_name") if doc.driver else "",
        "requester_name": frappe.db.get_value("User", doc.requested_by, "full_name") or doc.requested_by,
        "stops": [{key: r.get(key) for key in ("name",) + tuple(STOP_FIELDS) +
                  ("arrived_at", "departed_at")} for r in (doc.get("stops") or [])],
        "operate": operate,
        "can_cancel": (is_admin() or doc.requested_by == frappe.session.user) and doc.status in ("Draft", "Requested", "Assigned"),
        "next_stop": row.name if row else None,
        "next_event": ("depart" if row.arrived_at else "arrive") if row else None,
        "can_end": operate and doc.status == "In Progress" and row is None,
    }


@frappe.whitelist()
def home(view="mine", start=0):
    login()
    if view not in ("mine", "driver"):
        frappe.throw("Choose employee or driver view")
    try:
        offset = int(start)
        if offset < 0 or offset > 10000:
            raise ValueError
    except (ValueError, TypeError):
        frappe.throw("Invalid trip page")
    filters = {"requested_by": frappe.session.user}
    if view == "driver":
        driver = active_driver()
        if not driver:
            frappe.throw("An enabled driver profile is required", frappe.PermissionError)
        filters = {"driver": driver, "status": ["in", ["Assigned", "In Progress"]]}
    rows = frappe.get_list("ADM Trip", filters=filters, fields=["name"],
        order_by=("planned_start asc, name asc" if view == "driver" else "planned_start desc, name desc"),
        start=offset, page_length=21)
    employee = active_employee()
    return {"trips": [serialize(frappe.get_doc("ADM Trip", r.name)) for r in rows[:20]],
            "has_more": len(rows) > 20, "start": offset,
            "is_driver": bool(active_driver()),
            "can_create": bool(employee and frappe.has_permission("ADM Trip", "create")),
            "company": employee.company if employee else ""}


@frappe.whitelist(methods=["POST"])
def create(values):
    login()
    employee = active_employee()
    if not employee or not frappe.has_permission("ADM Trip", "create"):
        frappe.throw("An active employee with trip request permission is required", frappe.PermissionError)
    values = frappe.parse_json(values) if isinstance(values, str) else values
    if not isinstance(values, dict) or not set(values) <= CREATE_FIELDS:
        frappe.throw("Unsupported trip request fields")
    stops = values.get("stops", [])
    if not isinstance(stops, list) or len(stops) > 30 or any(
        not isinstance(r, dict) or not set(r) <= STOP_FIELDS for r in stops):
        frappe.throw("Invalid trip stops")
    # Company/department/requester are always server-owned.
    doc = frappe.get_doc({"doctype": "ADM Trip", **values,
        "company": employee.company, "department": employee.department}).insert()
    services.request_trip(doc.name)
    return {"name": doc.name}
