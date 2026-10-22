"""Operational costs only: these records do not create ERPNext GL entries."""
import frappe
from frappe.utils import getdate, now_datetime
from eup_administration.permissions import is_admin, active_driver
from eup_administration.rules import reading, money
from eup_administration.services import lock, period, validation, admin_only, save_action, _action


def validate_ledger(doc, kind):
    vehicle = frappe.get_doc('ADM Vehicle', doc.vehicle, for_update=True)
    vehicle.check_permission('read')
    doc.company = vehicle.company
    doc.currency = frappe.db.get_value('Company', vehicle.company, 'default_currency')
    if not doc.currency:
        frappe.throw('Company currency is required')
    if getdate(doc.posting_date) > getdate(now_datetime()):
        frappe.throw('Costs cannot be dated in the future')
    old = doc.get_doc_before_save()
    if old and (old.owner != doc.owner or old.vehicle != doc.vehicle or old.trip != doc.trip):
        frappe.throw('Owner, vehicle and trip cannot be changed; create a replacement')
    if doc.trip:
        trip = frappe.get_doc('ADM Trip', doc.trip)
        trip.check_permission('read')
        if trip.vehicle != doc.vehicle or trip.company != doc.company:
            frappe.throw('Trip and vehicle must match')
        if trip.status not in ('In Progress', 'Completed'):
            frappe.throw('Costs require a started or completed trip')
    if not is_admin():
        if not doc.trip:
            frappe.throw('A trip is required for non-managers', frappe.PermissionError)
        driver = active_driver()
        own_request = 'Administration User' in frappe.get_roles() and trip.requested_by == frappe.session.user
        if not (own_request or (driver and trip.driver == driver)):
            frappe.throw('Only trip requester or assigned driver may record costs', frappe.PermissionError)
        if doc.docstatus != 0:
            frappe.throw('Manager approval is required', frappe.PermissionError)
    if kind == 'fuel':
        doc.odometer = validation(reading, doc.odometer)
        doc.liters = validation(money, doc.liters)
        doc.price_per_liter = validation(money, doc.price_per_liter)
        doc.amount = validation(money, doc.liters * doc.price_per_liter)
        if doc.trip and not trip.start_odometer <= doc.odometer <= (trip.end_odometer if trip.status == 'Completed' else float('inf')):
            frappe.throw('Fuel reading must be within the trip readings')
        # Historical fuel readings never update the vehicle odometer.
    else:
        doc.amount = validation(money, doc.amount)
    if doc.receipt:
        receipt = frappe.db.get_value('File', {'file_url': doc.receipt}, ['name', 'is_private'], as_dict=True)
        if not receipt or not receipt.is_private:
            frappe.throw('Receipts must be uploaded as private files')
        frappe.get_doc('File', receipt.name).check_permission('read')


def validate_maintenance(doc):
    admin_only()
    period(doc.starts_at, doc.ends_at)
    lock('ADM Vehicle', doc.vehicle)
    vehicle = frappe.get_doc('ADM Vehicle', doc.vehicle, for_update=True)
    vehicle.check_permission('read')
    doc.company = vehicle.company
    doc.currency = frappe.db.get_value('Company', vehicle.company, 'default_currency')
    doc.cost = validation(money, doc.cost or 0, False)
    old = doc.get_doc_before_save()
    if not old:
        doc.status, doc.completed_at = 'Scheduled', None
    elif not _action.get():
        if doc.status != old.status or doc.completed_at != old.completed_at:
            frappe.throw('Use maintenance action buttons')
        if old.status != 'Scheduled':
            frappe.throw('Started or closed maintenance cannot be edited')
    if old and old.vehicle != doc.vehicle:
        frappe.throw('Maintenance vehicle cannot be changed')
    if doc.status in ('Scheduled', 'In Progress'):
        if frappe.db.sql('''SELECT name FROM `tabADM Trip` WHERE vehicle=%s
            AND (status='In Progress' OR (status='Assigned' AND planned_start < %s AND planned_end > %s)) LIMIT 1 FOR UPDATE''',
            (doc.vehicle, doc.ends_at, doc.starts_at)):
            frappe.throw('Vehicle has an assigned or active trip')
        if frappe.db.sql('''SELECT name FROM `tabADM Maintenance` WHERE vehicle=%s AND name != %s
            AND (status='In Progress' OR (status='Scheduled' AND starts_at < %s AND ends_at > %s)) LIMIT 1 FOR UPDATE''',
            (doc.vehicle, doc.name or '', doc.ends_at, doc.starts_at)):
            frappe.throw('Vehicle has conflicting maintenance')
    if doc.status == 'Completed':
        doc.odometer = validation(reading, doc.odometer)
        if doc.odometer < vehicle.last_odometer:
            frappe.throw('Maintenance reading cannot be below the latest vehicle reading')
        if doc.next_due_odometer and doc.next_due_odometer <= doc.odometer:
            frappe.throw('Next service reading must exceed completion reading')
        if doc.next_due_date and getdate(doc.next_due_date) <= getdate(doc.completed_at):
            frappe.throw('Next service date must follow completion')


@frappe.whitelist(methods=['POST'])
def maintenance_action(name, status, odometer=None, cost=None, next_due_date=None, next_due_odometer=None):
    admin_only()
    lock('ADM Maintenance', name)
    doc = frappe.get_doc('ADM Maintenance', name, for_update=True)
    doc.check_permission('write')
    transitions = {'Scheduled': {'In Progress', 'Cancelled'}, 'In Progress': {'Completed'}}
    if status not in transitions.get(doc.status, set()):
        frappe.throw('Invalid maintenance transition')
    doc.status = status
    if status == 'Completed':
        doc.odometer = validation(reading, odometer)
        doc.cost = validation(money, cost, False)
        doc.completed_at = now_datetime()
        doc.next_due_date = next_due_date
        doc.next_due_odometer = validation(reading, next_due_odometer) if next_due_odometer not in (None, '') else None
    result = save_action(doc)
    if status == 'Completed':
        frappe.db.set_value('ADM Vehicle', doc.vehicle, 'last_odometer', doc.odometer)
    return result
