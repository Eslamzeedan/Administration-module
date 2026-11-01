"""Ordered administrative trip visits. Parent trip locks serialize every milestone."""
import math
import frappe
from frappe.utils import get_datetime, now_datetime

ROUTE_FIELDS = ("location", "purpose", "expected_wait_minutes")
EVENT_FIELDS = ("arrived_at", "departed_at", "arrived_by", "departed_by")
DESTINATION_FIELDS = ("destination_arrived_at", "destination_arrived_by")


def snapshot(rows, fields):
    return [tuple(row.get(key) or None for key in fields) for row in rows]


def validate_stops(doc, internal=False):
    rows = doc.get("stops") or []
    old = doc.get_doc_before_save()
    before = (old.get("stops") or []) if old else []
    if len(rows) > 30:
        frappe.throw("A trip supports at most 30 stops")
    for row in rows:
        if not isinstance(row.get("location"), str) or not row.location.strip() or len(row.location) > 140:
            frappe.throw("Each stop requires an address of at most 140 characters")
        if (row.get("purpose") is not None and not isinstance(row.get("purpose"), str)) or len(row.get("purpose") or "") > 2000:
            frappe.throw("Stop purpose must be at most 2000 characters")
        try:
            wait = float(row.get("expected_wait_minutes") or 0)
            if not math.isfinite(wait) or wait != int(wait) or not 0 <= wait <= 1440:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            frappe.throw("Expected wait must be whole minutes between 0 and 1440")
        row.expected_wait_minutes = int(wait)
    if rows and rows[-1].location.strip() != str(doc.destination or "").strip():
        frappe.throw("The last stop address must match the final destination")
    if old and old.status != "Draft" and snapshot(rows, ("name",) + ROUTE_FIELDS) != snapshot(before, ("name",) + ROUTE_FIELDS):
        frappe.throw("Submitted trip stops cannot be added, removed, reordered or edited")
    if not internal:
        if snapshot(rows, ("name",) + EVENT_FIELDS) != snapshot(before, ("name",) + EVENT_FIELDS):
            # Draft route edits may add/remove rows, but can never write milestone fields.
            if any(any(r.get(k) for k in EVENT_FIELDS) for r in rows) or any(
                    any(r.get(k) for k in EVENT_FIELDS) for r in before):
                frappe.throw("Use the arrival and departure actions")
        if any(doc.get(k) != (old.get(k) if old else None) for k in DESTINATION_FIELDS):
            frappe.throw("Use the destination arrival action")


def require_finished(doc):
    if any(not row.get("departed_at") for row in (doc.get("stops") or [])):
        frappe.throw("Record arrival and departure for every stop before ending the trip")


def next_visit(doc):
    return next((row for row in (doc.get("stops") or []) if not row.get("departed_at")), None)


@frappe.whitelist(methods=["POST"])
def mark_stop(name, stop_name, event):
    from eup_administration.services import get_locked_trip, driver_check, save_action
    doc = get_locked_trip(name)
    driver_check(doc)
    if doc.status != "In Progress" or event not in ("arrive", "depart"):
        frappe.throw("An active trip and a valid arrival or departure action are required")
    row = next_visit(doc)
    if not row or row.name != stop_name:
        frappe.throw("This stop is no longer current; refresh the trip")
    at = now_datetime()
    previous = doc.actual_start
    for visit in doc.stops:
        if visit.name == row.name:
            break
        previous = visit.departed_at
    if event == "arrive":
        if row.arrived_at:
            frappe.throw("Arrival has already been recorded")
        if at < get_datetime(previous):
            frappe.throw("Arrival cannot precede the previous milestone")
        row.arrived_at, row.arrived_by = at, frappe.session.user
        if row.name == doc.stops[-1].name:
            doc.destination_arrived_at, doc.destination_arrived_by = at, frappe.session.user
    else:
        if not row.arrived_at or row.departed_at:
            frappe.throw("Record arrival once before departure")
        if at < get_datetime(row.arrived_at):
            frappe.throw("Departure cannot precede arrival")
        row.departed_at, row.departed_by = at, frappe.session.user
    return save_action(doc)


@frappe.whitelist(methods=["POST"])
def arrive_destination(name):
    from eup_administration.services import get_locked_trip, driver_check, save_action
    doc = get_locked_trip(name)
    driver_check(doc)
    if doc.status != "In Progress" or doc.get("stops") or doc.get("destination_arrived_at"):
        frappe.throw("Destination arrival is only available once on an active single-destination trip")
    at = now_datetime()
    if at < get_datetime(doc.actual_start):
        frappe.throw("Arrival cannot precede trip start")
    doc.destination_arrived_at, doc.destination_arrived_by = at, frappe.session.user
    return save_action(doc)


def publish_progress(doc, method=None):
    """In-page notifications only, after commit; no email, outbox or worker."""
    old = doc.get_doc_before_save()
    if not old:
        return
    changed = doc.status != old.status or snapshot(doc.get("stops") or [], EVENT_FIELDS) != snapshot(old.get("stops") or [], EVENT_FIELDS)
    changed = changed or doc.get("destination_arrived_at") != old.get("destination_arrived_at")
    if not changed:
        return
    recipients = set()
    if "Administration User" in frappe.get_roles(doc.requested_by):
        recipients.add(doc.requested_by)
    if doc.driver:
        user = frappe.db.get_value("ADM Driver", {"name": doc.driver, "enabled": 1}, "user")
        if user and "Administration Driver" in frappe.get_roles(user):
            recipients.add(user)
    for user in recipients:
        if frappe.db.get_value("User", user, "enabled"):
            frappe.publish_realtime("adm_trip_progress", {"name": doc.name},
                user=user, after_commit=True)
