"""Offline contract checks for the all-in-one bundle; real database acceptance is separate."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "eup_administration"
DOCTYPE = APP / "eup_administration" / "doctype"

V3_DOCS = (
    "adm_request_registry", "adm_general_service_request", "adm_approval_policy",
    "adm_approval_step", "adm_approval_case", "adm_approval_decision",
    "adm_approval_delegation", "adm_sla_policy", "adm_request_event",
    "adm_notification_outbox", "adm_settings", "adm_vehicle_document",
    "adm_vehicle_incident", "adm_meeting_checkin", "adm_stock_count",
    "adm_stock_count_line", "adm_consumable_erp_mapping",
    "adm_purchasing_link", "adm_custody_handover", "adm_request_feedback",
)

class TestV3Bundle(unittest.TestCase):
    def test_all_new_doctype_packages(self):
        for slug in V3_DOCS:
            with self.subTest(doctype=slug):
                path = DOCTYPE / slug / (slug + ".json")
                schema = json.loads(path.read_text())
                controller = DOCTYPE / slug / (slug + ".py")
                self.assertTrue(controller.is_file())
                self.assertTrue((path.parent / "__init__.py").is_file())
                self.assertEqual(schema["module"], "EuP Administration")
                self.assertEqual(schema["field_order"], [x["fieldname"] for x in schema["fields"]])
                py = ast.parse(controller.read_text())
                expected = schema["name"].replace(" ", "")
                self.assertTrue(any(isinstance(n, ast.ClassDef) and n.name == expected for n in py.body))

    def test_mutable_ledger_not_open_to_users(self):
        for slug in ("adm_request_event", "adm_notification_outbox", "adm_approval_decision",
                     "adm_request_registry", "adm_purchasing_link", "adm_request_feedback"):
            schema = json.loads((DOCTYPE / slug / (slug + ".json")).read_text())
            self.assertFalse(any(x.get("create") or x.get("write") or x.get("delete") for x in schema["permissions"]))

    def test_sensitive_bridge_flags_disabled(self):
        x = json.loads((DOCTYPE / "adm_settings" / "adm_settings.json").read_text())
        fields = {f["fieldname"]: f for f in x["fields"]}
        for name in ("enable_v3_requests", "enable_email_notifications", "enable_purchasing_bridge",
                     "enable_accounting_bridge", "enable_nextcloud_links", "enable_auto_release_meetings"):
            self.assertEqual(fields[name]["default"], "0")

    def test_erpnext_side_navigation(self):
        x = json.loads((APP / "desktop_icon" / "eup_administration_v3.json").read_text())
        self.assertEqual(x["parent_icon"], "ERPNext")
        self.assertEqual(x["link_type"], "Workspace Sidebar")
        nav = json.loads((APP / "workspace_sidebar" / "eup_administration_v3.json").read_text())
        self.assertTrue(any(s.get("link_to") == "ADM General Service Request" for s in nav["items"]))
        self.assertTrue(any(s.get("link_to") == "ADM Stock Count" for s in nav["items"]))

    def test_all_v3_sources_parse(self):
        for path in (APP / "v3").glob("*.py"):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(encoding="utf-8"))

    def test_api_mutations_are_post_only(self):
        for name, funcs in {
            "general": {"submit", "assign", "start", "complete", "close", "cancel"},
            "approval": {"decide"}, "inventory": {"submit_count", "approve_count", "post_count"},
            "meetings": {"check_in"}, "purchasing": {"create_material_request"},
            "custody": {"confirm"}, "vehicle_documents": {"verify"}, "feedback": {"submit_feedback"},
        }.items():
            code = (APP / "v3" / (name + ".py")).read_text()
            mod = ast.parse(code)
            for fn in (n for n in mod.body if isinstance(n, ast.FunctionDef) and n.name in funcs):
                self.assertTrue(any("POST" in ast.unparse(d) and "whitelist" in ast.unparse(d)
                                    for d in fn.decorator_list), name + "." + fn.name)
                funcs.discard(fn.name)
            self.assertFalse(funcs, "Missing protected endpoint(s) in " + name + ": " + repr(funcs))

    def test_no_legacy_doctype_schema_removed(self):
        legacy = ("adm_trip", "adm_vehicle", "adm_driver", "adm_meeting_booking",
                  "adm_service_request", "adm_supply_request", "adm_consumable_transaction")
        for slug in legacy:
            self.assertTrue((DOCTYPE / slug / (slug + ".json")).exists())
