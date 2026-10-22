from frappe.model.document import Document
from eup_administration.v3.general import validate


class ADMGeneralServiceRequest(Document):
    def validate(self):
        validate(self)
