"""Exercise integration-test isolation and protected snapshots without a live DB."""
from copy import deepcopy
import importlib.util
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


class TestProtectedSetupSnapshot(unittest.TestCase):
    def setUp(self):
        self.frappe = types.ModuleType("frappe")
        base = types.ModuleType("eup_administration.tests.base")
        base.AdministrationIntegrationTestCase = unittest.TestCase
        bootstrap = types.ModuleType("eup_administration.v3.bootstrap")
        bootstrap.configure = Mock()
        registry = types.ModuleType("eup_administration.v3.registry")
        registry.rebuild_registry = Mock()
        self.configure = bootstrap.configure
        self.rebuild = registry.rebuild_registry
        modules = patch.dict(sys.modules, {
            "frappe": self.frappe, "eup_administration.tests.base": base,
            "eup_administration.v3.bootstrap": bootstrap,
            "eup_administration.v3.registry": registry,
        })
        modules.start()
        self.addCleanup(modules.stop)
        self.module = load_module("v3_snapshot_under_test",
                                 "eup_administration/tests/test_v3_integration.py")
        self.rows = {dt: [] for dt in self.module.REQUIRED_ERP_TABLES}
        self.rows["GL Entry"] = [{"name": "GL-1", "debit": 10, "credit": 0}]
        self.queries = []

        def sql(query, as_dict=False):
            doctype = query.split("`tab", 1)[1].split("`", 1)[0]
            self.queries.append(doctype)
            return deepcopy(self.rows[doctype])

        def table_exists(doctype, *, cached):
            self.assertFalse(cached)  # A stale table list must not mask table creation.
            return doctype in self.rows

        self.frappe.db = types.SimpleNamespace(table_exists=table_exists, sql=sql)

    def run_boundary_test(self):
        case = self.module.TestV3Integration(
            "test_financial_and_procurement_tables_unchanged_by_admin_setup")
        case.test_financial_and_procurement_tables_unchanged_by_admin_setup()

    def test_missing_optional_table_still_runs_both_admin_actions(self):
        self.run_boundary_test()
        self.configure.assert_called_once_with()
        self.rebuild.assert_called_once_with()
        self.assertNotIn("Expense Claim", self.queries)
        snapshot = self.module.protected_snapshot()
        self.assertEqual(snapshot["Expense Claim"], {"exists": False})
        self.assertEqual(set(snapshot), set(self.module.PROTECTED))

    def test_same_count_content_write_is_detected(self):
        self.configure.side_effect = lambda: self.rows["GL Entry"][0].update(debit=999)
        with self.assertRaises(AssertionError):
            self.run_boundary_test()

    def test_optional_table_creation_is_detected(self):
        self.configure.side_effect = lambda: self.rows.update({"Expense Claim": []})
        with self.assertRaises(AssertionError):
            self.run_boundary_test()

    def test_table_removal_is_detected(self):
        self.configure.side_effect = lambda: self.rows.pop("Payment Entry")
        with self.assertRaises(AssertionError):
            self.run_boundary_test()

    def test_missing_required_erpnext_table_fails_before_setup(self):
        self.rows.pop("GL Entry")
        with self.assertRaisesRegex(AssertionError, "Required ERPNext fixture table"):
            self.run_boundary_test()
        self.configure.assert_not_called()
        self.rebuild.assert_not_called()


class TestGeneralFlowFixtureIsolation(unittest.TestCase):
    def test_policy_and_setting_cleanup_after_error_and_repeat_run(self):
        class FixtureDB:
            def __init__(self):
                self.state = {"policies": [{"company": "Other fixture"}], "enabled": 0}
                self.points = {}

            def savepoint(self, name):
                self.points[name] = deepcopy(self.state)

            def rollback(self, *, save_point):
                self.state = deepcopy(self.points[save_point])

            def get_single_value(self, *args):
                return self.state["enabled"]

            def set_single_value(self, doctype, field, value):
                self.state["enabled"] = value

        db = FixtureDB()
        initial = deepcopy(db.state)
        frappe = types.ModuleType("frappe")
        frappe.db = db
        frappe.set_user = Mock()

        def get_doc(values):
            doc = types.SimpleNamespace(**values)
            def insert(**kwargs):
                db.state["policies"].append(deepcopy(values))
                return doc
            doc.insert = insert
            return doc
        frappe.get_doc = get_doc

        class FixtureBase(unittest.TestCase):
            def setUp(self):
                self.company = "Isolated"

        base = types.ModuleType("eup_administration.tests.base")
        base.AdministrationIntegrationTestCase = FixtureBase
        v3 = types.ModuleType("eup_administration.v3")
        v3.general = types.ModuleType("eup_administration.v3.general")
        v3.approval = types.ModuleType("eup_administration.v3.approval")
        with patch.dict(sys.modules, {
            "frappe": frappe, "eup_administration.tests.base": base,
            "eup_administration.v3": v3,
        }):
            module = load_module("v3_flow_fixture_under_test",
                                 "eup_administration/tests/test_v3_general_flow.py")

            class Case(module.TestV3GeneralFlow):
                fail_body = False

                def runTest(self):
                    scoped = [p for p in db.state["policies"] if p["company"] == self.company]
                    self.assertEqual(scoped, [])
                    self.make_policy()
                    self.assertEqual(db.state["enabled"], 1)
                    if self.fail_body:
                        raise RuntimeError("simulated test error")

            failed = Case("runTest")
            failed.fail_body = True
            first = unittest.TestResult()
            failed.run(first)
            self.assertEqual(len(first.errors), 1)
            self.assertIn("simulated test error", first.errors[0][1])
            self.assertEqual(db.state, initial)

            second = unittest.TestResult()
            Case("runTest").run(second)
            self.assertTrue(second.wasSuccessful(), second.errors)
            self.assertEqual(db.state, initial)
