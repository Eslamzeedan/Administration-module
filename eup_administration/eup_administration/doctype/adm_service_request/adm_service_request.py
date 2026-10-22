from frappe.model.document import Document
from eup_administration.runner import validate_request


class ADMServiceRequest(Document):
    def validate(self):
        validate_request(self)
