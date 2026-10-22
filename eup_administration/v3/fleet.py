"""Permission-filtered fleet availability and operational KPIs."""
import frappe
from frappe.utils import get_datetime, getdate
from eup_administration.v3.security import is_manager, roles, active_employee


@frappe.whitelist()
def availability(start, end, company=None):
    if not (is_manager() or roles() & {"Administration User", "Administration Coordinator"}):
        frappe.throw("Fleet access required", frappe.PermissionError)
    start, end = get_datetime(start), get_datetime(end)
    if end <= start or (end - start).days > 31:
        frappe.throw("Choose a valid date range of at most 31 days")
    if not is_manager():
        emp = active_employee()
        if not emp or (company and emp.company != company):
            frappe.throw("Company access denied", frappe.PermissionError)
        company = emp.company
    if not company:
        frappe.throw("Company must be selected")
    vehicles = frappe.get_list("ADM Vehicle", filters={"company": company},
        fields=["name", "plate_number", "status", "seat_capacity"], limit_page_length=500)
    trips = frappe.get_list("ADM Trip", filters={
        "company": company, "status": ["in", ["Assigned", "In Progress"]],
        "planned_start": ["<", end], "planned_end": [">", start],
    }, fields=["vehicle"], limit_page_length=0)
    blocked = {r.vehicle for r in trips}
    maintenance = frappe.get_list("ADM Maintenance", filters={
        "company": company, "status": ["in", ["Scheduled", "In Progress"]],
        "starts_at": ["<", end], "ends_at": [">", start],
    }, fields=["vehicle"], limit_page_length=0)
    blocked.update(x.vehicle for x in maintenance)
    return [{"vehicle": v.name, "plate": v.plate_number, "seats": v.seat_capacity,
             "available": v.status == "Available" and v.name not in blocked} for v in vehicles]


@frappe.whitelist()
def fuel_kpi(company, from_date, to_date):
    if not is_manager():
        frappe.throw("Administration Manager required", frappe.PermissionError)
    if getdate(to_date) < getdate(from_date) or (getdate(to_date) - getdate(from_date)).days > 366:
        frappe.throw("Date range must be at most 366 days")
    fuel = frappe.get_list("ADM Fuel Log", filters={
        "company": company, "posting_date": ["between", [from_date, to_date]], "docstatus": 1
    }, fields=["vehicle", "liters", "amount"], limit_page_length=0)
    usage = {}
    for row in fuel:
        v = usage.setdefault(row.vehicle, {"liters": 0, "fuel_cost": 0})
        v["liters"] += row.liters or 0
        v["fuel_cost"] += row.amount or 0
    # Travel distance is not mixed with fuel readings: they may cover different periods.
    return usage
