#!/usr/bin/env python3
"""Numerical promotion comparison ignores cycles but never output/CSR identity."""
import unittest

from audit_live_regression import numerical_signature


class SignatureTest(unittest.TestCase):
    def test_decode_uses_mode_shape_output_and_csrs(self):
        row = dict(case=1, trial=1, requested=1, checksum='abc', fcsr=3, vcsr=5, cycles=42)
        expected = numerical_signature([row], 'decode')
        self.assertEqual(expected, numerical_signature([dict(row, cycles=44)], 'decode'))
        for key, value in [('case', 2), ('trial', 0), ('requested', 0), ('checksum', 'abd'),
                           ('fcsr', 1), ('vcsr', 0)]:
            with self.subTest(key=key):
                self.assertNotEqual(expected, numerical_signature([dict(row, **{key:value})], 'decode'))

    def test_prefill_preserves_mode_and_result(self):
        row = dict(trial=1, paired=1, checksum='xyz', fcsr=3, vcsr=5, cycles=100)
        expected = numerical_signature([row], 'prefill')
        self.assertEqual(expected, numerical_signature([dict(row, cycles=110)], 'prefill'))
        self.assertNotEqual(expected, numerical_signature([dict(row, paired=0)], 'prefill'))
        with self.assertRaises(KeyError):
            numerical_signature([dict(trial=1, paired=1)], 'prefill')


if __name__ == '__main__':
    unittest.main()
