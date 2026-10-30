"""Mutate complete passing evidence, including strict producer accounting."""
import argparse
from pathlib import Path
import unittest
from check import check
from accept import merge

LOG = None


class CheckerTests(unittest.TestCase):
    def test_complete_pass(self):
        report = check(LOG)
        self.assertEqual(report['completed_cases'], 4)
        self.assertEqual(sum(c['outputs'] for c in report['cases']), 704)
        self.assertFalse(any(c['mismatches'] for c in report['cases']))
        self.assertEqual(report['native_qbs_calls'], 0)

    def test_mutations(self):
        producer = 'GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=0 path=generic k='
        value = next(l for l in LOG.splitlines() if l.startswith('RF_VALUE '))
        mutations = {
            'missing_gather': LOG.replace(producer+'256', 'REMOVED', 1),
            'full_k_instead_of_gather': LOG.replace(producer+'256', producer+'512', 1),
            'wrong_dense_k': LOG.replace(producer+'512', producer+'256', 1),
            'extra_producer': LOG.replace(producer+'256', producer+'256\n'+producer+'256', 1),
            'enabled_producer': LOG.replace('enabled=0 path=generic', 'enabled=1 path=generic', 1),
            'wrong_producer_path': LOG.replace('path=generic', 'path=packed', 1),
            'native_qbs': LOG+'\nGGML_RISCV_QBS_CALL type=q4_K',
            'qbs_selected': LOG.replace('decision=runtime_disabled', 'decision=selected', 1),
            'ownership': LOG.replace('owned=1', 'owned=0', 1),
            'backing_callback': LOG.replace('same_backing=1', 'same_backing=0', 1),
            'stride': LOG.replace('nb1=2112', 'nb1=2048', 1),
            'integrity': LOG.replace('weight_integrity=1', 'weight_integrity=0', 1),
            'missing_value': LOG.replace(value, '', 1),
            'duplicate_value': LOG.replace(value, value+'\n'+value, 1),
            'guest_exit': LOG.replace('GUEST_TEST_EXIT=0', 'GUEST_TEST_EXIT=1'),
            'early_stop': LOG.replace('completed=4 skipped=0', 'completed=3 skipped=1'),
            'nonfinite': LOG.replace(value, value.replace(next(w for w in value.split() if w.startswith('got_bits=')), 'got_bits=7fc00000'), 1),
            'numeric': LOG.replace(value, value.replace(next(w for w in value.split() if w.startswith('got_bits=')), 'got_bits=3f800000'), 1),
            'dense_control': LOG.replace(value, value.replace(next(w for w in value.split() if w.startswith('control_bits=')), 'control_bits=3f800000'), 1),
        }
        for name, mutant in mutations.items():
            with self.subTest(name=name):
                self.assertNotEqual(mutant, LOG)
                with self.assertRaises(ValueError):
                    check(mutant)

    def test_conflicting_pins(self):
        pins = {'sealed': 'old'}
        with self.assertRaises(ValueError):
            merge(pins, {'new': 'new', 'sealed': 'changed'})
        self.assertEqual(pins, {'sealed': 'old'})
        merge(pins, {'sealed': 'old', 'new': 'new'})
        self.assertEqual(pins, {'sealed': 'old', 'new': 'new'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', required=True, type=Path)
    args = parser.parse_args()
    LOG = args.log.read_text()
    unittest.main(argv=[__file__])
