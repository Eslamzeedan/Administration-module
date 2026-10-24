import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)


class TestCompanySecurity(unittest.TestCase):
    def setUp(self):
        fake = types.ModuleType("frappe")
        fake.session = Row(user="employee")
        fake.db = types.SimpleNamespace(escape=lambda value: "'" + value.replace("'", "''") + "'")
        fake.PermissionError = PermissionError
        fake.throw = lambda message, exc=ValueError: (_ for _ in ()).throw(exc(message))
        v3 = types.ModuleType("eup_administration.v3.security")
        self.employee = Row(company="A", department="IT")
        self.roles = {"Administration User"}
        v3.active_employee = lambda *a: self.employee
        v3.roles = lambda *a: self.roles
        with patch.dict(sys.modules, {"frappe": fake, "eup_administration.v3.security": v3}):
            spec = importlib.util.spec_from_file_location("v4_company_security", ROOT / "eup_administration/v4/security.py")
            self.security = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.security)
        self.doc = Row(company="A", requested_by="employee", assigned_to=None, workflow_policy=None)

    def test_employee_own_draft_read_write(self):
        self.assertTrue(self.security.operation_permission(self.doc, ptype="read"))
        self.assertTrue(self.security.operation_permission(self.doc, ptype="write"))

    def test_started_document_denies_direct_write(self):
        self.doc.workflow_policy = "policy"
        self.assertFalse(self.security.operation_permission(self.doc, ptype="write"))

    def test_cross_company_manager_denied(self):
        self.roles = {"Administration Manager"}
        self.doc.company = "B"
        self.assertFalse(self.security.operation_permission(self.doc, ptype="read"))
        self.assertFalse(self.security.operation_permission(self.doc, ptype="write"))

    def test_unrelated_employee_denied(self):
        self.doc.requested_by = "other"
        self.assertFalse(self.security.operation_permission(self.doc, ptype="read"))

    def test_assignee_read_but_no_draft_write(self):
        self.doc.requested_by = "other"
        self.doc.assigned_to = "employee"
        self.assertTrue(self.security.operation_permission(self.doc, ptype="read"))
        self.assertFalse(self.security.operation_permission(self.doc, ptype="write"))

    def test_disabled_employee_denied(self):
        self.employee = None
        self.assertFalse(self.security.operation_permission(self.doc, ptype="read"))
        self.assertEqual(self.security.query_for("ADM Facility Ticket"), "1=0")

    def test_query_contains_company_and_ownership(self):
        query = self.security.query_for("ADM Facility Ticket")
        self.assertIn("company", query)
        self.assertIn("'A'", query)
        self.assertIn("requested_by", query)
        self.assertIn("assigned_to", query)

    def test_recipient_query_scoped(self):
        self.assertIn("recipient", self.security.query_for("ADM Parcel"))

    def test_manager_query_keeps_company(self):
        self.roles = {"Administration Manager"}
        query = self.security.query_for("ADM Facility Ticket")
        self.assertIn("'A'", query)
        self.assertNotIn("requested_by", query)

    def test_escalations_require_role_and_company(self):
        doc = Row(company="A", escalation_role="Administration Manager")
        self.assertFalse(self.security.escalation_permission(doc, ptype="read"))
        self.roles = {"Administration Manager"}
        self.assertTrue(self.security.escalation_permission(doc, ptype="read"))
        doc.company = "B"
        self.assertFalse(self.security.escalation_permission(doc, ptype="read"))
