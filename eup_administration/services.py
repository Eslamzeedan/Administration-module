"""Transactional actions. Supports MariaDB; test on a staging site before use."""
from contextvars import ContextVar
from contextlib import contextmanager
import frappe
from frappe.utils import get_datetime, now_datetime
from eup_administration.permissions import is_admin, active_driver
from eup_administration.rules import reading, start_reading, trip_distance

_action = ContextVar('administration_action', default=False)

@contextmanager
def action_context():
    token = _action.set(True)
    try:
        yield
    finally:
        _action.reset(token)

def lock(doctype, name):
    # Only hard-coded DocTypes from application code reach this helper.
    if doctype not in ('ADM Trip', 'ADM Vehicle', 'ADM Driver', 'ADM Meeting Room', 'ADM Meeting Booking', 'ADM Maintenance'):
        frappe.throw('Invalid lock target')
    if not frappe.db.sql(f'SELECT name FROM `tab{doctype}` WHERE name=%s FOR UPDATE', (name,)):
        frappe.throw(f'{doctype} record not found')

def admin_only():
    if not is_admin():
        frappe.throw('Administration Manager role required', frappe.PermissionError)

def validation(fn, *args):
    try:
        return fn(*args)
    except ValueError as exc:
        frappe.throw(str(exc))

def period(start, end):
    if not start or not end or get_datetime(end) <= get_datetime(start):
        frappe.throw('End time must follow start time')

def validate_trip(doc):
    old = doc.get_doc_before_save()
    if not old:
        doc.requested_by = frappe.session.user
        doc.status = 'Draft'
        for key in ('start_odometer', 'end_odometer', 'distance_km', 'duration_minutes'):
            doc.set(key, 0)
        for key in ('actual_start', 'actual_end', 'approved_by', 'gap_reason', 'rejection_reason', 'rejected_by'):
            doc.set(key, None)
    else:
        if doc.requested_by != old.requested_by:
            frappe.throw('Requester cannot be changed')
        protected = ('status', 'start_odometer', 'end_odometer', 'distance_km', 'duration_minutes', 'actual_start', 'actual_end', 'approved_by', 'gap_reason', 'rejection_reason', 'rejected_by')
        if not _action.get() and any(doc.get(k) != old.get(k) for k in protected):
            frappe.throw('Use the trip action buttons to change trip state or readings')
        if not _action.get() and old.status != 'Draft':
            frappe.throw('Submitted trips are immutable; cancel and create a replacement')
    period(doc.planned_start, doc.planned_end)
    if (doc.passenger_count or 0) < 1:
        frappe.throw('Passenger count must be positive')
    if doc.cost_center and frappe.db.get_value('Cost Center', doc.cost_center, 'company') != doc.company:
        frappe.throw('Cost center belongs to another company')
    if doc.status in ('Assigned', 'In Progress'):
        if not doc.vehicle or not doc.driver:
            frappe.throw('Vehicle and driver are required')
        lock('ADM Vehicle', doc.vehicle)
        lock('ADM Driver', doc.driver)
        vehicle = frappe.get_doc('ADM Vehicle', doc.vehicle, for_update=True)
        driver = frappe.get_doc('ADM Driver', doc.driver, for_update=True)
        if vehicle.company != doc.company:
            frappe.throw('Vehicle belongs to another company')
        check_resources(doc, vehicle, driver)
        if vehicle.status != 'Available' or not driver.enabled:
            frappe.throw('Vehicle or driver is unavailable')
        conflicts = frappe.db.sql('''
            SELECT name FROM `tabADM Trip`
            WHERE name != %s AND (vehicle=%s OR driver=%s)
            AND (status='In Progress' OR
                (status='Assigned' AND planned_start < %s AND planned_end > %s))
            LIMIT 1 FOR UPDATE
        ''', (doc.name or '', doc.vehicle, doc.driver, doc.planned_end, doc.planned_start))
        if conflicts:
            frappe.throw('Vehicle or driver has a conflicting or active trip')

def validate_booking(doc):
    from eup_administration.meetings import validate_services
    validate_services(doc)
    old = doc.get_doc_before_save()
    if not old:
        doc.organizer = (doc.organizer or frappe.session.user) if _action.get() else frappe.session.user
        if not _action.get():
            doc.recurrence_root = None
        doc.status = 'Confirmed'
    else:
        if not _action.get() and doc.get('recurrence_root') != old.get('recurrence_root'):
            frappe.throw('Use the recurrence action')
        if old.organizer != doc.organizer:
            frappe.throw('Organizer cannot be changed')
        if not _action.get() and old.status != doc.status:
            frappe.throw('Use the booking action buttons')
        if not _action.get() and old.status != 'Confirmed':
            frappe.throw('Closed bookings cannot be edited')
    period(doc.starts_at, doc.ends_at)
    lock('ADM Meeting Room', doc.room)
    room = frappe.get_doc('ADM Meeting Room', doc.room, for_update=True)
    room.check_permission('read')
    doc.company = room.company
    if doc.status != 'Confirmed':
        return
    if not room.enabled:
        frappe.throw('Room is unavailable')
    if not 1 <= (doc.attendee_count or 0) <= room.capacity:
        frappe.throw('Attendee count exceeds room capacity or is invalid')
    from datetime import timedelta
    buffer = timedelta(minutes=room.buffer_minutes or 0)
    conflicts = frappe.db.sql('''
        SELECT name FROM `tabADM Meeting Booking`
        WHERE name != %s AND room=%s AND status='Confirmed'
        AND starts_at < %s AND ends_at > %s LIMIT 1 FOR UPDATE
    ''', (doc.name or '', doc.room, get_datetime(doc.ends_at) + buffer, get_datetime(doc.starts_at) - buffer))
    if conflicts:
        frappe.throw('Room is already booked, including preparation time')

def get_locked_trip(name):
    lock('ADM Trip', name)
    doc = frappe.get_doc('ADM Trip', name, for_update=True)
    doc.check_permission('read')
    return doc

def save_action(doc):
    with action_context():
        doc.save(ignore_permissions=True)
    return doc.as_dict()

@frappe.whitelist(methods=['POST'])
def request_trip(name):
    doc = get_locked_trip(name)
    if doc.requested_by != frappe.session.user and not is_admin():
        frappe.throw('Only requester can submit this trip', frappe.PermissionError)
    if doc.status != 'Draft':
        frappe.throw('Only draft trips can be requested')
    doc.status = 'Requested'
    return save_action(doc)

@frappe.whitelist(methods=['POST'])
def assign_trip(name, vehicle, driver):
    admin_only()
    doc = get_locked_trip(name)
    if doc.status != 'Requested':
        frappe.throw('Only requested trips can be assigned')
    doc.vehicle, doc.driver = vehicle, driver
    doc.status, doc.approved_by = 'Assigned', frappe.session.user
    return save_action(doc)

def driver_check(doc):
    if not is_admin() and (not doc.driver or doc.driver != active_driver()):
        frappe.throw('Only the assigned driver can operate this trip', frappe.PermissionError)

@frappe.whitelist(methods=['POST'])
def start_trip(name, odometer=None, gap_reason=None):
    doc = get_locked_trip(name)
    driver_check(doc)
    if doc.status != 'Assigned':
        frappe.throw('Trip must be assigned before starting')
    lock('ADM Vehicle', doc.vehicle)
    lock('ADM Driver', doc.driver)
    current = validation(start_reading, odometer, frappe.db.get_value('ADM Vehicle', doc.vehicle, 'last_odometer', for_update=True), gap_reason)
    doc.start_odometer, doc.gap_reason = current, gap_reason
    doc.actual_start, doc.status = now_datetime(), 'In Progress'
    result = save_action(doc)
    frappe.db.set_value('ADM Vehicle', doc.vehicle, 'last_odometer', current)
    return result

@frappe.whitelist(methods=['POST'])
def end_trip(name, odometer=None):
    doc = get_locked_trip(name)
    driver_check(doc)
    if doc.status != 'In Progress':
        frappe.throw('Only an active trip can be completed')
    lock('ADM Vehicle', doc.vehicle)
    lock('ADM Driver', doc.driver)
    current = validation(reading, odometer)
    if current < frappe.db.get_value('ADM Vehicle', doc.vehicle, 'last_odometer', for_update=True):
        frappe.throw('End reading cannot reduce the latest vehicle reading')
    doc.distance_km = validation(trip_distance, doc.start_odometer, current)
    doc.end_odometer, doc.actual_end, doc.status = current, now_datetime(), 'Completed'
    doc.duration_minutes = (doc.actual_end - get_datetime(doc.actual_start)).total_seconds() / 60
    result = save_action(doc)
    frappe.db.set_value('ADM Vehicle', doc.vehicle, 'last_odometer', current)
    return result

@frappe.whitelist(methods=['POST'])
def cancel_trip(name):
    doc = get_locked_trip(name)
    if not is_admin() and doc.requested_by != frappe.session.user:
        frappe.throw('Only requester or manager can cancel', frappe.PermissionError)
    if doc.status not in ('Draft', 'Requested', 'Assigned'):
        frappe.throw('Active or completed trips cannot be cancelled')
    doc.status = 'Cancelled'
    return save_action(doc)

@frappe.whitelist(methods=['POST'])
def close_booking(name, status):
    lock('ADM Meeting Booking', name)
    doc = frappe.get_doc('ADM Meeting Booking', name, for_update=True)
    doc.check_permission('write')
    if doc.status != 'Confirmed' or status not in ('Completed', 'Cancelled'):
        frappe.throw('Invalid booking transition')
    if status == 'Completed' and get_datetime(doc.ends_at) > now_datetime():
        frappe.throw('Booking cannot be completed before scheduled end')
    doc.status = status
    return save_action(doc)

@frappe.whitelist()
def room_availability(room, starts_at, ends_at):
    frappe.has_permission('ADM Meeting Room', 'read', throw=True)
    period(starts_at, ends_at)
    room_doc = frappe.get_doc('ADM Meeting Room', room)
    room_doc.check_permission('read')
    from datetime import timedelta
    buffer = timedelta(minutes=room_doc.buffer_minutes or 0)
    starts_at = get_datetime(starts_at) - buffer
    ends_at = get_datetime(ends_at) + buffer
    # Occupancy only; never expose another organizer's meeting title or guests.
    return frappe.get_all('ADM Meeting Booking', filters={
        'room': room, 'status': 'Confirmed', 'starts_at': ['<', ends_at], 'ends_at': ['>', starts_at]
    }, fields=['starts_at', 'ends_at'])


def check_resources(doc, vehicle, driver):
    from frappe.utils import getdate
    vehicle.check_permission('read')
    driver.check_permission('read')
    at = max(getdate(doc.planned_start), getdate(now_datetime()))
    for expiry in (vehicle.license_expiry, vehicle.insurance_expiry, driver.license_expiry):
        if expiry and getdate(expiry) < at:
            frappe.throw('Vehicle or driver document has expired')
    if not frappe.db.get_value('User', driver.user, 'enabled'):
        frappe.throw('Driver login is disabled')
    if 'Administration Driver' not in frappe.get_roles(driver.user):
        frappe.throw('Assigned driver must have the Administration Driver role')
    if vehicle.get('seat_capacity') and doc.passenger_count > vehicle.seat_capacity:
        frappe.throw('Vehicle passenger capacity exceeded')
    if frappe.db.sql('''SELECT name FROM `tabADM Maintenance`
        WHERE vehicle=%s AND (status='In Progress' OR
        (status='Scheduled' AND starts_at < %s AND ends_at > %s)) LIMIT 1 FOR UPDATE''',
        (doc.vehicle, doc.planned_end, doc.planned_start)):
        frappe.throw('Vehicle has scheduled or active maintenance')


@frappe.whitelist(methods=['POST'])
def reject_trip(name, reason):
    admin_only()
    doc = get_locked_trip(name)
    if doc.status != 'Requested' or not str(reason or '').strip():
        frappe.throw('A requested trip and rejection reason are required')
    doc.status = 'Rejected'
    doc.rejection_reason = str(reason).strip()
    doc.rejected_by = frappe.session.user
    return save_action(doc)


@frappe.whitelist()
def trip_capabilities(name):
    doc = frappe.get_doc('ADM Trip', name)
    doc.check_permission('read')
    return {'manager': is_admin(), 'operate': bool(is_admin() or (doc.driver and doc.driver == active_driver())),
            'requester': doc.requested_by == frappe.session.user}
