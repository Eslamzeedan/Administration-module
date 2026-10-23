"""Requires a disposable v16 site. Missing fixtures FAIL rather than silently skip."""
import hashlib
import json
import frappe
from frappe.tests import IntegrationTestCase
from frappe.exceptions import UniqueValidationError
from frappe.utils import now_datetime, add_to_date, add_days, today
from eup_administration.v4 import workflow, operations, jobs

PROTECTED = (
    "GL Entry", "Journal Entry", "Payment Entry", "Payment Request", "Expense Claim",
    "Purchase Invoice", "Purchase Order", "Purchase Receipt", "Material Request",
    "Stock Entry", "Stock Ledger Entry", "Bin", "Asset", "Asset Movement", "Asset Repair",
    "Asset Capitalization", "Item", "Warehouse", "Sales Invoice", "Delivery Note",
)


def protected_snapshot():
    result = {}
    for doctype in PROTECTED:
        if not frappe.db.table_exists(doctype):
            continue
        # Fixed identifiers from the constant list only, no external input.
        rows = frappe.db.sql("SELECT * FROM `tab" + doctype + "` ORDER BY name", as_dict=True)
        result[doctype] = (len(rows), hashlib.sha256(
            json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest())
    return result


class TestIndependentV4(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        if (not frappe.conf.get("adm_allow_integration_tests") or
                not frappe.local.site.startswith(("test-", "staging-")) or
                frappe.local.site == "erpnext-v16.eup-cairo.local"):
            self.fail("V4 tests require an isolated test-/staging- site and adm_allow_integration_tests=1")
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        self.company = frappe.conf.get("adm_test_company")
        self.approver = frappe.conf.get("adm_test_approver")
        self.assertTrue(self.company, "Set adm_test_company to the isolated fixture company")
        self.assertTrue(self.approver, "Set adm_test_approver to a precreated active Employee/User with Administration Manager")
        self.assertEqual(frappe.db.get_value("Employee", {"user_id": self.approver, "status": "Active"}, "company"), self.company)
        self.assertIn("Administration Manager", frappe.get_roles(self.approver))
        self.before = protected_snapshot()
        self.addCleanup(self.assert_protected_unchanged)

    def assert_protected_unchanged(self):
        frappe.set_user("Administrator")
        self.assertEqual(self.before, protected_snapshot())

    def ticket(self):
        return frappe.get_doc({"doctype": "ADM Facility Ticket", "subject": "Isolated test",
            "company": self.company, "location": "Test office", "priority": "High"}).insert()

    def policy(self):
        # One enabled policy per company and target; change fixtures only on disposable site.
        for name in frappe.get_all("ADM Workflow Policy", filters={"company": self.company,
                "target_doctype": "ADM Facility Ticket", "enabled": 1}, pluck="name"):
            old = frappe.get_doc("ADM Workflow Policy", name)
            old.enabled = 0
            old.save()
        return frappe.get_doc({"doctype": "ADM Workflow Policy", "policy_title": "Isolated review",
            "company": self.company, "target_doctype": "ADM Facility Ticket", "enabled": 1,
            "initial_state": "Draft", "states": [
                {"state": "Draft", "sla_hours": 1, "escalation_role": "Administration Manager"},
                {"state": "Done", "is_terminal": 1}],
            "transitions": [{"action": "Complete", "from_state": "Draft", "to_state": "Done",
                "allowed_role": "System Manager", "approval_required": 1, "conditions": "[]"}],
            "approval_bands": [{"transition_action": "Complete", "step_number": 1,
                "approver_role": "Administration Manager", "same_company": 1,
                "same_department": 0, "allow_delegation": 1}]}).insert()

    def test_complete_workflow_feedback_and_audit(self):
        doc, policy = self.ticket(), self.policy()
        workflow.start(doc.doctype, doc.name, policy.name)
        info = workflow.transition(doc.doctype, doc.name, "Complete", 1)
        with self.assertRaises(frappe.PermissionError):
            workflow.decide(doc.doctype, doc.name, "Approved", info["revision"])
        frappe.set_user(self.approver)
        result = workflow.decide(doc.doctype, doc.name, "Approved", info["revision"])
        self.assertEqual(result["state"], "Done")
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.count("ADM Workflow Audit", {"reference_name": doc.name}), 3)
        feedback_filters = {"reference_key": workflow.key(doc.doctype, doc.name)}
        total_before = frappe.db.count("ADM Operation Feedback")
        created = operations.feedback(doc.doctype, doc.name, 5, "Completed")
        self.assertEqual(frappe.db.count("ADM Operation Feedback", feedback_filters), 1)
        self.assertEqual(frappe.db.count("ADM Operation Feedback"), total_before + 1)
        # Frappe v16 distinguishes a unique field collision from a duplicate name.
        with self.assertRaises((frappe.DuplicateEntryError, UniqueValidationError)):
            operations.feedback(doc.doctype, doc.name, 1, "Duplicate attempt")
        self.assertEqual(frappe.db.count("ADM Operation Feedback", feedback_filters), 1)
        self.assertEqual(frappe.db.count("ADM Operation Feedback"), total_before + 1)
        self.assertEqual(frappe.db.get_value("ADM Operation Feedback", created["feedback"],
                                           ["rating", "comment"]), (5, "Completed"))
        with self.assertRaises(frappe.ValidationError):
            workflow.decide(doc.doctype, doc.name, "Approved", result["revision"])

    def test_stale_revision_and_forged_state(self):
        doc, policy = self.ticket(), self.policy()
        workflow.start(doc.doctype, doc.name, policy.name)
        with self.assertRaises(frappe.ValidationError):
            workflow.transition(doc.doctype, doc.name, "Complete", 0)
        doc.reload()
        doc.workflow_state = "Done"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_used_policy_frozen_but_can_be_disabled(self):
        doc, policy = self.ticket(), self.policy()
        workflow.start(doc.doctype, doc.name, policy.name)
        policy.transitions[0].to_state = "Draft"
        with self.assertRaises(frappe.ValidationError):
            policy.save()
        policy.reload()
        policy.enabled = 0
        policy.save()
        self.assertFalse(policy.enabled)

    def test_equipment_conflicts_and_release(self):
        equipment = frappe.get_doc({"doctype": "ADM Shared Equipment", "equipment_name": "Isolated projector",
                                   "company": self.company, "enabled": 1}).insert()
        start = add_to_date(now_datetime(), days=1)
        end = add_to_date(start, hours=1)
        def booking():
            return frappe.get_doc({"doctype": "ADM Equipment Booking", "subject": "Projector",
                "company": self.company, "equipment": equipment.name, "starts_at": start, "ends_at": end})
        first = booking().insert()
        with self.assertRaises(frappe.ValidationError):
            booking().insert()
        operations.release_booking(first.name)
        self.assertTrue(booking().insert().name)

    def test_recurring_is_idempotent(self):
        previous = frappe.conf.get("adm_v4_jobs_enabled")
        frappe.conf.adm_v4_jobs_enabled = True
        self.addCleanup(frappe.conf.update, {"adm_v4_jobs_enabled": previous})
        task = frappe.get_doc({"doctype": "ADM Recurring Task", "subject": "Weekly office inspection",
            "company": self.company, "next_due": today(), "interval_days": 7, "enabled": 1}).insert()
        operations.recurring()
        operations.recurring()
        self.assertEqual(frappe.db.count("ADM Task Occurrence", {"task": task.name}), 1)

    def test_sla_is_idempotent(self):
        previous = frappe.conf.get("adm_v4_jobs_enabled")
        frappe.conf.adm_v4_jobs_enabled = True
        self.addCleanup(frappe.conf.update, {"adm_v4_jobs_enabled": previous})
        doc, policy = self.ticket(), self.policy()
        workflow.start(doc.doctype, doc.name, policy.name)
        run_name = frappe.db.get_value("ADM Workflow Run", {"reference_key": workflow.key(doc.doctype, doc.name)}, "name")
        run = frappe.get_doc("ADM Workflow Run", run_name)
        run.due_at = add_to_date(now_datetime(), hours=-1)
        workflow.save_internal(run)
        jobs.escalate()
        jobs.escalate()
        self.assertEqual(frappe.db.count("ADM SLA Escalation", {"reference_name": doc.name}), 1)

    def test_direct_audit_creation_forbidden(self):
        doc, policy = self.ticket(), self.policy()
        workflow.start(doc.doctype, doc.name, policy.name)
        filters = {"reference_doctype": doc.doctype, "reference_name": doc.name}
        before = frappe.get_all("ADM Workflow Audit", filters=filters, pluck="name", order_by="name")
        self.assertEqual(len(before), 1)  # The protected workflow action really created an audit.
        total_before = frappe.db.count("ADM Workflow Audit")
        forged = frappe.get_doc({"doctype": "ADM Workflow Audit", "reference_doctype": doc.doctype,
            "reference_name": doc.name, "policy": policy.name, "company": self.company,
            "actor": "Administrator", "action": "FORGED", "from_state": "Draft",
            "to_state": "Done", "revision": "999"})
        with self.assertRaisesRegex(frappe.PermissionError, "Use protected workflow actions"):
            forged.insert(ignore_permissions=True)
        self.assertEqual(frappe.db.count("ADM Workflow Audit"), total_before)
        self.assertEqual(frappe.get_all("ADM Workflow Audit", filters=filters,
                                       pluck="name", order_by="name"), before)
        self.assertFalse(frappe.db.exists("ADM Workflow Audit",
                                        dict(filters, action="FORGED")))
