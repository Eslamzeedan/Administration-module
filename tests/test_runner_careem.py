"""Offline permission and workflow tests; bench/migration tests still required."""
import importlib
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch


class D(dict):
    def __getattr__(self, name):
        return self.get(name)

    def __setattr__(self, name, value):
        self[name] = value

    def is_new(self):
        return self.get('_new', False)

    def get_doc_before_save(self):
        return self.get('_old')

    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value):
        self[key] = value

    def append(self, key, value):
        self.setdefault(key, []).append(D(value))

    def save(self, **kw):
        if getattr(self, 'validate_on_save', False):
            import eup_administration.runner
            eup_administration.runner.validate_request(self)
        return self

    def check_permission(self, ptype):
        pass


class TestRunnerCareem(unittest.TestCase):
    def setUp(self):
        self.frappe = types.ModuleType('frappe')
        self.frappe.session = D(user='employee@eup.test')
        self.frappe.PermissionError = PermissionError
        self.frappe.throw = lambda m, exc=ValueError: self.fail_thrown(m, exc)
        self.frappe.db = MagicMock()
        self.frappe.db.sql.return_value = [('ADM-REQ-1',)]
        self.frappe.db.escape.side_effect = lambda v: "'" + v.replace("'", "''") + "'"
        self.roles = {
            'employee@eup.test': ['Administration Requester'],
            'approver@eup.test': ['Administration Department Approver'],
            'runner@eup.test': ['Administration Runner'],
            'stranger@eup.test': [],
            'manager@eup.test': ['Administration Manager'],
        }
        self.frappe.get_roles = lambda u=None: self.roles.get(u or self.frappe.session.user, [])
        self.emp = {
            'employee@eup.test': D(department='Finance',company='EuP Egypt'),
            'approver@eup.test': D(department='Finance',company='EuP Egypt'),
            'runner@eup.test': D(department='Logistics',company='EuP Egypt'),
        }
        def get_value(doctype, name, field, **kw):
            if doctype == 'Employee':
                return self.emp.get(name['user_id'])
            if doctype == 'User':
                return 1
            if doctype == 'Company':
                return 'EGP'
            if doctype == 'Cost Center':
                return 'EuP Egypt'
            if doctype == 'File':
                return D(is_private=1, owner=self.frappe.session.user,
                         attached_to_doctype=None, attached_to_name=None)
            return None
        self.frappe.db.get_value.side_effect = get_value
        self.frappe.get_doc = MagicMock()
        def whitelist(methods=None):
            def decorated(fn):
                fn.methods = methods
                return fn
            return decorated
        self.frappe.whitelist = whitelist
        utils = types.ModuleType('frappe.utils')
        utils.now_datetime = lambda: datetime(2026, 10, 22, 12, 30)
        utils.get_datetime = lambda x: datetime.fromisoformat(str(x))
        self.context = patch.dict(sys.modules, {'frappe': self.frappe, 'frappe.utils': utils})
        self.context.start()
        self.addCleanup(self.context.stop)
        for name in ['eup_administration.permissions', 'eup_administration.runner']:
            sys.modules.pop(name, None)
        self.runner = importlib.import_module('eup_administration.runner')

    def fail_thrown(self, message, exc):
        raise exc(message)

    def doc(self, **updates):
        defaults=dict(name='ADM-REQ-1',_new=False,_old=None,request_type='Bank',
            purpose='Deposit official paperwork',service_location='Bank branch',
            needed_by='2026-10-23 12:00',priority='Normal',cost_center=None,
            requested_by='employee@eup.test',department='Finance',company='EuP Egypt',
            status='Pending Approval',assigned_runner=None,approved_by=None,rejected_by=None,
            rejection_reason=None,verified_by=None,started_at=None,completed_at=None,
            closed_at=None,completion_proof=None,completion_notes=None,currency='EGP',
            estimated_transport_cost=60, actual_transport_cost=0,rides=[],stops=[])
        defaults.update(updates)
        return D(defaults)

    def as_user(self, username):
        self.frappe.session.user=username

    def test_requester_and_assignee_row_level_restrictions(self):
        doc=self.doc(status='Assigned',assigned_runner='runner@eup.test')
        self.assertTrue(self.runner.request_permission(doc, user='employee@eup.test', ptype='read'))
        self.assertTrue(self.runner.request_permission(doc, user='runner@eup.test', ptype='read'))
        self.assertFalse(self.runner.request_permission(doc, user='runner@eup.test', ptype='write'))
        self.assertFalse(self.runner.request_permission(doc, user='stranger@eup.test', ptype='read'))
        self.assertIn('assigned_runner', self.runner.request_query('runner@eup.test'))
        self.assertIn('1=0', self.runner.request_query('stranger@eup.test'))

    def test_other_department_cannot_approve(self):
        self.as_user('approver@eup.test')
        doc=self.doc(department='Logistics')
        self.frappe.get_doc.return_value=doc
        with self.assertRaises(PermissionError):
            self.runner.approve_request(doc.name)

    def test_approver_cannot_approve_own_request(self):
        self.as_user('approver@eup.test')
        self.assertFalse(self.runner.approver_for(self.doc(requested_by='approver@eup.test')))

    def test_company_mismatch_prevents_approval(self):
        self.as_user('approver@eup.test')
        self.assertFalse(self.runner.approver_for(self.doc(company='Other Company')))

    def test_server_generates_request_identity_and_ignores_forged_state(self):
        forged=self.doc(_new=True,requested_by='other@eup.test',department='Other',
                        company='Other',status='Closed',assigned_runner='someone',
                        rides=[D(fare=200)],completion_proof='/private/files/forged.pdf')
        self.runner.validate_request(forged)
        self.assertEqual((forged.requested_by,forged.department,forged.company),
                         ('employee@eup.test','Finance','EuP Egypt'))
        self.assertEqual(forged.status,'Draft')
        self.assertEqual(forged.rides,[])
        self.assertIsNone(forged.completion_proof)

    def test_protected_fields_cannot_be_changed_in_form(self):
        old=self.doc(status='Draft')
        changed=self.doc(_old=old,status='Assigned',assigned_runner='runner@eup.test')
        with self.assertRaisesRegex(ValueError,'workflow'):
            self.runner.validate_request(changed)

    def test_private_receipt_cannot_be_public_or_foreign(self):
        with self.assertRaises(ValueError):
            self.runner.private_file('/files/public.pdf','ADM-REQ-1')
        self.frappe.db.get_value.side_effect=lambda *args,**kw: D(is_private=1,
            owner='another@eup.test',attached_to_doctype='Other',attached_to_name='ABC')
        with self.assertRaises(PermissionError):
            self.runner.private_file('/private/files/abc.pdf','ADM-REQ-1')

    def test_only_assigned_runner_can_start(self):
        self.as_user('stranger@eup.test')
        doc=self.doc(status='Assigned',assigned_runner='runner@eup.test')
        self.frappe.get_doc.return_value=doc
        with self.assertRaises(PermissionError):
            self.runner.start_errand(doc.name)
        self.as_user('runner@eup.test')
        result=self.runner.start_errand(doc.name)
        self.assertEqual(result['status'],'In Progress')
        self.assertEqual(doc.started_at, datetime(2026,10,22,12,30))

    def test_careem_legs_add_to_total_and_do_not_create_fleet_trips(self):
        self.as_user('runner@eup.test')
        doc=self.doc(status='In Progress',assigned_runner='runner@eup.test')
        # Frappe calls validate from save; test that fare and proof remain secure.
        doc.validate_on_save=True
        doc._old=self.doc(status='In Progress',assigned_runner='runner@eup.test')
        self.frappe.get_doc.return_value=doc
        result=self.runner.add_careem_ride(doc.name,'HQ','Bank','2026-10-22 13:00',
            '65.50','/private/files/careem.pdf','CR-123')
        self.assertEqual(result['status'],'In Progress')
        self.assertEqual(doc.actual_transport_cost,65.5)
        self.assertEqual(len(doc.rides),1)
        self.frappe.db.set_value.assert_not_called()

    def test_bad_amount_and_duplicate_booking_rejected(self):
        for value in ('NaN','Infinity','-1','hello'):
            with self.assertRaises(ValueError):
                self.runner.money(value)
        self.as_user('runner@eup.test')
        doc=self.doc(status='In Progress',assigned_runner='runner@eup.test',
                     rides=[D(pickup='A',dropoff='B',ridden_at='2026-10-22 12:00',fare=10,
                              receipt='/private/files/receipt.pdf',booking_reference='CR-123')])
        self.frappe.get_doc.return_value=doc
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            self.runner.add_careem_ride(doc.name,'HQ','Bank','2026-10-22 13:00',
                '20','/private/files/careem.pdf','CR-123')

    def test_workflow_closure_requires_department_verification(self):
        self.as_user('runner@eup.test')
        doc=self.doc(status='In Progress',assigned_runner='runner@eup.test',
                     rides=[D(pickup='HQ',dropoff='Bank',ridden_at='2026-10-22 12:00',fare=60,
                              receipt='/private/files/careem.pdf',booking_reference='CR-123')])
        self.frappe.get_doc.return_value=doc
        with self.assertRaises(ValueError):
            self.runner.complete_errand(doc.name,'/files/public.pdf','ok')
        self.runner.complete_errand(doc.name,'/private/files/completion.pdf','Delivered paperwork')
        self.assertEqual(doc.status,'Completed')
        with self.assertRaises(PermissionError):
            self.runner.close_errand(doc.name)
        self.as_user('approver@eup.test')
        self.runner.close_errand(doc.name)
        self.assertEqual(doc.status,'Closed')
        self.assertEqual(doc.verified_by,'approver@eup.test')

    def test_mutations_post_only(self):
        for method in ('submit_request','approve_request','reject_request','assign_runner',
                       'start_errand','add_careem_ride','complete_errand','close_errand','cancel_request'):
            self.assertEqual(getattr(self.runner,method).methods,['POST'])
