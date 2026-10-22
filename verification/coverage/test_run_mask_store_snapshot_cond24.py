import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_mask_store_snapshot_cond24 as r


class RuntimeAdapterTests(unittest.TestCase):
    def test_parent_authorization_required(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):r.claim_once(Path(t),'seal',None)
            self.assertFalse((Path(t)/'launch-once.json').exists())

    def test_once_receipt_exclusive(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);r.claim_once(p,'seal',r.AUTHORIZATION)
            with self.assertRaises(FileExistsError):r.claim_once(p,'seal',r.AUTHORIZATION)
            self.assertFalse(json.loads((p/'launch-once.json').read_bytes())['application_approval'])

    def test_previous_failure_not_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'DVEfiles').mkdir()
            with self.assertRaises(ValueError):r.claim_once(p,'seal',r.AUTHORIZATION)

    def test_environment_removes_DVE_and_shell_ENV(self):
        base={'tool_identity':{'test':True},'future_environment':{
            'remove':['DVE','ENV','BASH_ENV','LD_PRELOAD','LD_AUDIT'],
            'set_values':{'DVE_COVERAGE_OUTPUT':'/out','DVE_REVIEWED_WAIVERS':'/hook',
                          'MASK_SNAPSHOT_BASE_TCL':'/base'}}}
        with patch.object(r.prepared,'read_config',return_value=base), \
             patch.object(r.runner.tool,'controlled_environment',return_value={'DVE':'bad','ENV':'bad','PATH':'/bin'}):
            env=r.environment(base['tool_identity'],Path('/out'))
        self.assertNotIn('DVE',env);self.assertNotIn('ENV',env)
        self.assertEqual(env['MASK_SNAPSHOT_BASE_TCL'],'/base')

    def test_wrong_environment_identity_rejects(self):
        with patch.object(r.prepared,'read_config',return_value={'tool_identity':{'expected':True}}):
            with self.assertRaises(ValueError):r.environment({},Path('/out'))

    def test_runtime_seal_mismatch_rejected_before_launch(self):
        with patch.object(r,'OUTPUT',Path('/out')),patch.object(r,'digest',return_value='actual'):
            with self.assertRaises(ValueError):r.read_config(Path('/out'),'wrong')

    def test_prepare_requires_fixed_existing_output(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):r.prepare(Path(t))

    def test_reuses_runner_with_live_identity_and_bounded_timeout(self):
        import inspect
        source=inspect.getsource(r.runner.capture)
        self.assertIn('find_live(',source);self.assertIn('process.wait(timeout=1800)',source)
        self.assertIn('os.killpg(',source)


if __name__=='__main__':
    unittest.main()
