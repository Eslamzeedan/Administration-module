from frappe.model.document import Document
from eup_administration.runner import validate_request
from eup_administration.mobile_errands import notify_transition


class ADMServiceRequest(Document):
    def validate(self):
        validate_request(self)

    def on_update(self):
        notify_transition(self)
