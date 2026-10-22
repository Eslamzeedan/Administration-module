"""Desk dashboard: only request registry rows the caller may read."""
from collections import Counter
import frappe
from frappe.utils import now_datetime, getdate
from eup_administration.v3.security import is_manager, active_employee


@frappe.whitelist()
def dashboard(company=None, limit=500):
    if not (is_manager() or frappe.has_permission("ADM Request Registry", "read")):
        frappe.throw("Administration access required", frappe.PermissionError)
    if not is_manager():
        emp = active_employee()
        if company and (not emp or company != emp.company):
            frappe.throw("Company access denied", frappe.PermissionError)
    filters = {"company": company} if company else {}
    data = frappe.get_list("ADM Request Registry", filters=filters,
        fields=["service_family", "source_status", "priority", "due_at"],
        limit_page_length=min(max(int(limit),1),5000))
    active = {"Requested", "Pending Approval", "Approved", "Assigned", "In Progress",
              "Partially Issued", "Submitted"}
    totals = Counter(row.service_family for row in data)
    overdue = sum(1 for row in data if row.source_status in active and row.due_at and row.due_at < now_datetime())
    return {"total": len(data), "by_service": dict(totals),
            "by_status": dict(Counter(row.source_status for row in data)),
            "overdue": overdue, "scope": "Only permitted records"}
