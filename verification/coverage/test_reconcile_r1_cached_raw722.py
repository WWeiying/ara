"""Actual sealed bitmap fixtures; no raw VDB recollection or terminal checker rerun."""
from copy import deepcopy
import json
import unittest
import reconcile_r1_cached_raw722 as p


class ReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before=json.loads((p.BASE/'combined-bits.json').read_text())
        cls.single=json.loads((p.CANDIDATE/'single-raw-bits.json').read_text())
    def test_exact_prefix_and_one_candidate(self):
        proposed,delta=p.combine(self.before,self.single)
        self.assertEqual(proposed['tests'][:722],self.before['tests']);self.assertEqual(len(proposed['tests']),723)
        self.assertTrue(any(v>0 for v in delta['metrics'].values()))
    def test_duplicate_vdb_rejected(self):
        single=deepcopy(self.single);single['tests']=[self.before['tests'][0]]
        with self.assertRaises(ValueError):p.combine(self.before,single)
    def test_shape_drift_rejected(self):
        single=deepcopy(self.single);row=next(iter(single['metrics']['line'].values()));row['checksum']='bad'
        with self.assertRaises(ValueError):p.combine(self.before,single)
    def test_non722_baseline_rejected(self):
        before=deepcopy(self.before);before['tests'].pop()
        with self.assertRaises(ValueError):p.combine(before,self.single)


if __name__=='__main__':unittest.main()
