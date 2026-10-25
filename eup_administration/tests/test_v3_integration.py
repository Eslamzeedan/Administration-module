"""Real-bench schema smoke tests; guarded to avoid touching a live site."""
import hashlib
import json
import frappe
from eup_administration.tests.base import AdministrationIntegrationTestCase


PROTECTED = (
    "GL Entry", "Journal Entry", "Payment Entry", "Payment Request", "Expense Claim",
    "Purchase Invoice", "Purchase Order", "Purchase Receipt", "Material Request",
    "Stock Entry", "Stock Ledger Entry", "Bin", "Asset", "Asset Movement", "Asset Repair",
    "Asset Capitalization", "Item", "Warehouse", "Sales Invoice", "Delivery Note",
)
REQUIRED_ERP_TABLES = (
    "GL Entry", "Journal Entry", "Payment Entry", "Purchase Invoice",
    "Stock Ledger Entry", "Stock Entry", "Material Request", "Purchase Order",
)


def protected_snapshot():
    """Include table absence so setup cannot silently create an optional table."""
    result = {}
    for doctype in PROTECTED:
        if not frappe.db.table_exists(doctype, cached=False):
            result[doctype] = {"exists": False}
            continue
        # Identifiers come only from PROTECTED; rows include all persisted fields.
        rows = frappe.db.sql("SELECT * FROM `tab" + doctype + "` ORDER BY name", as_dict=True)
        result[doctype] = {
            "exists": True, "count": len(rows),
            "sha256": hashlib.sha256(
                json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest(),
        }
    return result


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
        before = protected_snapshot()
        for doctype in REQUIRED_ERP_TABLES:
            self.assertTrue(before[doctype]["exists"],
                            "Required ERPNext fixture table is missing: " + doctype)
        from eup_administration.v3.bootstrap import configure
        from eup_administration.v3.registry import rebuild_registry
        configure()
        rebuild_registry()
        after = protected_snapshot()
        self.assertEqual(after, before)
