from frappe.model.document import Document
from eup_administration.consumables import validate_custody


class ADMAdminCustody(Document):
    def validate(self):
        validate_custody(self)

    def on_trash(self):
        pass
