import frappe
from frappe.tests import IntegrationTestCase

PRODUCTION_SITE = 'erpnext-v16.eup-cairo.local'

class AdministrationIntegrationTestCase(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        # Frappe commits generated dependencies in setUpClass, before setUp runs.
        # Refuse unsafe sites before calling into that lifecycle.
        if (frappe.local.site == PRODUCTION_SITE or
                not frappe.local.site.startswith(('test-', 'staging-')) or
                not frappe.conf.get('adm_allow_integration_tests')):
            raise AssertionError('Use an isolated test-/staging- site with adm_allow_integration_tests=1')
        super().setUpClass()

    def setUp(self):
        super().setUp()
        frappe.set_user('Administrator')
        self.addCleanup(frappe.set_user, 'Administrator')
        self.company = frappe.conf.get('adm_test_company')
        self.assertTrue(self.company, 'Set adm_test_company to an existing isolated fixture Company')
        self.assertTrue(frappe.db.exists('Company', self.company),
                        'adm_test_company must name an existing Company; tests never generate ERPNext fixtures')
        from eup_administration.install import ensure_roles
        ensure_roles()
        suffix = frappe.generate_hash(length=10)
        self.driver_user = self.make_user('driver-' + suffix, 'Administration Driver')
        self.requester_user = self.make_user('requester-' + suffix, 'Administration User')
        self.other_user = self.make_user('other-' + suffix, 'Administration Driver')
        self.vehicle = frappe.get_doc({'doctype':'ADM Vehicle', 'plate_number':'TEST-' + suffix,
            'company':self.company, 'initial_odometer':1000}).insert()
        self.driver = frappe.get_doc({'doctype':'ADM Driver', 'driver_name':suffix,
            'user':self.driver_user, 'enabled':1}).insert()
        self.room = frappe.get_doc({'doctype':'ADM Meeting Room','room_name':'TEST-'+suffix,
            'company':self.company,'capacity':10,'buffer_minutes':15}).insert()
    def make_user(self, identifier, role):
        user = frappe.get_doc({'doctype':'User','email':identifier+'@example.com','first_name':identifier,
            'enabled':1,'send_welcome_email':0,'roles':[{'role':role}]}).insert(ignore_permissions=True)
        return user.name
    def new_trip(self, start='2099-01-01 08:00:00', end='2099-01-01 10:00:00'):
        frappe.set_user(self.requester_user)
        return frappe.get_doc({'doctype':'ADM Trip','purpose':'Test journey','company':self.company,
            'origin':'Cairo','destination':'Sadat','planned_start':start,'planned_end':end,'passenger_count':1}).insert()
    def assigned(self):
        from eup_administration import services
        doc = self.new_trip()
        services.request_trip(doc.name)
        frappe.set_user('Administrator')
        services.assign_trip(doc.name,self.vehicle.name,self.driver.name)
        return doc
    def booking(self, start, end):
        return frappe.get_doc({'doctype':'ADM Meeting Booking','title':'Test meeting','room':self.room.name,
            'starts_at':start,'ends_at':end,'attendee_count':2}).insert()
