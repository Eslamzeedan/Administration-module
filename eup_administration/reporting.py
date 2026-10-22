"""All reads use get_list so role, row and company restrictions also cover reports."""
from collections import Counter, defaultdict
from datetime import timedelta
import frappe
from frappe.utils import getdate, nowdate
from eup_administration.permissions import is_admin


def bounds(filters=None):
    filters = frappe._dict(filters or {})
    start = getdate(filters.get('from_date') or (getdate(nowdate()) - timedelta(days=30)))
    end = getdate(filters.get('to_date') or nowdate())
    if end < start or (end - start).days > 366:
        frappe.throw('Choose a date range of up to 366 days')
    return filters, start, end


def rows(doctype, fields, filters):
    if not frappe.has_permission(doctype, 'read'):
        return []
    return frappe.get_list(doctype, fields=fields, filters=filters, limit_page_length=0, order_by='creation desc')


def trip_rows(filters=None):
    f, start, end = bounds(filters)
    query = {'planned_start': ['<', str(end + timedelta(days=1))], 'planned_end': ['>', str(start)]}
    if f.company:
        query['company'] = f.company
    return rows('ADM Trip', ['name', 'company', 'purpose', 'requested_by', 'vehicle', 'driver', 'status',
        'planned_start', 'planned_end', 'actual_start', 'actual_end', 'distance_km', 'duration_minutes'], query)


def cost_rows(filters=None):
    f, start, end = bounds(filters)
    out = []
    for dt in ('ADM Fuel Log', 'ADM Trip Expense', 'ADM Maintenance'):
        query = {'posting_date': ['between', [str(start), str(end)]], 'docstatus': 1} if dt != 'ADM Maintenance' else {
            'status': 'Completed', 'completed_at': ['>=', str(start)]}
        if dt == 'ADM Maintenance':
            query = [['status', '=', 'Completed'], ['completed_at', '>=', str(start)], ['completed_at', '<', str(end + timedelta(days=1))]]
            if f.company:
                query.append(['company', '=', f.company])
        elif f.company:
            query['company'] = f.company
        fields = ['name', 'vehicle', 'company', 'currency']
        fields += ['cost', 'completed_at'] if dt == 'ADM Maintenance' else ['amount', 'posting_date', 'trip']
        for row in rows(dt, fields, query):
            out.append({'record_type': dt, 'name': row.name, 'vehicle': row.vehicle, 'company': row.company,
                'currency': row.currency, 'amount': row.get('cost', row.get('amount')) or 0,
                'date': row.get('completed_at', row.get('posting_date')), 'trip': row.get('trip')})
    return out


def meeting_rows(filters=None):
    f, start, end = bounds(filters)
    query = {'starts_at': ['<', str(end + timedelta(days=1))], 'ends_at': ['>', str(start)], 'status': ['!=', 'Cancelled']}
    if f.company:
        query['company'] = f.company
    if f.room:
        query['room'] = f.room
    from frappe.utils import get_datetime
    result = []
    for row in rows('ADM Meeting Booking', ['name', 'room', 'company', 'organizer', 'title', 'starts_at', 'ends_at', 'status', 'attendee_count'], query):
        row['booked_hours'] = round((min(get_datetime(row.ends_at), get_datetime(end + timedelta(days=1))) - max(get_datetime(row.starts_at), get_datetime(start))).total_seconds()/3600, 2)
        result.append(row)
    return result


def renewal_rows(filters=None):
    f, _, end = bounds(filters)
    query = {'company': f.company} if f.company else {}
    result = []
    for row in rows('ADM Vehicle', ['name', 'company', 'last_odometer', 'license_expiry', 'insurance_expiry'], query):
        for key, label in (('license_expiry', 'Vehicle License'), ('insurance_expiry', 'Insurance')):
            if row.get(key) and getdate(row[key]) <= end:
                result.append({'vehicle': row.name, 'company': row.company, 'item': label, 'due_date': row[key], 'due_odometer': None})
    latest = {}
    query = {'status': 'Completed'}
    if f.company:
        query['company'] = f.company
    for row in rows('ADM Maintenance', ['name', 'vehicle', 'company', 'completed_at', 'next_due_date', 'next_due_odometer'], query):
        if row.vehicle not in latest or row.completed_at > latest[row.vehicle].completed_at:
            latest[row.vehicle] = row
    for row in latest.values():
        vehicle = frappe.get_doc('ADM Vehicle', row.vehicle)
        vehicle.check_permission('read')
        if (row.next_due_date and getdate(row.next_due_date) <= end) or (row.next_due_odometer and row.next_due_odometer <= vehicle.last_odometer):
            result.append({'vehicle': row.vehicle, 'company': row.company, 'item': 'Maintenance',
                'due_date': row.next_due_date, 'due_odometer': row.next_due_odometer})
    return result


@frappe.whitelist()
def dashboard(from_date=None, to_date=None, company=None):
    if not (is_admin() or set(frappe.get_roles()) & {'Administration User', 'Administration Driver'}):
        frappe.throw('Administration access required', frappe.PermissionError)
    filters = {'from_date': from_date, 'to_date': to_date, 'company': company}
    trips = trip_rows(filters)
    costs = cost_rows(filters)
    totals = defaultdict(float)
    for cost in costs:
        totals[cost['currency']] += float(cost['amount'])
    meetings = meeting_rows(filters)
    return {'trip_status': dict(Counter(row.status for row in trips)),
        'distance_km': sum(row.distance_km or 0 for row in trips if row.status == 'Completed'),
        'booked_hours': round(sum(row.booked_hours for row in meetings), 2),
        'meeting_count': len(meetings), 'costs_by_currency': dict(totals),
        'renewals_due': len(renewal_rows(filters)), 'scope': 'Records visible to your account',
        'cost_scope': 'Submitted fuel/expenses and completed maintenance; operational costs, no GL postings'}
