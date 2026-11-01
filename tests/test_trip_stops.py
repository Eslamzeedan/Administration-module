"""Offline action/security tests; real database coverage lives in app integration tests."""
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)
    def __setattr__(self, key, value):
        self[key] = value
    def get_doc_before_save(self):
        return self.get("_old")
    def set(self, key, value):
        self[key] = value
    def as_dict(self):
        return dict(self)


class TripStopsTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 11, 1, 10)
        self.saved, self.locks = [], []
        self.fake = types.ModuleType("frappe")
        self.fake.session = Row(user="driver")
        self.fake.PermissionError = PermissionError
        self.fake.throw = lambda message, exc=ValueError: (_ for _ in ()).throw(exc(message))
        def whitelist(methods=None):
            def wrap(fn):
                fn.allowed_methods = methods
                return fn
            return wrap
        self.fake.whitelist = whitelist
        self.fake.db = MagicMock()
        self.fake.publish_realtime = MagicMock()
        self.fake.get_roles = lambda user: ["Administration User"] if user == "employee" else ["Administration Driver"]
        utils = types.ModuleType("frappe.utils")
        utils.now_datetime = lambda: self.at
        utils.get_datetime = lambda value: datetime.fromisoformat(value) if isinstance(value, str) else value
        services = types.ModuleType("eup_administration.services")
        def load(name):
            self.locks.append(name)
            if not self.readable:
                raise PermissionError("Not visible")
            return self.doc
        def driver(doc):
            if self.fake.session.user not in ("driver", "manager"):
                raise PermissionError("Assigned driver only")
        services.get_locked_trip, services.driver_check = load, driver
        services.save_action = lambda doc: self.saved.append(copy.deepcopy(doc)) or doc.as_dict()
        self.context = patch.dict(sys.modules, {"frappe": self.fake, "frappe.utils": utils,
            "eup_administration.services": services})
        self.context.start()
        self.addCleanup(self.context.stop)
        spec = importlib.util.spec_from_file_location("trip_stops_actions", ROOT / "eup_administration/trip_stops.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.doc = Row(name="TRIP", status="In Progress", requested_by="employee", driver="DRIVER",
            actual_start=self.at-timedelta(hours=1), destination="Office",
            stops=[self.stop("BANK", "Bank"), self.stop("OFFICE", "Office")])
        self.readable = True

    def stop(self, name, location):
        return Row(name=name, location=location, purpose="", expected_wait_minutes=0,
            arrived_at=None, departed_at=None, arrived_by=None, departed_by=None)

    def mark(self, name="BANK", event="arrive"):
        return self.module.mark_stop("TRIP", name, event)

    def test_ordered_arrival_departure_and_final_destination(self):
        self.mark()
        self.assertEqual(self.doc.stops[0].arrived_at, self.at)
        self.assertEqual(self.doc.stops[0].arrived_by, "driver")
        self.mark(event="depart")
        self.mark("OFFICE")
        self.assertEqual(self.doc.destination_arrived_at, self.at)
        self.assertEqual(self.doc.destination_arrived_by, "driver")
        self.mark("OFFICE", "depart")
        self.module.require_finished(self.doc)
        self.assertEqual(len(self.saved), 4)
        self.assertEqual(self.locks, ["TRIP"]*4)

    def test_cannot_skip_first_stop_or_supply_foreign_child(self):
        for name in ("OFFICE", "ANOTHER-TRIP-STOP"):
            with self.assertRaises(ValueError):
                self.mark(name)
        self.assertFalse(self.saved)

    def test_departure_requires_arrival(self):
        with self.assertRaises(ValueError):
            self.mark(event="depart")
        self.assertFalse(self.saved)

    def test_arrival_replay_preserves_original_time_and_actor(self):
        self.mark()
        self.at += timedelta(minutes=5)
        with self.assertRaises(ValueError):
            self.mark()
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.doc.stops[0].arrived_at, self.at-timedelta(minutes=5))

    def test_departure_replay_cannot_advance_the_next_stop(self):
        self.mark()
        self.mark(event="depart")
        with self.assertRaises(ValueError):
            self.mark(event="depart")
        self.assertIsNone(self.doc.stops[1].arrived_at)
        self.assertEqual(len(self.saved), 2)

    def test_only_assigned_driver_or_manager_operates(self):
        for actor in ("employee", "other-driver"):
            self.fake.session.user = actor
            with self.assertRaises(PermissionError):
                self.mark()
        self.fake.session.user = "manager"
        self.mark()
        self.assertEqual(self.doc.stops[0].arrived_by, "manager")

    def test_invisible_trip_denied_before_any_action(self):
        self.readable = False
        with self.assertRaises(PermissionError):
            self.mark()
        self.assertFalse(self.saved)

    def test_inactive_states_and_invalid_events_rejected(self):
        for state in ("Draft", "Requested", "Assigned", "Completed", "Cancelled", "Rejected"):
            self.doc.status = state
            with self.assertRaises(ValueError):
                self.mark()
        self.doc.status = "In Progress"
        with self.assertRaises(ValueError):
            self.mark(event="skip")
        self.assertFalse(self.saved)

    def test_clock_cannot_go_backwards(self):
        self.doc.actual_start = self.at+timedelta(minutes=1)
        with self.assertRaises(ValueError):
            self.mark()
        self.doc.actual_start = self.at-timedelta(hours=1)
        self.mark()
        self.at -= timedelta(minutes=1)
        with self.assertRaises(ValueError):
            self.mark(event="depart")

    def test_end_guard_requires_all_stops_departed(self):
        with self.assertRaises(ValueError):
            self.module.require_finished(self.doc)
        self.mark()
        with self.assertRaises(ValueError):
            self.module.require_finished(self.doc)

    def test_legacy_no_stops_can_end_without_arrival(self):
        self.doc.stops = []
        self.module.require_finished(self.doc)
        self.module.arrive_destination("TRIP")
        self.assertEqual(self.doc.destination_arrived_at, self.at)
        with self.assertRaises(ValueError):
            self.module.arrive_destination("TRIP")

    def test_destination_shortcut_cannot_bypass_stops(self):
        with self.assertRaises(ValueError):
            self.module.arrive_destination("TRIP")
        self.assertFalse(self.saved)

    def test_all_new_mutations_require_post(self):
        for name in ("mark_stop", "arrive_destination"):
            self.assertEqual(getattr(self.module, name).allowed_methods, ["POST"])

    def test_valid_draft_route_and_empty_legacy_route(self):
        self.module.validate_stops(self.doc)
        self.doc.stops = []
        self.module.validate_stops(self.doc)

    def test_final_stop_must_match_destination(self):
        self.doc.destination = "Other"
        with self.assertRaisesRegex(ValueError, "final destination"):
            self.module.validate_stops(self.doc)

    def test_stop_limit_blank_address_and_long_purpose(self):
        for rows in ([self.stop(str(i), "Office") for i in range(31)],
                     [self.stop("S", " ")], [Row(self.stop("S", "Office"), purpose="x"*2001)]):
            self.doc.stops = rows
            with self.assertRaises(ValueError):
                self.module.validate_stops(self.doc)

    def test_wait_bounds_finite_whole_minutes(self):
        for value in (-1, 1441, 1.5, "bad", float("nan"), float("inf")):
            self.doc.stops[0].expected_wait_minutes = value
            with self.assertRaisesRegex(ValueError, "whole minutes"):
                self.module.validate_stops(self.doc)
        self.doc.stops[0].expected_wait_minutes = "1440"
        self.module.validate_stops(self.doc)
        self.assertEqual(self.doc.stops[0].expected_wait_minutes, 1440)

    def test_forged_milestones_rejected_on_new_and_existing_draft(self):
        self.doc.stops[0].arrived_at = self.at
        with self.assertRaisesRegex(ValueError, "arrival and departure"):
            self.module.validate_stops(self.doc)
        self.doc.stops[0].arrived_at = None
        self.doc.destination_arrived_at = self.at
        with self.assertRaisesRegex(ValueError, "destination arrival"):
            self.module.validate_stops(self.doc)

    def test_submitted_route_cannot_change_even_in_internal_context(self):
        for mutation in ("edit", "reorder", "remove", "add"):
            doc = copy.deepcopy(self.doc)
            doc._old = copy.deepcopy(self.doc)
            if mutation == "edit":
                doc.stops[0].purpose = "Changed"
            elif mutation == "reorder":
                doc.stops.reverse()
                doc.destination = "Bank"
            elif mutation == "remove":
                doc.stops = doc.stops[1:]
            else:
                doc.stops.insert(0, self.stop("NEW", "New"))
            with self.assertRaisesRegex(ValueError, "Submitted trip stops"):
                self.module.validate_stops(doc, internal=True)

    def test_direct_edit_cannot_clear_existing_milestone(self):
        self.doc.stops[0].arrived_at = self.at
        self.doc._old = copy.deepcopy(self.doc)
        self.doc.stops[0].arrived_at = None
        with self.assertRaisesRegex(ValueError, "arrival and departure"):
            self.module.validate_stops(self.doc)

    def test_progress_notifications_are_scoped_and_after_commit(self):
        self.doc._old = copy.deepcopy(self.doc)
        self.doc.stops[0].arrived_at = self.at
        self.fake.db.get_value.side_effect = lambda dt, *a, **kw: "driver" if dt == "ADM Driver" else 1
        self.module.publish_progress(self.doc)
        calls = self.fake.publish_realtime.call_args_list
        self.assertEqual({c.kwargs["user"] for c in calls}, {"employee", "driver"})
        self.assertTrue(all(c.kwargs["after_commit"] for c in calls))
        self.assertTrue(all(c.args[1] == {"name": "TRIP"} for c in calls))

    def test_no_notification_on_insert_or_unrelated_edit(self):
        self.module.publish_progress(self.doc)
        self.doc._old = copy.deepcopy(self.doc)
        self.module.publish_progress(self.doc)
        self.fake.publish_realtime.assert_not_called()
