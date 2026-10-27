"""Canonical helper must retain the measured algorithm without semantic edits."""
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
CANONICAL=HERE.parents[2]/'software/qbs/ggml/q8_K-decode-sums.h'


class SharedTest(unittest.TestCase):
    def test_measured_body_unchanged(self):
        text=CANONICAL.read_text()
        for old,new in (
            ('GGML_RISCV_Q8_K_DECODE_SUMS_H','QBS_DECODE_SUMS_LAYOUT_CANDIDATE_H'),
            ('ggml_riscv_q8_K_sum_distinct','qbs_decode_sum_distinct'),
            ('ggml_riscv_q8_K_bsums','qbs_decode_sums_layout_candidate')):
            text=text.replace(old,new)
        self.assertEqual(text,(HERE/'sums_layout.h').read_text())


if __name__=='__main__':unittest.main()
