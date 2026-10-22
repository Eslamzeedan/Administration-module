"""Offline, isolated tests; Frappe v16 database/permission integration remains mandatory."""
import importlib
import json
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch


class D(dict):
    def __getattr__(self, key):
        try: return self[key]
        except KeyError: return None

    def __setattr__(self, key, value): self[key] = value
    def get(self, key, default=None): return super().get(key, default)
    def is_new(self): return bool(self.get('_new', False))
    def get_doc_before_save(self): return self.get('_old')
    def save(self, **kw):
        if self.get('validate_on_save'):
            import eup_administration.consumables
            eup_administration.consumables.validate_supply_request(self)
        return self
    def insert(self, **kw): return self


class ConsumableTests(unittest.TestCase):
    def setUp(self):
        self.fr = types.ModuleType('frappe')
        self.fr.PermissionError = PermissionError
        self.fr.session = D(user='requester@company.test')
        self.fr.throw = lambda msg, exc=ValueError: (_ for _ in ()).throw(exc(msg))
        self.fr.db = MagicMock()
        self.fr.db.sql.return_value = [('ITEM',)]
        self.fr.db.escape.side_effect = lambda value: "'" + str(value).replace("'", "''") + "'"
        self.users = {
            'requester@company.test': ['Administration Requester'],
            'approver@company.test': ['Administration Department Approver'],
            'store@company.test': ['Administration Storekeeper'],
            'manager@company.test': ['Administration Manager'],
            'other@company.test': [],
        }
        self.fr.get_roles = lambda u=None: self.users.get(u or self.fr.session.user, [])
        self.emp = {
            'requester@company.test': D(company='EuP', department='Accounting'),
            'approver@company.test': D(company='EuP', department='Accounting'),
            'store@company.test': D(company='EuP', department='Administration'),
        }
        self.fr.db.get_value.side_effect = self.get_value
        self.fr.get_doc = MagicMock()
        def whitelist(methods=None):
            def decorate(fn): fn.http_methods = methods; return fn
            return decorate
        self.fr.whitelist = whitelist
        utils = types.ModuleType('frappe.utils')
        utils.getdate = lambda val: str(val)[:10]
        utils.now_datetime = lambda: '2026-10-22 13:00:00'
        self.modules = patch.dict(sys.modules, {'frappe': self.fr, 'frappe.utils': utils})
        self.modules.start(); self.addCleanup(self.modules.stop)
        for m in ['eup_administration.permissions', 'eup_administration.consumables']:
            sys.modules.pop(m, None)
        self.supply = importlib.import_module('eup_administration.consumables')

    def get_value(self, doctype, name, fields, **kwargs):
        if doctype == 'Employee':
            if isinstance(name, dict): return self.emp.get(name.get('user_id'))
            return 'EuP'
        if doctype == 'ADM Consumable Item':
            if isinstance(fields, list): return D(company='EuP', enabled=1)
            return 'EuP'
        if doctype == 'ADM Consumable Location': return 'EuP'
        if doctype == 'Cost Center': return 'EuP'
        return None

    def as_user(self, user): self.fr.session.user = user
    def request(self, **updates):
        values=dict(name='ADM-SUP-1', _new=False, _old=None, requested_by='requester@company.test',
                    department='Accounting', company='EuP', needed_by='2026-10-24', purpose='Paper',
                    status='Pending Approval', approved_by=None, rejection_reason=None, closed_at=None,
                    cost_center=None, items=[D(name='line-1',item='A4',requested_qty=10,
                                                approved_qty=0,issued_qty=0,notes='')])
        values.update(updates)
        return D(values)

    def test_invalid_quantity_rejected(self):
        for val in [None,'',False,0,-1,'NaN','inf',float('nan'), '3.1234', '1000000001']:
            with self.subTest(val=val), self.assertRaises(ValueError): self.supply.quantity(val)
        self.assertEqual(self.supply.quantity('2.375'), Decimal('2.375'))
        self.assertEqual(self.supply.quantity('0', allow_zero=True), Decimal(0))

    def test_direct_attempt_to_raise_approved_qty_blocked(self):
        old=self.request(status='Draft')
        forged=self.request(status='Draft',_old=old, items=[D(name='line-1',item='A4',requested_qty=10,
                                                               approved_qty=10,issued_qty=0,notes='')])
        with self.assertRaisesRegex(ValueError, 'workflow'):
            self.supply.validate_supply_request(forged)

    def test_new_request_resets_identity_approval_and_stock(self):
        forged=self.request(_new=True,requested_by='other@company.test', company='Other',
                            status='Fulfilled', items=[D(name='line-1',item='A4',requested_qty=5,
                                                         approved_qty=5,issued_qty=5)])
        self.supply.validate_supply_request(forged)
        self.assertEqual((forged.requested_by, forged.company, forged.status),
                         ('requester@company.test','EuP','Draft'))
        self.assertEqual((forged.get('items')[0].approved_qty,forged.get('items')[0].issued_qty),(0,0))

    def test_row_permissions_are_separated_by_department_and_company(self):
        doc=self.request(status='Approved')
        self.assertTrue(self.supply.supply_request_permission(doc,'requester@company.test','read'))
        self.assertTrue(self.supply.supply_request_permission(doc,'store@company.test','read'))
        self.assertFalse(self.supply.supply_request_permission(doc,'other@company.test','read'))
        self.assertFalse(self.supply.supply_request_permission(doc,'store@company.test','write'))
        self.assertIn('status IN', self.supply.supply_request_query('store@company.test'))
        self.assertEqual(self.supply.transaction_query('other@company.test'),'1=0')

    def test_department_approval_blocks_self_approval_and_cross_department(self):
        self.assertFalse(self.supply.department_approver(self.request(requested_by='approver@company.test'),
                                                         'approver@company.test'))
        self.assertFalse(self.supply.department_approver(self.request(department='Logistics'),
                                                         'approver@company.test'))
        self.assertTrue(self.supply.department_approver(self.request(), 'approver@company.test'))

    def test_approval_quantities_cannot_exceed_requested(self):
        self.as_user('approver@company.test')
        doc=self.request(_old=self.request(), validate_on_save=True)
        self.fr.get_doc.return_value=doc
        with self.assertRaisesRegex(ValueError,'exceed'):
            self.supply.approve_supply_request(doc.name, {'line-1': '11'})
        doc=self.request(_old=self.request(), validate_on_save=True)
        self.fr.get_doc.return_value=doc
        result=self.supply.approve_supply_request(doc.name, {'line-1': '8'})
        self.assertEqual((result['status'],doc.get('items')[0].approved_qty),('Approved',8.0))

    def test_stock_issue_blocks_over_issue_and_unauthorized_users(self):
        doc=self.request(status='Approved', items=[D(name='line-1',item='A4',
                        requested_qty=10, approved_qty=7, issued_qty=5, notes='')])
        self.fr.get_doc.return_value=doc
        self.as_user('other@company.test')
        with self.assertRaises(PermissionError):
            self.supply.issue_consumables(doc.name,'line-1','LOC',1)
        self.as_user('store@company.test')
        with self.assertRaisesRegex(ValueError,'more than approved'):
            self.supply.issue_consumables(doc.name,'line-1','LOC',3)

    def test_insufficient_stock_is_blocked_under_item_lock(self):
        self.as_user('store@company.test')
        self.fr.db.sql.side_effect = lambda query, *args: [(1,)] if 'SUM(signed_quantity)' in query else [('yes',)]
        self.fr.get_doc.side_effect = lambda dt,*args: D(company='EuP',enabled=1)
        with self.assertRaisesRegex(ValueError,'Insufficient'):
            self.supply.issue_consumables('request','line','location',2) if False else self.supply._post_movement(item='A4',location='LOC',kind='Issue',qty=2)

    def test_duplicate_posting_protected_by_lock_and_request_line(self):
        self.as_user('store@company.test')
        self.fr.db.sql.side_effect=lambda query,*args: [(20,)] if 'SUM(signed_quantity)' in query else [('yes',)]
        def get_doc(arg, name=None):
            if isinstance(arg,dict): return D(name='ADM-MOV-1',_new=True,**arg)
            return D(company='EuP', enabled=1)
        self.fr.get_doc.side_effect=get_doc
        doc=self.request(status='Approved', items=[D(name='line-1',item='A4',requested_qty=10,approved_qty=5,issued_qty=0,notes='')])
        old=doc.copy()
        self.fr.get_doc.side_effect=lambda arg,*args: doc if arg=='ADM Supply Request' else get_doc(arg,*args)
        result=self.supply.issue_consumables(doc.name,'line-1','LOC',3)
        self.assertEqual((result['status'],doc.get('items')[0].issued_qty),('Partially Issued',3))
        result=self.supply.issue_consumables(doc.name,'line-1','LOC',2)
        self.assertEqual((result['status'],doc.get('items')[0].issued_qty),('Fulfilled',5))
        with self.assertRaises(ValueError): self.supply.issue_consumables(doc.name,'line-1','LOC',1)

    def test_manual_transaction_creation_or_editing_forbidden(self):
        self.as_user('manager@company.test')
        doc=D(_new=True,movement_type='Receipt',quantity=1,signed_quantity=1,
              balance_before=0,balance_after=1)
        with self.assertRaises(PermissionError): self.supply.validate_transaction(doc)
        with self.supply.internal_action():
            doc._new=False
            with self.assertRaises(PermissionError): self.supply.validate_transaction(doc)
        with self.assertRaises(PermissionError): self.supply.prevent_transaction_deletion(doc)

    def test_stock_count_zero_delta_and_required_reason(self):
        self.as_user('manager@company.test')
        self.fr.db.sql.side_effect=lambda query,*args: [(4,)] if 'SUM(signed_quantity)' in query else [('yes',)]
        self.fr.get_doc.side_effect=lambda dt,*args: D(company='EuP', enabled=1)
        with self.assertRaisesRegex(ValueError, 'reason'):
            self.supply.reconcile_consumables('A4','LOC',4,'')
        result=self.supply.reconcile_consumables('A4','LOC',4,'Annual count')
        self.assertEqual(result,{'changed':False,'balance':4.0})

    def test_all_mutating_actions_are_post_only(self):
        for action in ('submit_supply_request','approve_supply_request','reject_supply_request',
                       'cancel_supply_request','receive_consumables','issue_consumables',
                       'reconcile_consumables','return_custody'):
            self.assertEqual(getattr(self.supply,action).http_methods,['POST'])


class SchemaTests(unittest.TestCase):
    def test_all_consumables_have_correct_doctype_controllers(self):
        root=Path(__file__).parents[1]/'eup_administration/eup_administration/doctype'
        for slug in ('adm_consumable_item','adm_consumable_location','adm_supply_request',
                     'adm_supply_request_line','adm_consumable_transaction','adm_admin_custody'):
            schema=json.loads((root/slug/(slug+'.json')).read_text())
            self.assertEqual(schema['module'],'EuP Administration')
            self.assertEqual(len(schema['fields']),len(schema['field_order']))
            self.assertTrue(schema['fields'])
            if slug == 'adm_consumable_transaction':
                self.assertTrue(all(not p.get('create') and not p.get('write') and not p.get('delete')
                                    for p in schema['permissions']))
            if slug == 'adm_supply_request_line':
                self.assertEqual(schema['istable'],1)
            else:
                self.assertTrue((root/slug/(slug+'.py')).exists())
