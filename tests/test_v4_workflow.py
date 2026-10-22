"""Behavioral tests execute the real engine with a small in-memory Frappe boundary."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value

    def as_dict(self):
        return dict(self)

    def check_permission(self, *args):
        return True

    def is_new(self):
        return not self.get("name")


class TestWorkflowEngine(unittest.TestCase):
    def setUp(self):
        self.records = []
        self.db = types.SimpleNamespace(
            get_value=lambda *a, **kw: None, exists=lambda *a: False,
            sql=lambda *a, **kw: [("record",)])
        self.frappe = types.ModuleType("frappe")
        self.frappe.db = self.db
        self.frappe.session = Row(user="approver@example.com")
        self.frappe.PermissionError = PermissionError
        self.frappe._dict = Row
        self.frappe.whitelist = lambda **kw: lambda f: f
        def throw(message, exc=ValueError):
            raise exc(message)
        self.frappe.throw = throw
        self.frappe.get_doc = lambda value, *a: Row(value) if isinstance(value, dict) else None
        self.frappe.get_all = lambda *a, **kw: []
        utils = types.ModuleType("frappe.utils")
        utils.now_datetime = lambda: datetime(2026, 10, 22, 10)
        utils.add_to_date = lambda date, hours: date + timedelta(hours=hours)
        model = types.ModuleType("frappe.model.document")
        model.Document = Row
        security = types.ModuleType("eup_administration.v4.security")
        security.require_company = lambda company: None
        security.manager = lambda *a: True
        v3sec = types.ModuleType("eup_administration.v3.security")
        v3sec.roles = lambda *a: {"Administration Manager"}
        approval = types.ModuleType("eup_administration.v3.approval")
        approval._authorized = lambda *a: (True, None)
        self.modules = patch.dict(sys.modules, {"frappe": self.frappe, "frappe.utils": utils,
            "frappe.model.document": model, "eup_administration.v4.security": security,
            "eup_administration.v3.security": v3sec, "eup_administration.v3.approval": approval})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location("v4_test_engine", ROOT / "eup_administration/v4/workflow.py")
        self.engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.engine)
        self.doc = Row(doctype="ADM Facility Ticket", name="TICKET", company="A",
                       requested_by="requester@example.com", workflow_state="Draft", priority="High")
        self.run = Row(name="RUN", revision=1, current_state="Draft", pending_action=None,
                       policy="POLICY", approval_step=0)
        self.transition = Row(action="Complete", from_state="Draft", to_state="Done",
                              allowed_role="Administration Manager", approval_required=1, conditions="[]")
        self.policy = Row(name="POLICY", transitions=[self.transition],
            states=[Row(state="Draft", sla_hours=24), Row(state="Done", is_terminal=1)],
            approval_bands=[Row(transition_action="Complete", step_number=1, approver_role="Administration Manager")])
        self.original_load = self.engine._load
        self.engine._load = lambda dt, n, revision=None: (self.doc, self.run, self.policy)
        self.engine.save_internal = lambda doc, insert=False: self.records.append(dict(doc)) or doc

    def request(self):
        return self.engine.transition(self.doc.doctype, self.doc.name, "Complete", 1)

    def test_approval_request_does_not_advance_state(self):
        result = self.request()
        self.assertEqual(result["state"], "Draft")
        self.assertEqual(result["pending_action"], "Complete")
        self.assertEqual(result["revision"], 2)
        self.assertEqual(self.records[-1]["decision"], "Requested")

    def test_approved_final_step_advances_and_clears_sla(self):
        self.request()
        result = self.engine.decide(self.doc.doctype, self.doc.name, "Approved", 2)
        self.assertEqual(result["state"], "Done")
        self.assertIsNone(result["pending_action"])
        self.assertIsNone(self.run.due_at)
        self.assertEqual(self.doc.workflow_state, "Done")
        self.assertEqual(self.records[-1]["actor"], "approver@example.com")

    def test_rejection_needs_reason(self):
        self.request()
        with self.assertRaises(ValueError):
            self.engine.decide(self.doc.doctype, self.doc.name, "Rejected", 2)

    def test_rejection_stays_in_source_state(self):
        self.request()
        self.engine.decide(self.doc.doctype, self.doc.name, "Rejected", 2, "Incomplete evidence")
        self.assertEqual(self.run.current_state, "Draft")
        self.assertIsNone(self.run.pending_action)
        self.assertEqual(self.records[-1]["comment"], "Incomplete evidence")

    def test_duplicate_request_denied(self):
        self.request()
        with self.assertRaises(ValueError):
            self.request()

    def test_duplicate_decision_denied(self):
        self.request()
        self.engine.decide(self.doc.doctype, self.doc.name, "Approved", 2)
        with self.assertRaises(ValueError):
            self.engine.decide(self.doc.doctype, self.doc.name, "Approved", 2)

    def test_transition_role_required(self):
        self.engine.roles = lambda: {"Administration User"}
        with self.assertRaises(PermissionError):
            self.request()

    def test_condition_failure_blocks_request(self):
        self.transition.conditions = '[{"field":"priority","op":"eq","value":"Critical"}]'
        with self.assertRaises(ValueError):
            self.request()

    def test_unauthorized_approval_denied(self):
        self.request()
        self.engine._authorized = lambda *a: (False, None)
        with self.assertRaises(PermissionError):
            self.engine.decide(self.doc.doctype, self.doc.name, "Approved", 2)

    def test_multi_step_stays_pending_until_last(self):
        self.policy.approval_bands.append(Row(transition_action="Complete", step_number=2))
        self.request()
        self.engine.decide(self.doc.doctype, self.doc.name, "Approved", 2)
        self.assertEqual(self.run.approval_step, 2)
        self.assertEqual(self.run.current_state, "Draft")
        self.engine.decide(self.doc.doctype, self.doc.name, "Approved", 3)
        self.assertEqual(self.run.current_state, "Done")

    def test_same_person_cannot_approve_two_steps(self):
        self.request()
        self.frappe.get_all = lambda *a, **kw: [Row(actor="approver@example.com", revision="2")]
        self.db.get_value = lambda *a, **kw: "2"
        with self.assertRaises(ValueError):
            self.engine.decide(self.doc.doctype, self.doc.name, "Approved", 2)

    def test_delegator_cannot_repeat_under_a_delegate(self):
        self.request()
        self.frappe.get_all = lambda *a, **kw: [Row(actor="original@example.com", revision="2")]
        self.db.get_value = lambda *a, **kw: "2"
        self.engine._authorized = lambda *a: (True, "original@example.com")
        with self.assertRaises(ValueError):
            self.engine.decide(self.doc.doctype, self.doc.name, "Approved", 2)

    def test_non_approval_transition_writes_audit(self):
        self.transition.approval_required = 0
        self.request()
        self.assertEqual(self.run.current_state, "Done")
        self.assertEqual(self.records[-1]["action"], "Complete")

    def test_protected_audit_cannot_be_forged(self):
        with self.assertRaises(PermissionError):
            self.engine.Audit().before_insert()
        with self.assertRaises(PermissionError):
            self.engine.Audit().validate()
        with self.assertRaises(PermissionError):
            self.engine.Audit().on_trash()

    def test_financial_and_legacy_targets_denied(self):
        for target in ["GL Entry", "Stock Entry", "Asset", "Material Request", "ADM Trip"]:
            with self.assertRaises(ValueError):
                self.engine.key(target, "TEST")

    def test_lock_uses_bound_name(self):
        calls = []
        self.db.sql = lambda *args: calls.append(args) or [("x",)]
        self.engine._lock("ADM Facility Ticket", "x'; DELETE FROM tabUser;--")
        self.assertEqual(calls[0][1], ("x'; DELETE FROM tabUser;--",))
        self.assertNotIn("DELETE", calls[0][0])

    def test_stale_revision_is_rejected_by_locked_load(self):
        self.db.get_value = lambda *a, **kw: "RUN"
        self.frappe.get_doc = lambda dt, name: self.doc if dt == self.doc.doctype else self.run
        with self.assertRaises(ValueError):
            self.original_load(self.doc.doctype, self.doc.name, 0)

    def test_valid_revision_load_returns_policy(self):
        self.db.get_value = lambda *a, **kw: "RUN"
        self.frappe.get_doc = lambda dt, name: (self.doc if dt == self.doc.doctype else
            self.run if dt == "ADM Workflow Run" else self.policy)
        doc, run, policy = self.original_load(self.doc.doctype, self.doc.name, 1)
        self.assertEqual(policy.name, "POLICY")
