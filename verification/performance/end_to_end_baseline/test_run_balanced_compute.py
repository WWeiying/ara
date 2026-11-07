from pathlib import Path
import unittest

from run_balanced_compute import TRANSFORMS, PARENT, EDGES, fixture
from run_mixed_compute import bound_vectors
from check_balanced_compute import vector


class BalancedRun(unittest.TestCase):
    def test_all_sources_generated_from_accepted_snapshot(self):
        self.assertEqual(len(TRANSFORMS),5)
        generated=[]
        for name,transform in TRANSFORMS.items():
            text,report=transform((PARENT/'source-snapshot'/(name+'.sv')).read_text())
            self.assertTrue(report['source_reversible'])
            self.assertIn('module '+name+'_balanced',text)
            generated.append(text)
        source=(PARENT/'source-snapshot/qbs_wide_compute_tb.sv').read_text()
        for mode in (0,1):
            text,report=fixture(source,mode)
            self.assertIn('qbs_balanced_compute_tb',text)
            self.assertIn('BC_PHYSICAL',text)
            self.assertEqual('qbs_compute_engine_balanced #' in text,bool(mode))

    def test_exact_case_count_and_work_conversion(self):
        old=(PARENT/'vectors-matrix1.txt').read_text()
        extras=(EDGES/'extras-native.txt').read_text()
        combined=(EDGES/'combined-matrix1-76.txt').read_text()
        self.assertEqual(len(bound_vectors(old,extras,combined)),76)
        modified=vector(combined)
        for a,b in zip(combined.splitlines(),modified.splitlines()):
            if not a.startswith('C '):self.assertEqual(a,b)
        self.assertNotEqual(combined,modified)


if __name__=='__main__':unittest.main()
