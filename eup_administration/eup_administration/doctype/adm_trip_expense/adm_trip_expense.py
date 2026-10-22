from frappe.model.document import Document
from eup_administration.fleet import validate_ledger

class ADMTripExpense(Document):
    def validate(self):
        validate_ledger(self, 'expense')

    def before_cancel(self):
        from eup_administration.services import admin_only
        admin_only()
