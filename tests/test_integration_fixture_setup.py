"""Offline checks for the real integration fixture lifecycle; no Frappe install needed."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestIntegrationFixtureSetup(unittest.TestCase):
    def setUp(self):
        self.parent_calls = []
        calls = self.parent_calls

        class IntegrationTestCase(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                calls.append("setUpClass")

            def setUp(self):
                calls.append("setUp")

        self.frappe = types.ModuleType("frappe")
        self.frappe.local = types.SimpleNamespace(site="test-administration-v4.local")
        self.frappe.conf = {"adm_allow_integration_tests": 1, "adm_test_company": "Isolated"}
        self.frappe.db = types.SimpleNamespace(exists=Mock(return_value=False))
        self.frappe.set_user = Mock()
        tests = types.ModuleType("frappe.tests")
        tests.IntegrationTestCase = IntegrationTestCase
        self.modules = patch.dict(sys.modules, {"frappe": self.frappe, "frappe.tests": tests})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.base = load_module("fixture_base_under_test", "eup_administration/tests/base.py")

    def test_unsafe_site_rejected_before_parent_fixture_generation(self):
        for site, enabled in (("erpnext-v16.eup-cairo.local", 1),
                              ("production.local", 1),
                              ("test-administration-v4.local", 0)):
            with self.subTest(site=site, enabled=enabled):
                self.frappe.local.site = site
                self.frappe.conf["adm_allow_integration_tests"] = enabled
                with self.assertRaises(AssertionError):
                    self.base.AdministrationIntegrationTestCase.setUpClass()
        self.assertEqual(self.parent_calls, [])

    def test_isolated_site_preserves_parent_lifecycle(self):
        self.base.AdministrationIntegrationTestCase.setUpClass()
        self.assertEqual(self.parent_calls, ["setUpClass"])

    def test_missing_company_fails_without_skip_or_generated_company(self):
        case = self.base.AdministrationIntegrationTestCase()
        with self.assertRaisesRegex(AssertionError, "existing Company"):
            case.setUp()
        case.doCleanups()
        self.frappe.db.exists.assert_called_once_with("Company", "Isolated")
        self.assertEqual(self.parent_calls, ["setUp"])

    def test_trip_explicit_fixtures_cut_every_recursive_link_edge(self):
        services = types.ModuleType("eup_administration.services")
        with patch.dict(sys.modules, {"eup_administration.tests.base": self.base,
                                      "eup_administration.services": services}):
            module = load_module("trip_fixture_under_test",
                "eup_administration/eup_administration/doctype/adm_trip/test_adm_trip.py")
        schema = json.loads((ROOT / "eup_administration/eup_administration/doctype/adm_trip/adm_trip.json").read_text())
        links = {field["options"] for field in schema["fields"] if field["fieldtype"] == "Link"}
        # Frappe v16 applies this override before recursing into dependency metadata.
        self.assertEqual(set(module.IGNORE_TEST_RECORD_DEPENDENCIES), links)
        self.assertTrue(issubclass(module.TestADMTrip, self.base.AdministrationIntegrationTestCase))
