import frappe
from frappe.model.document import Document
from eup_administration.v4.security import require_company, manager


class ADMSharedEquipment(Document):
    def validate(self):
        require_company(self.company)
        if not manager(self.company):
            frappe.throw("Administration manager required", frappe.PermissionError)
        old = self.get_doc_before_save()
        if old and old.company != self.company:
            frappe.throw("Equipment company cannot change")
