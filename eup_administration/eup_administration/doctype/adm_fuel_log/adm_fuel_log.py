from frappe.model.document import Document
from eup_administration.fleet import validate_ledger

class ADMFuelLog(Document):
    def validate(self):
        validate_ledger(self, 'fuel')

    def before_cancel(self):
        from eup_administration.services import admin_only
        admin_only()
