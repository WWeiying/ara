import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_narrow_clip_reject_simulation as r


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = r.life.read_bound(r.PRE / 'preflight-manifest.json', r.PRE_SEAL)

    def test_real_sealed_preflight_and_ELF(self):
        self.assertEqual(r.verify_preflight(), self.pre)
        self.assertEqual(r.life.digest(r.ELF), r.ELF_SHA)

    def test_runtime66_preserves_extra_provenance(self):
        pre = copy.deepcopy(self.pre)
        pre['pins']['/synthetic/provenance'] = 'a' * 64
        runtime = r.runtime_inputs(pre)
        self.assertEqual(len(runtime), 66)
        self.assertIn('/synthetic/provenance', pre['pins'])
        for path in (str(r.life.IMAGE), next(p for p in runtime if p != str(r.life.IMAGE))):
            changed = copy.deepcopy(pre)
            changed['pins'][path] = 'b' * 64
            with self.assertRaises(ValueError):
                r.runtime_inputs(changed)

    def test_runtime_extra_member_rejected(self):
        plan = r.life.read_bound(r.life.PLAN, r.life.PLAN_SEAL)
        plan['image']['/synthetic/runtime'] = 'a' * 64
        with patch.object(r.life, 'read_bound', return_value=plan):
            with self.assertRaises(ValueError):
                r.runtime_inputs(self.pre)

    def test_preflight_weakening_rejected_before_replay(self):
        for key, value in [('checks', 2093), ('trap_cells', 16), ('elf_sha256', 'b' * 64),
                           ('full_VRF_snapshots', 2), ('DUT_differential_executed', True)]:
            pre = copy.deepcopy(self.pre)
            pre[key] = value
            with patch.object(r.life, 'read_bound', return_value=pre), patch.object(r.preflight, 'verify') as replay:
                with self.assertRaises(ValueError):
                    r.verify_preflight()
                replay.assert_not_called()

    def test_actual_test_drift_rejected(self):
        original = r.life.digest
        with patch.object(r.life, 'digest', side_effect=lambda p: 'b' * 64 if Path(p) == r.ACTUAL_TEST else original(p)):
            with self.assertRaises(ValueError):
                r.verify_preflight()

    def test_command_same_ELF_all_traces_budget(self):
        cmd = r.command(r.life.OUT / 'synthetic-clip17-run')
        self.assertEqual(r.BUDGET, 300)
        self.assertEqual([v for v in cmd if v.startswith('+PRELOAD=')], ['+PRELOAD=' + str(r.ELF)])
        self.assertIn('+NO_FSDB', cmd)
        self.assertIn('line+cond+fsm+tgl+branch', cmd)
        self.assertEqual(sum(v.startswith('+COMMIT_TRACE=') for v in cmd), 1)
        self.assertEqual(sum(v.startswith('+VECTOR_TRACE=') for v in cmd), 1)

    def test_manifest_all_predecessor_pins_and_extra_test(self):
        with patch.object(r, 'verify_preflight', return_value=self.pre), patch.object(r.life, 'check'):
            record = r.manifest(r.life.OUT / 'synthetic-clip17-run')
        self.assertTrue(self.pre['pins'].items() <= record['pins'].items())
        self.assertEqual(record['pins'][str(r.ACTUAL_TEST)], r.ACTUAL_TEST_SHA)
        self.assertEqual(record['systemd_policy']['RuntimeMaxSec'], 360)
        self.assertFalse(record['automatic_retry'])
        self.assertFalse(record['coverage_admitted'])

    def test_existing_directory_rejects_retry_before_preflight(self):
        with patch.object(r, 'manifest') as manifest:
            with self.assertRaises(ValueError):
                r.prepare(r.PRE)
            manifest.assert_not_called()

    def test_existing_terminal_verify_never_fresh_prepare(self):
        with patch.object(r, 'prepare', side_effect=AssertionError('fresh forbidden')), patch.object(r, 'manifest', return_value={'x': 1}):
            self.assertEqual(r.verify_prepared(r.PRE, {'x': 1}), {'x': 1})
            with self.assertRaises(ValueError):
                r.verify_prepared(r.PRE, {'x': 2})

    def test_foreground_binding_restored_on_error(self):
        keys = ('PRE', 'ELF_SEAL', 'IMAGE_SEAL', 'BUDGET', 'preflight', 'command')
        old = {key: getattr(r.frozen, key) for key in keys}
        out = r.life.OUT / 'synthetic-clip17-run'
        record = {'timeout_s': 300}
        def fail(output, receipt):
            self.assertEqual(output, out)
            self.assertEqual(receipt, record)
            self.assertEqual(r.frozen.BUDGET, 300)
            self.assertEqual(r.frozen.PRE, r.PRE)
            self.assertEqual(r.frozen.ELF_SEAL, r.ELF_SHA)
            self.assertEqual(r.frozen.preflight.NAME, r.NAME)
            self.assertEqual(r.frozen.command(out), r.command(out))
            raise RuntimeError('mock only')
        with patch.object(r, 'prepare', return_value=record), patch.object(r.frozen, 'run', side_effect=fail) as run:
            with self.assertRaises(RuntimeError):
                r.invoke_run(out, record)
            self.assertEqual(run.call_count, 1)
        self.assertEqual({key: getattr(r.frozen, key) for key in keys}, old)

    def test_unauthorized_run_rejected_before_read(self):
        with patch.object(r.life, 'read_bound') as read:
            with self.assertRaises(ValueError):
                r.main(['run', '--output', str(r.life.OUT / 'synthetic-clip17-run'), '--prepared-seal', 'a' * 64])
            read.assert_not_called()

    def test_prepare_no_execution_and_no_run_directory(self):
        with tempfile.TemporaryDirectory(dir=r.life.OUT) as temp:
            out = Path(temp) / 'run'
            with patch.object(r, 'prepare', return_value={'timeout_s': 300}), patch.object(r, 'invoke_run') as run:
                r.main(['prepare', '--output', str(out)])
                run.assert_not_called()
                self.assertFalse(out.exists())
                self.assertEqual(json.loads(out.with_name('run.prepared.json').read_text()), {'timeout_s': 300})


if __name__ == '__main__':
    unittest.main()
