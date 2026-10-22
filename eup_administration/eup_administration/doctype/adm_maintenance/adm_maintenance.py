from frappe.model.document import Document
from eup_administration.fleet import validate_maintenance

class ADMMaintenance(Document):
    def validate(self):
        validate_maintenance(self)
