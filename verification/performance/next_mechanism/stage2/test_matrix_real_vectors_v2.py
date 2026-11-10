#!/usr/bin/env python3
"""Discover-safe successor for the sealed evidence-only nine-test entry point."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest

PREPARED = None
SEALED = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_matrix_qwen3_vcs_20261109_01/inputs/verification/performance/next_mechanism/stage2/test_matrix_real_vectors.py')
SEALED_SHA = '69fbda7160b0255d6890a1dd9d61ed9b64a8cb207fc3e73b17df61a64d7c0b4b'


def options(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path)
    return parser.parse_known_args(argv)


class EntryPointTest(unittest.TestCase):
    def test_no_evidence_by_default(self):
        self.assertIsNone(options([])[0].prepared)

    def test_discovery_words_not_evidence(self):
        parsed, rest = options(['discover', '-s', 'tests'])
        self.assertIsNone(parsed.prepared)
        self.assertEqual(rest, ['discover', '-s', 'tests'])

    def test_explicit_directory(self):
        self.assertEqual(options(['--prepared', '/example'])[0].prepared, Path('/example'))


class EvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if PREPARED is None:
            raise unittest.SkipTest('Evidence-only tests require --prepared DIRECTORY')

    def test_sealed_nine_tests_explicit_directory(self):
        self.assertEqual(hashlib.sha256(SEALED.read_bytes()).hexdigest(), SEALED_SHA)
        result = subprocess.run([sys.executable, '-B', str(SEALED), str(PREPARED.resolve())],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Ran 9 tests', result.stderr)
        self.assertIn('\nOK\n', result.stderr)


if __name__ == '__main__':
    parsed, rest = options(sys.argv[1:])
    PREPARED = parsed.prepared
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
