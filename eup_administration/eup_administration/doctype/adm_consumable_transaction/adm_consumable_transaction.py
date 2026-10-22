from frappe.model.document import Document
from eup_administration.consumables import validate_transaction


class ADMConsumableTransaction(Document):
    def validate(self):
        validate_transaction(self)

    def on_trash(self):
        from eup_administration.consumables import prevent_transaction_deletion
        prevent_transaction_deletion(self)
