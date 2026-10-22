from frappe.model.document import Document
from eup_administration.services import validate_booking
class ADMMeetingBooking(Document):
    def validate(self):
        validate_booking(self)
