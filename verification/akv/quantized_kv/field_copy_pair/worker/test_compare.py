"""Host-only tests of the pair comparison; original checker supplies fixtures."""
import copy
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as worker
import compare as c


def checked_fixture():
    import test_threeway_attention_check as original
    original.ThreewayCheckTest.setUpClass()
    text = original.ThreewayCheckTest().transcript(1)
    golden = original.ThreewayCheckTest.gold
    parsed = worker.accepted.checker.check_log(text, 1, golden, worker.accepted.RTL.read_text())
    return text, golden, parsed


def cycles(report, values):
    for t, value in zip(report['trials'], values):
        t['cycles'] = value
    report['sums'] = {str(mode): sum(t['cycles'] for t in report['trials'] if t['mode'] == mode)
                      for mode in range(3)}
    return report


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.text, self.golden, self.old = checked_fixture()
        self.new = copy.deepcopy(self.old)

    def test_all_real_six_call_output_pairs_and_counts(self):
        result = c.compare(self.old, self.new)
        self.assertEqual(result['output_words_per_binary'], 4608)
        self.assertEqual(result['cross_binary_word_comparisons'], 4608)
        self.assertEqual(result['total_output_values_read'], 9216)
        self.assertEqual(len(result['trials']), 6)
        self.assertEqual(result['regressed_modes'], [])
        self.assertFalse(result['historical_timing_used'])
        self.assertFalse(result['performance_acceptance'])
        self.assertTrue(result['independent_parent_review_required'])
        self.assertFalse(result['same_elf'])

    def test_fresh_mode_sums_and_each_repeat_cycle_delta(self):
        cycles(self.old, [3000, 2200, 1500, 1400, 2100, 2900])
        cycles(self.new, [1500, 1100, 750, 700, 1050, 1450])
        result = c.compare(self.old, self.new)
        self.assertEqual(result['baseline_total_cycles'], 13100)
        self.assertEqual(result['candidate_total_cycles'], 6550)
        for row in result['trials']:
            self.assertEqual(row['baseline_over_candidate'], 2)
            self.assertLess(row['cycle_delta'], 0)
        for row in result['modes'].values():
            self.assertEqual(row['baseline_over_candidate'], 2)
            self.assertEqual(len(row['baseline_repeat_cycles']), 2)

    def test_regression_is_explicit_not_relabelled_as_speedup(self):
        cycles(self.new, [3000, 3000, 1000, 1000, 3000, 3000])
        result = c.compare(self.old, self.new)
        self.assertEqual(result['regressed_modes'], [1])
        self.assertLess(result['modes']['1']['baseline_over_candidate'], 1)
        self.assertFalse(result['performance_acceptance'])

    def test_cross_program_bits_csrs_and_work_reject(self):
        for key in c.MATCHED:
            candidate = copy.deepcopy(self.new)
            for index in (0, 5):
                if key == 'output_bits':
                    candidate['trials'][index][key][-1] ^= 1
                else:
                    candidate['trials'][index][key] += 1
            with self.subTest(field=key), self.assertRaises(ValueError):
                c.compare(self.old, candidate)

    def test_no_three_call_or_missing_hardware_substitution(self):
        for mutation in ('three_calls', 'no_record', 'missing_word', 'wrong_order', 'wrong_sum'):
            candidate = copy.deepcopy(self.new)
            if mutation == 'three_calls': candidate['trials'] = candidate['trials'][:3]
            elif mutation == 'no_record': candidate['hardware_records'].pop()
            elif mutation == 'missing_word': candidate['trials'][0]['output_bits'].pop()
            elif mutation == 'wrong_order': candidate['trials'][1]['mode'] = 2
            else: candidate['sums']['0'] += 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                c.compare(self.old, candidate)

    def test_same_program_repeats_must_match_bits_and_csrs(self):
        for key in ('output_bits', 'fcsr', 'vcsr'):
            candidate = copy.deepcopy(self.new)
            if key == 'output_bits': candidate['trials'][5][key][0] ^= 1
            else: candidate['trials'][5][key] += 1
            with self.subTest(field=key), self.assertRaises(ValueError):
                c.compare(self.old, candidate)

    def test_cycle_bound_types(self):
        for value in (True, 0, -1, 2**64, 1.5):
            candidate = copy.deepcopy(self.new)
            candidate['trials'][0]['cycles'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                c.compare(self.old, candidate)

    def test_unchecked_oracle_state_reject(self):
        for key, value in (('state', 'PASS'), ('original_golden_checked', False),
                           ('original_golden_checked', 1)):
            candidate = copy.deepcopy(self.new)
            candidate[key] = value
            with self.subTest(field=key, value=value), self.assertRaises(ValueError):
                c.compare(self.old, candidate)

    def test_original_frozen_checker_is_still_gate(self):
        self.assertEqual(worker.s.digest(worker.PAIR.parent/'check_threeway_attention.py'),
                         'ac2fecc27be77220a442bfdfb2292c37a9fe585148d4fe79da9aae09ff34dd05')
        work = next(line for line in self.text.splitlines() if line.startswith('[QBS_PERF]'))
        for old, new in (('commands=8', 'commands=7'), ('quantizations=6', 'quantizations=5'),
                         ('vcsr=5', 'vcsr=4'), ('hex=3f800000', 'hex=7fc00000'),
                         (work+'\n', ''), ('UVM_ERROR : 0', 'UVM_ERROR : 1')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                worker.accepted.checker.check_log(self.text.replace(old, new, 1), 1,
                                                   self.golden, worker.accepted.RTL.read_text())


if __name__ == '__main__':
    unittest.main()
