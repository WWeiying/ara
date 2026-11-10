#!/usr/bin/env python3
"""Host contract tests, not hardware acceptance."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import run_matrix as r


def vector(m=8, profile=1):
    stride = 32 if m <= 4 else 16
    return (f'QBSCMD1 1\nCMD 0 {profile} 1 2 {m} 4 1 01\n' +
            ''.join(f'O {row * stride + col} 3f800000\n' for row in range(m) for col in range(4)) +
            'C 2 576 2336 8192 8192 256 192 32\nEND\n')


def log(cooperative=1):
    native = 128 if cooperative else 256
    loan = 128 if cooperative else 0
    return (f'STAGE2_MATRIX_COMMAND seq=1 cooperative={cooperative} m=8 n=4 profile=1 success=1 fault=0 '
            f'native_issues={native} native_useful={native*32} native_products={native*32} '
            f'loan_issues={loan} loan_useful={loan*32} loan_products={loan*32} loan_returns={loan} latency=3\n'
            'QBS end-to-end case 0 PASS profile=1 M=8 N=4 Kb=1 layouts=1/2 cycles=999\n'
            'QBS engine PASS: 1 functional cases\n'
            f'STAGE2_MATRIX_LENDERS_DONE commands=1 native_issues={native} loan_issues={loan} '
            f'loan_returns={loan} reset_commands=0 reset_flushed=0 latency=3 instances=4 scope=engine_not_soc\n')


class MatrixTest(unittest.TestCase):
    def check(self, text, cooperative=1, suite='real'):
        return r.check_log(text, r.vectors(vector()), cooperative, suite)

    def test_original_composition_additive(self):
        sys.path.insert(0, str(r.ROOT / r.COMPOSER))
        import compose_canonical_standalone as composer
        wrapper = composer.compose('qbs')
        bench = composer.adapt_tb((r.ROOT / r.TB).read_text(), 'qbs')
        new_wrapper, new_bench = r.adapt(wrapper, bench)
        self.assertEqual(new_wrapper.count('qbs_akv_shared_reader #('), 1)
        self.assertIn('.CooperativeWaves(CooperativeWaves)', new_wrapper)
        self.assertIn('.lease_i(busy)', new_bench)
        self.assertEqual(new_bench.count('$fatal'), bench.count('$fatal'))
        self.assertIn('unexpected_write_count', new_bench)

    def test_nonunique_anchor_rejected(self):
        with self.assertRaises(ValueError):
            r.once('a a', 'a', 'b')

    def test_dot_only_adaptation(self):
        before = vector()
        after, changes = r.candidate_vector(before)
        self.assertEqual(after, before.replace('8192 256 192', '8192 128 192'))
        self.assertEqual(changes, [dict(before=256, after=128)])
        self.assertEqual(r.vectors(before)[0]['outputs'], r.vectors(after)[0]['outputs'])

    def test_fallback_vectors_unchanged(self):
        for m in range(1, 8):
            self.assertEqual(r.candidate_vector(vector(m))[0], vector(m))
        self.assertEqual(r.candidate_vector(vector(profile=3))[0], vector(profile=3))

    def test_odd_counter_rejected(self):
        with self.assertRaises(ValueError):
            r.candidate_vector(vector().replace('8192 256 192', '8192 255 192'))

    def test_duplicate_output_rejected(self):
        with self.assertRaises(ValueError):
            r.vectors(vector().replace('C 2 ', 'O 0 3f800000\nC 2 '))

    def test_stride_rejected(self):
        with self.assertRaises(ValueError):
            r.vectors(vector().replace('O 16 ', 'O 8 '))

    def test_baseline_and_candidate(self):
        for cooperative in (0, 1):
            result = self.check(log(cooperative), cooperative)
            self.assertEqual(result['cycles'], [999])
            self.assertEqual(result['totals']['instances'], 4)

    def test_terminal_required(self):
        for bad in (log().replace('QBS engine PASS: 1 functional cases\n', ''),
                    log() + 'QBS engine PASS: 1 functional cases\n'):
            with self.assertRaises(ValueError):
                self.check(bad)

    def test_late_fatal_rejected(self):
        for ending in ('Fatal: mismatch', 'Error-[SE] syntax', 'Assertion failed xyz', '$fatal(1)'):
            with self.assertRaises(ValueError):
                self.check(log() + ending + '\n')

    def test_missing_fault_suite_rejected(self):
        with self.assertRaises(ValueError):
            self.check(log().replace('1 functional cases', '1 functional cases plus four fault classes'), suite='synthetic')

    def test_missing_context_checks_rejected(self):
        with self.assertRaises(ValueError):
            self.check(log(), suite='context')

    def test_physical_and_return_accounting(self):
        for before, after in (('native_products=4096', 'native_products=4095'),
                              ('loan_returns=128 latency', 'loan_returns=127 latency'),
                              ('latency=3', 'latency=2'),
                              ('commands=1', 'commands=2'),
                              ('loan_issues=128', 'loan_issues=0')):
            with self.assertRaises(ValueError):
                self.check(log().replace(before, after))

    def test_baseline_cannot_borrow(self):
        with self.assertRaises(ValueError):
            self.check(log().replace('cooperative=1', 'cooperative=0'), 0)

    def test_lender_has_real_multipliers(self):
        source = (r.HERE / 'matrix_lenders.sv').read_text()
        for text in ('lane < 4', 'qbs_lane_mul_borrow borrower', 'simd_mul #',
                     '.ElementWidth(EW8)', '.ExternalProduct(1\'b0)', '.NumPipeRegs(0)',
                     '.product_o(product[lane])', '.native_quiescent_i(1\'b1)',
                     'loan_result_valid_o === {4{return_due[2]}}'):
            self.assertIn(text, source)
        self.assertNotIn('qbs_dot_array', source)

    def test_source_list_and_pin_drift(self):
        sources = r.rtl_sources(r.ROOT)
        self.assertEqual(sources.count('hardware/src/vlsu/qbs/qbs_dot_array.sv'), 1)
        self.assertIn('hardware/src/vlsu/qbs_akv_shared_reader.sv', sources)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input'
            path.write_text('before')
            pins = {str(path): r.sha(path)}
            r.verify(pins)
            path.write_text('after')
            with self.assertRaises(ValueError):
                r.verify(pins)


if __name__ == '__main__':
    unittest.main(verbosity=2)
