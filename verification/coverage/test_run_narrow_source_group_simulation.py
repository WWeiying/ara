import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import run_narrow_source_group_simulation as r


class Tests(unittest.TestCase):
    def test_runtime66_and_separate_provenance_pins(self):
        runtime={str(r.life.IMAGE):r.p.prior.IMAGE_SHA}
        runtime.update({'/runtime/%d'%i:'a'*64 for i in range(65)})
        plan={'simv':str(r.life.IMAGE),'image':runtime}
        inputs=dict(runtime,**{'/provenance/%d'%i:'b'*64 for i in range(3)})
        with patch.object(r.life,'read_bound',return_value=plan):
            r.check_runtime_inputs(inputs)
            missing=dict(inputs);missing.pop('/runtime/0')
            with self.assertRaises(ValueError):r.check_runtime_inputs(missing)
            changed=dict(inputs);changed[str(r.life.IMAGE)]='c'*64
            with self.assertRaises(ValueError):r.check_runtime_inputs(changed)
            plan['image']=dict(runtime,**{'/extra-runtime':'a'*64})
            with self.assertRaises(ValueError):r.check_runtime_inputs(inputs)

    def test_real_serialized_preflight_opcode_inventory(self):
        pre=r.life.read_bound(r.PRE/'preflight-manifest.json',r.PRE_SEAL)
        self.assertTrue(all(type(row) is list for row in pre['explicit_RVV']))
        r.preflight.verify_words([tuple(row) for row in pre['explicit_RVV']],pre['symbols'])
        self.assertEqual(pre['elf_sha256'],r.ELF_SHA)

    def test_exact180_budget_and_noFSDB_command_same_ELF(self):
        self.assertEqual(r.BUDGET,180)
        command=r.command(r.life.OUT/'synthetic-narrow-run')
        self.assertEqual([x for x in command if x.startswith('+PRELOAD=')],['+PRELOAD='+str(r.ELF)])
        self.assertIn('+NO_FSDB',command);self.assertIn('+TESTCASE='+r.NAME,command)

    def test_existing_directory_prepare_rejected_without_preflight(self):
        with patch.object(r,'manifest') as manifest:
            with self.assertRaises(ValueError):r.prepare(r.PRE)
            manifest.assert_not_called()

    def test_terminal_existing_directory_verification_not_fresh_prepare(self):
        with patch.object(r,'prepare',side_effect=AssertionError('fresh prepare forbidden')), \
             patch.object(r,'manifest',return_value={'x':1}),patch.object(r,'verify_preflight',return_value={'ok':True}):
            self.assertEqual(r.verify_prepared(r.PRE,{'x':1}),{'ok':True})

    def test_prepared_fields_drift_rejected(self):
        with patch.object(r,'manifest',return_value={'timeout_s':180,'pins':{'/x':'a'*64}}):
            for record in ({'timeout_s':600},{'timeout_s':180,'pins':{}}):
                with self.assertRaises(ValueError):r.verify_prepared(r.PRE,record)

    def test_foreground_lifecycle_globals_bound_and_restored_on_failure(self):
        old={k:getattr(r.frozen,k) for k in ('BUDGET','PRE','ELF_SEAL','preflight','command')}
        record={'timeout_s':180};out=r.life.OUT/'synthetic-narrow-run'
        def fail(output,manifest):
            self.assertEqual(r.frozen.BUDGET,180);self.assertEqual(r.frozen.PRE,r.ELF.parent)
            self.assertEqual(r.frozen.preflight.NAME,r.NAME)
            self.assertEqual(r.frozen.command(out),r.command(out))
            raise RuntimeError('mock no EDA')
        with patch.object(r,'prepare',return_value=record),patch.object(r.frozen,'run',side_effect=fail):
            with self.assertRaises(RuntimeError):r.invoke_run(out,record)
        self.assertEqual({k:getattr(r.frozen,k) for k in old},old)

    def test_run_without_authorization_rejected_before_prepare(self):
        with patch.object(r,'prepare') as prepare:
            with self.assertRaises(ValueError):
                r.main(['run','--output',str(r.life.OUT/'synthetic-run'),'--prepared-seal','a'*64])
            prepare.assert_not_called()

    def test_prepare_has_no_execution(self):
        with tempfile.TemporaryDirectory(dir=r.life.OUT) as temp:
            out=Path(temp)/'run'
            with patch.object(r,'prepare',return_value={'timeout_s':180}),patch.object(r,'invoke_run') as run:
                r.main(['prepare','--output',str(out)])
                run.assert_not_called();self.assertFalse(out.exists())
                self.assertEqual(json.loads(out.with_name(out.name+'.prepared.json').read_text()),{'timeout_s':180})


if __name__=='__main__':unittest.main()
