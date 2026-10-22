import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "eup_administration"
DT = APP / "eup_administration/doctype"


class TestV4Contracts(unittest.TestCase):
    def test_post_only_mutations(self):
        expected = {"workflow": {"start", "transition", "decide"},
                    "operations": {"acknowledge_parcel", "release_booking", "feedback", "update_details", "assign_operator"}, "portal": {"create_request"}}
        for module, names in expected.items():
            tree = ast.parse((APP / "v4" / (module + ".py")).read_text())
            found = set()
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name in names:
                    found.add(node.name)
                    self.assertTrue(any("whitelist" in ast.unparse(d) and "POST" in ast.unparse(d) for d in node.decorator_list))
            self.assertEqual(found, names)

    def test_no_runtime_financial_targets(self):
        from eup_administration.v4.rules import OPERATIONS
        forbidden = {"GL Entry", "Journal Entry", "Payment Entry", "Payment Request", "Material Request",
                     "Purchase Invoice", "Purchase Order", "Stock Entry", "Stock Ledger Entry", "Asset",
                     "Expense Claim", "Item", "Warehouse"}
        for file in (APP / "v4").glob("*.py"):
            tree = ast.parse(file.read_text())
            literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            self.assertFalse(literals & forbidden, file.name)
        self.assertFalse(set(OPERATIONS) & forbidden)

    def test_internal_ledgers_have_no_user_writes(self):
        for name in ["adm_workflow_run", "adm_workflow_audit", "adm_operation_feedback", "adm_sla_escalation"]:
            schema = json.loads((DT / name / (name + ".json")).read_text())
            self.assertTrue(any(f["fieldname"] == "company" for f in schema["fields"]))
            self.assertFalse(any(p.get("create") or p.get("write") or p.get("delete") for p in schema["permissions"]))

    def test_workflow_cannot_target_legacy_or_erpnext(self):
        from eup_administration.v4.rules import OPERATIONS
        policy = json.loads((DT / "adm_workflow_policy/adm_workflow_policy.json").read_text())
        fields = {f["fieldname"]: f for f in policy["fields"]}
        self.assertEqual(set(fields["target_doctype"]["options"].splitlines()), set(OPERATIONS))
        self.assertTrue(fields["enabled_key"]["unique"])

    def test_all_operation_permission_hooks_present(self):
        from eup_administration.v4.rules import OPERATIONS
        hooks = (APP / "hooks.py").read_text()
        for dt in OPERATIONS:
            self.assertIn('has_permission["' + dt + '"]', hooks)
            self.assertIn('permission_query_conditions["' + dt + '"]', hooks)

    def test_jobs_require_opt_in(self):
        for file in ["operations", "jobs"]:
            self.assertIn('frappe.conf.get("adm_v4_jobs_enabled")', (APP / "v4" / (file + ".py")).read_text())
