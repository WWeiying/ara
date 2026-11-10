#!/usr/bin/env python3
import argparse
import collections
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
import run_matrix_special_v2 as s

PREPARED = None


def raw_fixture(bits):
    return f'QBSCMD1 1\nCMD 0 1 2 1 1 1 1 10\nO 0 {bits:08x}\nC 1 144 292 256 256 32 6 1\nEND\n'


class AdapterTest(unittest.TestCase):
    def test_nan_payload_and_sign_only(self):
        for bits in (0x7fc02000, 0xffc00000, 0x7f800001, 0xffa00001):
            raw = raw_fixture(bits)
            mapped, changes = s.canonicalize(raw)
            self.assertEqual(mapped, raw.replace(f'O 0 {bits:08x}', 'O 0 7fc00000'))
            self.assertEqual(len(changes), 1)
            s.validate_adaptation(raw, mapped)

    def test_non_nan_all_bits_preserved(self):
        for bits in (0, 0x80000000, 0x7f800000, 0xff800000, 1, 0x007fffff, 0x3f800000, 0x7f7fffff):
            raw = raw_fixture(bits)
            self.assertEqual(s.canonicalize(raw), (raw, []))
            s.validate_adaptation(raw, raw)

    def test_flag_mutation_rejected(self):
        raw = raw_fixture(0x7fc02000)
        mapped, _ = s.canonicalize(raw)
        with self.assertRaises(ValueError):
            s.validate_adaptation(raw, mapped.replace('1 1 1 10', '1 1 1 00'))

    def test_finite_mutation_rejected(self):
        raw = raw_fixture(0x3f800000)
        with self.assertRaises(ValueError):
            s.validate_adaptation(raw, raw.replace('3f800000', '3f800001'))

    def test_signed_zero_mutation_rejected(self):
        raw = raw_fixture(0x80000000)
        with self.assertRaises(ValueError):
            s.validate_adaptation(raw, raw.replace('O 0 80000000', 'O 0 00000000'))

    def test_inf_mutation_rejected(self):
        raw = raw_fixture(0x7f800000)
        with self.assertRaises(ValueError):
            s.validate_adaptation(raw, raw.replace('7f800000', '7fc00000'))

    def test_count_and_shape_mutation_rejected(self):
        raw = raw_fixture(0x7fc02000)
        mapped, _ = s.canonicalize(raw)
        for before, after in (('C 1 144', 'C 2 144'), ('1 1 1 10', '2 1 1 10')):
            with self.assertRaises(ValueError):
                s.validate_adaptation(raw, mapped.replace(before, after))

    def test_other_nan_not_accepted(self):
        raw = raw_fixture(0x7fc02000)
        with self.assertRaises(ValueError):
            s.validate_adaptation(raw, raw_fixture(0xffc00000))


class PreparedSpecialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if PREPARED is None:
            raise unittest.SkipTest('Pass --prepared DIRECTORY')
        cls.raw = (PREPARED / 'raw_evidence/original_vectors.txt').read_text()
        cls.runtime = (PREPARED / 'vectors.txt').read_text()

    def test_original_failure_preserved(self):
        self.assertEqual(s.checker.sha(PREPARED / 'raw_evidence/original_vectors.txt'), s.RAW_SHA)
        self.assertEqual(s.checker.sha(PREPARED / 'raw_evidence/host-tests.log'), s.RAW_LOG_SHA)
        self.assertIn('FAILED (failures=1)', (PREPARED / 'raw_evidence/host-tests.log').read_text())

    def test_six_shapes_and_original_flags(self):
        cases = s.checker.legacy().vectors(self.runtime)
        self.assertEqual([c['flags'] for c in cases], [0, 0, 0x10, 0x10, 0, 1])
        self.assertEqual(len(cases), 6)
        for c in cases:
            self.assertEqual((c['profile'], c['m'], c['n'], c['kb']), (1, 8, 5, 2))

    def test_exact_adaptation_and_difference_manifest(self):
        changes, dots = s.validate_adaptation(self.raw, self.runtime)
        manifest = json.loads((PREPARED / 'nan-differences.json').read_text())
        self.assertEqual(changes, manifest['changes'])
        self.assertEqual(dots, manifest['dot_changes'])
        self.assertEqual(collections.Counter(c['case'] for c in changes), {1: 40, 2: 32, 3: 16})

    def test_every_non_nan_and_source_record_unchanged(self):
        canonical, changes = s.canonicalize(self.raw)
        for before, after in zip(self.raw.splitlines(), canonical.splitlines()):
            if not before.startswith('O ') or not s.is_nan(int(before.split()[2], 16)):
                self.assertEqual(before, after)
        config = json.loads((PREPARED / 'selection.json').read_text())
        self.assertFalse(config['recompiled_rtl'])
        self.assertFalse(config['half_snan_nv_independently_verified'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared', type=Path)
    args, rest = parser.parse_known_args()
    PREPARED = args.prepared
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
