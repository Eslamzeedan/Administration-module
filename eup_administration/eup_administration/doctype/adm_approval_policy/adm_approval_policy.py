from frappe.model.document import Document
from eup_administration.v3.approval import validate_policy


class ADMApprovalPolicy(Document):
    def validate(self):
        validate_policy(self)
