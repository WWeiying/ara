from pathlib import Path
import unittest
from unittest import mock
import run_readonly_csr_simulation_v2 as v


class RunnerAdapterTests(unittest.TestCase):
    def test_exact_import_and_identity(self):
        ns = v.load_adapter()
        self.assertEqual(ns['preflight'].__name__, 'build_readonly_csr_preflight_v2')
        self.assertEqual(ns['BUDGET'], 600)
        self.assertEqual(v.life.digest(Path(v.frozen.__file__)), v.FROZEN_SHA)

    def test_reject_extra_or_missing_import(self):
        source = Path(v.frozen.__file__).read_text()
        for bad in (source + '\nimport build_readonly_csr_preflight as preflight\n',
                    source.replace('import build_readonly_csr_preflight as preflight', 'pass')):
            with self.assertRaises(ValueError): v.adapted_source(bad)

    def test_old_existing_run_still_rejected(self):
        ns = v.load_adapter()
        with mock.patch.object(ns['preflight'], 'verify') as verify:
            with self.assertRaises(ValueError): ns['prepare'](v.life.OUT, v.life.OUT / 'unused', 'a' * 64)
            verify.assert_not_called()

    def test_review_drift_never_runs(self):
        ns = v.load_adapter(); out = v.life.OUT / 'uncreated-readonly-csr-fixture'
        manifest = dict(preflight=str(v.life.OUT / 'pre/preflight-manifest.json'), preflight_seal='a' * 64)
        with mock.patch.dict(ns, prepare=lambda *args: {}), mock.patch.object(ns['frozen'], 'run') as run:
            with self.assertRaises(ValueError): ns['invoke_run'](out, manifest)
            run.assert_not_called()


if __name__ == '__main__': unittest.main()
