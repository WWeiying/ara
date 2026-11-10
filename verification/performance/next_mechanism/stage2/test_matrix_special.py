#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
import check_matrix_v2 as checker

PREPARED = None


class SpecialOracleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if PREPARED is None:
            raise unittest.SkipTest('Pass --prepared DIRECTORY')
        cls.old = checker.legacy()
        cls.cases = cls.old.vectors((PREPARED / 'original_vectors.txt').read_text())

    def test_six_shapes(self):
        self.assertEqual(len(self.cases), 6)
        for c in self.cases:
            self.assertEqual((c['profile'], c['m'], c['n'], c['kb']), (1, 8, 5, 2))

    def test_only_dot_counts_adapted(self):
        updated, changes = self.old.candidate_vector((PREPARED / 'original_vectors.txt').read_text())
        self.assertEqual(updated, (PREPARED / 'vectors.txt').read_text())
        self.assertEqual(len(changes), 6)

    def test_scale_classes_in_raw_weight_beats(self):
        groups, kind = {}, None
        for line in (PREPARED / 'original_vectors.txt').read_text().splitlines():
            f = line.split()
            if f[0] == 'CMD': kind = int(f[1]); groups[kind] = set()
            if f[0] == 'W' and int(f[2]) == 0:
                bits = int(f[4], 16)
                groups[kind].add((bits & 0xffff, bits >> 16 & 0xffff))
        for kind, value in enumerate((0x7e00, 0x7c01, 0x7c00, 0xfc00)):
            self.assertEqual({d for d, dm in groups[kind]}, {value})
        self.assertEqual({v for pair in groups[4] for v in pair}, {0, 0x8000})
        self.assertTrue(all(0 < v < 0x400 for pair in groups[5] for v in pair))

    def test_signaling_nan_invalid_flag(self):
        self.assertTrue(self.cases[1]['flags'] & 0x10)

    def test_zero_and_subnormal_results(self):
        self.assertTrue(all(bits & 0x7fffffff == 0 for bits in self.cases[4]['outputs'].values()))
        self.assertTrue(all(bits & 0x7f800000 != 0x7f800000 for bits in self.cases[5]['outputs'].values()))

    def test_original_reference_contract_is_not_hidden(self):
        config = json.loads((PREPARED / 'selection.json').read_text())
        self.assertEqual(config['numerical_policy'], 'unmodified original qbs_ref bit patterns/flags')
        self.assertFalse(config['recompiled_rtl'])
        self.assertEqual(config['depths'], [0, 16])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepared', type=Path)
    args, rest = parser.parse_known_args()
    PREPARED = args.prepared
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
