from frappe.model.document import Document
from eup_administration.v3.custody import validate


class ADMCustodyHandover(Document):
    def validate(self):
        validate(self)
