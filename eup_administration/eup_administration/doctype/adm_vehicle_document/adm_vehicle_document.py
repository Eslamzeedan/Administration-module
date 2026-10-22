from frappe.model.document import Document
from eup_administration.v3.vehicle_documents import validate


class ADMVehicleDocument(Document):
    def validate(self):
        validate(self)
