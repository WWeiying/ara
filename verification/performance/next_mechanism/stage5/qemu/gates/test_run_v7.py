"""Host-only launcher contracts. Fixtures never count as native acceptance."""
import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('directed_launcher_host',HERE/'run_v7.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)


def proof(variant):
    cases=r.read(variant['expected'])['cases']
    return dict(state='DIRECTED_GUEST_ARCHITECTURE_CHECKED',checker_successor='info-result-v2',
        qemu_image_checked=False,service_owner_checked=False,rtl_timing=False,elf_sha256=variant['elf_sha256'],
        numerical=dict(cases=len(cases),traps=sum(bool(c['cause']) for c in cases),
            output_records=sum(len(c['expected']) for c in cases),csr_guards_checked=True),
        work=dict(helper_calls=sum(c['layer']!='decode' and c['op']!='info' for c in cases),
            memory_callback_faults=sum(c['layer']=='memory' for c in cases),successful_resident=sum(c['active'] for c in cases),
            ram_reads=0,real_no_end_faults_checked=True),
        info_trace=dict(records=sum(c['op']=='info' and not c['cause'] for c in cases),trace_results_checked=True))


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.fw=r.read(r.FIRMWARE/'build.json')

    def test_real_firmware03_and_successor_pins(self):
        fw,pins=r.collect_firmware()
        self.assertEqual(fw['state'],'DIRECTED_GUESTS_BUILT_NOT_EXECUTED')
        self.assertEqual(pins[str(r.FIRMWARE/'build.json')],r.FW_SHA)
        self.assertEqual([v['cases'] for v in fw['variants']],[100,4,2])

    def test_frozen_shared_build_validator_api(self):
        module=r.validator()
        self.assertTrue(callable(module.checked_build))
        self.assertEqual(module.PREPARED.name,'stage5_qemu_prepare_20261110_03')
        self.assertEqual(module.OWN,r.VALIDATOR_FILES)
        self.assertEqual(len(module.OWN),12)
        with tempfile.TemporaryDirectory() as temporary:
            frozen=Path(temporary)
            for name in r.VALIDATOR_FILES:shutil.copyfile(r.VALIDATOR_ROOT/name,frozen/name)
            copied=r.validator(frozen)
            self.assertEqual(copied.HERE,frozen)
            self.assertEqual(copied.v4.HERE,frozen)
            self.assertEqual(copied.identity(),module.identity())
        with patch.object(r,'VALIDATOR_SHA','0'*64),self.assertRaisesRegex(ValueError,'Identity drift'):r.validator()
        with patch.object(r,'VALIDATOR_SHA',None),self.assertRaisesRegex(ValueError,'not yet frozen'):r.validator()

    def variant_fixture(self,root):
        paths={name:root/name for name in ('original','variant','toolenv','audit','build')}
        for path in paths.values():path.mkdir()
        for name in ('original','variant'):
            path=paths[name];(path/'source').write_text('host fixture, not QEMU source')
            (path/'lock').write_bytes(b'')
            r.save(path/'source-pins.json',{str(path/'source'):r.sha(path/'source')})
            r.save(path/'tree-inventory.json',{'source':dict(kind='file',sha256=r.sha(path/'source'))})
        original=paths['original'];variant=paths['variant'];audit=paths['audit'];tools=paths['toolenv'];build=paths['build']
        r.save(original/'prepare.json',dict(source_pins_sha256=r.sha(original/'source-pins.json')))
        (audit/'archive-proof').write_text('fixture asset proof')
        apins={str(audit/'archive-proof'):r.sha(audit/'archive-proof')}
        r.save(audit/'audit.json',dict(pins=apins,artifacts=apins))
        r.save(variant/'prepare.json',dict(audit=str(audit),audit_sha256=r.sha(audit/'audit.json'),
            source_pins_sha256=r.sha(variant/'source-pins.json'),tree_inventory_sha256=r.sha(variant/'tree-inventory.json'),
            original_generated_metadata={str(original/'lock'):r.sha(original/'lock')}))
        (tools/'tool').write_text('fixture tool')
        tpins={str(tools/'tool'):r.sha(tools/'tool')};r.save(tools/'tool-pins.json',tpins)
        r.save(tools/'toolenv.json',dict(tool_pins_sha256=r.sha(tools/'tool-pins.json'),artifacts=tpins))
        for name in ('configure.log','build.log','qemu-system-riscv64'):(build/name).write_text('not executed')
        (build/'qemu-system-riscv64').chmod(0o700)
        report=dict(schema='stage5-qemu-build-v7',state='BUILT_NOT_EXECUTED',prepared=str(variant),
            prepare_sha256=r.sha(variant/'prepare.json'),original_prepare_sha256=r.sha(original/'prepare.json'),
            preflight=str(tools),preflight_sha256=r.sha(tools/'toolenv.json'),guest_executed=False,post_pins_match=True,
            executable=str(build/'qemu-system-riscv64'),executable_sha256=r.sha(build/'qemu-system-riscv64'),
            generated_metadata_after={str(variant/'lock'):r.sha(variant/'lock')})
        r.save(build/'build.json',report)
        module=SimpleNamespace(PREPARED=original,PREPARE_SHA=r.sha(original/'prepare.json'),
            ORIGINAL_TREE_SHA=r.sha(original/'tree-inventory.json'),checked_build=Mock(return_value=report))
        return paths,module,report

    def test_variant_original_audit_and_generated_metadata_are_pinned(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);paths,module,_=self.variant_fixture(root);build=paths['build'];digest=r.sha(build/'build.json')
            with patch.object(r,'OUT',root):contract,pins=r.collect_qemu(build,digest,module)
            module.checked_build.assert_called_once_with(build,digest)
            self.assertNotEqual(contract['prepared'],contract['original_prepared'])
            self.assertEqual(contract['original_prepared'],str(paths['original']))
            for name,file in (('original','source'),('variant','source'),('original','lock'),('variant','lock'),
                              ('audit','archive-proof'),('audit','audit.json'),('toolenv','tool')):
                self.assertEqual(pins[str(paths[name]/file)],r.sha(paths[name]/file))

    def test_variant_collector_rejects_old_schema_and_lock_drift(self):
        for mutation in ('v5','v6','lock'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);paths,module,report=self.variant_fixture(root)
                if mutation=='lock':(paths['variant']/'lock').write_bytes(b'not empty')
                else:report['schema']='stage5-qemu-build-'+mutation
                with patch.object(r,'OUT',root),self.assertRaises(ValueError):
                    r.collect_qemu(paths['build'],r.sha(paths['build']/'build.json'),module)

    def test_exact_modes_same_image_and_no_launch(self):
        qemu=dict(executable='/fixture/not-executed/qemu-system-riscv64')
        commands=r.recipes(Path('/tmp/directed-fixture'),qemu,self.fw,'/usr/bin/python3')
        self.assertEqual([c['mode'] for c in commands],[0,1,2])
        for mode,c in enumerate(commands):
            guest=c['guest'];self.assertEqual(guest[0],qemu['executable'])
            self.assertEqual(guest[guest.index('-kernel')+1],self.fw['variants'][mode]['elf'])
            cpu=guest[guest.index('-cpu')+1]
            self.assertIn('xaraqbs=true',cpu)
            self.assertIn('xaraakv='+('false' if mode==2 else 'true')+',',cpu)
            self.assertTrue(cpu.endswith('xaraakv-resident='+('true' if mode==0 else 'false')))
            self.assertIn('enable=akv_arch_*',guest)
            self.assertIn('check_v2.py',' '.join(c['checker']))
            self.assertFalse(any('ignore' in arg or 'allow' in arg for arg in c['checker']))

    def test_direct_service_review_one_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary);(out/'work').mkdir();(out/'source-pins.json').write_text('{}')
            review=r.sha(out/'source-pins.json');s=dict(python='/usr/bin/python3',environment=r.environment())
            with patch.object(r,'verify_prepared',return_value=(s,{},self.fw)):
                command=r.service_command(out,review)
                self.assertEqual(command[0],'/usr/bin/systemd-run')
                for option in ('--property=KillMode=control-group','--property=RuntimeMaxSec=1800','--parent-reviewed'):
                    self.assertIn(option,command)
                self.assertIn(str(out/'inputs/run_v7.py'),command)
                self.assertFalse(any(x in command for x in ('sh','bash','nohup','&')))
                with self.assertRaises(ValueError):r.service_command(out,'bad')
                for name in ('attempt.json','owner.json','result.json','work/stale'):
                    p=out/name;p.write_text('fixture')
                    with self.assertRaises(ValueError):r.service_command(out,review)
                    p.unlink()

    def test_environment_not_inherited(self):
        with patch.dict(os.environ,dict(LD_PRELOAD='poison',LD_LIBRARY_PATH='poison',PYTHONPATH='poison',CC='poison')):
            env=r.environment()
        for k in ('LD_PRELOAD','LD_LIBRARY_PATH','PYTHONPATH','CC'):self.assertNotIn(k,env)
        self.assertEqual(env['PATH'],'/usr/bin:/bin')
        self.assertEqual(env['XDG_RUNTIME_DIR'],'/run/user/'+str(os.getuid()))
        self.assertEqual(env['PYTHONNOUSERSITE'],'1')

    def test_checker_contract_and_typed_counts(self):
        for mode,variant in enumerate(self.fw['variants']):
            valid=proof(variant);r.checked_mode(valid,mode,variant)
            for path,value in [(('state',),'PASS'),(('checker_successor',),'old'),(('elf_sha256',),'bad'),
                (('qemu_image_checked',),True),(('info_trace','trace_results_checked'),False),
                (('numerical','traps'),True),(('work','memory_callback_faults'),False)]:
                changed=copy.deepcopy(valid);node=changed
                for key in path[:-1]:node=node[key]
                node[path[-1]]=value
                with self.subTest(mode=mode,path=path),self.assertRaises(ValueError):r.checked_mode(changed,mode,variant)

    def test_aggregate_requires_all_three_same_firmware(self):
        rows=[dict(mode=i,state='PASS',returncode=0,elf_sha256=v['elf_sha256'],checked=proof(v))
              for i,v in enumerate(self.fw['variants'])]
        r.aggregate_modes(rows,self.fw)
        for changed in (rows[:2],rows+[rows[-1]],list(reversed(rows)),
                        [dict(rows[0],returncode=False),*rows[1:]],
                        [dict(rows[0],state='FAIL'),*rows[1:]],
                        [dict(rows[0],elf_sha256='wrong'),*rows[1:]]):
            with self.assertRaises(ValueError):r.aggregate_modes(changed,self.fw)

    def test_first_failure_stops_no_retry_preserves_completed_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary);(out/'work').mkdir();pin=out/'pin';pin.write_text('synthetic fixture')
            s=dict(environment=r.environment(),commands=r.recipes(out,dict(executable='/not-run'),self.fw,'/python'))
            phases=[];rows=[]
            def fake(argv,cwd,log,seconds,env,status,status_path,phase):
                phases.append(phase)
                if phase=='MODE1_GUEST':raise ValueError('Synthetic first failure')
                if phase.endswith('_GUEST'):
                    log.write_text('host fixture, not guest execution');(cwd/'trace.log').write_text('')
                else:
                    p=proof(self.fw['variants'][0]);p.update(log_sha256=r.sha(cwd/'guest.log'),trace_sha256=r.sha(cwd/'trace.log'))
                    log.write_text(json.dumps(p))
                return dict(returncode=0)
            with patch.object(r,'execute',side_effect=fake),self.assertRaisesRegex(ValueError,'Synthetic first failure'):
                r.run_modes(out,s,self.fw,{str(pin):r.sha(pin)},dict(invocation_id='a'*32),rows)
            self.assertEqual(phases,['MODE0_GUEST','MODE0_CHECK','MODE1_GUEST'])
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['mode'],0)
            self.assertFalse((out/'work/mode2').exists())

    def test_checker_cannot_mutate_original_guest_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary);(out/'work').mkdir();pin=out/'pin';pin.write_text('fixture')
            s=dict(environment=r.environment(),commands=r.recipes(out,dict(executable='/not-run'),self.fw,'/python'))
            def fake(argv,cwd,log,seconds,env,status,status_path,phase):
                if phase.endswith('_GUEST'):
                    log.write_text('fixture');(cwd/'trace.log').write_text('fixture')
                else:
                    (cwd/'guest.log').write_text('mutated');log.write_text('{}')
                return dict(returncode=0)
            with patch.object(r,'execute',side_effect=fake),self.assertRaisesRegex(ValueError,'Identity drift'):
                r.run_modes(out,s,self.fw,{str(pin):r.sha(pin)},dict(invocation_id='a'*32))

    def test_timeout_cleanup_and_failed_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);process=Mock(pid=123456,returncode=-15)
            process.wait.side_effect=[subprocess.TimeoutExpired(['fixture'],1),-15]
            with patch.object(r.subprocess,'Popen',return_value=process),patch.object(r.os,'killpg') as kill, \
                 self.assertRaises(subprocess.TimeoutExpired):
                r.execute(['fixture'],directory,directory/'guest.log',1,{}, {},directory/'status.json','FIXTURE')
            self.assertEqual(kill.call_count,1)
            receipt=r.read(directory/'guest.command.json')
            self.assertEqual(receipt['state'],'INTERRUPTED_OR_TIMEOUT');self.assertEqual(receipt['returncode'],-15)

    def test_nonzero_exit_never_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);process=Mock(pid=123456,returncode=7);process.wait.return_value=7
            with patch.object(r.subprocess,'Popen',return_value=process),self.assertRaisesRegex(ValueError,'Command exit failure'):
                r.execute(['fixture'],directory,directory/'guest.log',1,{}, {},directory/'status.json','FIXTURE')
            self.assertEqual(r.read(directory/'guest.command.json')['returncode'],7)

    def test_failed_prepare_cannot_be_resumed(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary);(out/'source-pins.json').write_text('{}');r.save(out/'selection.json',{})
            r.save(out/'prepared.json',dict(state='PREPARED_NOT_EXECUTED',guest_executed=False,source_pins_sha256=r.sha(out/'source-pins.json')))
            r.save(out/'prepare-report.json',dict(state='FAIL'))
            with patch.object(r,'output_path',side_effect=Path),self.assertRaisesRegex(ValueError,'Preparation failed'):
                r.verify_prepared(out)

    def test_owner_and_live_run_rejected_before_execution(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaisesRegex(ValueError,'systemd invocation'):
            r.owner(Path('/tmp/owner-fixture'))
        with patch.object(r,'output_path',side_effect=Path),patch.object(r,'owner') as owner:
            for reviewed in (False,True):
                with self.assertRaisesRegex(ValueError,'Reviewed frozen worker'):
                    r.run(Path('/tmp/live-worker'),'bad',reviewed)
            owner.assert_not_called()

    def test_consumer_can_validate_with_recorded_python(self):
        out=Path('/tmp/no-execution');qemu=dict(executable='/not-run')
        s=r.selection(out,qemu,self.fw,python='/usr/bin/python3.11')
        self.assertEqual(s['python'],str(Path('/usr/bin/python3.11').resolve()))
        self.assertEqual(r.OWN,('run_v7.py','test_run_v7.py'))
        self.assertLess(3*(r.GUEST_SECONDS+r.CHECK_SECONDS),r.SERVICE_SECONDS)


if __name__=='__main__':
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--output',type=Path)
    args,other=p.parse_known_args()
    if args.output is None:unittest.main(argv=[sys.argv[0],*other])
    else:
        out=args.output.absolute()
        if out.parent!=r.OUT or out!=out.resolve() or out.exists():raise ValueError('Fresh direct signoff output required')
        out.mkdir();inputs=out/'inputs';inputs.mkdir();pins={}
        for n in r.OWN:
            source=HERE/n;shutil.copyfile(source,inputs/n)
            pins[str(source)]=r.sha(source);pins[str(inputs/n)]=r.sha(inputs/n)
        log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(RunnerTests))
        (out/'host.log').write_text(log.getvalue());r.save(out/'source-pins.json',pins)
        matched=all(r.sha(Path(path))==h for path,h in pins.items())
        report=dict(state='HOST_DIRECTED_RUNNER_PASS_NOT_EXECUTED' if result.wasSuccessful() and matched else 'FAIL',
            host_tests=result.testsRun,post_pins_match=matched,qemu_executed=False,prepared=False,
            source_pins_sha256=r.sha(out/'source-pins.json'))
        r.save(out/'result.json',report);print(log.getvalue(),end='');print(json.dumps(report,sort_keys=True))
        raise SystemExit(int(report['state']=='FAIL'))
