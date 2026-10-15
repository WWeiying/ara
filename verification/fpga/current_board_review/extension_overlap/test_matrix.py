"""Read-only checks of the generated same-source matrix and cycle proof."""
import json
import re
import unittest

from adapter import HERE, prepare
from matrix import SHAPES, cases, derivative_assembly


class MatrixTests(unittest.TestCase):
    def test_assembly_derivatives_preserve_original_setup(self):
        for sew, regs, factor, digest in SHAPES:
            name = f'extension_e{sew}_m{regs}_vf{factor}'
            original = HERE / 'matrix01/prepared' / name / 'original'
            source = (original / 'source.S').read_text()
            result = (original / 'scenario.S').read_text()
            self.assertEqual(prepare.sha(original / 'source.S'), digest)
            self.assertEqual(result, derivative_assembly(source))
            self.assertTrue(result.startswith(source))
            self.assertEqual(result.count('csrw vstart,a5'), 8)
            self.assertEqual(len(re.findall(r'^v[zs]ext', result, re.M)), 12)
            self.assertEqual(result.count(',v0.t'), 8)

    def test_rows_cover_masks_prefix_factors_and_controls(self):
        for sew, regs, factor, _ in SHAPES:
            cap, rows = cases(sew, regs, factor)
            self.assertEqual(len(rows), 24)
            self.assertEqual({r['mode'] for r in rows[:8]}, {0, 1, 2, 3})
            self.assertEqual({r['op'] for r in rows[:8]}, {2, 3})
            self.assertTrue(any(r['unmasked'] and r['start'] for r in rows))
            self.assertTrue(any(r['vl'] == r['start'] for r in rows))
            self.assertTrue(any(r['vl'] == cap for r in rows))
            self.assertTrue(any(r['vl'] == 0 for r in rows))
            self.assertEqual({r['op'] for r in rows[-4:-2]}, {0, 1})
            stored = HERE / 'matrix01/prepared' / f'extension_e{sew}_m{regs}_vf{factor}'
            self.assertEqual(rows, json.loads((stored / 'original/cases.json').read_text()))

    def test_reference_and_generated_pins(self):
        ref = json.loads((HERE / 'matrix01/reference.json').read_text())
        self.assertEqual(ref['status'], 'PASS')
        self.assertEqual(len(ref['results']), 7)
        self.assertEqual(ref['total_unique_cases'], 144)
        for result in ref['results']:
            self.assertEqual(result['status'], 'PASS')
            log = HERE / 'matrix01' / (result['name'] + '.log')
            self.assertEqual(prepare.sha(log), result['log_sha256'])
            self.assertEqual(log.read_text().count('EXTENSION_TRIAL '),
                             144 if result['name'] == 'all' else 24)
        prepare.check(HERE / 'matrix01/prepared')

    def test_corrected_cycle_classification(self):
        finding = json.loads((HERE / 'cycle_review02/finding.json').read_text())
        self.assertTrue(finding['classifier_loop_proved'])
        self.assertEqual(finding['maintenance_VSLIDEDOWN_handshakes'], 65)
        self.assertEqual(finding['original_VADD_handshakes'], 0)
        self.assertEqual(finding['target_front_handshakes'], 0)
        self.assertEqual(len(finding['decode_cycles']), 43)
        self.assertEqual(len(finding['v25_eew_transitions']), 43)
        self.assertTrue(any(r['state_q'] == 1 for r in finding['decode_cycles']))


if __name__ == '__main__':
    unittest.main()
