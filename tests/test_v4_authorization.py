"""Exercise the unchanged v3 authorization primitive reused by the designer."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)


class TestApprovalAuthorization(unittest.TestCase):
    def setUp(self):
        self.role_map = {"actor": {"Manager"}, "delegator": {"Manager"}, "requester": {"Manager"}}
        self.employees = {"actor": Row(company="A", department="IT"),
                          "delegator": Row(company="A", department="IT")}
        self.delegations = []
        fake = types.ModuleType("frappe")
        fake.whitelist = lambda **kw: lambda f: f
        fake.get_all = lambda *a, **kw: self.delegations
        utils = types.ModuleType("frappe.utils")
        utils.now_datetime = lambda: datetime(2026, 10, 22, 10)
        utils.get_datetime = lambda value: datetime.fromisoformat(value) if isinstance(value, str) else value
        security = types.ModuleType("eup_administration.v3.security")
        security.active_employee = lambda user=None: self.employees.get(user)
        security.roles = lambda user=None: self.role_map.get(user, set())
        security.is_manager = lambda *a: False
        with patch.dict(sys.modules, {"frappe": fake, "frappe.utils": utils,
                "eup_administration.v3.security": security}):
            spec = importlib.util.spec_from_file_location("v3_auth_for_v4", ROOT / "eup_administration/v3/approval.py")
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.step = Row(approver_role="Manager", same_company=1, same_department=1, allow_delegation=1)
        self.case = Row(requested_by="requester", company="A", department="IT")

    def authorized(self):
        return self.module._authorized(self.step, self.case, "actor")

    def delegation(self, **kw):
        self.role_map["actor"] = set()
        self.delegations = [Row(delegator="delegator", department="IT",
            valid_from="2026-10-01", valid_until="2026-10-31", **kw)]

    def test_correct_role_scope_allowed(self):
        self.assertEqual(self.authorized(), (True, None))

    def test_self_approval_denied(self):
        self.case.requested_by = "actor"
        self.assertFalse(self.authorized()[0])

    def test_other_company_denied(self):
        self.employees["actor"] = Row(company="B", department="IT")
        self.assertFalse(self.authorized()[0])

    def test_other_department_denied(self):
        self.employees["actor"] = Row(company="A", department="Other")
        self.assertFalse(self.authorized()[0])

    def test_active_delegation_allowed(self):
        self.delegation()
        self.assertEqual(self.authorized(), (True, "delegator"))

    def test_expired_delegation_denied(self):
        self.delegation()
        self.delegations[0]["valid_until"] = "2026-10-21"
        self.assertFalse(self.authorized()[0])

    def test_delegation_from_requester_denied(self):
        self.delegation()
        self.case.requested_by = "delegator"
        self.assertFalse(self.authorized()[0])

    def test_cross_company_delegator_denied(self):
        self.delegation()
        self.employees["delegator"] = Row(company="B", department="IT")
        self.assertFalse(self.authorized()[0])

    def test_disabled_delegation_step_denied(self):
        self.delegation()
        self.step.allow_delegation = 0
        self.assertFalse(self.authorized()[0])
