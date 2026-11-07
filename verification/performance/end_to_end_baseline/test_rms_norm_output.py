import unittest
from pathlib import Path

from rms_norm_source import START, END, SUM, ORDERED
from rms_norm_output_source import OUTPUT, VECTOR_OUTPUT, candidate, caller
from rms_norm_completion import BEFORE, completed_caller


class RMSOutputSourceTests(unittest.TestCase):
    def fixture(self):
        return START+SUM+'void ggml_compute_forward_rms_norm_mul_fused(\n'+OUTPUT+END

    def test_only_registered_sum_and_fused_output_change(self):
        text = candidate(self.fixture())
        self.assertIn(ORDERED, text)
        self.assertIn(VECTOR_OUTPUT, text)
        self.assertIn('y[i00] = x[i00] * scale * w[i00]', text)
        self.assertIn('#include "rms_output.h"', text)
        self.assertNotIn(SUM, text)
        self.assertIn('candidate_rms_norm(', text)
        self.assertIn('strict_candidate_rms_norm(', candidate(self.fixture(), 'strict_candidate'))

    def test_changed_or_duplicate_output_rejects(self):
        for source in (self.fixture().replace(OUTPUT,''), self.fixture().replace(OUTPUT,OUTPUT*2)):
            with self.assertRaises(ValueError): candidate(source)

    def test_preserves_completed_timer_and_adds_untimed_checks(self):
        text = 'int main() {\ntiming=complete_call\n'+BEFORE
        completed = completed_caller(text)
        changed = caller(completed)
        self.assertIn(completed.split('int main() {\n')[1], changed)
        self.assertLess(changed.index('rms_output_checks())'), changed.index('timing='))
        self.assertIn('timing=call_and_csr_completion', changed)
        with self.assertRaises(ValueError): caller(text)

    def test_helper_keeps_two_roundings_and_partial_overlap_rejection(self):
        path = Path(__file__).resolve().parents[3] / 'software/rvv/experimental/ordered_rms_norm/rms_output.h'
        text = path.read_text()
        self.assertLess(text.index('__riscv_vfmul_vf_'), text.index('__riscv_vfmul_vv_'))
        self.assertIn('n > SIZE_MAX / sizeof(float)', text)
        self.assertIn('a == b ||', text)
        self.assertNotIn('__riscv_vfmacc', text)


if __name__ == '__main__': unittest.main()
