import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime


class ADMApprovalDelegation(Document):
    def validate(self):
        if self.delegator == self.delegate:
            frappe.throw("Cannot delegate approvals to yourself")
        if self.valid_from and self.valid_until and get_datetime(self.valid_until) <= get_datetime(self.valid_from):
            frappe.throw("Delegation end must be later than start")
        if not self.company:
            frappe.throw("Company is required")
