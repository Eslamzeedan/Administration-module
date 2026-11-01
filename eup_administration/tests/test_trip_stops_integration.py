"""Disposable Frappe v16 site only; these tests have NOT been run by offline CI."""
import frappe
from eup_administration import services, trip_stops, trip_portal
from eup_administration.tests.base import AdministrationIntegrationTestCase
from eup_administration.tests.test_v4_independent_integration import protected_snapshot


class TestTripStopsIntegration(AdministrationIntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.protected = protected_snapshot()
        self.addCleanup(self.assert_protected)

    def assert_protected(self):
        frappe.set_user("Administrator")
        self.assertEqual(self.protected, protected_snapshot())

    def route(self, start=True):
        doc = self.new_trip()
        doc.append("stops", {"location": "Bank", "purpose": "Documents", "expected_wait_minutes": 10})
        doc.append("stops", {"location": "Sadat", "purpose": "Meeting"})
        doc.save()
        services.request_trip(doc.name)
        frappe.set_user("Administrator")
        services.assign_trip(doc.name, self.vehicle.name, self.driver.name)
        frappe.set_user(self.driver_user)
        if start:
            services.start_trip(doc.name, 1000)
        doc.reload()
        return doc

    def test_full_ordered_route_as_read_only_driver(self):
        doc = self.route()
        self.assertFalse(frappe.has_permission("ADM Trip", "write", doc=doc))
        with self.assertRaises(frappe.ValidationError):
            services.end_trip(doc.name, 1020)
        for row in doc.stops:
            trip_stops.mark_stop(doc.name, row.name, "arrive")
            trip_stops.mark_stop(doc.name, row.name, "depart")
        services.end_trip(doc.name, 1020)
        doc.reload()
        self.assertEqual(doc.status, "Completed")
        self.assertEqual(doc.distance_km, 20)
        self.assertEqual(doc.destination_arrived_by, self.driver_user)
        self.assertTrue(doc.destination_arrived_at)
        self.assertTrue(all(r.arrived_by == self.driver_user and r.departed_by == self.driver_user for r in doc.stops))
        self.assertTrue(all(r.departed_at >= r.arrived_at for r in doc.stops))
        frappe.set_user(self.requester_user)
        visible = next(r for r in trip_portal.home()["trips"] if r["name"] == doc.name)
        self.assertEqual(visible["status"], "Completed")
        self.assertTrue(visible["stops"][1]["arrived_at"])
        self.assertFalse(visible["operate"])

    def test_skip_and_replay_leave_milestone_unchanged(self):
        doc = self.route()
        with self.assertRaises(frappe.ValidationError):
            trip_stops.mark_stop(doc.name, doc.stops[1].name, "arrive")
        trip_stops.mark_stop(doc.name, doc.stops[0].name, "arrive")
        doc.reload()
        original = (doc.stops[0].arrived_at, doc.stops[0].arrived_by)
        with self.assertRaises(frappe.ValidationError):
            trip_stops.mark_stop(doc.name, doc.stops[0].name, "arrive")
        doc.reload()
        self.assertEqual((doc.stops[0].arrived_at, doc.stops[0].arrived_by), original)
        self.assertFalse(doc.stops[1].arrived_at)

    def test_requester_and_other_driver_cannot_operate(self):
        doc = self.route()
        for actor in (self.requester_user, self.other_user):
            frappe.set_user(actor)
            with self.assertRaises(frappe.PermissionError):
                trip_stops.mark_stop(doc.name, doc.stops[0].name, "arrive")
        self.assertNotIn(doc.name, [r["name"] for r in trip_portal.home("driver")["trips"]])
        frappe.set_user("Administrator")
        doc.reload()
        self.assertFalse(doc.stops[0].arrived_at)

    def test_submitted_route_and_milestones_cannot_be_saved_directly(self):
        doc = self.route()
        frappe.set_user("Administrator")
        doc.reload()
        doc.stops[0].location = "Forged route"
        with self.assertRaises(frappe.ValidationError):
            doc.save()
        doc.reload()
        doc.stops[0].arrived_by = "Administrator"
        with self.assertRaises(frappe.ValidationError):
            doc.save()
        doc.reload()
        self.assertEqual(doc.stops[0].location, "Bank")
        self.assertFalse(doc.stops[0].arrived_by)

    def test_single_destination_arrival_and_legacy_completion(self):
        doc = self.assigned()
        frappe.set_user(self.driver_user)
        services.start_trip(doc.name, 1000)
        trip_stops.arrive_destination(doc.name)
        with self.assertRaises(frappe.ValidationError):
            trip_stops.arrive_destination(doc.name)
        services.end_trip(doc.name, 1010)
        doc.reload()
        self.assertTrue(doc.destination_arrived_at)
        self.assertEqual(doc.status, "Completed")

    def test_arrival_before_start_is_rejected(self):
        doc = self.route(start=False)
        with self.assertRaises(frappe.ValidationError):
            trip_stops.mark_stop(doc.name, doc.stops[0].name, "arrive")

    def test_portal_create_uses_real_employee_company(self):
        frappe.set_user("Administrator")
        template = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"},
            ["gender", "naming_series"], as_dict=True)
        self.assertTrue(template and template.gender, "Existing isolated fixture Employee/Gender required")
        fields = {"doctype": "Employee", "first_name": "ADM trip QA", "gender": template.gender,
            "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01", "status": "Active",
            "company": self.company, "user_id": self.requester_user, "create_user_permission": 0}
        if template.naming_series:
            fields["naming_series"] = template.naming_series
        frappe.get_doc(fields).insert()
        frappe.set_user(self.requester_user)
        values = {"purpose": "Portal trip QA", "origin": "Cairo", "destination": "Sadat",
            "planned_start": "2099-01-02 08:00:00", "planned_end": "2099-01-02 10:00:00",
            "passenger_count": 1, "stops": [{"location": "Bank"}, {"location": "Sadat"}]}
        result = trip_portal.create(values)
        doc = frappe.get_doc("ADM Trip", result["name"])
        self.assertEqual(doc.requested_by, self.requester_user)
        self.assertEqual(doc.company, self.company)
        self.assertEqual(doc.status, "Requested")
        self.assertEqual(len(doc.stops), 2)
        before = frappe.db.count("ADM Trip")
        with self.assertRaises(frappe.ValidationError):
            trip_portal.create({**values, "company": "FORGED"})
        self.assertEqual(frappe.db.count("ADM Trip"), before)

    def test_guest_cannot_list_trips(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            trip_portal.home()
