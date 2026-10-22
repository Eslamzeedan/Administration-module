import frappe
from frappe.model.document import Document
from eup_administration.services import lock

class ADMDriver(Document):
    def validate(self):
        old = self.get_doc_before_save()
        if old:
            lock('ADM Driver', self.name)
            if self.user != old.user or self.enabled != old.enabled:
                if frappe.db.sql('''SELECT name FROM `tabADM Trip` WHERE driver=%s
                    AND status IN ('Assigned', 'In Progress') LIMIT 1 FOR UPDATE''', (self.name,)):
                    frappe.throw('Resolve assigned and active trips before changing driver login or availability')
