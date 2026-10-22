"""Real-bench schema smoke tests; guarded to avoid touching a live site."""
import frappe
from eup_administration.tests.base import AdministrationIntegrationTestCase


class TestV3Integration(AdministrationIntegrationTestCase):
    def test_v3_schema_and_navigation(self):
        for slug in (
            "ADM Request Registry", "ADM General Service Request",
            "ADM Approval Policy", "ADM Approval Case", "ADM Approval Decision",
            "ADM SLA Policy", "ADM Stock Count", "ADM Custody Handover",
            "ADM Meeting Checkin", "ADM Vehicle Document"
        ):
            self.assertTrue(frappe.db.exists("DocType", slug), slug)
            self.assertTrue(frappe.get_meta(slug).get("fields") is not None)
        self.assertTrue(frappe.db.exists("Workspace", "EuP Administration v3"))
        self.assertTrue(frappe.db.exists("Workspace Sidebar", "EuP Administration v3"))
        self.assertEqual(frappe.db.get_value("Desktop Icon", "EuP Administration v3", "parent_icon"), "ERPNext")

    def test_integrations_disabled_before_acceptance(self):
        for name in ("enable_email_notifications", "enable_nextcloud_links"):
            self.assertFalse(frappe.db.get_single_value("ADM Settings", name))

    def test_financial_and_procurement_tables_unchanged_by_admin_setup(self):
        """All financial records are outside Administration's write boundary."""
        tracked = ("GL Entry", "Journal Entry", "Payment Entry", "Expense Claim",
                   "Purchase Invoice", "Stock Ledger Entry", "Stock Entry",
                   "Material Request", "Purchase Order")
        before = {dt: frappe.db.count(dt) for dt in tracked}
        from eup_administration.v3.bootstrap import configure
        from eup_administration.v3.registry import rebuild_registry
        configure()
        rebuild_registry()
        after = {dt: frappe.db.count(dt) for dt in tracked}
        self.assertEqual(after, before)
