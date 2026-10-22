import frappe
from eup_administration.v4.portal import identity

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/administration_self_service"
        raise frappe.Redirect
    context.company = identity().company
    context.no_cache = 1
