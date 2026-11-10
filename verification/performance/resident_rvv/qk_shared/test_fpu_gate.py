#!/usr/bin/env python3
"""Focused host contracts/mutations; real-FPU execution is a separate gate."""
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
import run_fpu_gate as gate
import fpu_gate_vectors as vectors

PREPARED = None
if '--prepared' in sys.argv:
    pos = sys.argv.index('--prepared')
    PREPARED = Path(sys.argv[pos + 1])
    del sys.argv[pos:pos + 2]


class FocusedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, _ = vectors.cases(vectors.reference.oracle.LIB if PREPARED is None else PREPARED / 'inputs/libsoftfloat.so')
        cls.expected = dict(cases=[{k: v for k, v in c.items() if k not in ('seeds', 'packets', 'operations', 'writes')}
            | dict(seeds=len(c['seeds']), packets=len(c['packets']), issued=len(c['operations']), writes=len(c['writes']))
            for c in cls.rows])

    def fixture(self):
        rows = []
        for i, c in enumerate(self.expected['cases']):
            row = dict(id=i, mode=c['mode'], elements=c['elements'], heads=c['heads'],
                iterations=c['iterations'], rm=c['rm'], action=c['action'], issued=c['issued'],
                returned=c['issued'], writes=c['writes'], flags=c['flags'], cancelled=0)
            if c['action'] == 1:
                row.update(issued=7, returned=7, writes=0, flags=0)
            elif c['action'] == 2:
                row.update(issued=7, returned=5, writes=0, flags=0, cancelled=2)
            rows.append('QKFPU_CASE ' + ' '.join(k + '=' + str(row[k]) for k in gate.FIELDS))
        rows.append('QKFPU_PASS cases=26 inactive=2 aborts=1 resets=1 prestart=182 qbs_issued=25 '
                    'qbs_returned=25 reset_cancelled=2 return_stalls=20 scope=controller_vmfpu_not_soc')
        return '\n'.join(rows) + '\n'

    def test_current_source_contracts(self):
        self.assertEqual(gate.audit_sources(gate.ROOT)['wrapper'], 'STATIC_ONLY')
        self.assertIn('inputs / FP_HELPER.relative_to(ROOT)', (Path(gate.__file__)).read_text())
        if PREPARED:
            self.assertTrue(Path(gate.FP.__file__).is_relative_to(PREPARED / 'inputs'))
            self.assertEqual(json.loads((PREPARED / 'expected.json').read_text())['cases'], self.expected['cases'])

    def test_shape_and_slot_work(self):
        self.assertEqual(len(self.rows), 26)
        self.assertEqual(sum(c['elements'] == 0 for c in self.rows), 2)
        self.assertEqual(sum(c['mode'] == 0 for c in self.rows), 3)
        for c in self.rows:
            width = 2 if c['mode'] else 4
            words = (c['elements'] + width - 1) // width
            self.assertEqual(len(c['operations']), words * c['heads'] * c['iterations'])
            self.assertEqual(len(c['writes']), words * c['heads'])
            self.assertTrue(all(slot < 16 for slot, _, _ in c['writes']))
        self.assertEqual(self.rows[1]['elements'], 0)

    def test_special_values_are_independent_and_masked(self):
        def item(part):
            return next(c for c in self.rows if part in c['name'])
        self.assertEqual(item('_masked_')['flags'], 0)
        self.assertEqual(item('_qnan_')['flags'], 0)
        self.assertEqual(item('_snan_')['flags'], 16)
        self.assertEqual(item('_invalid_')['flags'], 16)
        self.assertEqual(item('_subnormal_')['flags'], 0)
        self.assertEqual(item('pv_underflow')['flags'], 3)
        self.assertEqual(vectors.reencode(vectors.reference.OrderedReference().sf, 0x7c01), 0x7f802000)

    def test_rounding_is_not_reassociated(self):
        cases = [c for c in self.rows if '_rounding_' in c['name']]
        self.assertEqual([c['rm'] for c in cases], list(range(5)))
        self.assertTrue(all(c['flags'] == 1 for c in cases))
        self.assertNotEqual(cases[0]['writes'], cases[3]['writes'])

    def test_parser_accepts_exact_ledger(self):
        self.assertEqual(len(gate.check(self.fixture(), self.expected)['cases']), 26)

    def test_parser_rejects_numerical_and_ownership_mutations(self):
        good = self.fixture()
        line = next(s for s in good.splitlines() if s.startswith('QKFPU_CASE id=2 '))
        bad = [good + line + '\n', good.replace(line, ''), good + 'Fatal: mutation\n',
               good.replace('prestart=182', 'prestart=0'), good.replace('qbs_returned=25', 'qbs_returned=24'),
               good.replace('reset_cancelled=2 return_stalls=20', 'reset_cancelled=0 return_stalls=20'),
               good.replace(line, line.replace('flags=' + line.split('flags=')[1].split()[0], 'flags=31'))]
        for text in bad:
            with self.subTest(text=text[-100:]), self.assertRaises(ValueError):
                gate.check(text, self.expected)


if __name__ == '__main__':
    unittest.main()
