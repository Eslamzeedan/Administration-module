"""UI context must describe, never expand, the logged-in user's company access."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class TestDashboardContext(unittest.TestCase):
    def setUp(self):
        self.user = "employee"
        self.employee = None
        self.manager = False
        frappe = types.ModuleType("frappe")
        frappe.session = types.SimpleNamespace(user=self.user)
        frappe.whitelist = lambda **kwargs: lambda fn: fn
        def get_value(doctype, filters, fields, **kwargs):
            self.assertEqual(doctype, "Employee")
            self.assertEqual(filters, {"user_id": frappe.session.user, "status": "Active"})
            return self.employee
        frappe.db = types.SimpleNamespace(get_value=get_value)
        utils = types.ModuleType("frappe.utils")
        for name in ("getdate", "get_datetime", "today", "now_datetime", "add_days", "get_url"):
            setattr(utils, name, lambda *args: None)
        security = types.ModuleType("eup_administration.v4.security")
        security.manager = lambda company: self.manager
        security.require_company = lambda company: None
        workflow = types.ModuleType("eup_administration.v4.workflow")
        workflow._authorized = lambda *args: (False, None)
        workflow._case = lambda *args: None
        with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils,
                "eup_administration.v4.security": security, "eup_administration.v4.workflow": workflow}):
            spec = importlib.util.spec_from_file_location("dashboard_context_under_test", ROOT / "eup_administration/v4/dashboard.py")
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.frappe = frappe

    def test_administrator_can_choose_company_without_employee(self):
        self.frappe.session.user = "Administrator"
        result = self.module.context()
        self.assertFalse(result["requires_employee"])
        self.assertTrue(result["can_choose_company"])
        self.assertIsNone(result["company"])

    def test_role_alone_does_not_bypass_missing_employee(self):
        self.manager = True
        result = self.module.context()
        self.assertTrue(result["requires_employee"])
        self.assertFalse(result["can_choose_company"])
        self.assertFalse(result["can_manage"])
        self.assertIsNone(result["company"])

    def test_employee_context_uses_only_linked_company(self):
        self.employee = types.SimpleNamespace(company="Company A")
        result = self.module.context()
        self.assertEqual(result["company"], "Company A")
        self.assertFalse(result["requires_employee"])
        self.assertFalse(result["can_manage"])
        self.assertFalse(result["can_choose_company"])

    def test_manager_must_still_have_employee_company(self):
        self.employee = types.SimpleNamespace(company="Company A")
        self.manager = True
        result = self.module.context()
        self.assertTrue(result["can_manage"])
        self.assertEqual(result["company"], "Company A")
