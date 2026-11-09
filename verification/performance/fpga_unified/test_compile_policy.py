#!/usr/bin/env python3
"""Reject ISA changes without imposing CPU-only flags on generic GGML."""
import unittest
from build_v2 import source_identity, verify_target_policy


class CompilePolicyTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            'llama/ggml/src/ggml.c': ['-march=rv64gcv', '-mabi=lp64d'],
            'llama/ggml/src/ggml-cpu/arch/riscv/qbs.cpp':
                ['-march=rv64gcv', '-mabi=lp64d', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d'],
            'ara/software/akv/src/akv_v2_attention_rvv.S': ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d'],
        }

    def test_exact_per_target_options_pass(self):
        for name, options in self.profile.items():
            row = dict(file='/new/inputs/' + name, command='gcc ' + ' '.join(options) + ' -O3 -c source')
            self.assertTrue(verify_target_policy(row, self.profile))

    def test_source_root_not_part_of_identity(self):
        self.assertEqual(source_identity('/old/inputs/llama/ggml/src/ggml.c'),
                         source_identity('/new/inputs/llama/ggml/src/ggml.c'))

    def test_extra_extension_rejected(self):
        row = dict(file='/new/inputs/llama/ggml/src/ggml.c', command='gcc -march=rv64gcv_zba -mabi=lp64d')
        with self.assertRaises(ValueError):
            verify_target_policy(row, self.profile)

    def test_abi_change_rejected(self):
        row = dict(file='/new/inputs/llama/ggml/src/ggml.c', command='gcc -march=rv64gcv -mabi=lp64')
        with self.assertRaises(ValueError):
            verify_target_policy(row, self.profile)

    def test_unknown_target_rejected(self):
        row = dict(file='/new/inputs/llama/ggml/src/unknown.c', command='gcc -march=rv64gcv -mabi=lp64d')
        with self.assertRaises(ValueError):
            verify_target_policy(row, self.profile)


if __name__ == '__main__':
    unittest.main()
