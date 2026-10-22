"""Offline runner contract tests; no simulator, converter, compiler or service."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_failed_repair_20261008_v5 as runner


class BuildContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / 'image04'
        self.image = self.build / 'sim/simv'
        self.image.parent.mkdir(parents=True)
        self.image.write_text('dummy image, never executed')
        self.image.chmod(0o700)
        library = Path(str(self.image)+'.daidir') / 'model.so'
        library.parent.mkdir()
        library.write_text('dummy runtime')
        self.rtl = self.root / 'source.sv'
        self.rtl.write_text('source pin fixture')
        self.images = runner.base.simulation_image(self.image)
        sources = runner.base.pins([self.rtl])
        tools = {str(Path(runner.__file__).with_name(n)):runner.SEALS[n]
                 for n in ('build_memory_vl0_repair.py','run_vcs_dve_checkpoint.py')}
        self.status = dict(status='PASS',old_vdb_reuse=False,image=self.images,unit='build04.service')
        for filename,value in [('build-status.json',self.status),('build-source-pins.json',sources),
            ('build-image.json',self.images),('build-tool-pins.json',tools),
            ('compile.command.json',dict(command=runner.legacy.builder.compile_command(self.build),
                                        cwd=str(runner.ROOT),timeout_s=7200)),
            ('sim/vcs_source_manifest.json',dict(files=[dict(path=str(self.rtl),sha256=sources[str(self.rtl)])]))]:
            runner.base.save(self.build/filename,value)
        (self.build/'compile.log').write_text('compiler completed fixture')
        (self.build/'sim/simulator.conf').write_text('fixture configuration')
        mock = patch.object(runner.base,'sources',side_effect=lambda p:runner.base.read(p))
        mock.start(); self.addCleanup(mock.stop)

    def test_verified_persisted_build_accepts_collected_unit(self):
        self.assertTrue(runner.build_ready(self.status,'build04.service',{'LoadState':'not-found'}))
        pins,proof=runner.build_evidence(self.build)
        self.assertIn(str(self.rtl),pins)
        self.assertEqual(proof['runtime_files'],2)
        self.assertFalse(proof['independent_compiler_exit_receipt'])

    def test_gc_without_pass_is_not_success(self):
        for state in ({},dict(self.status,status='BUILDING'),dict(self.status,status='FAIL')):
            with self.assertRaises(RuntimeError):
                runner.build_ready(state,'build04.service',{'LoadState':'not-found'})

    def test_live_pass_receipt_waits_for_service(self):
        self.assertFalse(runner.build_ready(self.status,'build04.service',
                         dict(LoadState='loaded',ActiveState='active',MainPID='123')))

    def test_nonzero_or_failed_service_rejected(self):
        for active,code in [('failed','1'),('inactive','2'),('failed','0')]:
            with self.assertRaises(RuntimeError):
                runner.build_ready(self.status,'build04.service',dict(LoadState='loaded',
                    ActiveState=active,MainPID='0',ExecMainStatus=code,Result='exit-code'))

    def test_service_identity_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'identity'):
            runner.build_ready(self.status,'other.service',{'LoadState':'not-found'})

    def test_source_drift_rejected(self):
        self.rtl.write_text('changed after build')
        with self.assertRaisesRegex(RuntimeError,'frozen input changed'):
            runner.build_evidence(self.build)

    def test_runtime_added_library_rejected(self):
        (Path(str(self.image)+'.daidir')/'extra.so').write_text('unsealed')
        with self.assertRaisesRegex(RuntimeError,'inventory differs'):
            runner.build_evidence(self.build)

    def test_manifest_source_mismatch_rejected(self):
        runner.base.save(self.build/'sim/vcs_source_manifest.json',dict(files=[]))
        with self.assertRaisesRegex(RuntimeError,'source manifest differs'):
            runner.build_evidence(self.build)

    def test_wrong_build_producer_rejected(self):
        runner.base.save(self.build/'build-tool-pins.json',{})
        with self.assertRaisesRegex(RuntimeError,'build producer'):
            runner.build_evidence(self.build)

    def test_build_command_configuration_rejected(self):
        data=runner.base.read(self.build/'compile.command.json')
        data['command'].append('nr_lanes=8')
        runner.base.save(self.build/'compile.command.json',data)
        with self.assertRaisesRegex(RuntimeError,'configuration differs'):
            runner.build_evidence(self.build)


class FreshExecution(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.name=runner.FOCUSED[0]
        self.directory=self.root/'results'/self.name
        self.directory.mkdir(parents=True)
        self.image=self.root/'image04/sim/simv'
        self.image.parent.mkdir(parents=True);self.image.write_text('never execute')
        (self.directory/'input.elf').write_text('dummy ELF')
        self.command=[str(self.image),'+PRELOAD='+str(self.directory/'input.elf')]
        runner.base.save(self.directory/'command.json',dict(command=self.command))
        self.stack.enter_context(patch.object(runner.legacy,'simulation_command',return_value=self.command))
        self.spawn=self.stack.enter_context(patch.object(runner.subprocess,'Popen'))
        self.proc=self.spawn.return_value.__enter__.return_value
        self.proc.pid=12345;self.proc.returncode=0;self.proc.wait.return_value=0
        self.proc.poll.return_value=0
        self.auditor=self.stack.enter_context(patch.object(runner,'audit',return_value=(
            dict(status='PASS'),dict(status='PASS',last_cycle=100))))

    def run_case(self,pins=None):
        return runner.run_case(self.name,self.root,self.image,pins or {},self.command)[1]

    def test_wait_exit_receipt_precedes_audit(self):
        def audit(*args):
            receipt=runner.base.read(self.directory/'simulation-exit.json')
            self.assertEqual(receipt['returncode'],0)
            self.assertEqual(receipt['pid'],12345)
            self.assertFalse(receipt['timeout'])
            self.assertFalse(receipt['audit_started'])
            return dict(status='PASS'),dict(last_cycle=100)
        self.auditor.side_effect=audit
        result=self.run_case()
        self.assertEqual(result['status'],'PASS')
        self.assertTrue(result['simulator_process_exit_verified'])
        self.assertFalse(result['reused_completed_same_image'])

    def test_bad_exit_blocks_audit(self):
        self.proc.wait.return_value=self.proc.returncode=7
        self.assertEqual(self.run_case()['status'],'FAIL')
        self.auditor.assert_not_called()
        self.assertEqual(runner.base.read(self.directory/'simulation-exit.json')['returncode'],7)

    def test_timeout_kills_only_owned_process_group_no_retry(self):
        self.proc.wait.side_effect=[subprocess.TimeoutExpired(self.command,1800),-9]
        self.proc.returncode=-9
        with patch.object(runner.os,'killpg') as kill:
            self.assertEqual(self.run_case()['status'],'FAIL')
            kill.assert_called_once_with(12345,runner.signal.SIGKILL)
        self.assertEqual(self.spawn.call_count,1)
        self.assertTrue(runner.base.read(self.directory/'simulation-exit.json')['timeout'])
        self.auditor.assert_not_called()

    def test_prelaunch_pin_failure_caught(self):
        result=self.run_case({str(self.image):'bad hash'})
        self.assertEqual(result['status'],'FAIL')
        self.assertFalse(result['simulation_launched'])
        self.spawn.assert_not_called()

    def test_prior_artifacts_no_receipt_refused(self):
        (self.directory/'run.vcs.log').write_text('partial failed attempt')
        self.assertIn('prior attempt',self.run_case()['reason'])
        self.spawn.assert_not_called()

    def test_spawn_error_recorded(self):
        self.spawn.side_effect=OSError('unable to execute')
        self.assertEqual(self.run_case()['status'],'FAIL')
        self.assertFalse((self.directory/'simulation-exit.json').exists())


class ScopeContracts(unittest.TestCase):
    def test_sealed_successor_dispatch(self):
        runner.sealed_modules()
        with patch.object(runner.prior,'completed_logs',return_value=dict(status='PASS')), \
             patch('audit_qbs_canonical_repair_v2.audit',return_value=dict(status='PASS')) as qbs, \
             patch('audit_fof_repair_v3.audit',return_value=dict(status='PASS')) as fof:
            runner.audit(Path('/tmp/no-execution'),'qbs_canonical')
            runner.audit(Path('/tmp/no-execution'),'vgap112_sv39_fof')
            qbs.assert_called_once();fof.assert_called_once()

    def test_no_execute_is_readonly_future_image(self):
        with tempfile.TemporaryDirectory(dir=runner.ROOT/'verification/out') as temp:
            out=Path(temp)/'new';image=Path(temp)/'future-image04'
            with patch.object(runner.base,'check_service',side_effect=AssertionError('service called')), \
                 patch.object(runner.subprocess,'Popen',side_effect=AssertionError('spawn called')), \
                 contextlib.redirect_stdout(io.StringIO()) as log:
                self.assertEqual(runner.main(['--image-directory',str(image),'--output',str(out)]),0)
            self.assertFalse(out.exists())
            self.assertEqual(json.loads(log.getvalue())['total'],23)

    def test_reuse_options_not_accepted(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                runner.main(['--image-directory','/tmp/build','--output','/tmp/out',
                             '--previous-output','/tmp/reuse05'])

    def test_preflight_failure_stops_before_any_launch(self):
        with tempfile.TemporaryDirectory(dir=runner.ROOT/'verification/out') as temp:
            output=Path(temp)/'new';image=Path(temp)/'image04'
            with patch.object(runner.base,'check_service'), \
                 patch.object(runner,'build_evidence',return_value=({},{})), \
                 patch.object(runner,'prepare_cases',side_effect=ValueError('bad ELF contract')), \
                 patch.object(runner.subprocess,'Popen') as spawn:
                with self.assertRaisesRegex(ValueError,'bad ELF'):
                    runner.main(['--execute','--image-directory',str(image),'--output',str(output)])
            spawn.assert_not_called()
            state=runner.base.read(output/'status.json')
            self.assertEqual(state['status'],'STOPPED')
            self.assertIn('bad ELF contract',state['controller_error'])

    def test_existing_output_never_overwritten(self):
        with tempfile.TemporaryDirectory(dir=runner.ROOT/'verification/out') as temp:
            output=Path(temp)/'existing';output.mkdir()
            original=dict(status='PASS',owner='prior run')
            runner.base.save(output/'status.json',original)
            with patch.object(runner.base,'check_service') as service, \
                 patch.object(runner.subprocess,'Popen') as spawn:
                with self.assertRaisesRegex(RuntimeError,'Fresh separate output'):
                    runner.main(['--execute','--image-directory',str(Path(temp)/'image04'),
                                 '--output',str(output)])
            spawn.assert_not_called();service.assert_not_called()
            self.assertEqual(runner.base.read(output/'status.json'),original)

    def test_all_23_actual_original_elf_commands_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp);image=output/'future-image04/sim/simv'
            with patch.object(runner.subprocess,'Popen', wraps=subprocess.Popen):
                # simulation_command runs readelf only; the image does not exist.
                pins,commands=runner.prepare_cases(output,image)
            self.assertEqual(tuple(commands),runner.SCOPE)
            self.assertEqual(len(commands),23)
            mmio=0
            for name,command in commands.items():
                self.assertEqual(command[0],str(image))
                self.assertEqual(runner.base.sha256(output/'results'/name/'input.elf'),
                                 runner.base.sha256(runner.legacy.source(name)/'input.elf'))
                mmio+=not any(a.startswith('+COMMIT_TOHOST=') for a in command)
            self.assertEqual(mmio,9)
            runner.base.check(pins)

    def test_all_23_fresh_success_two_gates(self):
        with tempfile.TemporaryDirectory() as temp:
            calls=[]
            def run(name,*args):
                calls.append(name);return name,dict(status='PASS')
            with patch.object(runner,'run_case',side_effect=run):
                self.assertEqual(runner.dispatch(Path(temp),Path('/image04'),{},
                                 dict.fromkeys(runner.SCOPE,[]),1),0)
            self.assertEqual(calls,list(runner.SCOPE))

    def test_first_failure_stops_queue_and_neighbours(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(runner,'run_case',return_value=(runner.FOCUSED[0],dict(status='FAIL'))) as run:
                self.assertEqual(runner.dispatch(Path(temp),Path('/image04'),{},
                                 dict.fromkeys(runner.SCOPE,[]),1),1)
            run.assert_called_once()
            status=runner.base.read(Path(temp)/'status.json')
            self.assertTrue(all(status['cases'][n]['status']=='QUEUED' for n in runner.NEIGHBOURS))


if __name__=='__main__':unittest.main()
