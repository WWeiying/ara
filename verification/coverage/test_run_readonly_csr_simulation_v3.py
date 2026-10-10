import os
from pathlib import Path
import unittest
from unittest import mock
import run_readonly_csr_simulation_v3 as v


class FinalRunnerTests(unittest.TestCase):
    def test_same_600s_lifecycle(self):
        ns = v.load_adapter()
        self.assertEqual(ns['BUDGET'], 600)
        self.assertEqual(ns['preflight'].__name__, 'build_readonly_csr_preflight_v3')
        self.assertEqual(ns['command'](v.life.OUT / 'fixture', v.life.OUT / 'pre'),
                         v.prior.frozen.command(v.life.OUT / 'fixture', v.life.OUT / 'pre'))

    def test_existing_run_rejected(self):
        ns = v.load_adapter()
        with self.assertRaises(ValueError): ns['prepare'](v.life.OUT, v.life.OUT / 'pre', 'a' * 64)

    def test_predecessor_drift(self):
        with mock.patch.object(v.life, 'digest', return_value='0' * 64):
            with self.assertRaises(ValueError): v.load_adapter()

    def test_changed_review_never_runs(self):
        ns = v.load_adapter()
        manifest = dict(preflight=str(v.life.OUT / 'pre/preflight-manifest.json'), preflight_seal='a' * 64)
        with mock.patch.dict(ns, prepare=lambda *args: {}), mock.patch.object(ns['frozen'], 'run') as run:
            with self.assertRaises(ValueError): ns['invoke_run'](v.life.OUT / 'unused', manifest)
            run.assert_not_called()

    @unittest.skipUnless(os.environ.get('RC_PREFLIGHT_V3'), 'Set RC_PREFLIGHT_V3 for real runner prepare')
    def test_real_existing_preflight_fresh_run_prepare(self):
        out = Path(os.environ['RC_PREFLIGHT_V3']); ns = v.load_adapter()
        plan = ns['prepare'](v.life.OUT / 'readonly-csr-real-test-not-created', out,
                             v.life.digest(out / 'preflight-manifest.json'))
        self.assertEqual(plan['raw_gain_requires_latest_formal_population_at_least'], 734)
        self.assertEqual((len(plan['targets']), plan['old_image_files_checked'], plan['software_checks']), (24, 66, 733))
        self.assertFalse((v.life.OUT / 'readonly-csr-real-test-not-created').exists())


if __name__ == '__main__': unittest.main()
