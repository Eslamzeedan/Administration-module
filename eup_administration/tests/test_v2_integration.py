from datetime import timedelta
import frappe
from frappe.utils import now_datetime
from eup_administration.tests.base import AdministrationIntegrationTestCase
from eup_administration import services, meetings, fleet

class TestV2Integration(AdministrationIntegrationTestCase):
    def test_recurrence_conflict_is_atomic(self):
        t = now_datetime()+timedelta(days=2)
        seed = self.booking(t,t+timedelta(hours=1))
        self.booking(t+timedelta(days=2),t+timedelta(days=2,hours=1))
        before = frappe.db.count('ADM Meeting Booking',{'room':self.room.name})
        with self.assertRaises(frappe.ValidationError):
            meetings.repeat_booking(seed.name,'Daily',3)
        self.assertEqual(frappe.db.count('ADM Meeting Booking',{'room':self.room.name}),before)
        self.assertFalse(frappe.db.get_value('ADM Meeting Booking',seed.name,'recurrence_root'))
    def test_buffer_prevents_booking_conflict(self):
        t = now_datetime()+timedelta(days=2)
        self.booking(t,t+timedelta(hours=1))
        with self.assertRaises(frappe.ValidationError):
            self.booking(t+timedelta(minutes=70),t+timedelta(hours=2))
        self.booking(t+timedelta(minutes=75),t+timedelta(hours=2))
    def test_series_copies_services_and_keeps_organizer(self):
        frappe.set_user(self.requester_user)
        t = now_datetime()+timedelta(days=2)
        seed = self.booking(t,t+timedelta(hours=1))
        seed.append('services',{'service_type':'IT','quantity':1,'status':'Requested'})
        seed.save()
        frappe.set_user('Administrator')
        result = meetings.repeat_booking(seed.name,'Weekly',3)
        self.assertEqual(len(result['created']),2)
        for name in result['created']:
            doc = frappe.get_doc('ADM Meeting Booking',name)
            self.assertEqual(doc.organizer,self.requester_user)
            self.assertEqual(doc.services[0].service_type,'IT')
    def test_driver_costs_need_manager_submission(self):
        trip = self.assigned()
        frappe.set_user(self.driver_user)
        services.start_trip(trip.name,1000)
        cost = frappe.get_doc({'doctype':'ADM Fuel Log','vehicle':self.vehicle.name,'trip':trip.name,
            'posting_date':now_datetime().date(),'odometer':1000,'liters':20,'price_per_liter':15}).insert()
        self.assertEqual(cost.amount,300)
        with self.assertRaises(frappe.PermissionError):
            cost.submit()
        frappe.set_user('Administrator')
        cost.reload()
        cost.submit()
        self.assertEqual(cost.docstatus,1)
    def test_maintenance_blocks_overlapping_assignment(self):
        frappe.get_doc({'doctype':'ADM Maintenance','vehicle':self.vehicle.name,'subject':'Service',
            'starts_at':'2099-01-01 08:00:00','ends_at':'2099-01-01 12:00:00'}).insert()
        trip = self.new_trip()
        services.request_trip(trip.name)
        frappe.set_user('Administrator')
        with self.assertRaises(frappe.ValidationError):
            services.assign_trip(trip.name,self.vehicle.name,self.driver.name)
    def test_maintenance_completion_updates_odometer(self):
        task = frappe.get_doc({'doctype':'ADM Maintenance','vehicle':self.vehicle.name,'subject':'Service',
            'starts_at':'2099-01-01 08:00:00','ends_at':'2099-01-01 12:00:00'}).insert()
        fleet.maintenance_action(task.name,'In Progress')
        fleet.maintenance_action(task.name,'Completed',odometer=1005,cost=250,next_due_odometer=2000)
        self.assertEqual(frappe.db.get_value('ADM Vehicle',self.vehicle.name,'last_odometer'),1005)
    def test_workspace_survives_repeated_setup(self):
        from eup_administration.install import setup
        setup()
        before = frappe.get_doc('Workspace','EuP Administration').content
        setup()
        self.assertEqual(frappe.get_doc('Workspace','EuP Administration').content,before)
        self.assertTrue(frappe.db.exists('Workspace','EuP Administration v2'))
