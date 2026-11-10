#!/usr/bin/env python3
"""Host-only runner contracts. Synthetic receipts never count as simulator evidence."""
import copy
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('stage4_projection_vcs_test',HERE/'vcs_run.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
SOC=r.OUT/'stage3_soc_20261110_02'


def chain_proof(sw):
    return dict(state='SDK_CHAIN_LOG_CHECKED',scope=sw['scope'],protocol_checked=False,
        post_image_checked=False,performance_acceptance=False,full_ggml=False,whole_model=False,
        commands=256,outputs_checked_by_target=32768,independent_oracle_hashes_checked=True,
        trials=[{}]*4,vector_work=dict(commands=256,result_bytes=131072,alloc_write_done_checked=True),
        actual_entries=dict(counts=sw['expected_entries'],abba_producer_then_native64=True,elf_pc_insn_bound=True))


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc=r.b.read(SOC/'build.json')
        cls.sw=r.checker().checked_build(r.SOFTWARE)

    def test_actual_frozen_soc_build02_full_inventory(self):
        soc,sw,pins=r.collect(SOC)
        self.assertEqual(soc['configuration'],r.b.CONFIG)
        self.assertEqual(soc['image_contract'],r.b.IMAGE_CONTRACT)
        self.assertEqual(soc['cpu_overlay'],r.b.CPU_OVERLAY)
        self.assertEqual(sw['elf_sha256'],r.ELF_SHA)
        self.assertEqual(pins[str(r.SOFTWARE/'build.json')],r.BUILD_SHA)
        self.assertEqual(pins[str(r.SOFTWARE/'source-pins.json')],r.FW_PINS_SHA)
        self.assertEqual(sw['expected_entries'],dict(stage4_baseline_produce=2,
            stage4_candidate_produce=2,qbs_native_execute_command=256))
        self.assertFalse(any(Path(p).is_relative_to(r.ROOT/'hardware/src') for p in pins))

    def test_checker_import_isolation_from_cached_root_modules(self):
        poison={name:types.ModuleType(name) for name in ('check','contract','elf_reader','build_soc')}
        before=list(sys.path)
        with patch.dict(sys.modules,poison):
            module=r.checker()
            self.assertIsNot(module,poison['check'])
            self.assertIsNot(module.c,poison['contract'])
            self.assertEqual(Path(module.c.__file__),r.SOFTWARE/'inputs/contract.py')
            for name,value in poison.items():self.assertIs(sys.modules[name],value)
        self.assertEqual(sys.path,before)

    def test_frozen_checker_copy_and_identity_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            local=Path(temp)
            for name in r.CHECKER:shutil.copyfile(r.SOFTWARE/'inputs'/name,local/name)
            self.assertEqual(Path(r.checker(local).c.__file__),local/'contract.py')
            for name in r.CHECKER:
                saved=(local/name).read_bytes();(local/name).write_text('raise RuntimeError("not imported")\n')
                with self.assertRaisesRegex(ValueError,'Identity drift'):r.checker(local)
                (local/name).write_bytes(saved)

    def test_exact_recipes_and_independent_zero_exception_protocol(self):
        out=Path('/tmp/stage4-recipe-only');python='/usr/bin/python3.9'
        commands=r.recipes(out,self.soc,self.sw,python)
        sim=commands['simulation']
        self.assertEqual(sim[:6],[self.soc['simv'],'-no_save','-l',str(out/'work/run.vcs.log'),
            '+PRELOAD='+self.sw['elf'],'+TESTCASE=stage4_projection_chain'])
        for arg in ('+NO_FSDB','+NO_INSTR_TRACE','+QBS_PERF',
                    '+COMMIT_TRACE='+str(out/'work/commit.csv'),
                    '+VECTOR_TRACE='+str(out/'work/vector_trace.csv')):
            self.assertEqual(sim.count(arg),1)
        self.assertFalse(any('AKV_PERF' in x or 'RESIDENT_' in x or x=='+FSDB' for x in sim))
        self.assertEqual(commands['image_contract'],['/usr/bin/bash',str(out/'inputs/image-check.sh'),
            str(Path(self.soc['simv']).parent),self.sw['elf'],'qbs'])
        self.assertEqual(commands['chain'],[python,'-B',str(out/'inputs/checker/check.py'),
            '--build',str(r.SOFTWARE),'--log',str(out/'work/run.vcs.log'),
            '--vector',str(out/'work/vector_trace.csv'),'--commit',str(out/'work/commit.csv')])
        for flag in ('--require-events','--require-backend','--require-axi','--require-axi-write'):
            self.assertIn(flag,commands['protocol'])
        self.assertFalse(any('allow' in x or 'ignore' in x for x in commands['protocol']))

    def test_fixed_bounds_no_automatic_launch_or_retry(self):
        self.assertEqual((r.SIM_SECONDS,r.CHECK_SECONDS,r.PROTOCOL_SECONDS,r.SERVICE_SECONDS),
                         (9000,300,900,10800))
        self.assertLessEqual(sum(seconds for _,_,seconds in r.STEPS),r.SERVICE_SECONDS)
        self.assertEqual(r.OWN,('vcs_run.py','test_vcs_run.py'))
        source=(HERE/'vcs_run.py').read_text()
        self.assertNotIn('subprocess.Popen',source)
        self.assertNotIn('import check',source)
        self.assertNotIn('sys.path.insert',source)

    def test_exact_snapshot_closure_not_whole_new_directory(self):
        layout=r.source_layout(SOC)
        expected=set(r.OWN)|{'build_soc.py',*r.b.HELPERS,'image-check.sh'}|{'checker/'+n for n in r.CHECKER}
        self.assertEqual({name for name in layout if not name.startswith('verification/')},expected)
        for p in r.protocol_inventory():
            self.assertIn('verification/'+str(Path(p).relative_to(r.ROOT/'verification')),layout)
        self.assertNotIn('README.md',layout)
        self.assertNotIn('build.py',layout)
        self.assertEqual(r.b.sha(layout['build_soc.py']),r.BUILDER_SHA)

    def test_environment_accepted_allowlist_no_cwd_library(self):
        source=dict(VCS_HOME='/vcs',VCS_ARCH_OVERRIDE='linux',SNPSLMD_LICENSE_FILE='port@host',
            HOME='/home/test',LD_LIBRARY_PATH=':/one:/one::/two:',SECRET='never forwarded',
            LLAMA_ATTN_SIM_L2_BYTES='1')
        with patch.object(r.b,'read',return_value={'environment':source}):
            env=r.environment(SOC,Path('/tmp/chain'))
        self.assertNotIn('SECRET',env);self.assertNotIn('LLAMA_ATTN_SIM_L2_BYTES',env)
        self.assertEqual(env['LD_LIBRARY_PATH'],'/vcs/linux64/lib:/one:/two')
        self.assertEqual(env['PYTHONPATH'],'/tmp/chain/inputs/verification')
        self.assertEqual(env['READELF'],'/usr/bin/readelf')
        for key in ('VCS_HOME','SNPSLMD_LICENSE_FILE'):
            altered=dict(source);altered[key]=''
            with patch.object(r.b,'read',return_value={'environment':altered}),self.assertRaises(ValueError):
                r.environment(SOC,Path('/tmp/chain'))
        source['HOME']='/home/test\nwrong'
        with patch.object(r.b,'read',return_value={'environment':source}),self.assertRaises(ValueError):
            r.environment(SOC,Path('/tmp/chain'))

    def test_direct_service_review_and_single_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'work').mkdir();(out/'source-pins.json').write_text('{}')
            review=r.b.sha(out/'source-pins.json')
            s=dict(python='/usr/bin/python3.9',environment={'LC_ALL':'C','PYTHONPATH':'/frozen'})
            with patch.object(r,'verify_prepared',return_value=(s,)):
                argv=r.service_command(out,review)
                self.assertEqual(argv[0],'/usr/bin/systemd-run')
                self.assertIn('--property=KillMode=control-group',argv)
                self.assertIn('--property=RuntimeMaxSec=10800',argv)
                self.assertIn('--property=StandardOutput=append:'+str(out/'service.stdout.log'),argv)
                self.assertIn('--setenv=LC_ALL=C',argv)
                self.assertIn(str(out/'inputs/vcs_run.py'),argv)
                self.assertIn('--parent-reviewed',argv)
                self.assertEqual(argv[-2:],['--review-sha256',review])
                self.assertFalse(any(x in argv for x in ('nohup','bash','sh','&')))
                with self.assertRaises(ValueError):r.service_command(out,'wrong')
                for name in ('attempt.json','owner.json','result.json','work/stale'):
                    p=out/name;p.write_text('{}')
                    with self.assertRaises(ValueError):r.service_command(out,review)
                    p.unlink()

    def test_unreviewed_or_live_worker_rejected_before_claim(self):
        out=r.OUT/'stage4_projection_chain_vcs_unit_only'
        with patch.object(r.b,'claim_attempt') as claim:
            for reviewed in (False,True):
                with self.assertRaisesRegex(ValueError,'Parent-reviewed frozen worker'):
                    r.run(out,'not-a-review',reviewed)
            claim.assert_not_called()
        for bad in (r.OUT/'stage4_projection_chain_build_wrong',Path('/tmp/stage4_projection_chain_vcs_x')):
            with self.assertRaises(ValueError):r.output_path(bad)

    def test_frozen_chain_result_contract_mutations(self):
        proof=chain_proof(self.sw);r.checked_chain(proof,self.sw)
        for path,value in ((('scope',),'wrong'),(('commands',),255),(('outputs_checked_by_target',),8192),
            (('independent_oracle_hashes_checked',),False),(('protocol_checked',),True),
            (('performance_acceptance',),True),(('full_ggml',),True),(('trials',),[{}]*3),
            (('vector_work','result_bytes'),131064),(('vector_work','commands'),255),
            (('actual_entries','counts','stage4_candidate_produce'),1),
            (('actual_entries','counts','qbs_native_execute_command'),255),
            (('actual_entries','abba_producer_then_native64'),False)):
            altered=copy.deepcopy(proof);node=altered
            for key in path[:-1]:node=node[key]
            node[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(ValueError):r.checked_chain(altered,self.sw)

    def test_real_image_protocol_identity_and_zero_exceptions(self):
        with tempfile.TemporaryDirectory() as temp:
            log,vector=Path(temp)/'log',Path(temp)/'vector'
            log.write_text('identity fixture only, not a simulation\n');vector.write_text('identity fixture only\n')
            proof=dict(status='PASS',issues=[],elf_sha256=self.sw['elf_sha256'],
                simv_sha256=r.b.sha(self.soc['simv']),
                sim_image_sha256={p:h for p,h in self.soc['image_pins'].items()
                                  if p==self.soc['simv'] or p.endswith('.so')},
                log_sha256=r.b.sha(log),vector_trace_sha256=r.b.sha(vector),
                contract_counts=dict(exceptions=0,protocol_errors=0,outstanding=0))
            r.checked_protocol(proof,self.soc,self.sw,log,vector)
            for key,value in (('status','FAIL'),('issues',['failure']),('elf_sha256','bad'),
                ('simv_sha256','bad'),('sim_image_sha256',{}),('log_sha256','bad'),
                ('vector_trace_sha256','bad'),('contract_counts',{})):
                with self.subTest(key=key),self.assertRaises(ValueError):
                    r.checked_protocol(dict(proof,**{key:value}),self.soc,self.sw,log,vector)
            for key in proof['contract_counts']:
                for value in (1,None,False):
                    altered=copy.deepcopy(proof);altered['contract_counts'][key]=value
                    with self.assertRaises(ValueError):r.checked_protocol(altered,self.soc,self.sw,log,vector)

    def test_executed_commands_cwd_timeouts_and_owner_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'work').mkdir();(out/'source-pins.json').write_text('{}')
            s=dict(commands={key:[key,'+exact-input'] for key,_,_ in r.STEPS})
            owner=dict(unit=r.service_unit(out),cgroup='/user.slice/'+r.service_unit(out),main_pid=42,owner_pid=42)
            r.b.save(out/'owner.json',owner)
            r.b.save(out/'attempt.json',dict(review_sha256=r.b.sha(out/'source-pins.json'),**owner))
            originals={}
            for command,name,seconds in r.STEPS:
                p=out/'work'/(name+'.command.json')
                originals[p]=dict(argv=s['commands'][command],cwd=str(out/'work'),timeout_seconds=seconds)
                r.b.save(p,originals[p])
            r.execution_receipts(out,s)
            for p,original in originals.items():
                for key,value in (('argv',['wrong-input']),('cwd','/wrong'),('timeout_seconds',1)):
                    p.unlink();r.b.save(p,dict(original,**{key:value}))
                    with self.assertRaises(ValueError):r.execution_receipts(out,s)
                p.unlink();r.b.save(p,original)
            (out/'owner.json').unlink();r.b.save(out/'owner.json',dict(owner,main_pid=99))
            with self.assertRaises(ValueError):r.execution_receipts(out,s)

    def test_qbs_image_and_unique_success_required(self):
        valid='sim_qbs_enabled=1\nsim_l2_bytes=16777216\n'
        r.checked_image_log(valid)
        for bad in (valid+valid,valid.replace('enabled=1','enabled=0'),valid.replace('16777216','2097152')):
            with self.assertRaises(ValueError):r.checked_image_log(bad)
        valid='Core Test *** SUCCESS ***\n';r.successful_log(valid)
        for bad in ('',valid+valid,valid+'Fatal: broken\n',valid+'FAILED\n'):
            with self.assertRaises(ValueError):r.successful_log(bad)

    def test_pin_merges_reject_conflicts(self):
        pins={'same':'digest'};r.merge(pins,{'same':'digest','another':'value'})
        self.assertEqual(pins,{'same':'digest','another':'value'})
        with self.assertRaises(ValueError):r.merge(pins,{'same':'changed'})


if __name__=='__main__':unittest.main()
