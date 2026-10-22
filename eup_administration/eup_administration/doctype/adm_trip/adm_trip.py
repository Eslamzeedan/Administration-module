import frappe
from frappe.model.document import Document
from eup_administration.services import validate_trip

class ADMTrip(Document):
    def validate(self):
        validate_trip(self)
