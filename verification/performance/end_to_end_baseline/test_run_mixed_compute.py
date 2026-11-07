import json
from pathlib import Path
import tempfile
import unittest

from run_mixed_compute import (PARENT, EDGES, PARENT_SHA, bound_vectors, pin, accepted)
from audit import digest


class MixedComputeRun(unittest.TestCase):
    def test_exact_66_plus_10_and_nx_only_fixtures(self):
        old=(PARENT/'vectors-matrix1.txt').read_text()
        extras=(EDGES/'extras-native.txt').read_text()
        combined=(EDGES/'combined-matrix1-76.txt').read_text()
        rows=bound_vectors(old,extras,combined)
        self.assertEqual(len(rows),76)
        self.assertEqual(rows[-1]['flags'],1)
        for a,b,c in ((old.replace('QBSCMD1 66','QBSCMD1 65',1),extras,combined),
                      (old,extras,combined.replace('QBSCMD1 76','QBSCMD1 75',1)),
                      (old,extras.replace('CMD 0 1','CMD 0 2',1),combined)):
            self.assertNotEqual((a,b,c),(old,extras,combined))
            with self.assertRaises(ValueError):bound_vectors(a,b,c)

    def test_predecessor_and_pin_drift_rejected(self):
        pins={}
        _,inventory=accepted(pins,PARENT,PARENT_SHA,'WIDE_WEIGHT_COMPUTE_PAIR_PASS')
        self.assertIn(str(PARENT/'source-snapshot/qbs_fp_accumulator.sv'),inventory)
        with self.assertRaises(ValueError):accepted({},PARENT,PARENT_SHA,'FAKE_PASS')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input';path.write_text('first');first=digest(path)
            pin(pins,path,first);path.write_text('second')
            with self.assertRaises(ValueError):pin(pins,path)
            with self.assertRaises(ValueError):pin({},path,first)


if __name__=='__main__':unittest.main()
