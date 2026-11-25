"""Isolated host-only admission tests; all service/dispatch calls are mocked."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('owner_chain',HERE/'chain_owner_v3.py')
chain=importlib.util.module_from_spec(spec); spec.loader.exec_module(chain)


class OwnerAdmission(unittest.TestCase):
    def test_absent_proc_is_exited_even_if_signal_probe_would_succeed(self):
        with patch.object(chain.Path,'exists',return_value=False),patch.object(chain.os,'kill') as kill:
            self.assertFalse(chain.pid_alive(424242))
            kill.assert_not_called()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.out=self.root/'new_chain'; (self.out/'inputs').mkdir(parents=True)
        self.owner=self.root/'owner'; self.owner.mkdir()
        self.prior=self.root/'prior'; self.prior.mkdir()
        self.future=self.root/'future'
        self.image=self.root/'image'; self.image.write_bytes(b'pinned image')
        self.owner_input=self.owner/'worker.py'; self.owner_input.write_bytes(b'pinned owner')
        chain.save(self.owner/'source-pins.json',{str(self.owner_input):chain.sha(self.owner_input)})
        chain.save(self.prior/'source-pins.json',{str(self.image):chain.sha(self.image)})
        chain.save(self.owner/'attempt.json',dict(owner_pid=424242,started=1))
        chain.save(self.owner/'result.json',dict(state='PASS',campaign=str(self.prior)))
        chain.save(self.prior/'result.json',dict(state='PASS',post_source_image_pins_match=True,cases=[dict(id='prior')]))
        self.worker=self.out/'inputs/chain_owner_v3.py'; self.worker.write_bytes((HERE/'chain_owner_v3.py').read_bytes())
        for name in ('campaign.py','collect.py','monitor_metrics.py'):
            (self.out/'inputs'/name).write_text('# frozen host-test fixture, never executed\n')
        self.plan=dict(owner_output=str(self.owner),prerequisite=str(self.prior),unit='owner.service',
            campaign=str(self.future),soc=str(self.root/'soc'),manifest=str(self.root/'manifest'),parallel=4)
        chain.save(self.out/'plan.json',self.plan)
        pins={str(p):chain.sha(p) for p in (self.worker,self.out/'plan.json',self.owner_input,
            self.owner/'source-pins.json',self.prior/'source-pins.json',self.image,
            *[self.out/'inputs'/n for n in ('campaign.py','collect.py','monitor_metrics.py')])}
        chain.save(self.out/'source-pins.json',pins)
        self.unit=dict(available=True,LoadState='loaded',ActiveState='inactive',MainPID='0',
                       ExecMainPID='424242',Result='success',ExecMainStatus='0')
        self.alive=False; self.calls=[]; self.sleeps=0
        self.on_sleep=None; self.on_collect=None; self.fail_successor=False

    def invoke(self,argv,**kwargs):
        self.calls.append((argv,kwargs))
        if 'prepare' in argv:
            self.assertFalse(self.alive)
            self.assertFalse(self.future.exists())
            self.future.mkdir(); (self.future/'inputs').mkdir()
            script=self.future/'inputs/campaign.py'
            script.write_bytes((self.out/'inputs/campaign.py').read_bytes())
            chain.save(self.future/'source-pins.json',{str(self.image):chain.sha(self.image),str(script):chain.sha(script)})
        elif 'execute' in argv:
            self.assertNotIn('start_new_session',kwargs)
            chain.save(self.future/'result.json',dict(state='INCOMPLETE' if self.fail_successor else 'PASS',
                post_source_image_pins_match=True,cases=[dict(id='new')]))
            (self.future/'numerical-evidence').write_text('original evidence')
            if self.fail_successor:
                return subprocess.CompletedProcess(argv,1)
        elif 'collect.py' in str(argv):
            if self.on_collect:
                self.on_collect(argv)
        else:
            self.fail('Unexpected real dispatch: '+repr(argv))
        return subprocess.CompletedProcess(argv,0)

    def sleep(self,seconds):
        self.assertEqual(seconds,60)
        self.sleeps+=1
        if self.sleeps>3:
            self.fail('Unexpected unbounded wait')
        if self.on_sleep:
            self.on_sleep()

    def execute(self):
        with patch.object(chain,'__file__',str(self.worker)), \
             patch.object(chain,'service_state',side_effect=lambda unit:dict(self.unit)), \
             patch.object(chain,'pid_alive',side_effect=lambda pid:self.alive), \
             patch.object(chain.subprocess,'run',side_effect=self.invoke), \
             patch.object(chain.time,'sleep',side_effect=self.sleep),contextlib.redirect_stdout(io.StringIO()):
            return chain.main(['execute','--output',str(self.out)])

    def assert_no_dispatch(self):
        self.assertFalse(any('prepare' in argv or 'execute' in argv for argv,_ in self.calls))
        self.assertFalse(self.future.exists())

    def test_campaign_pass_owner_collect_fail_never_dispatches(self):
        original=(self.prior/'result.json').read_bytes()
        chain.save(self.owner/'result.json',dict(state='FAIL',error='owner collect failed'))
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()
        self.assertEqual((self.prior/'result.json').read_bytes(),original)

    def test_campaign_pass_live_owner_waits_until_pass_and_exit(self):
        self.unit.update(ActiveState='active',MainPID='424242'); self.alive=True
        def finish():
            self.assert_no_dispatch()
            self.unit.update(ActiveState='inactive',MainPID='0'); self.alive=False
        self.on_sleep=finish
        self.assertEqual(self.execute(),0)
        self.assertEqual(self.sleeps,1)
        dispatched=[argv for argv,_ in self.calls if 'prepare' in argv or 'execute' in argv]
        self.assertEqual(len(dispatched),2)
        self.assertEqual(dispatched[0][-1],'4')

    def test_owner_pass_but_service_still_active_waits(self):
        self.unit.update(ActiveState='active',MainPID='424242')
        self.on_sleep=lambda:self.unit.update(ActiveState='inactive',MainPID='0')
        self.assertEqual(self.execute(),0); self.assertEqual(self.sleeps,1)

    def test_owner_exit_without_receipt_fails(self):
        (self.owner/'result.json').unlink()
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()

    def test_owner_missing_attempt_is_not_admitted(self):
        (self.owner/'attempt.json').unlink()
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()

    def test_pass_receipts_do_not_override_failed_service(self):
        self.unit.update(ActiveState='failed',Result='exit-code',ExecMainStatus='1')
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()

    def test_unloaded_unit_without_owner_receipt_is_not_success(self):
        self.unit=dict(available=False); (self.owner/'result.json').unlink()
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()

    def test_unloaded_unit_requires_pass_receipts_dead_pid_and_pins(self):
        self.unit=dict(available=False)
        self.assertEqual(self.execute(),0)
        result=json.loads((self.out/'result.json').read_text())
        self.assertFalse(result['owner_gate']['service']['available'])
        self.assertEqual(result['owner_gate']['owner_pid'],424242)

    def test_owner_registry_drift_blocks_dispatch(self):
        chain.save(self.owner/'source-pins.json',{})
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()

    def test_owner_dependency_receipt_is_rechecked(self):
        dependency=self.root/'ancestor-result.json'; dependency.write_text('PASS')
        chain.save(self.owner/'result.json',dict(state='PASS',campaign=str(self.prior),
            dependency_pins={str(dependency):chain.sha(dependency)}))
        dependency.write_text('FAIL')
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()

    def test_owner_result_drift_during_collect_blocks_dispatch(self):
        self.on_collect=lambda argv:chain.save(self.owner/'result.json',dict(state='FAIL'))
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()

    def test_owner_declared_inventory_hash_is_checked(self):
        chain.save(self.owner/'result.json',dict(state='PASS',campaign=str(self.prior),source_pins_sha256='0'*64))
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()

    def test_parent_control_completed_list_binds_final_campaign(self):
        chain.save(self.owner/'result.json',dict(state='PASS',completed=[dict(campaign=str(self.prior),
            result_sha256=chain.sha(self.prior/'result.json'))]))
        self.assertEqual(self.execute(),0)

    def test_wrong_campaign_owner_pass_is_rejected(self):
        chain.save(self.owner/'result.json',dict(state='PASS',campaign=str(self.root/'unrelated')))
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()

    def test_restarted_owner_pid_is_rejected(self):
        self.unit.update(ActiveState='active',MainPID='999999')
        self.assertEqual(self.execute(),1); self.assert_no_dispatch()

    def test_failed_successor_keeps_evidence_and_never_retries(self):
        self.fail_successor=True
        self.assertEqual(self.execute(),1)
        self.assertEqual((self.future/'numerical-evidence').read_text(),'original evidence')
        self.assertEqual(sum('execute' in argv for argv,_ in self.calls),1)
        with self.assertRaises(FileExistsError):
            self.execute()

    def test_final_collect_drift_prevents_owner_pass(self):
        def corrupt(argv):
            if str(self.future) in argv:
                self.image.write_bytes(b'changed')
        self.on_collect=corrupt
        self.assertEqual(self.execute(),1)
        self.assertFalse(json.loads((self.out/'result.json').read_text())['post_source_image_pins_match'])

    def test_result_is_published_last_and_binds_own_pins(self):
        saves=[]; original=chain.save
        def track(path,value):
            saves.append(path); original(path,value)
        with patch.object(chain,'save',side_effect=track):
            self.assertEqual(self.execute(),0)
        self.assertEqual(saves[-2:],[self.out/'status.json',self.out/'result.json'])
        result=json.loads((self.out/'result.json').read_text())
        self.assertEqual(result['source_pins_sha256'],chain.sha(self.out/'source-pins.json'))
        self.assertEqual(result['attempt_sha256'],chain.sha(self.out/'attempt.json'))
        self.assertEqual(result['dependency_pins'][str(self.owner/'result.json')],chain.sha(self.owner/'result.json'))

    def test_status_write_failure_does_not_publish_owner_pass_or_damage_numeric(self):
        original=chain.save
        def fail_status(path,value):
            if path==self.out/'status.json' and value.get('state')=='PASS':
                raise OSError('injected final status failure')
            original(path,value)
        with patch.object(chain,'save',side_effect=fail_status),self.assertRaises(OSError):
            self.execute()
        self.assertFalse((self.out/'result.json').exists())
        self.assertEqual(json.loads((self.future/'result.json').read_text())['state'],'PASS')
        self.assertEqual((self.future/'numerical-evidence').read_text(),'original evidence')

    def test_prepare_is_fresh_pins_owner_and_never_dispatches(self):
        soc=self.root/'soc'; soc.mkdir()
        chain.save(soc/'source-pins.json',{str(self.image):chain.sha(self.image)})
        chain.save(soc/'build.json',dict(image_pins={str(self.image):chain.sha(self.image)}))
        elf=self.root/'test.elf'; elf.write_bytes(b'host-only ELF fixture')
        manifest=self.root/'manifest.json'
        chain.save(manifest,dict(cases=[dict(elf=str(elf),elf_sha256=chain.sha(elf),
            source_pins=str(self.prior/'source-pins.json'))]))
        output=self.root/'prepared_v2'
        args=['--prepare','--output',str(output),'--owner-output',str(self.owner),
            '--prerequisite',str(self.prior),'--unit','owner.service','--soc',str(soc),
            '--manifest',str(manifest),'--campaign',str(self.future)]
        with patch.object(chain.subprocess,'run',side_effect=AssertionError('prepare dispatched a subprocess')):
            self.assertEqual(chain.main(args),0)
        self.assertFalse(self.future.exists())
        self.assertFalse((output/'attempt.json').exists())
        pins=json.loads((output/'source-pins.json').read_text())
        self.assertEqual(pins[str(self.owner/'source-pins.json')],chain.sha(self.owner/'source-pins.json'))
        self.assertEqual(pins[str(output/'inputs/chain_owner_v3.py')],chain.sha(output/'inputs/chain_owner_v3.py'))
        self.assertEqual(json.loads((output/'plan.json').read_text())['owner_output'],str(self.owner))
        with self.assertRaisesRegex(ValueError,'Fresh'):
            chain.main(args)


class ServiceLookup(unittest.TestCase):
    def test_bus_error_is_not_missing_unit_success(self):
        response=subprocess.CompletedProcess([],1,stdout='',stderr='bus unavailable')
        with patch.object(chain.subprocess,'run',return_value=response),self.assertRaises(ValueError):
            chain.service_state('owner.service')


if __name__=='__main__':
    unittest.main()
