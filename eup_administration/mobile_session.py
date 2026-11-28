import frappe
from frappe.sessions import get_csrf_token


@frappe.whitelist(methods=["GET"])
def csrf():
    """Issue the current signed-in session's token for native POST requests."""
    frappe.local.response_headers["Cache-Control"] = "private, no-store"
    return get_csrf_token()
