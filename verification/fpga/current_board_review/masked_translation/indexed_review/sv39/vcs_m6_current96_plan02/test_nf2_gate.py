"""Full-schema synthetic NF2 gate negatives; never reads live NF2 artifacts."""
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import nf2_gate as g


class NF2Gate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Module import only. The real admission/static_identity is NOT executed.
        cls.authority=g.load_auditor()
        cls.original_plan=g.read(g.P/'plan.json')

    def save(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,indent=2)+'\n')

    def text(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=g.HERE,prefix='nf2_host_synthetic_')
        self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.A=self.root/'audit';self.F=self.root/'worker';self.P=self.F/'prepared01'
        self.REF=self.root/'reference';self.J4=self.root/'J4';self.T=self.A/'terminal01';self.W=self.A/'wait01'
        # Functions retain their module globals; patch ONLY for synthetic Host scope.
        a=self.authority
        for name,value in [('HERE',self.A),('F',self.F),('P',self.P),('REF',self.REF),('J4',self.J4)]:
            scope=patch.object(a,name,value);scope.start();self.addCleanup(scope.stop)
        for name,value in [('A',self.A),('P',self.P)]:
            scope=patch.object(g,name,value);scope.start();self.addCleanup(scope.stop)
        self.text(self.root/'sentinel','unchanged synthetic input')
        self.basepins={str(self.root/'sentinel'):g.sha(self.root/'sentinel')}
        self.plan=copy.deepcopy(self.original_plan)
        self.plan['pins']=dict(self.basepins)
        for i,case in enumerate(self.plan['cases']):
            p=self.root/'elfs'/f'{i}.elf';self.text(p,f'synthetic not executable {i}')
            case.update(elf=str(p),sha256=g.sha(p))
        self.save(self.P/'plan.json',self.plan);self.plan_sha=g.sha(self.P/'plan.json')
        for module in (g,a):
            scope=patch.object(module,'PLAN_SHA',self.plan_sha);scope.start();self.addCleanup(scope.stop)
        self.coverage={'synthetic_complete10_schema_only':g.NAMES}
        self.prepared=dict(pins=self.basepins,coverage=self.coverage)
        self.save(self.A/'prepared.json',self.prepared);self.prepared_sha=g.sha(self.A/'prepared.json')
        scope=patch.object(g,'PREPARED_SHA',self.prepared_sha);scope.start();self.addCleanup(scope.stop)
        self.ledger=dict(simv='/synthetic/not-executed/simv',files={'synthetic-image':'fixed'})
        checker=SimpleNamespace(VETO=re.compile(r'FAIL'),common=SimpleNamespace(SUCCESS='Core Test *** SUCCESS *** (tohost = 0)'))
        scope=patch.object(a,'static_identity',return_value=(self.plan,dict(self.basepins),checker,self.ledger,None))
        scope.start();self.addCleanup(scope.stop)
        scope=patch.object(a,'source_identity',return_value=self.coverage);scope.start();self.addCleanup(scope.stop)
        # Only static identity resolution is substituted; admission() below is unchanged.
        owner=dict(properties=dict(Id=a.UNIT,MainPID='123',LoadState='loaded',ActiveState='active',SubState='running',
            RuntimeMaxUSec='7h 30min',KillMode='control-group',Restart='no',ControlGroup='/user/'+a.UNIT),
            pid=123,cgroup='0::/user/'+a.UNIT)
        self.save(self.F/'parent_review.json',{'synthetic':True});parent_sha=g.sha(self.F/'parent_review.json')
        scope=patch.object(a,'PARENT_SHA',parent_sha);scope.start();self.addCleanup(scope.stop)
        self.launch=dict(owner=owner,plan_sha256=self.plan_sha,started=1,
                         approval_pins={str(self.F/'parent_review.json'):parent_sha})
        self.save(self.P/'launch.json',self.launch)
        self.run=dict(status='COMPLETE',tests=g.NAMES,status_counts={'PASS':10},jobs=3,timeout_s=None,
            seed=1,simv=self.ledger['simv'],commit_trace=True,input_snapshots=True,code_coverage=False,
            contract_monitor=False,probe_kinds=[],created_at='2026-10-12T00:00:00+00:00',
            completed_at='2026-10-12T00:01:00+00:00',invocation=[str(self.F/'replay.py'),'run',
            '--authorize-run','--plan-sha256',self.plan_sha,'--parent-review',str(self.F/'parent_review.json'),
            '--parent-review-sha256',parent_sha])
        self.save(self.P/'replay/run.json',self.run)
        self.results=[];self.items=[];self.exits=[]
        evidence=[self.P/n for n in ('launch.json','replay/run.json','replay/summary.json')]
        for case in self.plan['cases']:
            name=case['id'];root=self.P/'replay/tests'/name;n=case['MX_N']
            result=dict(name=name,kind='app',status='PASS',reason=None,returncode=0,elapsed_s=1.0,artifact_dir=str(root))
            self.results.append(result)
            self.text(root/'input.elf',Path(case['elf']).read_text())
            self.save(root/'inputs.json',dict(binary=dict(source=case['elf'],path=str(root/'input.elf'),sha256=case['sha256']),
                simv=dict(path=self.ledger['simv'],image_sha256=self.ledger['files'])))
            command=dict(command=[self.ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1',
                '+PRELOAD='+str(root/'input.elf'),'+TESTCASE='+name,'+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')],cwd=str(root/'work'))
            self.save(root/'command.json',command)
            child=dict(result,schema='UNVALIDATED_CHILD_OUTCOME_V1',architectural_acceptance=False,
                command=command,command_path=str(root/'command.json'),command_sha256=g.sha(root/'command.json'))
            self.save(root/'child_outcome.unvalidated.json',child)
            report=dict(status='NF2_CSV_ORACLE_PASS',cases=list(range(n)),checks=case['checks'],
                alternate_protected_field=[False]*n,checkpoints=[dict(case=i//2,phase=1+i%2) for i in range(2*n)],traps=[])
            strict=dict(status='STRICT_NF2_ORIGINAL_SCOPE_PASS',case_id=name,observer=report,
                source_cases=case['source_cases'],positive_controls=case.get('positive_controls',[]),
                observer_generation=case['kind'],current_image='M6',Linux_signalframe_proved=False,
                child_outcome_sha256=g.sha(root/'child_outcome.unvalidated.json'))
            self.save(root/'strict_original.json',strict)
            if case['kind']=='remaining34':
                oc=[sys.executable,'-B',str(self.REF/'observer_cli.py'),'--group',case['group'],'--csv',str(root/'commit_trace.csv'),'--out',str(root/'observer.json')]
                self.save(root/'observer.json',report);self.text(root/'observer.stdout','NF2_CSV_ORACLE_PASS\n')
                evidence.append(root/'observer.json')
            else:
                oc=[sys.executable,'-B',str(self.J4/'csv_check.py'),str(root/'commit_trace.csv'),'--symbols',str(self.J4/'reference01/soc.symbols.json')]
                self.save(root/'observer.stdout',report)
            self.save(root/'observer.command.json',dict(command=oc,cwd=str(self.F),timeout_s=600))
            self.text(root/'observer.stderr','')
            for p in (root/'console.log',root/'work/run.vcs.log'):
                self.text(p,case['pass_markers'][0]+'\n'+checker.common.SUCCESS+'\n$finish\n')
            self.text(root/'commit_trace.csv','SYNTHETIC ROWS; NOT AN ARCHITECTURAL CSV\n')
            generic=dict(rows=10,retire_count=9);self.save(root/'trace_summary.json',dict(generic,status='VALID'))
            item=dict(status='INDEPENDENT_ONE_CSV_ACCEPTED',name=name,csv_parses=1,generic=generic,observer=report,
                source_cases=case['source_cases'],positive_controls=case.get('positive_controls',[]),child_outcome=child,
                csv_sha256=g.sha(root/'commit_trace.csv'),lossless=dict(rows=10,delivered=10,before_sha256='0'*64,after_sha256='0'*64),
                actual_pc_counts={'0x80000000':9},audit_seconds=0.001)
            self.items.append(item);self.save(self.T/name/'result.json',item)
            self.text(self.T/(name+'.stdout'),'INDEPENDENT_ONE_CSV_ACCEPTED\n');self.text(self.T/(name+'.stderr'),'')
            ex=dict(name=name,pid=1000+len(self.exits),actual_wait_returncode=0,time=3,
                stdout_sha256=g.sha(self.T/(name+'.stdout')),stderr_sha256=g.sha(self.T/(name+'.stderr')))
            self.exits.append(ex);self.save(self.T/(name+'.exit.json'),ex)
            evidence += [root/k for k in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log',
                'commit_trace.csv','trace_summary.json','child_outcome.unvalidated.json','observer.command.json',
                'observer.stdout','observer.stderr','strict_original.json')]
        self.save(self.P/'replay/summary.json',self.results)
        self.done=dict(status=a.PASS,plan_sha256=self.plan_sha,results=self.results,retries=0,aborted=False,
            pins_unchanged=True,new34_accepted=True,J4_current_M6_accepted=True,positive_controls_not_failure_count=2,
            source_failure_count_with_accepted_pilot=40,Linux_signalframe_proved=False,finished=100,
            evidence_pins={str(p):g.sha(p) for p in evidence})
        self.save(self.P/'complete.json',self.done)
        self.result=dict(status=g.ACCEPT,accepted=True,plan_sha256=self.plan_sha,parent_sha256=parent_sha,
            prepared_sha256=self.prepared_sha,complete_sha256=g.sha(self.P/'complete.json'),image_sha256=g.IMAGE_SHA,
            cases=self.items,case_audit_exits=self.exits,source_coverage=self.coverage,
            aggregate=dict(csv_files=10,csv_parses=10,rows=100,retired_rows=90,
                checks=sum(c['checks'] for c in self.plan['cases']),checkpoints=76,pagefaults=0,ecalls=0),
            pins_verified=0,original_plan_pins=1240,pins_pre_post_unchanged=True,source_failures_this_batch=36,
            prior_pilot_source_failures=4,distinct_failed_sources_current_M6=40,positive_controls_separate=2,
            prior_pilot_audit_sha256=self.plan['pilot_audit_sha256'],outer_service_returncode=None,
            outer_service_terminal_observed=False,no_retry=True,Linux_signalframe_proved=False,
            original_linux_ELF_replay=False,reference_substituted_for_DUT=False,audit_seconds=1)
        self.save(self.T/'result.json',self.result);self.text(self.T/'REVIEW.md','Synthetic accepted schema only\n')
        self.resign()

    def resign(self):
        # Re-sign synthetic evidence to test semantic rejection, not stale hashes alone.
        done=g.read(self.P/'complete.json')
        done['evidence_pins']={p:g.sha(p) for p in done['evidence_pins']}
        self.save(self.P/'complete.json',done);complete_sha=g.sha(self.P/'complete.json')
        pins=dict(self.basepins)
        pins.update({str(self.A/'prepared.json'):self.prepared_sha,str(self.P/'complete.json'):complete_sha})
        pins.update(self.launch['approval_pins']);pins.update(done['evidence_pins'])
        self.save(self.T/'verified_pins.json',pins)
        result=g.read(self.T/'result.json');result['complete_sha256']=complete_sha;result['pins_verified']=len(pins)
        self.save(self.T/'result.json',result)
        self.save(self.W/'audit_invocation.json',dict(pid=222,parent_pid=221,started=2,
            command=[sys.executable,'-B',str(self.A/'audit.py'),'terminal','--authorize-terminal-audit',
                '--prepared-sha256',self.prepared_sha,'--complete-sha256',complete_sha],
            complete_sha256=complete_sha,prepared_sha256=self.prepared_sha))
        self.text(self.W/'audit.stdout.log',g.ACCEPT+' '+g.sha(self.T/'result.json')+'\n')
        self.text(self.W/'audit.stderr.log','')
        self.save(self.W/'audit_exit.json',dict(pid=222,actual_wait_returncode=0,time=4,
            evidence='Actual subprocess.Popen.wait; synthetic schema only',
            stdout_sha256=g.sha(self.W/'audit.stdout.log'),stderr_sha256=g.sha(self.W/'audit.stderr.log')))
        self.save(self.W/'complete.json',dict(status='INDEPENDENT_TERMINAL_AUDIT_ACCEPTED',actual_audit_returncode=0,
            result_sha256=g.sha(self.T/'result.json'),review_sha256=g.sha(self.T/'REVIEW.md'),complete_sha256=complete_sha,no_retry=True))
        self.rebind()

    def rebind(self):
        self.payload=dict(decision='TERMINAL_INDEPENDENTLY_ACCEPTED',terminal_path=str(self.P/'complete.json'),
            terminal_sha256=g.sha(self.P/'complete.json'),plan_sha256=self.plan_sha,audit_prepared_sha256=self.prepared_sha,
            result_path=str(self.T/'result.json'),result_sha256=g.sha(self.T/'result.json'),
            verified_pins_sha256=g.sha(self.T/'verified_pins.json'),audit_exit_sha256=g.sha(self.W/'audit_exit.json'),
            wait_complete_sha256=g.sha(self.W/'complete.json'),review_sha256=g.sha(self.T/'REVIEW.md'))

    def mutate(self,path,key,value,resign=True):
        data=g.read(path);data[key]=value;self.save(path,data)
        if resign:self.resign()
        else:self.rebind()

    def check(self):return g.check(self.payload,auditor=self.authority)

    def rejected(self):
        with self.assertRaises((ValueError,AssertionError,KeyError,OSError,TypeError)):self.check()

    def test_complete_positive_full_schema(self):
        pins=self.check();self.assertIn(str(self.P/'replay/run.json'),pins)
        self.assertEqual(len(g.read(self.T/'result.json')['cases']),10)
        self.assertIsNone(g.read(self.T/'result.json')['outer_service_returncode'])

    def test_accepted_false(self):
        self.mutate(self.T/'result.json','accepted',False);self.rejected()

    def test_not_accepted_text(self):
        self.mutate(self.T/'result.json','status','NOT_ACCEPTED_NO_RETRY');self.rejected()

    def test_old_text_review_schema(self):
        self.payload['review_path']=str(self.T/'REVIEW.md');self.rejected()

    def test_partial_wrong_members(self):
        done=g.read(self.P/'complete.json');done['results']=[dict(self.results[0],name='wrong',status='FAIL',returncode=17)]
        self.save(self.P/'complete.json',done);self.resign();self.rejected()

    def test_retry_one(self):
        self.mutate(self.P/'complete.json','retries',1);self.rejected()

    def test_retry_false_not_integer(self):
        self.mutate(self.P/'complete.json','retries',False);self.rejected()

    def test_abort_true(self):
        self.mutate(self.P/'complete.json','aborted',True);self.rejected()

    def test_child_bool_not_integer(self):
        self.mutate(self.P/'replay/tests'/g.NAMES[0]/'child_outcome.unvalidated.json','returncode',False);self.rejected()

    def test_child_exit17(self):
        self.mutate(self.P/'replay/tests'/g.NAMES[0]/'child_outcome.unvalidated.json','returncode',17);self.rejected()

    def test_result_bool_not_integer(self):
        results=g.read(self.P/'replay/summary.json');results[0]['returncode']=False
        self.save(self.P/'replay/summary.json',results)
        self.mutate(self.P/'complete.json','results',results);self.rejected()

    def test_run_partial(self):
        self.mutate(self.P/'replay/run.json','status','RUNNING');self.rejected()

    def test_run_wrong_members(self):
        self.mutate(self.P/'replay/run.json','tests',g.NAMES[:-1]);self.rejected()

    def test_missing_oracle_pin(self):
        done=g.read(self.P/'complete.json');done['evidence_pins'].pop(str(self.P/'replay/tests'/g.NAMES[0]/'strict_original.json'))
        self.save(self.P/'complete.json',done);self.resign();self.rejected()

    def test_missing_run_pin(self):
        done=g.read(self.P/'complete.json');done['evidence_pins'].pop(str(self.P/'replay/run.json'))
        self.save(self.P/'complete.json',done);self.resign();self.rejected()

    def test_full_pin_drift(self):
        self.text(self.root/'sentinel','drift');self.rejected()

    def test_verified_pins_partial(self):
        pins=g.read(self.T/'verified_pins.json');pins.pop(str(self.P/'replay/run.json'))
        self.save(self.T/'verified_pins.json',pins);self.rebind();self.rejected()

    def test_stale_result(self):
        self.mutate(self.T/'result.json','complete_sha256','0'*64,resign=False);self.rejected()

    def test_wrong_image(self):
        self.mutate(self.T/'result.json','image_sha256','0'*64);self.rejected()

    def test_independent_partial_members(self):
        self.mutate(self.T/'result.json','cases',self.items[:-1]);self.rejected()

    def test_audit_exit17(self):
        self.mutate(self.W/'audit_exit.json','actual_wait_returncode',17,resign=False);self.rejected()

    def test_audit_exit_bool(self):
        self.mutate(self.W/'audit_exit.json','actual_wait_returncode',False,resign=False);self.rejected()

    def test_wait_exit_bool(self):
        self.mutate(self.W/'complete.json','actual_audit_returncode',False,resign=False);self.rejected()

    def test_missing_exit(self):
        (self.W/'audit_exit.json').unlink();self.rejected()

    def test_wait_not_accepted(self):
        self.mutate(self.W/'complete.json','status','NOT_ACCEPTED_NO_RETRY',resign=False);self.rejected()

    def test_wrong_wait_result(self):
        self.mutate(self.W/'complete.json','result_sha256','0'*64,resign=False);self.rejected()

    def test_outer_exit_must_not_be_invented(self):
        self.mutate(self.T/'result.json','outer_service_returncode',0);self.rejected()

    def test_prepared_identity_wrong(self):
        self.payload['audit_prepared_sha256']='0'*64;self.rejected()

    def test_wrong_fixed_plan_identity(self):
        self.payload['plan_sha256']='0'*64;self.rejected()

    def test_independent_postpins_false(self):
        self.mutate(self.T/'result.json','pins_pre_post_unchanged',False);self.rejected()
