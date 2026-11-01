import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)
    def __setattr__(self, key, value):
        self[key] = value
    def check_permission(self, action):
        if self.get("_deny"):
            raise PermissionError("Not visible")


class TripPortalTests(unittest.TestCase):
    def setUp(self):
        self.fake = types.ModuleType("frappe")
        self.fake.session = Row(user="employee")
        self.fake.PermissionError = PermissionError
        self.fake.whitelist = lambda **kw: lambda f: f
        self.fake.throw = lambda message, exc=ValueError: (_ for _ in ()).throw(exc(message))
        self.fake.parse_json = json.loads
        self.fake.has_permission = MagicMock(return_value=True)
        self.fake.get_list = MagicMock(return_value=[Row(name="TRIP")])
        self.doc = Row(name="TRIP", requested_by="employee", driver="DRIVER", status="In Progress",
            stops=[Row(name="STOP", location="Office", expected_wait_minutes=0, arrived_at=None, departed_at=None)])
        self.fake.get_doc = MagicMock(return_value=self.doc)
        self.fake.db = MagicMock()
        self.fake.db.get_value.return_value = "Display Name"
        permissions = types.ModuleType("eup_administration.permissions")
        permissions.active_driver = lambda: "DRIVER" if self.fake.session.user == "driver" else None
        permissions.is_admin = lambda: self.fake.session.user == "manager"
        security = types.ModuleType("eup_administration.v3.security")
        self.employee = Row(company="COMPANY", department="DEPT")
        security.active_employee = lambda: self.employee
        stops = types.ModuleType("eup_administration.trip_stops")
        stops.next_visit = lambda doc: next((r for r in doc.stops if not r.departed_at), None)
        services = types.ModuleType("eup_administration.services")
        services.request_trip = MagicMock()
        self.services = services
        self.context = patch.dict(sys.modules, {"frappe": self.fake,
            "eup_administration.permissions": permissions, "eup_administration.v3.security": security,
            "eup_administration.trip_stops": stops, "eup_administration.services": services})
        self.context.start()
        self.addCleanup(self.context.stop)
        # 'from eup_administration import services' reads the package attribute if already loaded.
        import eup_administration
        self.attr = patch.object(eup_administration, "services", services, create=True)
        self.attr.start()
        self.addCleanup(self.attr.stop)
        spec = importlib.util.spec_from_file_location("trip_portal_actions", ROOT / "eup_administration/trip_portal.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_employee_view_never_returns_other_requesters(self):
        info = self.module.home()
        self.assertEqual(self.fake.get_list.call_args.kwargs["filters"], {"requested_by": "employee"})
        self.assertFalse(info["trips"][0]["operate"])
        self.assertFalse(info["trips"][0]["can_end"])

    def test_driver_view_requires_enabled_profile_and_scopes_driver(self):
        with self.assertRaises(PermissionError):
            self.module.home("driver")
        self.fake.session.user = "driver"
        info = self.module.home("driver")
        self.assertEqual(self.fake.get_list.call_args.kwargs["filters"]["driver"], "DRIVER")
        self.assertTrue(info["trips"][0]["operate"])

    def test_individual_permission_checked_after_list(self):
        self.doc._deny = True
        with self.assertRaises(PermissionError):
            self.module.home()
        self.fake.db.get_value.assert_not_called()

    def test_pages_are_bounded_and_sentinel_is_not_serialized(self):
        self.fake.get_list.return_value = [Row(name=str(i)) for i in range(21)]
        info = self.module.home(start="20")
        self.assertEqual(len(info["trips"]), 20)
        self.assertTrue(info["has_more"])
        self.assertEqual(self.fake.get_list.call_args.kwargs["start"], 20)
        self.assertEqual(self.fake.get_list.call_args.kwargs["page_length"], 21)

    def test_invalid_page_and_view_rejected(self):
        for start in (-1, 10001, "bad"):
            with self.assertRaises(ValueError):
                self.module.home(start=start)
        with self.assertRaises(ValueError):
            self.module.home("all")

    def test_guest_is_denied_before_any_read_or_creation(self):
        self.fake.session.user = "Guest"
        for action in (lambda: self.module.home(), lambda: self.module.create({})):
            with self.assertRaises(PermissionError):
                action()
        self.fake.get_list.assert_not_called()
        self.fake.get_doc.assert_not_called()

    def test_create_uses_employee_identity_and_existing_request_action(self):
        inserted = Row(name="NEW")
        wrapper = MagicMock()
        wrapper.insert.return_value = inserted
        self.fake.get_doc.return_value = wrapper
        values = {"purpose": "Visit", "origin": "HQ", "destination": "Office",
            "planned_start": "2099-01-01 08:00", "planned_end": "2099-01-01 10:00",
            "passenger_count": 1, "stops": [{"location": "Office"}]}
        self.assertEqual(self.module.create(json.dumps(values)), {"name": "NEW"})
        payload = self.fake.get_doc.call_args.args[0]
        self.assertEqual(payload["company"], "COMPANY")
        self.assertEqual(payload["department"], "DEPT")
        self.assertNotIn("requested_by", payload)
        wrapper.insert.assert_called_once_with()
        self.services.request_trip.assert_called_once_with("NEW")

    def test_create_rejects_forged_parent_and_child_fields(self):
        for values in ({"company": "OTHER"}, {"requested_by": "victim"}, {"driver": "OTHER"},
                {"status": "Assigned"}, {"stops": [{"location": "Office", "arrived_at": "2026-11-01"}]},
                {"stops": [{"name": "FOREIGN"}]}, {"stops": "bad"}, {"stops": [{}]*31}):
            with self.assertRaises(ValueError):
                self.module.create(values)
        self.fake.get_doc.assert_not_called()

    def test_create_requires_active_employee_and_create_permission(self):
        self.employee = None
        with self.assertRaises(PermissionError):
            self.module.create({})
        self.employee = Row(company="COMPANY")
        self.fake.has_permission.return_value = False
        with self.assertRaises(PermissionError):
            self.module.create({})
        self.fake.get_doc.assert_not_called()

    def test_next_event_and_end_capabilities_follow_actual_stops(self):
        self.fake.session.user = "driver"
        self.assertEqual(self.module.serialize(self.doc)["next_event"], "arrive")
        self.doc.stops[0].arrived_at = "2026-11-01 10:00:00"
        self.assertEqual(self.module.serialize(self.doc)["next_event"], "depart")
        self.assertFalse(self.module.serialize(self.doc)["can_end"])
        self.doc.stops[0].departed_at = "2026-11-01 10:05:00"
        self.assertTrue(self.module.serialize(self.doc)["can_end"])
        self.assertIsNone(self.module.serialize(self.doc)["next_stop"])

    def test_serialization_does_not_expose_actor_ids_or_unrelated_fields(self):
        self.doc.secret = "HIDDEN"
        self.doc.stops[0].arrived_by = "ACTOR"
        info = self.module.serialize(self.doc)
        self.assertNotIn("secret", info)
        self.assertNotIn("arrived_by", info["stops"][0])
