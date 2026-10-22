"""Operational consumable requests and stock quantities (not ERPNext Stock/GL).

Rows in ADM Consumable Transaction are append-only. Every movement is created
through an authenticated POST action, and an item row lock serializes balance
reads and writes, including stock counts, across concurrent requests.
"""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation

import frappe
from frappe.utils import now_datetime, getdate

from eup_administration.permissions import is_admin

_action = ContextVar('eup_adm_supply_action', default=False)
READ = {'read', 'select', 'print', 'email', 'report', 'export'}
REQUESTERS = {'Administration Requester', 'Administration User'}
APPROVER = 'Administration Department Approver'
STOREKEEPER = 'Administration Storekeeper'
MOVEMENTS = {'Receipt': 1, 'Issue': -1, 'Adjustment In': 1, 'Adjustment Out': -1}
MAX_LINES = 60
MAX_QTY = Decimal('1000000000')


@contextmanager
def internal_action():
    token = _action.set(True)
    try:
        yield
    finally:
        _action.reset(token)


def roles(user=None):
    return set(frappe.get_roles(user or frappe.session.user))


def deny(reason='Not authorized'):
    frappe.throw(reason, frappe.PermissionError)


def can_store(user=None):
    return is_admin(user) or STOREKEEPER in roles(user)


def require_store_manager():
    if not is_admin():
        deny('Administration Manager role required')


def require_store():
    if not can_store():
        deny('Administration Storekeeper role required')


def employee_for(user=None):
    return frappe.db.get_value('Employee', {'user_id': user or frappe.session.user, 'status': 'Active'},
                               ['department', 'company'], as_dict=True)


def department_approver(doc, user=None):
    user = user or frappe.session.user
    if user in {doc.requested_by, getattr(doc, 'approved_by', None)}:
        # Already approving is not a reason to prevent reading, but self-approval is.
        if user == doc.requested_by:
            return False
    if is_admin(user):
        return user != doc.requested_by
    if APPROVER not in roles(user):
        return False
    emp = employee_for(user)
    return bool(emp and emp.company == doc.company and emp.department == doc.department)


def supply_request_query(user=None):
    user = user or frappe.session.user
    if is_admin(user):
        return ''
    conditions = ['1=0']
    if roles(user) & REQUESTERS:
        conditions.append('`tabADM Supply Request`.requested_by = ' + frappe.db.escape(user))
    if APPROVER in roles(user):
        emp = employee_for(user)
        if emp and emp.company and emp.department:
            conditions.append('(`tabADM Supply Request`.company = ' + frappe.db.escape(emp.company)
                              + ' AND `tabADM Supply Request`.department = ' + frappe.db.escape(emp.department) + ')')
    if STOREKEEPER in roles(user):
        emp = employee_for(user)
        if emp and emp.company:
            conditions.append('(`tabADM Supply Request`.company = ' + frappe.db.escape(emp.company)
                              + " AND `tabADM Supply Request`.status IN ('Approved','Partially Issued','Fulfilled'))")
    return '(' + ' OR '.join(conditions) + ')'


def supply_request_permission(doc, user=None, ptype=None, permission_type=None, **kwargs):
    user = user or frappe.session.user
    ptype = ptype or permission_type or 'read'
    if is_admin(user):
        return True
    r = roles(user)
    if doc.is_new():
        return bool(r & REQUESTERS and ptype in {'create', 'write', 'read'})
    own = bool(r & REQUESTERS and doc.requested_by == user)
    approver = APPROVER in r and department_approver(doc, user)
    emp = employee_for(user) if STOREKEEPER in r else None
    store = bool(emp and emp.company == doc.company and doc.status in {'Approved', 'Partially Issued', 'Fulfilled'})
    if ptype in READ:
        return own or approver or store
    return bool(ptype == 'write' and own and doc.status == 'Draft')


def transaction_query(user=None):
    user = user or frappe.session.user
    if is_admin(user):
        return ''
    if STOREKEEPER in roles(user):
        emp = employee_for(user)
        if emp and emp.company:
            return '`tabADM Consumable Transaction`.company = ' + frappe.db.escape(emp.company)
    return '1=0'


def transaction_permission(doc, user=None, ptype=None, permission_type=None, **kwargs):
    user = user or frappe.session.user
    if (ptype or permission_type or 'read') not in READ:
        return False
    if is_admin(user):
        return True
    emp = employee_for(user) if STOREKEEPER in roles(user) else None
    return bool(emp and emp.company == doc.company)


def custody_query(user=None):
    user = user or frappe.session.user
    if is_admin(user):
        return ''
    if STOREKEEPER in roles(user):
        emp = employee_for(user)
        if emp and emp.company:
            return '`tabADM Admin Custody`.company = ' + frappe.db.escape(emp.company)
    return '1=0'


def custody_permission(doc, user=None, ptype=None, permission_type=None, **kwargs):
    user = user or frappe.session.user
    if is_admin(user):
        return True
    emp = employee_for(user) if STOREKEEPER in roles(user) else None
    if not emp or emp.company != doc.company:
        return False
    ptype = ptype or permission_type or 'read'
    return ptype in READ | {'create', 'write'} and (ptype != 'write' or doc.status == 'Issued')


def quantity(value, *, allow_zero=False):
    """Strict, finite three-decimal quantity; boolean, NaN and huge values rejected."""
    try:
        if isinstance(value, bool) or value is None or str(value).strip() == '':
            raise ValueError()
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or (n == 0 and not allow_zero) or n > MAX_QTY:
            raise ValueError()
        if n != n.quantize(Decimal('0.001')):
            raise ValueError()
        return n
    except (TypeError, ValueError, InvalidOperation, OverflowError):
        frappe.throw('Quantity must be finite, positive, at most 3 decimal places and within limits')


def validate_item(doc):
    if not doc.item_code or not str(doc.item_code).strip() or not doc.company or not doc.uom:
        frappe.throw('Item code, company and unit are mandatory')
    doc.minimum_balance = float(quantity(doc.minimum_balance or 0, allow_zero=True))
    old = doc.get_doc_before_save()
    if old and (doc.item_code != old.item_code or doc.company != old.company or doc.uom != old.uom):
        frappe.throw('Item identity/company/UOM cannot change once created')


def validate_location(doc):
    if not doc.company or not doc.location_name:
        frappe.throw('Location company and name required')
    old = doc.get_doc_before_save()
    if old and doc.company != old.company:
        frappe.throw('Location company cannot change')


def line_fingerprint(doc):
    return [(v.name, v.item, str(v.requested_qty), str(v.approved_qty or 0),
             str(v.issued_qty or 0), v.notes) for v in doc.get('items') or []]


def validate_supply_request(doc):
    old = doc.get_doc_before_save()
    if not old:
        if not (roles() & REQUESTERS or is_admin()):
            deny('Requester role required')
        emp = employee_for()
        if not emp or not emp.company or not emp.department:
            frappe.throw('Active Employee with Department/Company is required')
        doc.requested_by, doc.department, doc.company = frappe.session.user, emp.department, emp.company
        doc.status = 'Draft'
        doc.approved_by = doc.closed_at = doc.rejection_reason = None
        for row in doc.get('items') or []:
            row.approved_qty = row.issued_qty = 0
    else:
        fixed = ('requested_by', 'department', 'company', 'status', 'approved_by', 'rejection_reason', 'closed_at')
        if any(doc.get(f) != old.get(f) for f in fixed) and not _action.get():
            frappe.throw('Use workflow actions for protected supply request fields')
        if old.status != 'Draft' and not _action.get():
            frappe.throw('Submitted supply request cannot be edited directly')
        if line_fingerprint(doc) != line_fingerprint(old) and old.status != 'Draft' and not _action.get():
            frappe.throw('Issued/approved lines are immutable outside workflow')
        if not _action.get():
            old_rows = {row.name: row for row in old.get('items') or []}
            for row in doc.get('items') or []:
                previous = old_rows.get(row.name)
                if row.approved_qty or row.issued_qty or (previous and (previous.approved_qty or previous.issued_qty)):
                    frappe.throw('Approval and issue quantities can only change via workflow')
    if not doc.purpose or not doc.needed_by:
        frappe.throw('Purpose and needed-by date required')
    getdate(doc.needed_by)
    if doc.cost_center and frappe.db.get_value('Cost Center', doc.cost_center, 'company') != doc.company:
        frappe.throw('Cost center company mismatch')
    lines = doc.get('items') or []
    if not lines or len(lines) > MAX_LINES:
        frappe.throw('Supply request needs 1 to 60 lines')
    seen = set()
    for row in lines:
        if not row.item or row.item in seen:
            frappe.throw('Every line needs a unique consumable item')
        seen.add(row.item)
        item = frappe.db.get_value('ADM Consumable Item', row.item, ['company', 'enabled'], as_dict=True)
        if not item or item.company != doc.company or not item.enabled:
            frappe.throw('Supply item must be active and belong to request company')
        requested = quantity(row.requested_qty)
        approved = quantity(row.approved_qty or 0, allow_zero=True)
        issued = quantity(row.issued_qty or 0, allow_zero=True)
        if not 0 <= issued <= approved <= requested:
            frappe.throw('Issued quantity cannot exceed approved, or approved exceed requested')


def validate_transaction(doc):
    if not _action.get() or not doc.is_new():
        deny('Consumable ledger is append-only; use authenticated posting actions')
    if doc.movement_type not in MOVEMENTS:
        frappe.throw('Invalid stock movement')
    n = quantity(doc.quantity)
    if Decimal(str(doc.signed_quantity)) != n * MOVEMENTS[doc.movement_type]:
        frappe.throw('Signed quantity does not match movement')
    if Decimal(str(doc.balance_after)) != Decimal(str(doc.balance_before)) + Decimal(str(doc.signed_quantity)):
        frappe.throw('Ledger balances do not reconcile')
    if Decimal(str(doc.balance_after)) < 0:
        frappe.throw('Negative stock is not permitted')
    item = frappe.db.get_value('ADM Consumable Item', doc.item, 'company')
    location = frappe.db.get_value('ADM Consumable Location', doc.location, 'company')
    if item != doc.company or location != doc.company:
        frappe.throw('Item/location company mismatch')


def prevent_transaction_deletion(doc):
    deny('Posted administrative stock movements cannot be deleted')


def _lock(doctype, name):
    if doctype not in {'ADM Supply Request', 'ADM Consumable Item', 'ADM Consumable Location', 'ADM Admin Custody'}:
        frappe.throw('Invalid lock target')
    rows = frappe.db.sql(f'SELECT name FROM `tab{doctype}` WHERE name=%s FOR UPDATE', (name,))
    if not rows:
        frappe.throw('Record not found')


def _fetch_stock(item, location):
    rows = frappe.db.sql('''SELECT COALESCE(SUM(signed_quantity),0) FROM `tabADM Consumable Transaction`
                            WHERE item=%s AND location=%s''', (item, location))
    return Decimal(str(rows[0][0] or 0))


def _validate_pair(item_name, location_name, company=None):
    item = frappe.get_doc('ADM Consumable Item', item_name)
    location = frappe.get_doc('ADM Consumable Location', location_name)
    if not item.enabled or not location.enabled or item.company != location.company:
        frappe.throw('Active stock item and location in same company required')
    if company and item.company != company:
        frappe.throw('Stock location/item belongs to a different company')
    if not is_admin():
        emp = employee_for()
        if not emp or emp.company != item.company:
            deny('Storekeeper company mismatch')
    return item.company


def _post_movement(*, item, location, kind, qty, request=None, request_line=None, reference=None, remarks=None):
    # Caller MUST hold an item-level FOR UPDATE lock before balance calculation.
    amount = quantity(qty)
    if kind not in MOVEMENTS:
        frappe.throw('Invalid movement type')
    before = _fetch_stock(item, location)
    signed = amount * MOVEMENTS[kind]
    after = before + signed
    if after < 0:
        frappe.throw('Insufficient administrative stock')
    company = _validate_pair(item, location)
    record = {'doctype': 'ADM Consumable Transaction', 'company': company,
              'item': item, 'location': location, 'movement_type': kind,
              'quantity': float(amount), 'signed_quantity': float(signed),
              'balance_before': float(before), 'balance_after': float(after),
              'posting_time': now_datetime(), 'performed_by': frappe.session.user,
              'request': request, 'request_line': request_line, 'reference': reference,
              'remarks': remarks}
    with internal_action():
        movement = frappe.get_doc(record).insert(ignore_permissions=True)
    return {'movement': movement.name, 'balance': float(after)}


@frappe.whitelist(methods=['POST'])
def submit_supply_request(name):
    _lock('ADM Supply Request', name)
    doc = frappe.get_doc('ADM Supply Request', name)
    if doc.status != 'Draft' or not (is_admin() or (doc.requested_by == frappe.session.user and roles() & REQUESTERS)):
        deny('Only requester can submit their draft')
    doc.status = 'Pending Approval'
    with internal_action(): doc.save(ignore_permissions=True)
    return {'name': doc.name, 'status': doc.status}


@frappe.whitelist(methods=['POST'])
def approve_supply_request(name, approved_quantities=None):
    _lock('ADM Supply Request', name)
    doc = frappe.get_doc('ADM Supply Request', name)
    if doc.status != 'Pending Approval' or not department_approver(doc):
        deny('A different department approver must approve this request')
    if approved_quantities is None:
        approved_quantities = {}
    if isinstance(approved_quantities, str):
        try: approved_quantities = json.loads(approved_quantities)
        except (ValueError, TypeError): frappe.throw('Invalid approval quantities JSON')
    if not isinstance(approved_quantities, dict): frappe.throw('Approval quantities must be a mapping')
    valid_keys = {r.name for r in doc.get('items') or []}
    if any(key not in valid_keys for key in approved_quantities):
        frappe.throw('Unknown supply request line')
    for row in doc.get('items') or []:
        # Default quantity is the requested amount; approvers may choose zero or reduce it.
        row.approved_qty = float(quantity(approved_quantities.get(row.name, row.requested_qty), allow_zero=True))
    if all(quantity(row.approved_qty, allow_zero=True) == 0 for row in doc.get('items') or []):
        frappe.throw('At least one approved quantity required; use rejection to deny all')
    doc.approved_by = frappe.session.user
    doc.status = 'Approved'
    with internal_action(): doc.save(ignore_permissions=True)
    return {'name': doc.name, 'status': doc.status}


@frappe.whitelist(methods=['POST'])
def reject_supply_request(name, reason):
    _lock('ADM Supply Request', name)
    doc = frappe.get_doc('ADM Supply Request', name)
    if doc.status != 'Pending Approval' or not department_approver(doc):
        deny('Department approver required')
    if not str(reason or '').strip():
        frappe.throw('Rejection reason required')
    doc.status = 'Rejected'; doc.rejection_reason = str(reason).strip()[:500]
    doc.closed_at = now_datetime()
    with internal_action(): doc.save(ignore_permissions=True)
    return {'name': doc.name, 'status': doc.status}


@frappe.whitelist(methods=['POST'])
def cancel_supply_request(name):
    _lock('ADM Supply Request', name)
    doc = frappe.get_doc('ADM Supply Request', name)
    if doc.status not in {'Draft', 'Pending Approval', 'Approved'}:
        frappe.throw('Cannot cancel after any supplies have been issued')
    if not (is_admin() or doc.requested_by == frappe.session.user and roles() & REQUESTERS):
        deny('Only requester/manager may cancel')
    doc.status = 'Cancelled';doc.closed_at = now_datetime()
    with internal_action():doc.save(ignore_permissions=True)
    return {'name': doc.name, 'status': doc.status}


@frappe.whitelist(methods=['POST'])
def receive_consumables(item, location, qty, reference, remarks=None):
    require_store()
    if not str(reference or '').strip():
        frappe.throw('Supplier/receipt reference required')
    # Serialize all locations of the item to prevent competing postings.
    _lock('ADM Consumable Item', item)
    _lock('ADM Consumable Location', location)
    _validate_pair(item, location)
    return _post_movement(item=item, location=location, kind='Receipt', qty=qty,
                          reference=str(reference)[:140], remarks=remarks)


@frappe.whitelist(methods=['POST'])
def issue_consumables(request_name, line_name, location, qty):
    require_store()
    _lock('ADM Supply Request', request_name)
    doc = frappe.get_doc('ADM Supply Request', request_name)
    if doc.status not in {'Approved', 'Partially Issued'}:
        frappe.throw('Approved request required before issuing supplies')
    row = next((line for line in doc.get('items') or [] if line.name == line_name), None)
    if row is None:
        frappe.throw('Supply line does not belong to request')
    amount = quantity(qty)
    outstanding = quantity(row.approved_qty or 0, allow_zero=True) - quantity(row.issued_qty or 0, allow_zero=True)
    if outstanding < amount:
        frappe.throw('Cannot issue more than approved and unissued quantity')
    _lock('ADM Consumable Item', row.item)
    _lock('ADM Consumable Location', location)
    _validate_pair(row.item, location, doc.company)
    result = _post_movement(item=row.item, location=location, kind='Issue', qty=amount,
                            request=doc.name, request_line=line_name, reference=doc.name,
                            remarks=f'Issued to {doc.department}')
    row.issued_qty = float(quantity(row.issued_qty or 0, allow_zero=True) + amount)
    # Fulfilled when ALL approved quantities (including zero-approved lines) are satisfied.
    done = all(quantity(r.issued_qty or 0, allow_zero=True) == quantity(r.approved_qty or 0, allow_zero=True)
               for r in doc.get('items') or [])
    doc.status = 'Fulfilled' if done else 'Partially Issued'
    if done: doc.closed_at = now_datetime()
    with internal_action():doc.save(ignore_permissions=True)
    result.update({'request': doc.name, 'status': doc.status})
    return result


@frappe.whitelist(methods=['POST'])
def reconcile_consumables(item, location, counted_qty, reason):
    require_store_manager()
    if not str(reason or '').strip():
        frappe.throw('Written stock count reason required')
    _lock('ADM Consumable Item', item)
    _lock('ADM Consumable Location', location)
    _validate_pair(item, location)
    counted = quantity(counted_qty, allow_zero=True)
    current = _fetch_stock(item, location)
    delta = counted - current
    if delta == 0:
        return {'changed': False, 'balance': float(current)}
    movement = _post_movement(item=item, location=location,
                              kind='Adjustment In' if delta > 0 else 'Adjustment Out',
                              qty=abs(delta), reference='Physical stock count',
                              remarks=f'{str(reason)[:300]} | counted={counted} before={current}')
    movement['changed'] = True
    return movement


@frappe.whitelist()
def get_consumable_balance(item, location):
    if not (can_store() or is_admin()):
        deny('Store role required')
    _validate_pair(item, location)
    # Read-only balance display; postings perform their own locked re-read.
    return {'item': item, 'location': location, 'balance': float(_fetch_stock(item, location))}


def validate_custody(doc):
    old = doc.get_doc_before_save()
    if not old:
        if not can_store(): deny('Storekeeper role required')
        doc.status = 'Issued'; doc.returned_on = doc.condition_in = None
    else:
        fixed = ('company','assigned_to','issued_on','custody_title','status','returned_on','condition_in')
        if any(doc.get(f) != old.get(f) for f in fixed) and not _action.get():
            frappe.throw('Custody identity and return state must use authorized action')
        if old.status != 'Issued' and not _action.get():
            frappe.throw('Returned custody is immutable')
    if not doc.assigned_to or not doc.company or not doc.issued_on:
        frappe.throw('Employee, company and issue date required')
    employee_company = frappe.db.get_value('Employee', doc.assigned_to, 'company')
    if employee_company != doc.company:
        frappe.throw('Custody employee belongs to another company')
    if not is_admin():
        emp = employee_for()
        if not emp or emp.company != doc.company:
            deny('Custody company mismatch')
    if doc.return_due and getdate(doc.return_due) < getdate(doc.issued_on):
        frappe.throw('Return due date cannot precede issue date')


@frappe.whitelist(methods=['POST'])
def return_custody(name, condition_in):
    require_store()
    _lock('ADM Admin Custody', name)
    doc = frappe.get_doc('ADM Admin Custody', name)
    if doc.status != 'Issued': frappe.throw('Custody is already returned')
    if not str(condition_in or '').strip(): frappe.throw('Return condition required')
    doc.status = 'Returned'; doc.returned_on = getdate(now_datetime()); doc.condition_in = str(condition_in).strip()
    with internal_action(): doc.save(ignore_permissions=True)
    return {'name': doc.name, 'status': doc.status}


def _report_company(company=None):
    """Managers can choose companies; storekeepers are restricted to their own."""
    if is_admin():
        if not company:
            frappe.throw('Select company for this report')
        return company
    if STOREKEEPER not in roles():
        deny('Stock reporting role required')
    emp = employee_for()
    if not emp or not emp.company or (company and company != emp.company):
        deny('Reporting company mismatch')
    return emp.company


@frappe.whitelist()
def consumable_low_stock(company=None):
    company = _report_company(company)
    return frappe.db.sql('''
        SELECT i.name AS item, i.item_name, i.uom, l.name AS location,
               i.minimum_balance, COALESCE(SUM(t.signed_quantity), 0) AS balance
        FROM `tabADM Consumable Item` i
        JOIN `tabADM Consumable Location` l ON l.company = i.company AND l.enabled = 1
        LEFT JOIN `tabADM Consumable Transaction` t
          ON t.item = i.name AND t.location = l.name
        WHERE i.company = %s AND i.enabled = 1
        GROUP BY i.name, i.item_name, i.uom, l.name, i.minimum_balance
        HAVING COALESCE(SUM(t.signed_quantity), 0) <= i.minimum_balance
        ORDER BY i.item_name, l.location_name
    ''', (company,), as_dict=True)


@frappe.whitelist()
def department_consumption(start_date, end_date, company=None):
    company = _report_company(company)
    start, end = getdate(start_date), getdate(end_date)
    if start > end or (end - start).days > 366:
        frappe.throw('Choose a valid report period of at most one year')
    return frappe.db.sql('''
        SELECT r.department, t.item, i.item_name, i.uom,
               SUM(t.quantity) AS quantity_issued
        FROM `tabADM Consumable Transaction` t
        JOIN `tabADM Supply Request` r ON r.name = t.request
        JOIN `tabADM Consumable Item` i ON i.name = t.item
        WHERE t.movement_type = 'Issue' AND t.company = %s
          AND DATE(t.posting_time) BETWEEN %s AND %s
        GROUP BY r.department, t.item, i.item_name, i.uom
        ORDER BY r.department, i.item_name
    ''', (company, start, end), as_dict=True)
