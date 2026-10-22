import frappe
from frappe.model.document import Document


class ADMMeetingCheckin(Document):
    def validate(self):
        if not getattr(frappe.flags, "adm_v3_checkin", False):
            frappe.throw("Use the authorized meeting check-in action", frappe.PermissionError)

    def on_trash(self):
        frappe.throw("Meeting check-ins are immutable", frappe.PermissionError)
