import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from contextvars import ContextVar
from datetime import datetime, date, timedelta

ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)
    def __setattr__(self, key, value):
        self[key] = value
    def set(self, key, value):
        self[key] = value
    def as_dict(self):
        return dict(self)


class TestOperationActions(unittest.TestCase):
    def setUp(self):
        self.doc = Row(doctype="ADM Parcel", name="PARCEL", company="A",
                       requested_by="requester", recipient="recipient", delivered_at=None)
        self.saved = []
        fake = types.ModuleType("frappe")
        fake.session = Row(user="recipient")
        fake.PermissionError = PermissionError
        fake.whitelist = lambda **kw: lambda f: f
        fake.throw = lambda message, exc=ValueError: (_ for _ in ()).throw(exc(message))
        fake.parse_json = __import__("json").loads
        fake.get_doc = lambda *a: self.doc
        model = types.ModuleType("frappe.model.document")
        model.Document = Row
        utils = types.ModuleType("frappe.utils")
        utils.get_datetime = lambda x: datetime.fromisoformat(x) if isinstance(x, str) else x
        utils.getdate = lambda x: date.fromisoformat(x) if isinstance(x, str) else x
        utils.now_datetime = lambda: datetime(2026, 10, 22, 10)
        utils.today = lambda: "2026-10-22"
        utils.add_days = lambda d, n: utils.getdate(d)+timedelta(days=n)
        security = types.ModuleType("eup_administration.v4.security")
        security.require_company = lambda company: None
        security.manager = lambda company: False
        workflow = types.ModuleType("eup_administration.v4.workflow")
        workflow._internal = ContextVar("internal_test", default=False)
        workflow._lock = lambda *a: None
        workflow.save_internal = lambda doc, insert=False: self.saved.append(dict(doc)) or doc
        workflow.key = lambda *a: "key"
        self.fake = fake
        with patch.dict(sys.modules, {"frappe": fake, "frappe.utils": utils, "frappe.model.document": model,
                "eup_administration.v4.security": security, "eup_administration.v4.workflow": workflow}):
            spec = importlib.util.spec_from_file_location("operation_actions", ROOT / "eup_administration/v4/operations.py")
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)

    def test_recipient_acknowledges_once(self):
        self.module.acknowledge_parcel("PARCEL")
        self.assertEqual(len(self.saved), 1)
        with self.assertRaises(PermissionError):
            self.module.acknowledge_parcel("PARCEL")

    def test_other_user_cannot_acknowledge(self):
        self.fake.session.user = "other"
        with self.assertRaises(PermissionError):
            self.module.acknowledge_parcel("PARCEL")
        self.assertFalse(self.saved)

    def test_operator_can_record_resolution(self):
        self.doc.doctype = "ADM Facility Ticket"
        self.doc.assigned_to = "recipient"
        self.module.update_details(self.doc.doctype, self.doc.name, {"resolution": "Repaired"})
        self.assertEqual(self.doc.resolution, "Repaired")

    def test_operator_cannot_set_state_or_identity(self):
        self.doc.assigned_to = "recipient"
        for values in [{"workflow_state": "Done"}, {"company": "B"}, {"requested_by": "actor"}]:
            with self.assertRaises(ValueError):
                self.module.update_details(self.doc.doctype, self.doc.name, values)
        self.assertFalse(self.saved)

    def test_unassigned_user_cannot_update(self):
        with self.assertRaises(PermissionError):
            self.module.update_details("ADM Facility Ticket", "X", {"resolution": "x"})

    def test_nonmanager_cannot_assign(self):
        with self.assertRaises(PermissionError):
            self.module.assign_operator("ADM Parcel", "PARCEL", "other")

    def test_nonmanager_cannot_change_recurring_schedule(self):
        self.doc.assigned_to = "recipient"
        with self.assertRaises(PermissionError):
            self.module.update_details("ADM Recurring Task", "TASK", {"enabled": 0})

    def test_feedback_wrong_person_denied(self):
        with self.assertRaises(PermissionError):
            self.module.feedback("ADM Parcel", "PARCEL", 5)

    def test_feedback_requires_workflow(self):
        self.fake.session.user = "requester"
        with self.assertRaises(ValueError):
            self.module.feedback("ADM Parcel", "PARCEL", 5)

    def test_detail_text_bounded(self):
        self.doc.assigned_to = "recipient"
        with self.assertRaises(ValueError):
            self.module.update_details("ADM Facility Ticket", "X", {"resolution": "x"*10001})

    def _use_validation_errors(self):
        class ValidationFailure(Exception):
            pass
        def throw(message, exc=ValidationFailure):
            raise exc(message)
        self.fake.throw = throw
        return ValidationFailure

    def test_invalid_operation_numbers_are_validation_errors(self):
        validation_error = self._use_validation_errors()
        self.module.manager = lambda company: True
        cases = (
            ("ADM Preventive Plan", {"interval_days": -2}, "Interval days"),
            ("ADM Recurring Task", {"interval_days": -1}, "Interval days"),
            ("ADM Preventive Plan", {"interval_days": 90, "next_odometer": float("nan")}, "Next odometer"),
            ("ADM Driver Checklist", {"odometer": -1}, "Odometer"),
            ("ADM Contract Register", {"starts_on": "2026-10-22",
                "expires_on": "2026-10-23", "notice_days": -1}, "Notice days"),
        )
        for doctype, values, label in cases:
            with self.subTest(doctype=doctype, field=label):
                doc = self.module.Operation(doctype=doctype, company="A", **values)
                doc.is_new = lambda: True
                doc.get_doc_before_save = lambda: None
                with self.assertRaisesRegex(validation_error, label):
                    doc.validate()
        self.assertFalse(self.saved)

    def test_detail_number_validation_preserves_values_and_zero(self):
        validation_error = self._use_validation_errors()
        self.module.manager = lambda company: True
        self.doc.doctype = "ADM Preventive Plan"
        self.doc.next_odometer = 100
        for value in (-1, float("nan"), float("inf"), "not-a-number"):
            with self.subTest(value=value):
                with self.assertRaises(validation_error):
                    self.module.update_details(self.doc.doctype, self.doc.name, {"next_odometer": value})
                self.assertEqual(self.doc.next_odometer, 100)
                self.assertFalse(self.saved)
        self.module.update_details(self.doc.doctype, self.doc.name, {"next_odometer": 0})
        self.assertEqual(self.doc.next_odometer, 0)
        self.assertEqual(len(self.saved), 1)
        self.saved.clear()
        self.doc.doctype = "ADM Recurring Task"
        self.doc.interval_days = 7
        with self.assertRaisesRegex(validation_error, "Interval days"):
            self.module.update_details(self.doc.doctype, self.doc.name, {"interval_days": -1})
        self.assertEqual(self.doc.interval_days, 7)
        self.assertFalse(self.saved)
