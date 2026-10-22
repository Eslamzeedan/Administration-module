import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class TestAdditiveSchema(unittest.TestCase):
    def test_original_fields_and_types_preserved(self):
        for source in (ROOT/'tests/fixtures/v0_1').glob('*.json'):
            slug = source.stem
            current = json.loads((ROOT/'eup_administration/eup_administration/doctype'/slug/source.name).read_text())
            baseline = json.loads(source.read_text())
            self.assertEqual(current['name'], baseline['name'])
            self.assertEqual(current['autoname'], baseline['autoname'])
            fields = {f['fieldname']: f for f in current['fields']}
            for old in baseline['fields']:
                with self.subTest(doctype=current['name'], field=old['fieldname']):
                    self.assertIn(old['fieldname'], fields)
                    self.assertEqual(fields[old['fieldname']]['fieldtype'], old['fieldtype'])
                    old_options = old.get('options')
                    if old['fieldtype'] == 'Select':
                        self.assertTrue(set((old_options or '').splitlines()) <= set(fields[old['fieldname']].get('options', '').splitlines()))
                    else:
                        self.assertEqual(fields[old['fieldname']].get('options'), old_options)
    def test_source_backed_v2_workspace(self):
        source = ROOT/'eup_administration/eup_administration/workspace/eup_administration_v2/eup_administration_v2.json'
        doc = json.loads(source.read_text())
        self.assertEqual(doc['standard'], 1)
        self.assertIsInstance(json.loads(doc['content']), list)
        self.assertEqual(len({r['label'] for r in doc['shortcuts']}), len(doc['shortcuts']))
    def test_new_permissions_do_not_grant_driver_submission(self):
        for slug in ('adm_fuel_log', 'adm_trip_expense'):
            doc = json.loads((ROOT/f'eup_administration/eup_administration/doctype/{slug}/{slug}.json').read_text())
            for row in doc['permissions']:
                if row['role'] in ('Administration User', 'Administration Driver'):
                    self.assertFalse(row.get('submit'))
                    self.assertFalse(row.get('cancel'))


class TestRunnerAdditiveSchema(unittest.TestCase):
    def test_runner_doc_types_and_careem_separation(self):
        base = ROOT/'eup_administration/eup_administration/doctype'
        request = json.loads((base/'adm_service_request/adm_service_request.json').read_text())
        careem = json.loads((base/'adm_careem_ride/adm_careem_ride.json').read_text())
        stops = json.loads((base/'adm_errand_stop/adm_errand_stop.json').read_text())
        self.assertEqual(careem['istable'], 1)
        self.assertEqual(stops['istable'], 1)
        self.assertTrue(request['track_changes'])
        fields = {f['fieldname']: f for f in request['fields']}
        self.assertEqual(fields['rides']['options'], 'ADM Careem Ride')
        self.assertEqual(fields['stops']['options'], 'ADM Errand Stop')
        self.assertNotIn('vehicle', fields)
        self.assertNotIn('odometer', fields)
        self.assertNotIn('driver', fields)
        self.assertEqual(fields['actual_transport_cost']['read_only'], 1)
        self.assertTrue(any(p['role'] == 'Administration Runner' for p in request['permissions']))
