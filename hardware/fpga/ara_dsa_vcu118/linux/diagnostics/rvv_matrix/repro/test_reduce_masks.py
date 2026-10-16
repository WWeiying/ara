import unittest
from pathlib import Path

from reduce_masks import reduce, stimulus
from trace_masks import instrument


class ReductionTests(unittest.TestCase):
    def result(self):
        return dict(status='failed', exit_code=1, output=(
            'RVV_MASK_BIT seed=0 op=0 vl=8 mask=0 vstart=4 element=2 active=0 old=0 expected=0 actual=1\n'
            'RVV_MASK_FIRST seed=0 op=0 vl=8 mask=0 vstart=4 returned_vstart=0 errors=1 guard_before=91 guard_after=91\n'))

    def test_measured_and_oracle_preserved(self):
        m, detail = stimulus(self.result())
        source = instrument((Path(__file__).parents[1]/'mask_oracle.c').read_text())
        changed = reduce(source, m)
        self.assertIn('unsigned lengths[]={8};', changed)
        self.assertIn('start=4;', changed)
        self.assertIn('element=2', detail)
        marker = '            unsigned long returned=functions'
        self.assertEqual(source[source.index(marker):], changed[changed.index(marker):])

    def test_reject_ambiguous_or_inconsistent_measurement(self):
        r = self.result()
        for output in (r['output']*2, r['output'].replace('FIRST seed=0', 'FIRST seed=1'),
                       r['output'].replace('expected=0 actual=1', 'expected=0 actual=0')):
            with self.assertRaises(ValueError):
                stimulus(dict(r, output=output))
        with self.assertRaises(ValueError):
            stimulus(dict(r, exit_code=0))


if __name__ == '__main__':
    unittest.main()
