import unittest
from pathlib import Path
from reduce_fp_moves import single_trial, prefix_trials


class SingleTrialTests(unittest.TestCase):
    def setUp(self):
        self.source = (Path(__file__).resolve().parents[1]/'fp_move_oracle.c').read_text()
        self.fields = dict(seed=0, scalar=0, invalid_box=0, op=4,
                           vl=2, mask=0, sticky=0, vstart=1)

    def test_preserves_oracle_and_vector_setup_call(self):
        reduced = single_trial(self.source, self.fields)
        start = '        uint64_t scalar_bits='
        self.assertEqual(self.source[self.source.index(start):], reduced[reduced.index(start):])
        self.assertNotIn('for(unsigned seed=', reduced)
        self.assertNotIn('unsigned lengths[]', reduced)
        self.assertEqual(reduced.count('functions[op]('), 1)
        self.assertIn('unsigned start=1;', reduced)
        self.assertIn('unsigned vl=2;', reduced)

    def test_preserves_nondefault_stimulus(self):
        values = dict(self.fields, seed=2, invalid_box=1, sticky=1, vstart=17)
        reduced = single_trial(self.source, values)
        for declaration in ('unsigned seed=2;', 'unsigned invalid=1;',
                            'unsigned sticky=1;', 'unsigned start=17;'):
            self.assertIn(declaration, reduced)

    def test_missing_or_negative_stimulus_rejected(self):
        for fields in ({}, dict(self.fields, vstart=-1)):
            with self.assertRaises(ValueError):
                single_trial(self.source, fields)

    def test_prefix_retains_loop_order_and_checks_before_stopping(self):
        reduced = prefix_trials(self.source, self.fields)
        self.assertIn('for(unsigned seed=0;seed<3;++seed)', reduced)
        self.assertIn('++cases;\n        if(seed==0', reduced)
        self.assertIn('start==1)goto selected_done;', reduced)
        self.assertLess(reduced.index('if(output[0]'), reduced.index('goto selected_done;'))
        self.assertLess(reduced.index('selected_done:'), reduced.index('text(errors ?'))


if __name__ == '__main__':
    unittest.main()
