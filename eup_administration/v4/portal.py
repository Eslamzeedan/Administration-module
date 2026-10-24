"""Authenticated employee portal. Identity always comes from the session."""
import frappe
from eup_administration.v3.security import active_employee
from eup_administration.v4.workflow import start
from eup_administration.v4.dashboard import command_center

FIELDS = {
    "ADM Facility Ticket": {"subject", "description", "priority", "location", "category"},
    "ADM Parcel": {"subject", "description", "priority", "tracking_number", "recipient", "sender", "tracking_type", "attachment"},
    "ADM Equipment Booking": {"subject", "description", "priority", "equipment", "starts_at", "ends_at"},
}


def identity():
    employee = active_employee()
    if frappe.session.user == "Guest" or not employee:
        frappe.throw("An active employee login is required", frappe.PermissionError)
    return employee


@frappe.whitelist()
def home():
    employee = identity()
    result = command_center(employee.company)
    result["company"] = employee.company
    result["policies"] = frappe.get_list("ADM Workflow Policy", filters={
        "company": employee.company, "enabled": 1}, fields=["name", "policy_title", "target_doctype"],
        limit_page_length=100)
    result["equipment"] = frappe.get_list("ADM Shared Equipment", filters={
        "company": employee.company, "enabled": 1}, fields=["name", "equipment_name"],
        limit_page_length=100)
    return result


@frappe.whitelist(methods=["POST"])
def create_request(doctype, values, policy_name):
    employee = identity()
    values = frappe.parse_json(values) if isinstance(values, str) else values
    if doctype not in FIELDS or not isinstance(values, dict) or not set(values) <= FIELDS[doctype]:
        frappe.throw("Unsupported self-service request fields")
    doc = frappe.get_doc({"doctype": doctype, **values, "company": employee.company,
                          "department": employee.department}).insert()
    start(doc.doctype, doc.name, policy_name)
    return {"doctype": doc.doctype, "name": doc.name}
