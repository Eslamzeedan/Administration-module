import frappe
from eup_administration.v3.security import active_employee

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/administration_self_service"
        raise frappe.Redirect
    employee = active_employee()
    context.company = employee.company if employee else ""
    context.requires_employee = not employee
    context.no_cache = 1
