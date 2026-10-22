"""Checks legacy fleet/meeting schema shape, not a substitute for site snapshots."""
import json
import unittest
from pathlib import Path


class LegacyCompatibility(unittest.TestCase):
    def test_old_core_fleet_and_meeting_fields_still_exist(self):
        base=Path(__file__).parents[1]/'eup_administration/eup_administration/doctype'
        expected={
            'ADM Vehicle': {'plate_number','company','last_odometer','initial_odometer','status'},
            'ADM Driver': {'driver_name','user','enabled'},
            'ADM Trip': {'vehicle','driver','status','start_odometer','end_odometer',
                         'requested_by','planned_start','planned_end','gap_reason'},
            'ADM Fuel Log': {'vehicle','trip','odometer','amount','receipt'},
            'ADM Trip Expense': {'vehicle','trip','amount','receipt'},
            'ADM Meeting Room': {'company','room_name','capacity'},
            'ADM Meeting Booking': {'room','starts_at','ends_at','status'},
        }
        for doctype, names in expected.items():
            slug=doctype.lower().replace(' ','_')
            dt=json.loads((base/slug/(slug+'.json')).read_text())
            self.assertEqual(dt['name'],doctype)
            self.assertTrue(names.issubset({f['fieldname'] for f in dt['fields']}),doctype)
