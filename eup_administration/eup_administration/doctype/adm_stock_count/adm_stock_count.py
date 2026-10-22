from frappe.model.document import Document
from eup_administration.v3.inventory import validate_count


class ADMStockCount(Document):
    def validate(self):
        validate_count(self)
