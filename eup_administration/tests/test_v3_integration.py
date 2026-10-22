"""Real-bench schema smoke tests; guarded to avoid touching a live site."""
import frappe
from eup_administration.tests.base import AdministrationIntegrationTestCase


class TestV3Integration(AdministrationIntegrationTestCase):
    def test_v3_schema_and_navigation(self):
        for slug in (
            "ADM Request Registry", "ADM General Service Request",
            "ADM Approval Policy", "ADM Approval Case", "ADM Approval Decision",
            "ADM SLA Policy", "ADM Stock Count", "ADM Custody Handover",
            "ADM Meeting Checkin", "ADM Vehicle Document", "ADM Purchasing Link"
        ):
            self.assertTrue(frappe.db.exists("DocType", slug), slug)
            self.assertTrue(frappe.get_meta(slug).get("fields") is not None)
        self.assertTrue(frappe.db.exists("Workspace", "EuP Administration v3"))
        self.assertTrue(frappe.db.exists("Workspace Sidebar", "EuP Administration v3"))
        self.assertEqual(frappe.db.get_value("Desktop Icon", "EuP Administration v3", "parent_icon"), "ERPNext")

    def test_integrations_disabled_before_acceptance(self):
        for name in ("enable_email_notifications", "enable_purchasing_bridge",
                     "enable_accounting_bridge", "enable_nextcloud_links"):
            self.assertFalse(frappe.db.get_single_value("ADM Settings", name))
