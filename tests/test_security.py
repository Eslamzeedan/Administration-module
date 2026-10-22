"""Boundary tests with an explicit framework double; these are not bench integration tests."""
import importlib
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

class AttrDict(dict):
    def __getattr__(self, key):
        return self.get(key)
    def __setattr__(self, key, value):
        self[key] = value

class Doc(AttrDict):
    def is_new(self):
        return self.get('_new', False)
    def get_doc_before_save(self):
        return self.get('_old')
    def set(self, key, value):
        self[key] = value
    def save(self, **kwargs):
        return self
    def as_dict(self):
        return dict(self)
    def check_permission(self, ptype):
        pass

class TestSecurity(unittest.TestCase):
    def setUp(self):
        self.frappe = types.ModuleType('frappe')
        self.frappe.session = AttrDict(user='driver@example.com')
        self.frappe.db = MagicMock()
        self.frappe.db.escape.side_effect = lambda v: "'" + v.replace("'", "''") + "'"
        self.frappe.db.get_value.return_value = 'DRV-1'
        self.frappe.db.sql.return_value = [('ok',)]
        self.frappe.PermissionError = PermissionError
        self.frappe.ValidationError = ValueError
        self.frappe.throw = lambda msg, exc=ValueError: self.raise_error(msg, exc)
        self.frappe.get_roles = MagicMock(return_value=['Administration Driver'])
        self.frappe.get_doc = MagicMock()
        self.frappe.get_list = MagicMock(return_value=[])
        self.frappe.get_all = MagicMock(return_value=[])
        self.frappe.has_permission = MagicMock(return_value=True)
        self.frappe._dict = AttrDict
        def whitelist(methods=None):
            def wrap(fn):
                fn.allowed_methods = methods
                return fn
            return wrap
        self.frappe.whitelist = whitelist
        utils = types.ModuleType('frappe.utils')
        utils.get_datetime = lambda v: v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
        utils.getdate = lambda v: utils.get_datetime(v).date()
        utils.now_datetime = lambda: datetime(2026, 10, 13, 12)
        utils.nowdate = lambda: '2026-10-13'
        self.context = patch.dict(sys.modules, {'frappe': self.frappe, 'frappe.utils': utils})
        self.context.start()
        self.addCleanup(self.context.stop)
        for module in ('permissions', 'services', 'meetings', 'fleet', 'reporting', 'install'):
            fullname = 'eup_administration.' + module
            sys.modules.pop(fullname, None)
            setattr(self, module, importlib.import_module(fullname))
    @staticmethod
    def raise_error(msg, exc):
        raise exc(msg)
    def trip(self, **kwargs):
        return Doc(name='TRIP-1', status='Assigned', requested_by='requester@example.com', driver='DRV-1', vehicle='CAR-1', **kwargs)
    def test_v16_ptype_denies_driver_writes(self):
        doc = self.trip()
        self.assertTrue(self.permissions.trip_permission(doc, ptype='read'))
        for ptype in ('write', 'delete', 'submit', 'cancel', 'create'):
            self.assertFalse(self.permissions.trip_permission(doc, ptype=ptype))
    def test_disabled_or_unroled_driver_is_denied(self):
        self.frappe.db.get_value.return_value = None
        self.assertFalse(self.permissions.trip_permission(self.trip(), ptype='read'))
        self.frappe.get_roles.return_value = ['Administration User']
        self.assertFalse(self.permissions.trip_permission(self.trip(), ptype='read'))
    def test_requester_only_edits_draft(self):
        self.frappe.session.user = 'requester@example.com'
        self.frappe.get_roles.return_value = ['Administration User']
        doc = self.trip()
        self.assertFalse(self.permissions.trip_permission(doc, ptype='write'))
        doc.status = 'Draft'
        self.assertTrue(self.permissions.trip_permission(doc, ptype='write'))
    def test_other_driver_cannot_start(self):
        self.frappe.get_doc.return_value = self.trip()
        self.frappe.db.get_value.return_value = 'DRV-OTHER'
        with self.assertRaises(PermissionError):
            self.services.start_trip('TRIP-1', 100)
    def test_nonmanager_cannot_approve_or_reject(self):
        with self.assertRaises(PermissionError):
            self.services.assign_trip('TRIP-1', 'CAR-1', 'DRV-1')
        with self.assertRaises(PermissionError):
            self.services.reject_trip('TRIP-1', 'reason')
    def test_new_trip_cannot_forge_state_or_readings(self):
        doc = Doc(_new=True, status='Completed', requested_by='victim', planned_start='2026-10-14 10:00', planned_end='2026-10-14 11:00', passenger_count=1, cost_center=None, start_odometer=999)
        self.services.validate_trip(doc)
        self.assertEqual(doc.status, 'Draft')
        self.assertEqual(doc.requested_by, self.frappe.session.user)
        self.assertEqual(doc.start_odometer, 0)
    def test_ledger_cannot_be_submitted_by_driver(self):
        self.assertFalse(self.permissions.ledger_permission(Doc(owner=self.frappe.session.user, docstatus=0), ptype='submit'))
        self.assertFalse(self.permissions.ledger_permission(Doc(owner='other', docstatus=0), ptype='read'))
    def test_service_fulfillment_is_manager_only(self):
        row = Doc(name='x', quantity=1, status='Delivered')
        with self.assertRaises(PermissionError):
            self.meetings.validate_services(Doc(services=[row]))
    def test_mutations_require_post(self):
        for module, names in ((self.services, ('request_trip','assign_trip','start_trip','end_trip','cancel_trip','close_booking','reject_trip')), (self.meetings, ('repeat_booking','cancel_series')), (self.fleet, ('maintenance_action',))):
            for name in names:
                self.assertEqual(getattr(module, name).allowed_methods, ['POST'])
    def test_recurrence_conflict_rolls_back_seed_and_occurrences(self):
        doc = Doc(name='BOOK-1', status='Confirmed', recurrence_root=None, starts_at='2026-10-14 10:00', ends_at='2026-10-14 11:00', room='ROOM-1', title='Meeting', organizer=self.frappe.session.user, attendee_count=1, services=[])
        child = MagicMock()
        child.insert.side_effect = ValueError('conflict')
        self.frappe.get_doc.side_effect = [doc, child]
        with self.assertRaises(ValueError):
            self.meetings.repeat_booking('BOOK-1', 'Weekly', 3)
        self.frappe.db.rollback.assert_called_once_with(save_point='adm_repeat_booking')
        self.assertFalse(self.services._action.get())
    def test_workspace_setup_preserves_existing_content(self):
        self.frappe.db.exists.return_value = True
        self.frappe.clear_cache = MagicMock()
        self.install.setup()
        self.install.setup()
        self.frappe.get_doc.assert_not_called()
    def test_reports_never_bypass_get_list(self):
        self.frappe.db.get_value.return_value = None
        self.reporting.trip_rows({'from_date':'2026-10-01','to_date':'2026-10-13'})
        self.reporting.cost_rows({'from_date':'2026-10-01','to_date':'2026-10-13'})
        self.frappe.get_all.assert_not_called()
        self.assertEqual(self.frappe.get_list.call_count, 4)

    def test_unassigned_trip_never_grants_operate_capability(self):
        doc = self.trip()
        doc.driver = None
        self.frappe.get_doc.return_value = doc
        self.frappe.db.get_value.return_value = None
        self.assertFalse(self.services.trip_capabilities(doc.name)['operate'])
        with self.assertRaises(PermissionError):
            self.services.driver_check(doc)
    def test_requester_cannot_delete_fulfilled_service(self):
        old = Doc(services=[Doc(name='service-1',quantity=1,status='Delivered',service_type='IT')])
        with self.assertRaises(PermissionError):
            self.meetings.validate_services(Doc(_old=old,services=[]))
    def test_fuel_amount_is_computed_without_modifying_odometer(self):
        vehicle = Doc(company='EuP Egypt')
        trip = self.trip()
        trip.status = 'In Progress'
        trip.company = 'EuP Egypt'
        trip.start_odometer = 1000
        self.frappe.get_doc.side_effect = [vehicle,trip]
        self.frappe.db.get_value.side_effect = ['EGP','DRV-1']
        doc = Doc(vehicle='CAR-1',trip='TRIP-1',posting_date='2026-10-13',owner=self.frappe.session.user,docstatus=0,
            odometer=1005,liters=20,price_per_liter=15,amount=9999,receipt=None)
        self.fleet.validate_ledger(doc,'fuel')
        self.assertEqual(doc.amount,300)
        self.assertEqual(doc.company,'EuP Egypt')
        self.frappe.db.set_value.assert_not_called()
    def test_driver_cannot_manage_maintenance(self):
        with self.assertRaises(PermissionError):
            self.fleet.maintenance_action('SERVICE-1','Completed',1000,10)
    def test_report_date_range_is_bounded(self):
        for dates in ({'from_date':'2026-10-14','to_date':'2026-10-13'}, {'from_date':'2020-01-01','to_date':'2026-10-13'}):
            with self.assertRaises(ValueError):
                self.reporting.bounds(dates)
    def test_private_receipt_is_required(self):
        self.frappe.get_roles.return_value = ['Administration Manager']
        self.frappe.get_doc.return_value = Doc(company='EuP Egypt')
        self.frappe.db.get_value.side_effect = ['EGP',Doc(name='FILE-1',is_private=0)]
        doc = Doc(vehicle='CAR-1',trip=None,posting_date='2026-10-13',docstatus=0,amount=25,receipt='/files/public.jpg')
        with self.assertRaises(ValueError):
            self.fleet.validate_ledger(doc,'expense')
