"""Promotion starts with the measured implementation, not an untested rewrite."""
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[3] / 'software/akv/experimental/quantized_kv/register_pv'


class PromotionTest(unittest.TestCase):
    def test_measured_source_identity(self):
        for old, new in (('candidate.h', 'kernel.h'),
                         ('online_candidate.h', 'online.h'),
                         ('runtime_candidate.h', 'runtime.h'),
                         ('runtime_candidate.c', 'runtime.c')):
            text = (HERE / old).read_text()
            text = text.replace('"candidate.h"', '"kernel.h"')
            text = text.replace('"online_candidate.h"', '"online.h"')
            text = text.replace('"runtime_candidate.h"', '"runtime.h"')
            text = text.replace('/* Experiment only: production scale/fused-MAD arithmetic and immutable buffers.',
                                '/* Opt-in RVV path: production scale/fused-MAD arithmetic and immutable buffers.')
            with self.subTest(source=old):
                self.assertEqual((SHARED / new).read_text(), text)


if __name__ == '__main__':
    unittest.main()
