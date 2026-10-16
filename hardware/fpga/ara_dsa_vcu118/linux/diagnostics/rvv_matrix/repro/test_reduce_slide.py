import unittest
from pathlib import Path
from reduce_slide import reduce, legacy_source


class SlideTests(unittest.TestCase):
    def test_short_sequence_retains_only_original_mask_prefix(self):
        source=(Path(__file__).parents[1]/'permutation_oracle.c').read_text()
        selector='            if(!(seed==0 && op==12 && s==2 && l==6 && mode<=3))continue;\n'
        self.assertEqual(reduce(source,0,3,mask_sequence=True).replace(selector,''),source)
        with self.assertRaises(ValueError):reduce(source,0,3,True,True)

    def test_legacy_interface_has_no_restart_argument(self):
        source=(Path(__file__).parents[1]/'permutation_oracle.c').read_text()
        changed=legacy_source(source)
        self.assertIn('predicate,scalars[s]))',changed)
        self.assertNotIn('scalars[s],start)',changed)
        with self.assertRaises(ValueError):
            legacy_source('missing')

    def test_fixture_and_target_unchanged(self):
        source=(Path(__file__).parents[1]/'permutation_oracle.c').read_text()
        for seed in range(3):
            for mode in (0,2,3):
                selector=f'            if(!(seed=={seed} && op==12 && s==2 && l==6 && mode=={mode}))continue;\n'
                self.assertEqual(reduce(source,seed,mode).replace(selector,''),source)

    def test_prefix_preserves_order(self):
        source=(Path(__file__).parents[1]/'permutation_oracle.c').read_text()
        changed=reduce(source,0,3,True)
        tail='\n            if(seed==0 && op==12 && s==2 && l==6 && mode==3)goto selected_done;'
        self.assertEqual(changed.replace(tail,'').replace('selected_done:\n',''),source)

    def test_source_drift_rejected(self):
        with self.assertRaises(ValueError):
            reduce('missing',0,0)


if __name__=='__main__':
    unittest.main()
