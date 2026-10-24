"""Integrated v3 acceptance on a physically separate disposable staging bench."""
import frappe
from eup_administration.tests.base import AdministrationIntegrationTestCase
from eup_administration.v3 import general, approval


class TestV3GeneralFlow(AdministrationIntegrationTestCase):
    def setUp(self):
        # Frappe v16 rolls back at class cleanup, not between test methods.
        # Keep each test's policies/users/requests inside its own savepoint.
        frappe.db.savepoint("adm_v3_general_flow")
        self.addCleanup(frappe.db.rollback, save_point="adm_v3_general_flow")
        super().setUp()
        frappe.set_user("Administrator")
        previous = frappe.db.get_single_value("ADM Settings", "enable_v3_requests")
        self.addCleanup(frappe.db.set_single_value, "ADM Settings", "enable_v3_requests", previous or 0)
        frappe.db.set_single_value("ADM Settings", "enable_v3_requests", 1)

    def new_request(self):
        return frappe.get_doc({
            "doctype": "ADM General Service Request",
            "service_type": "Facilities", "subject": "Test service",
            "description": "Test permission-safe service workflow",
            "company": self.company, "priority": "Normal",
        }).insert(ignore_permissions=True)

    def make_policy(self, approver_role="Administration Manager"):
        return frappe.get_doc({
            "doctype": "ADM Approval Policy", "policy_name": "Test General",
            "request_type": "General", "company": self.company, "enabled": 1,
            "steps": [{"step_number": 1, "approver_role": approver_role,
                       "same_company": 0, "same_department": 0, "allow_delegation": 0}]
        }).insert(ignore_permissions=True)

    def test_complete_approval_and_registry_index(self):
        self.make_policy()
        request = self.new_request()
        self.assertEqual(request.status, "Draft")
        info = general.submit(request.name)
        self.assertEqual(info["status"], "Pending Approval")
        self.assertTrue(frappe.db.exists("ADM Request Registry",
                         {"reference_doctype": request.doctype, "reference_name": request.name}))
        approver = self.make_user("admin-approver-" + frappe.generate_hash(length=8),
                                  "Administration Manager")
        frappe.set_user(approver)
        result = approval.decide(info["approval_case"], "Approved")
        self.assertEqual(result["request_status"], "Approved")
        self.assertEqual(frappe.db.get_value(request.doctype, request.name, "status"), "Approved")
        decisions = frappe.get_all("ADM Approval Decision",
                                   filters={"approval_case": info["approval_case"]}, pluck="name")
        self.assertEqual(len(decisions), 1)

    def test_cannot_forge_general_status_directly(self):
        request = self.new_request()
        request.status = "Closed"
        with self.assertRaises(frappe.PermissionError):
            request.save(ignore_permissions=True)

    def test_self_approval_is_forbidden(self):
        self.make_policy("System Manager")
        request = self.new_request()
        case = general.submit(request.name)["approval_case"]
        self.assertEqual(request.requested_by, frappe.session.user)
        self.assertIn("System Manager", frappe.get_roles(frappe.session.user))
        before = frappe.db.count("ADM Approval Decision", {"approval_case": case})
        with self.assertRaisesRegex(frappe.PermissionError, "Not authorized to decide this step"):
            approval.decide(case, "Approved")
        self.assertEqual(frappe.db.count("ADM Approval Decision", {"approval_case": case}), before)
        self.assertEqual(frappe.db.get_value("ADM Approval Case", case, "status"), "Pending")
        request.reload()
        self.assertEqual(request.status, "Pending Approval")
