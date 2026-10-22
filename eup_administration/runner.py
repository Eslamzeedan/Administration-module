"""Administration errand workflows; Careem journeys stay separate from company fleet.

All state transitions use whitelisted POST actions with server-side authorization.
This module does NOT book Careem rides and does NOT post to ERPNext accounting.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation

import frappe
from frappe.utils import get_datetime, now_datetime

from eup_administration.permissions import is_admin

_transition = ContextVar('adm_runner_transition', default=False)
READ_TYPES = {'read', 'select', 'print', 'email', 'report', 'export'}
REQUESTER_ROLES = {'Administration User', 'Administration Requester'}
APPROVER_ROLE = 'Administration Department Approver'
RUNNER_ROLE = 'Administration Runner'


@contextmanager
def transition_context():
    token = _transition.set(True)
    try:
        yield
    finally:
        _transition.reset(token)


def reject(message):
    frappe.throw(message, frappe.PermissionError)


def roles(user=None):
    return set(frappe.get_roles(user or frappe.session.user))


def employee_record(user=None):
    return frappe.db.get_value('Employee', {'user_id': user or frappe.session.user, 'status': 'Active'},
                               ['department', 'company'], as_dict=True)


def approver_for(doc, user=None):
    user = user or frappe.session.user
    if is_admin(user):
        return True
    if APPROVER_ROLE not in roles(user):
        return False
    # Prevent users from approving their own requests or their own runner work.
    if user in {doc.requested_by, doc.assigned_runner}:
        return False
    emp = employee_record(user)
    return bool(emp and emp.department and emp.department == doc.department and emp.company == doc.company)


def valid_runner(user):
    if not user or RUNNER_ROLE not in roles(user):
        return False
    return frappe.db.get_value('User', user, 'enabled') == 1


def request_query(user=None):
    user = user or frappe.session.user
    if is_admin(user):
        return ''
    r = roles(user)
    conditions = ['1=0']
    if r & REQUESTER_ROLES:
        conditions.append('`tabADM Service Request`.requested_by = ' + frappe.db.escape(user))
    if RUNNER_ROLE in r:
        conditions.append('`tabADM Service Request`.assigned_runner = ' + frappe.db.escape(user))
    if APPROVER_ROLE in r:
        emp = employee_record(user)
        if emp and emp.department and emp.company:
            conditions.append('(`tabADM Service Request`.department = ' + frappe.db.escape(emp.department)
                              + ' AND `tabADM Service Request`.company = ' + frappe.db.escape(emp.company) + ')')
    return '(' + ' OR '.join(conditions) + ')'


def request_permission(doc, user=None, ptype=None, permission_type=None, **kwargs):
    user = user or frappe.session.user
    ptype = ptype or permission_type or 'read'
    if is_admin(user):
        return True
    r = roles(user)
    if doc.is_new():
        return bool(r & REQUESTER_ROLES and ptype in {'create', 'write', 'read'})
    own = bool(r & REQUESTER_ROLES and doc.requested_by == user)
    assigned = bool(RUNNER_ROLE in r and doc.assigned_runner == user)
    dept = approver_for(doc, user)
    if ptype in READ_TYPES:
        return own or assigned or dept
    if ptype == 'write':
        return own and doc.status == 'Draft'
    return False


def money(value, *, allow_zero=True):
    try:
        amount = Decimal(str(value or 0))
        if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
            raise ValueError()
        return amount.quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        frappe.throw('Fare must be a finite, non-negative currency amount')


def private_file(url, request_name=None):
    """Reject public and unrelated attachments, including guessed private File URLs."""
    if not url or not str(url).startswith('/private/files/'):
        frappe.throw('Upload a private file as the receipt/proof')
    file = frappe.db.get_value('File', {'file_url': url},
                               ['is_private', 'owner', 'attached_to_doctype', 'attached_to_name'], as_dict=True)
    if not file or not file.is_private:
        frappe.throw('File must exist and be private')
    if not is_admin() and file.owner != frappe.session.user:
        if file.attached_to_doctype != 'ADM Service Request' or file.attached_to_name != request_name:
            reject('This private attachment is not owned by you or this request')
    if file.attached_to_doctype and (file.attached_to_doctype != 'ADM Service Request'
                                    or file.attached_to_name != request_name):
        reject('Receipt belongs to another document')


def ride_signature(doc):
    return [(r.pickup, r.dropoff, r.booking_reference, str(r.fare), r.receipt, str(r.ridden_at))
            for r in doc.get('rides') or []]


def validate_request(doc):
    old = doc.get_doc_before_save()
    if not old:
        user = frappe.session.user
        if not (roles(user) & REQUESTER_ROLES or is_admin(user)):
            reject('Request access role required')
        emp = employee_record(user)
        if not emp or not emp.department or not emp.company:
            frappe.throw('Requesters must have an active Employee with Department and Company')
        doc.requested_by, doc.department, doc.company = user, emp.department, emp.company
        doc.status = 'Draft'
        doc.assigned_runner = doc.approved_by = doc.rejected_by = doc.rejection_reason = None
        doc.verified_by = doc.started_at = doc.completed_at = doc.closed_at = None
        doc.completion_proof = doc.completion_notes = None
        doc.set('rides', [])
    else:
        immutable = ('requested_by', 'department', 'company', 'status', 'assigned_runner',
                     'approved_by', 'rejected_by', 'rejection_reason', 'verified_by',
                     'started_at', 'completed_at', 'closed_at', 'completion_proof',
                     'completion_notes', 'currency', 'actual_transport_cost')
        if any(doc.get(field) != old.get(field) for field in immutable) and not _transition.get():
            frappe.throw('Use the approved workflow buttons to change protected fields')
        if ride_signature(doc) != ride_signature(old) and not _transition.get():
            frappe.throw('Add Careem rides using the assigned runner action')
        if old.status != 'Draft' and not _transition.get():
            frappe.throw('Submitted requests cannot be edited directly')
    if doc.cost_center and frappe.db.get_value('Cost Center', doc.cost_center, 'company') != doc.company:
        frappe.throw('Cost center company mismatch')
    if not doc.request_type or not doc.purpose or not doc.service_location or not doc.needed_by:
        frappe.throw('Request type, purpose, location and required time are mandatory')
    get_datetime(doc.needed_by)
    doc.currency = frappe.db.get_value('Company', doc.company, 'default_currency') or 'EGP'
    doc.estimated_transport_cost = float(money(doc.estimated_transport_cost))
    doc.actual_transport_cost = float(sum((money(ride.fare) for ride in doc.get('rides') or []), Decimal(0)))
    if doc.get('completion_proof'):
        private_file(doc.completion_proof, doc.name)
    if len(doc.get('rides') or []) > 20:
        frappe.throw('Maximum 20 Careem rides per request')
    for ride in doc.get('rides') or []:
        if not ride.pickup or not ride.dropoff or not ride.ridden_at:
            frappe.throw('Each Careem ride needs pickup, drop-off and time')
        money(ride.fare)
        private_file(ride.receipt, doc.name)
    if doc.status in {'Completed', 'Closed'} and not doc.completion_proof:
        frappe.throw('Completion proof is required before closure')


def _load(name):
    # Lock row to serialize competing approvals/assignments/close actions.
    if not frappe.db.sql('SELECT name FROM `tabADM Service Request` WHERE name=%s FOR UPDATE', (name,)):
        frappe.throw('Service request not found')
    return frappe.get_doc('ADM Service Request', name)


def _require_status(doc, *allowed):
    if doc.status not in allowed:
        frappe.throw(f'Action not allowed in status {doc.status}')


def _save(doc):
    with transition_context():
        doc.save(ignore_permissions=True)
    return {'name': doc.name, 'status': doc.status}


def _requester(doc):
    if not (is_admin() or (doc.requested_by == frappe.session.user and roles() & REQUESTER_ROLES)):
        reject('Only the requester can submit this request')


def _runner(doc):
    if not (doc.assigned_runner == frappe.session.user and valid_runner(frappe.session.user)):
        reject('Only the assigned, active runner can act on this errand')


@frappe.whitelist(methods=['POST'])
def submit_request(name):
    doc = _load(name)
    _requester(doc)
    _require_status(doc, 'Draft')
    doc.status = 'Pending Approval'
    return _save(doc)


@frappe.whitelist(methods=['POST'])
def approve_request(name):
    doc = _load(name)
    if not approver_for(doc):
        reject('Department approver or administration manager role required')
    _require_status(doc, 'Pending Approval')
    doc.approved_by = frappe.session.user
    doc.status = 'Approved'
    return _save(doc)


@frappe.whitelist(methods=['POST'])
def reject_request(name, reason):
    doc = _load(name)
    if not approver_for(doc):
        reject('Department approver role required')
    _require_status(doc, 'Pending Approval')
    if not reason or not str(reason).strip():
        frappe.throw('Rejection reason is required')
    doc.rejection_reason = str(reason).strip()
    doc.rejected_by = frappe.session.user
    doc.status = 'Rejected'
    return _save(doc)


@frappe.whitelist(methods=['POST'])
def assign_runner(name, runner):
    doc = _load(name)
    if not is_admin():
        reject('Administration Manager required for dispatch')
    _require_status(doc, 'Approved')
    if not valid_runner(runner):
        frappe.throw('Runner must have Administration Runner role and an enabled User account')
    doc.assigned_runner = runner
    doc.status = 'Assigned'
    return _save(doc)


@frappe.whitelist(methods=['POST'])
def start_errand(name):
    doc = _load(name)
    _runner(doc)
    _require_status(doc, 'Assigned')
    doc.started_at = now_datetime()
    doc.status = 'In Progress'
    return _save(doc)


@frappe.whitelist(methods=['POST'])
def add_careem_ride(name, pickup, dropoff, ridden_at, fare, receipt, booking_reference=None):
    doc = _load(name)
    _runner(doc)
    _require_status(doc, 'In Progress')
    if not str(pickup or '').strip() or not str(dropoff or '').strip():
        frappe.throw('Pickup and drop-off are required')
    if not ridden_at:
        frappe.throw('Ride time is required')
    get_datetime(ridden_at)
    fare = money(fare)
    private_file(receipt, doc.name)
    if booking_reference and any(r.booking_reference == booking_reference for r in doc.get('rides') or []):
        frappe.throw('Duplicate Careem booking reference')
    if len(doc.get('rides') or []) >= 20:
        frappe.throw('Maximum 20 Careem rides')
    doc.append('rides', dict(pickup=str(pickup).strip(), dropoff=str(dropoff).strip(),
                             ridden_at=ridden_at, fare=float(fare), receipt=receipt,
                             booking_reference=str(booking_reference or '').strip()))
    return _save(doc)


@frappe.whitelist(methods=['POST'])
def complete_errand(name, proof, notes):
    doc = _load(name)
    _runner(doc)
    _require_status(doc, 'In Progress')
    if not (doc.get('rides') or []):
        frappe.throw('Record at least one Careem ride with its private receipt')
    if not str(notes or '').strip():
        frappe.throw('Completion notes required')
    private_file(proof, doc.name)
    doc.completion_proof = proof
    doc.completion_notes = str(notes).strip()
    doc.completed_at = now_datetime()
    doc.status = 'Completed'
    return _save(doc)


@frappe.whitelist(methods=['POST'])
def close_errand(name):
    doc = _load(name)
    if not approver_for(doc):
        reject('Department approver or administration manager must verify the result')
    _require_status(doc, 'Completed')
    doc.verified_by = frappe.session.user
    doc.closed_at = now_datetime()
    doc.status = 'Closed'
    return _save(doc)


@frappe.whitelist(methods=['POST'])
def cancel_request(name):
    doc = _load(name)
    _require_status(doc, 'Draft', 'Pending Approval', 'Approved', 'Assigned')
    if not is_admin():
        _requester(doc)
        if doc.status not in {'Draft', 'Pending Approval'}:
            reject('Only Administration Manager can cancel an approved request')
    doc.status = 'Cancelled'
    return _save(doc)


@frappe.whitelist()
def capabilities(name):
    doc = frappe.get_doc('ADM Service Request', name)
    doc.check_permission('read')
    requester = is_admin() or (doc.requested_by == frappe.session.user and bool(roles() & REQUESTER_ROLES))
    approved = approver_for(doc)
    runner = doc.assigned_runner == frappe.session.user and valid_runner(frappe.session.user)
    manager = is_admin()
    return {'submit': doc.status == 'Draft' and requester,
            'approve': doc.status == 'Pending Approval' and approved,
            'assign': doc.status == 'Approved' and manager,
            'start': doc.status == 'Assigned' and runner,
            'complete': doc.status == 'In Progress' and runner,
            'add_ride': doc.status == 'In Progress' and runner,
            'reject': doc.status == 'Pending Approval' and approved,
            'cancel': doc.status in {'Draft', 'Pending Approval'} and requester or (manager and doc.status in {'Approved','Assigned'}),
            'close': doc.status == 'Completed' and approved}
