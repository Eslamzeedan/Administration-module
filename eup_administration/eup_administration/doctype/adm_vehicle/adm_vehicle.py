import frappe
from frappe.model.document import Document
from eup_administration.rules import reading

class ADMVehicle(Document):
    def validate(self):
        from eup_administration.services import lock
        if (self.seat_capacity or 0) < 0:
            frappe.throw('Passenger capacity cannot be negative')
        old = self.get_doc_before_save()
        if old:
            lock('ADM Vehicle', self.name)
            if self.company != old.company and any(frappe.db.exists(dt, {'vehicle': self.name}) for dt in ('ADM Trip', 'ADM Maintenance', 'ADM Fuel Log', 'ADM Trip Expense')):
                frappe.throw('Vehicle company cannot change after it has administration history')
            if self.status != old.status and frappe.db.sql("SELECT name FROM `tabADM Trip` WHERE vehicle=%s AND status IN ('Assigned', 'In Progress') LIMIT 1 FOR UPDATE", (self.name,)):
                frappe.throw('Resolve assigned and active trips before changing vehicle company or availability')
        if not old:
            self.last_odometer = reading(self.initial_odometer)
        elif self.initial_odometer != old.initial_odometer or self.last_odometer != old.last_odometer:
            frappe.throw("Odometer changes must come from trip actions; initial reading is immutable.")
