from frappe.model.document import Document
from eup_administration.consumables import validate_supply_request


class ADMSupplyRequest(Document):
    def validate(self):
        validate_supply_request(self)

    def on_trash(self):
        pass
