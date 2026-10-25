import frappe
from eup_administration.tests.base import AdministrationIntegrationTestCase
from eup_administration import services

# These tests create their own ADM documents/users and use the configured existing
# Company. Do not recursively generate ERPNext's Company/Cost Center dependency
# graph (which can reach optional payments DocTypes on Frappe v16).
# This is Frappe's supported fixture-discovery override, not a test skip.
IGNORE_TEST_RECORD_DEPENDENCIES = (
    "Company", "User", "Department", "Cost Center", "ADM Vehicle", "ADM Driver",
)

class TestADMTrip(AdministrationIntegrationTestCase):
    def test_start_end(self):
        doc = self.assigned()
        with self.assertRaises(frappe.ValidationError):
            services.start_trip(doc.name)
        services.start_trip(doc.name, 1000)
        with self.assertRaises(frappe.ValidationError):
            services.end_trip(doc.name, 999)
        services.end_trip(doc.name, 1075)
        doc.reload()
        self.assertEqual(doc.status, 'Completed')
        self.assertEqual(doc.distance_km, 75)
        self.assertEqual(frappe.db.get_value('ADM Vehicle', self.vehicle.name, 'last_odometer'), 1075)
    def test_cannot_forge_readings_through_save(self):
        doc = self.assigned()
        doc.reload()
        doc.start_odometer = 12345
        with self.assertRaises(frappe.ValidationError):
            doc.save()
    def test_conflicting_assignment(self):
        self.assigned()
        second = self.new_trip()
        services.request_trip(second.name)
        # new_trip() switches to the requester; assignment must run as a manager
        # so this test reaches resource-conflict validation, not the role guard.
        frappe.set_user('Administrator')
        with self.assertRaisesRegex(frappe.ValidationError, 'conflicting or active trip'):
            services.assign_trip(second.name, self.vehicle.name, self.driver.name)
        second.reload()
        self.assertEqual(second.status, 'Requested')
        self.assertFalse(second.vehicle)
        self.assertFalse(second.driver)

    def test_assigned_driver_operates_without_write_permission(self):
        doc = self.assigned()
        frappe.set_user(self.driver_user)
        self.assertTrue(frappe.has_permission('ADM Trip','read',doc=frappe.get_doc('ADM Trip',doc.name)))
        self.assertFalse(frappe.has_permission('ADM Trip','write',doc=frappe.get_doc('ADM Trip',doc.name)))
        services.start_trip(doc.name,1000)
        services.end_trip(doc.name,1020)
        self.assertEqual(frappe.db.get_value('ADM Trip',doc.name,'status'),'Completed')
    def test_unassigned_driver_cannot_read_or_operate(self):
        doc = self.assigned()
        frappe.set_user(self.other_user)
        self.assertNotIn(doc.name,frappe.get_list('ADM Trip',pluck='name',limit_page_length=0))
        with self.assertRaises(frappe.PermissionError):
            services.start_trip(doc.name,1000)
    def test_driver_cannot_mutate_trip_via_save(self):
        doc = self.assigned()
        frappe.set_user(self.driver_user)
        doc = frappe.get_doc('ADM Trip',doc.name)
        doc.purpose = 'Forged edit'
        with self.assertRaises(frappe.PermissionError):
            doc.save()
