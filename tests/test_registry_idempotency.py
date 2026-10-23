"""Execute registry hooks against a DB boundary that reproduces v16 hash autonaming."""
from copy import deepcopy
from datetime import datetime
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
    def __getattr__(self, name):
        return self.get(name)
    def __setattr__(self, name, value):
        self[name] = value


class TestRegistryIdentity(unittest.TestCase):
    def setUp(self):
        self.tables = {"ADM Request Registry": {}, "ADM Request Event": {}, "ADM Approval Case": {},
                       "ADM Request Feedback": {}}
        self.source = Row(doctype="ADM Meeting Booking", name="MEET-1", company="Fixture",
                          organizer="requester", title="Fixture meeting", status="Confirmed")
        self.sources = {("ADM Meeting Booking", "MEET-1"): self.source}
        self.calls = []
        self.serial = 0
        owner = self

        class Document(Row):
            def insert(self, ignore_permissions=False, set_name=None):
                owner.serial += 1
                # Deliberately discard a document.name without explicit set_name.
                self.name = set_name or "hash-" + str(owner.serial)
                if self.name in owner.tables[self.doctype]:
                    raise ValueError("duplicate primary key")
                owner.tables[self.doctype][self.name] = self
                return self
            def save(self, **kwargs):
                owner.tables[self.doctype][self.name] = self
                return self
            def check_permission(self, *args):
                return True

        self.Document = Document
        self.frappe = types.ModuleType("frappe")
        self.frappe.flags = Row(in_migrate=False)
        self.frappe.session = Row(user="Administrator")
        self.frappe.PermissionError = PermissionError
        self.frappe.throw = lambda message, exc=ValueError: (_ for _ in ()).throw(exc(message))
        self.frappe.whitelist = lambda **kwargs: lambda fn: fn
        self.frappe.get_roles = lambda *args: ["System Manager"]
        self.frappe.set_user = lambda value: setattr(self.frappe.session, "user", value)

        def matches(row, filters):
            return all(row.get(k) == v for k, v in filters.items())
        def exists(doctype, filters):
            if doctype == "DocType":
                return True
            rows = self.tables.get(doctype, {})
            return filters in rows if isinstance(filters, str) else any(matches(r, filters) for r in rows.values())
        def get_all(doctype, filters=None, fields=None, pluck=None, **kwargs):
            if doctype in self.tables:
                rows = [Row(r) for r in self.tables[doctype].values() if matches(r, filters or {})]
            else:
                rows = [Row(doc) for (dt, _), doc in self.sources.items() if dt == doctype]
            return [r[pluck] for r in rows] if pluck else rows
        def get_doc(doctype, name=None):
            if isinstance(doctype, dict):
                return Document(deepcopy(doctype))
            if (doctype, name) in self.sources:
                return self.sources[(doctype, name)]
            return self.tables[doctype][name]
        def sql(query, values):
            self.calls.append(("sql", query, values))
            self.assertIn("FOR UPDATE", query)
            return [(values[0],)]
        def set_value(doctype, name, values, **kwargs):
            self.assertEqual(doctype, "ADM Request Registry")
            self.tables[doctype][name].update(deepcopy(values))
        def delete(doctype, filters):
            self.assertEqual(doctype, "ADM Request Registry")
            self.assertEqual(set(filters), {"name", "reference_doctype", "reference_name"})
            for name, row in list(self.tables[doctype].items()):
                if matches(row, filters):
                    del self.tables[doctype][name]

        self.frappe.db = types.SimpleNamespace(
            exists=exists, sql=sql, set_value=set_value, delete=delete,
            table_exists=lambda *args, **kwargs: True, get_single_value=lambda *args: 1)
        self.frappe.get_all = get_all
        self.frappe.get_doc = get_doc
        self.notify = Mock()
        notifications = types.ModuleType("eup_administration.v3.notifications")
        notifications.prepare_event = self.notify
        security = types.ModuleType("eup_administration.v3.security")
        security.active_employee = lambda *args: None
        security.is_manager = lambda *args: True
        security.roles = lambda *args: {"System Manager"}
        utils = types.ModuleType("frappe.utils")
        utils.now_datetime = lambda: datetime(2026, 10, 23, 12)
        utils.get_datetime = lambda value: value
        self.patches = patch.dict(sys.modules, {
            "frappe": self.frappe, "frappe.utils": utils,
            "eup_administration.v3.notifications": notifications,
            "eup_administration.v3.security": security,
        })
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.registry = self.load("registry_under_test", "eup_administration/v3/registry.py")
        self.module_patch = patch.dict(sys.modules, {"eup_administration.v3.registry": self.registry})
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)

    def load(self, name, relative):
        spec = importlib.util.spec_from_file_location(name, ROOT / relative)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_two_lifecycle_hooks_create_one_canonical_row_and_event(self):
        self.registry.sync_document(self.source)
        self.registry.sync_document(self.source)
        key = self.registry.registry_key(self.source.doctype, self.source.name)
        self.assertEqual(list(self.tables["ADM Request Registry"]), [key])
        self.assertEqual(len(self.tables["ADM Request Event"]), 1)
        self.notify.assert_called_once()

    def test_status_change_updates_same_row(self):
        self.registry.sync_document(self.source)
        self.source.status = "Cancelled"
        self.registry.sync_document(self.source)
        rows = list(self.tables["ADM Request Registry"].values())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].source_status, "Cancelled")
        events = list(self.tables["ADM Request Event"].values())
        self.assertEqual([e.event_type for e in events], ["Created", "Status Changed"])

    def test_legacy_duplicates_are_repaired_without_source_or_event_loss(self):
        for name in ("legacy-a", "legacy-b"):
            self.tables["ADM Request Registry"][name] = Row(
                name=name, reference_doctype=self.source.doctype, reference_name=self.source.name,
                source_status="Confirmed")
        self.tables["ADM Request Event"]["history"] = Row(name="history", event_type="Created")
        self.source.status = "Cancelled"
        source_before = deepcopy(self.source)
        self.registry.sync_document(self.source, emit_events=False)
        self.assertEqual(self.source, source_before)
        self.assertEqual(list(self.tables["ADM Request Event"]), ["history"])
        self.assertEqual(len(self.tables["ADM Request Registry"]), 1)
        self.assertEqual(next(iter(self.tables["ADM Request Registry"].values())).source_status, "Cancelled")
        self.notify.assert_not_called()

    def test_rebuild_runs_during_migrate_is_idempotent_and_emits_no_events(self):
        self.frappe.flags.in_migrate = True
        self.registry.sync_document(self.source)
        self.assertEqual(self.tables["ADM Request Registry"], {})
        for _ in range(2):
            self.assertEqual(self.registry.rebuild_registry()["ADM Meeting Booking"], 1)
        self.assertEqual(len(self.tables["ADM Request Registry"]), 1)
        self.assertEqual(self.tables["ADM Request Event"], {})
        self.notify.assert_not_called()

    def test_unrelated_key_collision_is_rejected(self):
        key = self.registry.registry_key(self.source.doctype, self.source.name)
        self.tables["ADM Request Registry"][key] = Row(name=key, reference_doctype="ADM Trip", reference_name="OTHER")
        with self.assertRaisesRegex(ValueError, "identity conflict"):
            self.registry.sync_document(self.source)
        self.assertEqual(self.tables["ADM Request Registry"][key].reference_name, "OTHER")

    def test_non_manager_cannot_rebuild(self):
        self.frappe.session.user = "requester"
        self.frappe.get_roles = lambda: ["Administration User"]
        with self.assertRaises(PermissionError):
            self.registry.rebuild_registry()
        self.assertEqual(self.calls, [])

    def test_unsupported_source_does_not_lock_or_write(self):
        self.registry.sync_document(Row(doctype="Purchase Order", name="PO-1"))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.tables["ADM Request Registry"], {})

    def test_approval_case_name_and_legacy_case_duplicate_detection(self):
        approval = self.load("approval_identity_under_test", "eup_administration/v3/approval.py")
        approval._policy = lambda doc: (Row(name="POLICY"), [])
        doc = Row(doctype="ADM General Service Request", name="REQ-1", company="Fixture", requested_by="requester")
        case = approval.create_case(doc)
        self.assertEqual(case.name, approval.case_name(doc.doctype, doc.name))
        with self.assertRaisesRegex(ValueError, "already exists"):
            approval.create_case(doc)
        self.tables["ADM Approval Case"].clear()
        self.tables["ADM Approval Case"]["legacy"] = self.Document(
            doctype="ADM Approval Case", name="legacy", reference_doctype=doc.doctype, reference_name=doc.name, status="Pending")
        with self.assertRaisesRegex(ValueError, "already exists"):
            approval.create_case(doc)
        approval.cancel_case(doc)
        self.assertEqual(self.tables["ADM Approval Case"]["legacy"].status, "Cancelled")

    def test_feedback_uses_deterministic_name_and_rejects_legacy_duplicate(self):
        self.source.status = "Completed"
        self.registry.sync_document(self.source, emit_events=False)
        self.frappe.session.user = "requester"
        feedback = self.load("feedback_identity_under_test", "eup_administration/v3/feedback.py")
        name = feedback.submit_feedback(self.source.doctype, self.source.name, 5)
        self.assertTrue(name.startswith("ADMFB-"))
        with self.assertRaisesRegex(ValueError, "already been submitted"):
            feedback.submit_feedback(self.source.doctype, self.source.name, 1)
        self.tables["ADM Request Feedback"] = {"old": Row(
            name="old", reference_doctype=self.source.doctype, reference_name=self.source.name, submitted_by="requester")}
        with self.assertRaisesRegex(ValueError, "already been submitted"):
            feedback.submit_feedback(self.source.doctype, self.source.name, 1)

    def test_patch_restores_user_if_repair_fails(self):
        patch_module = self.load("registry_patch_under_test", "eup_administration/patches/v4_1/repair_request_registry.py")
        self.frappe.session.user = "patch-user"
        with patch.object(self.registry, "rebuild_registry", side_effect=RuntimeError("repair failed")):
            with self.assertRaisesRegex(RuntimeError, "repair failed"):
                patch_module.execute()
        self.assertEqual(self.frappe.session.user, "patch-user")
