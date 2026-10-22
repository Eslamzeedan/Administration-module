from frappe.model.document import Document
from eup_administration.consumables import validate_item


class ADMConsumableItem(Document):
    def validate(self):
        validate_item(self)

    def on_trash(self):
        pass
