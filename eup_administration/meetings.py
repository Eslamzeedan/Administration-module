import frappe
from eup_administration.permissions import is_admin
from eup_administration.rules import recurrence_dates
from eup_administration.services import lock, _action, action_context, save_action, validation
from frappe.utils import get_datetime


def validate_services(doc):
    old = doc.get_doc_before_save()
    rows = {r.name: r for r in (old.get('services') or [])} if old else {}
    if not is_admin():
        current = {r.name: r for r in doc.get('services') or []}
        for name, previous in rows.items():
            if previous.status != 'Requested':
                row = current.get(name)
                if not row or any(row.get(key) != previous.get(key) for key in ('service_type', 'details', 'quantity', 'status')):
                    frappe.throw('Fulfilled or cancelled service requests cannot be changed by requesters', frappe.PermissionError)
    for row in doc.get('services') or []:
        if isinstance(row.quantity, bool) or not isinstance(row.quantity, int) or row.quantity < 1:
            frappe.throw('Service quantity must be a positive integer')
        previous = rows.get(row.name)
        if not is_admin():
            if row.status != (previous.status if previous else 'Requested'):
                frappe.throw('Only managers can change service fulfillment', frappe.PermissionError)


@frappe.whitelist(methods=['POST'])
def repeat_booking(name, frequency, count):
    lock('ADM Meeting Booking', name)
    doc = frappe.get_doc('ADM Meeting Booking', name, for_update=True)
    doc.check_permission('write')
    if doc.status != 'Confirmed' or doc.recurrence_root:
        frappe.throw('Use an ungrouped confirmed booking as the series seed')
    dates = validation(recurrence_dates, get_datetime(doc.starts_at), get_datetime(doc.ends_at), frequency, count)
    lock('ADM Meeting Room', doc.room)
    # A savepoint ensures all occurrences and the seed annotation roll back on any conflict,
    # even when an internal caller catches the exception.
    frappe.db.savepoint('adm_repeat_booking')
    try:
        created = []
        with action_context():
            doc.recurrence_root = doc.name
            doc.save()
            for start, end in dates:
                occurrence = frappe.get_doc({'doctype': 'ADM Meeting Booking', 'title': doc.title,
                    'room': doc.room, 'organizer': doc.organizer, 'starts_at': start, 'ends_at': end,
                    'attendee_count': doc.attendee_count, 'requirements': doc.requirements,
                    'meeting_link': doc.meeting_link, 'recurrence_root': doc.name,
                    'services': [{'service_type': r.service_type, 'details': r.details,
                        'quantity': r.quantity, 'status': 'Requested'} for r in doc.get('services') or []]})
                occurrence.insert()
                created.append(occurrence.name)
        return {'seed': doc.name, 'created': created}
    except Exception:
        frappe.db.rollback(save_point='adm_repeat_booking')
        raise


@frappe.whitelist(methods=['POST'])
def cancel_series(name):
    lock('ADM Meeting Booking', name)
    seed = frappe.get_doc('ADM Meeting Booking', name, for_update=True)
    seed.check_permission('write')
    root = seed.recurrence_root or seed.name
    # Current read after locking the series seed; each row is authorized again below.
    records = [row[0] for row in frappe.db.sql("SELECT name FROM `tabADM Meeting Booking` WHERE recurrence_root=%s AND status='Confirmed' ORDER BY name FOR UPDATE", (root,))]
    frappe.db.savepoint('adm_cancel_series')
    try:
        for record in records:
            lock('ADM Meeting Booking', record)
            doc = frappe.get_doc('ADM Meeting Booking', record, for_update=True)
            doc.check_permission('write')
            if doc.status != 'Confirmed':
                continue
            doc.status = 'Cancelled'
            save_action(doc)
        return records
    except Exception:
        frappe.db.rollback(save_point='adm_cancel_series')
        raise
