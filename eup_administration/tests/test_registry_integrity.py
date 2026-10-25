"""Real v16 naming, deduplication and administrative-only integrity checks."""
import frappe
from eup_administration.tests.base import AdministrationIntegrationTestCase
from eup_administration.tests.test_v3_integration import protected_snapshot
from eup_administration.v3 import registry
from eup_administration import services


class TestRegistryIntegrity(AdministrationIntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.before = protected_snapshot()
        self.addCleanup(self.assert_protected_unchanged)

    def assert_protected_unchanged(self):
        frappe.set_user("Administrator")
        self.assertEqual(self.before, protected_snapshot())

    def booking_fixture(self):
        return self.booking("2099-02-01 10:00:00", "2099-02-01 11:00:00")

    def test_repeated_sync_and_cancel_keep_one_current_row(self):
        doc = self.booking_fixture()
        filters = {"reference_doctype": doc.doctype, "reference_name": doc.name}
        registry.sync_document(doc)
        registry.sync_document(doc)
        self.assertEqual(frappe.db.count("ADM Request Registry", filters), 1)
        self.assertTrue(frappe.db.exists("ADM Request Registry", registry.registry_key(doc.doctype, doc.name)))
        self.assertEqual(frappe.db.count("ADM Request Event", filters), 1)
        services.close_booking(doc.name, "Cancelled")
        row = frappe.get_doc("ADM Request Registry", registry.registry_key(doc.doctype, doc.name))
        self.assertEqual(row.source_status, "Cancelled")
        self.assertEqual(frappe.db.count("ADM Request Registry", filters), 1)
        self.assertEqual(frappe.db.count("ADM Request Event", filters), 2)

    def test_legacy_index_repair_is_idempotent_and_preserves_events(self):
        doc = self.booking_fixture()
        filters = {"reference_doctype": doc.doctype, "reference_name": doc.name}
        original_events = frappe.get_all("ADM Request Event", filters=filters, pluck="name", order_by="name")
        canonical = frappe.get_doc("ADM Request Registry", registry.registry_key(doc.doctype, doc.name))
        values = {field: canonical.get(field) for field in canonical.meta.get_valid_columns()
                  if field not in {"name", "creation", "modified", "modified_by", "owner", "docstatus", "idx"}}
        frappe.db.delete("ADM Request Registry", filters)
        for _ in range(2):
            frappe.get_doc({"doctype": "ADM Request Registry", **values}).insert(ignore_permissions=True)
        self.assertEqual(frappe.db.count("ADM Request Registry", filters), 2)
        for _ in range(2):
            registry.rebuild_registry()
        self.assertEqual(frappe.db.count("ADM Request Registry", filters), 1)
        self.assertEqual(frappe.get_all("ADM Request Event", filters=filters, pluck="name", order_by="name"), original_events)
        self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "status"), "Confirmed")

    def test_explicit_rebuild_can_run_under_migration_flag(self):
        doc = self.booking_fixture()
        old = frappe.flags.in_migrate
        try:
            frappe.flags.in_migrate = True
            registry.rebuild_registry()
        finally:
            frappe.flags.in_migrate = old
        self.assertTrue(frappe.db.exists("ADM Request Registry", registry.registry_key(doc.doctype, doc.name)))
