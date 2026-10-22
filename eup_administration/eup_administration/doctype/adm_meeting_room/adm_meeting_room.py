import frappe
from frappe.model.document import Document
class ADMMeetingRoom(Document):
    def validate(self):
        if self.capacity < 1 or (self.buffer_minutes or 0) < 0:
            frappe.throw("Capacity must be positive and preparation time cannot be negative.")
        if not self.is_new():
            old = self.get_doc_before_save()
            if old.buffer_minutes != self.buffer_minutes or old.capacity != self.capacity:
                if frappe.db.exists("ADM Meeting Booking", {"room": self.name, "status": "Confirmed"}):
                    frappe.throw("Cancel or complete confirmed bookings before changing capacity or preparation time.")
