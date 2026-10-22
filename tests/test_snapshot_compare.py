import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('compare_snapshots', Path(__file__).resolve().parents[1]/'tools/compare_snapshots.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class TestSnapshotGate(unittest.TestCase):
    def setUp(self):
        self.before = {'legacy':{'ADM Trip':{'count':3,'sha256':'same'}}, 'permissions':{'ADM Trip':[]},
            'workspace':{'EuP Administration':{'content_sha256':'layout','shortcuts':[]}}}
        self.after = copy.deepcopy(self.before)
        self.after['workspace']['EuP Administration v2'] = {'content_sha256':'new','shortcuts':[]}
    def test_unchanged_original_records_pass(self):
        self.assertEqual(module.compare(self.before,self.after),[])
    def test_same_count_but_changed_data_fails(self):
        self.after['legacy']['ADM Trip']['sha256'] = 'changed'
        self.assertTrue(module.compare(self.before,self.after))
    def test_lost_workspace_fails(self):
        del self.after['workspace']['EuP Administration']
        self.assertTrue(module.compare(self.before,self.after))
    def test_changed_permissions_fail(self):
        self.after['permissions']['ADM Trip'] = [{'role':'Administration Driver','write':1}]
        self.assertTrue(module.compare(self.before,self.after))
