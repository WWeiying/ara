#!/usr/bin/env python3
"""Host-only source/identity/oracle, fail-stop and startup/admission regressions."""
import copy
import csv
import errno
from fractions import Fraction
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import replay_remainder75 as replay
import check_remainder75 as checker
from prepare_batch import HERE, INTEGRATION, sha, save
from prepare_successor import replacements, symbol
from audit_accepted8 import OBJDUMP
from replay_candidate03 import read, pins_check, oracle

DATA = checker.DATA


def fixture_plan():
    cases = read(DATA / 'prepared75/provenance.json')['cases']
    names = [c['id'] for c in cases]
    return dict(names=names,remaining_source_names=[c['original_case']['name'] for c in cases],
        remaining_source_keys=[[c['original_case']['sew'],c['original_case']['lmul'],c['original_case']['selected_trial']['op']] for c in cases],
        accepted_source_names=[r['original_case']['name'] for r in read(HERE / 'acceptance_audit01/audit.json')['results']],
        jobs=4,timeout_per_case_s=300,retries=0,stop_first_failure=True,skip_accepted_execution=True,
        parent_closure=False,original_linux_elf_replay=False,image=str(replay.IMAGE),image_sha256=replay.IMAGE_SHA,
        service_runtime_max_s=6300,requires_parent_review=True,
        unit=replay.UNIT,programs=str(DATA / 'soc75'),
        stages=[dict(name='first12',cases=names[:12],jobs=4),dict(name='remaining63',cases=names[12:],jobs=4)])


class Gates(unittest.TestCase):
    def test_all75_sources_full_oracle_host_and_spike(self):
        pins_check(read(DATA / 'baseline_pins.json'))
        provenance = read(DATA / 'prepared75/provenance.json')
        sys.path.insert(0,str(INTEGRATION))
        from prepare import adapt
        checks = {r['name']:r for r in read(DATA / 'host_semantics.json')['results']}
        references = {r['name']:r for r in read(DATA / 'reference75/reference.json')['results']}
        programs = {backend:read(DATA / backend / 'programs.json')['programs'] for backend in ('soc75','spike75')}
        self.assertEqual(len(provenance['cases']),75)
        for file,digest in provenance['files'].items():
            self.assertEqual(sha(DATA / 'prepared75' / file),digest)
        for case in provenance['cases']:
            name,original = case['id'],case['original_case']
            folder = DATA / 'prepared75' / name
            adapted = adapt((Path(case['source_directory']) / 'scenario.c').read_text(),name)
            port = (folder / 'case.c').read_text()
            restored = port
            for before,after in replacements(original['selected_trial']['op']):
                self.assertEqual(restored.count(after),1)
                restored = restored.replace(after,before)
            self.assertEqual(restored,adapted)
            anchor = '            for(unsigned i=0;i<128;'
            self.assertEqual(port[port.index(anchor):],adapted[adapted.index(anchor):])
            for file,digest in original['scenario_sources'].items():
                self.assertEqual(sha(folder / 'original' / file),digest)
            cap = int(Fraction(original['lmul'].replace('mf','1/').replace('m',''))*1024/original['sew'])
            x,data = 0xe736815b449aec21,[]
            for _ in range(cap):
                for shift in (13,-7,17):
                    x = (x ^ (x << shift if shift > 0 else x >> -shift)) % (1 << 64)
                data.append(x % (1 << original['sew']))
            op = original['selected_trial']['op']
            index = 1 if op in (0,20) else 31 if op == 3 else 0
            self.assertEqual(checks[name]['full_cap_expected'],[91,data[index] if index < cap else 0]+[91]*(cap-2))
            self.assertEqual(checks[name]['tuple'],[0,op,0,2,0,0])
            self.assertEqual(checks[name]['guards'],[91,91])
            ref = references[name]
            self.assertEqual(ref['returncode'],0)
            self.assertEqual(ref['spike_target_hits'],1)
            self.assertEqual(ref['original_routine_instructions'],13)
            for backend in programs:
                entry = programs[backend][name]
                self.assertEqual(sha(Path(entry['path'])),entry['sha256'])
                self.assertEqual(ref['soc_elf_sha256'] if backend == 'soc75' else ref['elf_sha256'],entry['sha256'])
            log = DATA / 'reference75' / (name+'.log')
            self.assertEqual(sha(log),ref['log_sha256'])
            self.assertTrue(oracle(programs['spike75'][name],log.read_text()))
            self.assertEqual(sha(DATA / 'reference75' / (name+'.commits.log')),ref['commit_log_sha256'])
        for file in ('runtime.c','startup.S','replay.ld'):
            self.assertEqual((DATA / 'prepared75' / file).read_bytes(),(INTEGRATION / file).read_bytes())
        reused = read(HERE / 'remainder12_01/soc01/programs.json')['programs']
        self.assertEqual({n:programs['soc75'][n] for n in reused},reused)

    def test_exact_union_and_bad_plan_negative_gates(self):
        plan = fixture_plan()
        checker.validate_plan(plan)
        for key,value in (('jobs',5),('timeout_per_case_s',301),('retries',1),('parent_closure',True),
                          ('skip_accepted_execution',False),('original_linux_elf_replay',True),('unit','wrong.service'),
                          ('service_runtime_max_s',6301),('requires_parent_review',False)):
            bad = copy.deepcopy(plan)
            bad[key] = value
            with self.assertRaises(ValueError):
                checker.validate_plan(bad)
        for key in ('names','remaining_source_names','remaining_source_keys'):
            bad = copy.deepcopy(plan)
            bad[key][1] = bad[key][0]
            with self.assertRaises(ValueError):
                checker.validate_plan(bad)
        bad = copy.deepcopy(plan)
        bad['remaining_source_names'][0] = bad['accepted_source_names'][0]
        with self.assertRaises(ValueError):
            checker.validate_plan(bad)
        coverage = read(DATA / 'coverage83.json')
        self.assertEqual((coverage['accepted'],coverage['prepared_not_dut'],coverage['not_prepared']),(8,75,0))
        self.assertEqual(len({tuple(r['shape_opcode']) for r in coverage['records']}),83)
        self.assertEqual(len({r['parent']['name'] for r in coverage['records']}),19)
        self.assertTrue(all(not r['parent_closed'] for r in coverage['records']))

    def test_stage_fail_stop_and_same_worker_progression(self):
        plan = fixture_plan()
        calls = []
        self.assertEqual(replay.run_stages(plan,lambda s:calls.append(s['name']) or 1,lambda s:None),1)
        self.assertEqual(calls,['first12'])
        calls.clear()
        def reject(s):
            raise ValueError('independent gate rejected')
        with self.assertRaises(ValueError):
            replay.run_stages(plan,lambda s:calls.append(s['name']) or 0,reject)
        self.assertEqual(calls,['first12'])
        calls.clear()
        self.assertEqual(replay.run_stages(plan,lambda s:calls.append('run:'+s['name']) or 0,
            lambda s:calls.append('gate:'+s['name'])),0)
        self.assertEqual(calls,['run:first12','gate:first12','run:remaining63','gate:remaining63'])

    def test_resource_cap_memory_unknown_and_unreadable_failclosed(self):
        available = 64*1024**3
        live = [dict(pid=i,argv=['simv','+PRELOAD='+token+'input']) for i in range(4)
                for token in ['/candidate04_regression38_03/']]
        self.assertEqual(replay.resource_gate(live,available)['total_live_reserved'],24)
        self.assertTrue(replay.resource_gate(live,available)['passed'])
        self.assertFalse(replay.resource_gate(live+[dict(pid=99,argv=['simv','/unknown/'])],available)['passed'])
        self.assertFalse(replay.resource_gate(live,31*1024**3)['passed'])
        self.assertFalse(replay.resource_gate(live,available,True)['passed'])
        class Proc:
            def __init__(self,name,err):
                self.name,self.comm,self.err = '101',name,err
            def __truediv__(self,field):
                def fail():
                    raise self.err
                return SimpleNamespace(read_bytes=fail,read_text=lambda:self.comm)
        for name in ('simv','python3','UNKNOWN'):
            _,_,uncertain = replay.scan_processes([Proc(name,PermissionError(errno.EACCES,'denied'))])
            self.assertEqual(len(uncertain),1)
        self.assertFalse(replay.scan_processes([Proc('node',PermissionError(errno.EACCES,'denied'))])[2])
        self.assertFalse(replay.scan_processes([Proc('simv',FileNotFoundError(errno.ENOENT,'exited'))])[2])
        self.assertFalse(replay.scan_processes([Proc('simv',ProcessLookupError(errno.ESRCH,'exited'))])[2])

    def progress_fixture(self):
        plan = fixture_plan()
        stage = plan['stages'][0]
        simv = read(replay.IMAGE / 'image.json')['simv']
        cgroup = '/user/'+replay.UNIT
        before = []
        for pid,name in zip(range(101,105),stage['cases']):
            folder = replay.OUT / stage['name'] / 'replay/tests' / name
            before.append(dict(pid=pid,start_ticks=1,cpu_ticks=10,trace_bytes=100,last_cycle=100,
                executable=simv,cgroup=cgroup,cwd=str(folder / 'work'),argv=[simv,'+TESTCASE='+name,
                '+PRELOAD='+str(folder / 'input.elf'),'+COMMIT_TRACE='+str(folder / 'commit_trace.csv')]))
        return plan,stage,before,cgroup

    def monitor(self,mode):
        plan,stage,before,cgroup = self.progress_fixture()
        clock,counts,records,cancelled = [0.0],[0],[],[]
        class Proc:
            def __init__(self,row):
                self.name,self.row = str(row['pid']),row
            def __truediv__(self,_):
                return SimpleNamespace(read_bytes=lambda:('\0'.join(self.row['argv'])+'\0').encode())
        def sample(pid,args):
            n = counts[0]
            counts[0] += 1
            row = copy.deepcopy(before[pid-101])
            if mode == 'race' and n == 4:
                raise FileNotFoundError(errno.ENOENT,'worker exited')
            if mode == 'generation' and 4 <= n < 8:
                row['start_ticks'] = 2
            if mode == 'identity' and n >= 4:
                row['executable'] = '/wrong/simv'
            threshold = {'delayed':8,'race':9,'generation':12}.get(mode)
            if threshold is not None and n >= threshold:
                row.update(cpu_ticks=20,trace_bytes=200,last_cycle=200)
            return row
        saved = Path.read_text
        with patch.object(Path,'glob',return_value=[Proc(r) for r in before]), \
             patch.object(Path,'read_text',new=lambda p,*a,**k:cgroup if str(p)=='/proc/self/cgroup' else saved(p,*a,**k)), \
             patch.object(replay,'read',side_effect=lambda p:plan if p.name=='plan.json' else
                dict(cgroup=cgroup) if p.name=='worker.json' else read(p)), \
             patch.object(replay,'sample',side_effect=sample), \
             patch.object(replay.time,'monotonic',side_effect=lambda:clock[0]), \
             patch.object(replay.time,'sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)), \
             patch.object(replay,'save',side_effect=lambda p,r:records.append(copy.deepcopy(r))):
            replay.confirm_startup(stage,threading.Event(),lambda:cancelled.append(True))
        return records[0],clock[0],cancelled

    def test_startup_delayed_growth_exit_race_generation_and_identity(self):
        for mode in ('delayed','race','generation'):
            record,elapsed,cancelled = self.monitor(mode)
            self.assertEqual(record['status'],'ADVANCING_4_SIMV')
            self.assertGreaterEqual(elapsed,1.0)
            self.assertFalse(cancelled)
            checker.verify_progress(replay.OUT,fixture_plan(),fixture_plan()['stages'][0],record,
                                    dict(cgroup=record['worker_cgroup']))
        record,elapsed,cancelled = self.monitor('identity')
        self.assertEqual(record['status'],'NOT_CONFIRMED')
        self.assertLess(elapsed,1.0)
        self.assertTrue(cancelled)
        record,elapsed,cancelled = self.monitor('flat')
        self.assertEqual(record['status'],'NOT_CONFIRMED')
        self.assertEqual(elapsed,60.0)
        self.assertTrue(cancelled)
        self.assertTrue(record['samples'])

    def test_progress_ignores_claimed_checks_and_requires_raw_growth(self):
        plan,stage,before,cgroup = self.progress_fixture()
        after = copy.deepcopy(before)
        for row in after:
            row.update(cpu_ticks=20,trace_bytes=200,last_cycle=200)
        record = dict(status='ADVANCING_4_SIMV',samples=[before,after],raw_samples_retained=True,
                      worker_cgroup=cgroup,checks=[True]*4)
        checker.verify_progress(replay.OUT,plan,stage,record,dict(cgroup=cgroup))
        after[0]['last_cycle'] = 100
        with self.assertRaisesRegex(ValueError,'growth failed'):
            checker.verify_progress(replay.OUT,plan,stage,record,dict(cgroup=cgroup))

    def raw_fixture(self,root):
        name = 'gather_e16_m1_ops0'
        origin = HERE / 'successor01/vcs_candidate04_01/control/replay/tests' / name
        folder = root / name
        (folder / 'work').mkdir(parents=True)
        for file in ('input.elf','console.log','commit_trace.csv','work/run.vcs.log'):
            shutil.copyfile(origin / file,folder / file)
        inputs = read(origin / 'inputs.json')
        inputs['binary']['path'] = str(folder / 'input.elf')
        save(folder / 'inputs.json',inputs)
        command = read(origin / 'command.json')
        command['cwd'] = str(folder / 'work')
        command['command'] = [a.replace(str(origin),str(folder)) for a in command['command']]
        save(folder / 'command.json',command)
        entry = read(HERE / 'successor01/soc01/programs.json')['programs'][name]
        case, = [r for r in read(HERE / 'successor01/prepared01/provenance.json')['cases'] if r['id']==name]
        expected, = [r for r in read(HERE / 'successor01/host_semantics.json')['results'] if r['name']==name]
        audit, = [r for r in read(HERE / 'acceptance_audit01/audit.json')['results'] if r['name']==name]
        reference = dict(output_address=symbol(Path(entry['path']),'output',OBJDUMP)[0],
            soc_target=dict(pc=int(audit['target']['pc'],16),insn=audit['target']['insn']),
            returned_vstart_pc=int(audit['returned_vstart']['pc'],16))
        result = dict(name=name,status='PASS',returncode=0,reason='',artifact_dir=str(folder),elapsed_s=29.31)
        sys.path.insert(0,str(Path(read(replay.IMAGE / 'image.json')['snapshot']) / 'sources/verification'))
        from ara_verify.trace import validate_trace
        return result,folder,entry,read(replay.IMAGE / 'image.json'),case,expected,reference,validate_trace

    def test_raw_exit_fullmarkers_failure_veto_identity_and_retirement_negatives(self):
        with tempfile.TemporaryDirectory(prefix='host_raw_',dir=DATA) as tmp:
            args = list(self.raw_fixture(Path(tmp)))
            self.assertEqual(checker.check_case(*args)['scalar_output_reads'],64)
            args[0]['returncode'] = 1
            with self.assertRaisesRegex(ValueError,'not PASS/exit0'):
                checker.check_case(*args)
            args[0]['returncode'] = 0
            log = args[1] / 'console.log'
            original = log.read_text()
            for mutated in (original.replace('RVV_PERMUTE_PASS','ABSENT'),original+'\nRVV_PERMUTE_DETAIL op=0\n',
                            original+'\nBOARD_REPLAY_PASS\n'):
                log.write_text(mutated)
                with self.assertRaises(ValueError):
                    checker.check_case(*args)
            log.write_text(original)
            trace = args[1] / 'commit_trace.csv'
            rows = list(csv.DictReader(trace.open()))
            target, = [r for r in rows if r['event']=='retire' and int(r['pc'],16)==args[6]['soc_target']['pc']]
            target['insn'] = '00000013'
            with trace.open('w',newline='') as stream:
                writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ValueError):
                checker.check_case(*args)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Gates)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    plan = DATA / 'plan.json'
    destination = DATA / ('host_gate.json' if plan.exists() else 'preseal_host.json')
    evidence = dict(status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,
        worker_sha256=sha(HERE / 'replay_remainder75.py'),checker_sha256=sha(HERE / 'check_remainder75.py'),
        test_sha256=sha(Path(__file__)),plan_sha256=sha(plan) if plan.exists() else None,no_dut_launched=True)
    save(destination,evidence)
    if result.wasSuccessful() and plan.exists() and (DATA / 'dryrun_gate.json').exists():
        replay.checked_plan()
        save(DATA / 'review_ready.json',dict(status='READY_75_STRICT_PLAN_HOST_DRYRUN_NOT_DUT',
            plan_sha256=sha(plan),host_gate_sha256=sha(destination),dryrun_gate_sha256=sha(DATA / 'dryrun_gate.json'),
            jobs=4,timeout_per_case_s=300,unit=replay.UNIT,vcs_started=False))
    raise SystemExit(not result.wasSuccessful())
