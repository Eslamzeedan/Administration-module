from frappe.model.document import Document
from eup_administration.consumables import validate_location


class ADMConsumableLocation(Document):
    def validate(self):
        validate_location(self)

    def on_trash(self):
        pass
