"""Explicit LLM build defaults without changing the generic configuration."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]


class Configuration(unittest.TestCase):
    def config(self, *options):
        result = subprocess.run(['make', '--no-print-directory', '-C', str(ROOT / 'hardware'),
            'config-check', *options], text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return dict(line.split('=', 1) for line in result.stdout.splitlines())

    def test_named_llm(self):
        config = self.config('config=llm')
        self.assertEqual(config['optimization_profile'], 'candidate_all')
        for key in ('shared_simd_mul', 'shared_fma', 'akv_resident', 'qbs_lane_mul'):
            self.assertEqual(config[key], '1')

    def test_generic(self):
        config = self.config('config=default')
        self.assertEqual(config['optimization_profile'], 'generic')
        for key in ('shared_simd_mul', 'shared_fma', 'akv_resident', 'qbs_lane_mul'):
            self.assertEqual(config[key], '0')

    def test_explicit_fma_disable(self):
        config = self.config('config=llm', 'shared_fma=0')
        self.assertEqual(config['shared_fma'], '0')
        self.assertNotIn('ARA_SHARED_FMA', config['bender_defs'])
        self.assertEqual(config['shared_simd_mul'], '1')

    def test_explicit_generic_profile(self):
        self.assertEqual(self.config('config=llm', 'optimization_profile=generic')['shared_fma'], '0')


if __name__ == '__main__':
    unittest.main(verbosity=2)
