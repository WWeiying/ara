"""Prepared-only NF7 M6 terminal auditor; explicit authorization required to parse."""
import argparse
import ast
from collections import Counter
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REF=HERE.parent
G=HERE.parents[3]
F=REF/'vcs_m6_current96_plan02'
P=F/'prepared01'
UNIT='ara-nf7-current96-m6-02.service'
PLAN_SHA='eebd310b9b9ccdf5b5ca398d556b2a7b6d07746c0f4149972130716ab7481cc0'
PARENT_SHA='80c8d257fbbfcb917287668e9da308867ff2b0ea26ad2478ec75a08d23777852'
LAUNCH_SHA='8427a10c7a2c6e9eba928ae5e1e2678463afc6766787c8356a736df3195509aa'
IMAGE_SHA='a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
PASS='PASS_M6_NF7_SOURCE_DERIVED96_GROUPS24_NOT_LINUX'
ACCEPT='INDEPENDENT_M6_NF7_FULL96_24CSV_ACCEPTED_NOT_LINUX'
NAMES=[f'nf7_g{i:02d}' for i in range(24)]
OLD=G/'masked_translation/segment_review/nf2_remaining4_terminal_audit01'
OLD_SHA='67aeb830406e679513dea0bb3a14236b6afd0ae9e1e2c97af40402b02f737110'
WAIT_SHA='1b46120b0e1d74353f61e247fc4aaadcc548c072975888c019c34d69815d2c41'


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


assert hashlib.sha256((OLD/'audit.py').read_bytes()).hexdigest()==OLD_SHA
u=load(OLD/'audit.py','nf7_accepted_utilities')
sha,read,save,add,verify=u.sha,u.read,u.save,u.add,u.verify


def zero(value):return type(value) is int and value==0


def elapsed(value,limit):return type(value) in (int,float) and math.isfinite(value) and 0<value<=limit


def complete_fields(plan,done,run,summary):
    assert done['status']==PASS and done['plan_sha256']==PLAN_SHA and done['image_sha256']==IMAGE_SHA
    assert done['aborted'] is False and zero(done['retries']) and done['pins_unchanged'] is True and not done.get('error')
    assert done['results']==summary and [r['name'] for r in summary]==NAMES
    assert done['trials']==list(range(96)) and done['groups']==24 and done['checks']==284816 and done['checkpoints']==168
    assert done['Linux_replay'] is False
    assert run['status']=='COMPLETE' and run['tests']==NAMES and run['status_counts']=={'PASS':24}
    assert run['jobs']==4 and run['timeout_s']==2400 and run['seed']==1
    assert run['commit_trace'] is True and run['input_snapshots'] is True and run['code_coverage'] is False
    assert run['contract_monitor'] is False and run['probe_kinds']==[]
    assert datetime.fromisoformat(run['completed_at'])>datetime.fromisoformat(run['created_at'])
    assert [c['id'] for c in plan['cases']]==NAMES
    for case,r in zip(plan['cases'],summary):
        assert r['name']==case['id'] and r['kind']=='app' and r['status']=='PASS' and not r['reason']
        assert zero(r['returncode']) and elapsed(r['elapsed_s'],2400)


def child_fields(result,child,command,command_sha):
    assert child['schema']=='UNVALIDATED_SIMULATOR_OUTCOME_V1'
    assert zero(child['returncode']) and child['returncode']==result['returncode']
    assert child['elapsed_s']==result['elapsed_s'] and elapsed(child['elapsed_s'],2400)
    assert child['timed_out'] is False and child['failure_seen'] is False and child['architectural_acceptance'] is False
    assert not child.get('command_identity_error')
    assert child['command']==command['command'] and child['cwd']==command['cwd'] and child['command_sha256']==command_sha


def static_identity():
    assert sha(P/'plan.json')==PLAN_SHA and sha(F/'parent_review.json')==PARENT_SHA and sha(P/'launch.json')==LAUNCH_SHA
    plan,parent,launch=read(P/'plan.json'),read(F/'parent_review.json'),read(P/'launch.json')
    assert len(plan['pins'])==878 and plan['status']=='PREPARED_NOT_RUN' and plan['image_sha256']==IMAGE_SHA
    assert plan['unit']==UNIT and [plan[k] for k in ('jobs','timeout_s','group_timeout_s','worker_timeout_s','service_timeout_s')]==[4,2400,2700,16200,16800]
    assert all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','no_coverage','stop_first_fail'))
    assert parent['decision']=='AUTHORIZE_NF7_CURRENT96_M6_ONCE' and parent['plan_sha256']==PLAN_SHA
    assert parent['image_sha256']==IMAGE_SHA and parent['unit']==UNIT and parent['budget_risk_accepted'] is True
    assert parent['entry_review_sha256']=='afb5b8f6e3e162f9172798fb7b76bf30fb3ba76a5a1ee3d67065c8656439d1da'
    pins=dict(plan['pins']);add(pins,launch['approval_pins'])
    add(pins,{str(P/'plan.json'):PLAN_SHA,str(F/'parent_review.json'):PARENT_SHA,str(P/'launch.json'):LAUNCH_SHA,
        str(OLD/'audit.py'):OLD_SHA,str(OLD/'wait_terminal.py'):WAIT_SHA,
        str(u.TRANSPORT):u.TRANSPORT_SHA,str(u.SUPPORT):u.SUPPORT_SHA})
    verify(pins)
    gate=load(F/'nf2_gate.py','nf7_frozen_NF2_contract')
    nf2pins=gate.bind_payload(parent['nf2_gate'])
    assert all(launch['approval_pins'][p]==h for p,h in nf2pins.items())
    # This is the actual completed NF2 prerequisite, not its early preparation label.
    nf2=read(gate.A/'terminal01/result.json');wait=read(gate.A/'wait01/complete.json')
    assert nf2['status']==gate.ACCEPT and nf2['accepted'] is True and nf2['image_sha256']==IMAGE_SHA
    assert nf2['complete_sha256']==parent['nf2_gate']['terminal_sha256']=='1deb030547d83611710247a8f486f7035eb30caa04e43a1dd9f78ba378f30ede'
    assert sha(gate.A/'terminal01/result.json')==parent['nf2_gate']['result_sha256']=='b9fb37c4fa561fedb9df805bcf242d77d0c5711469e04a3d5384d17dc63ea6f0'
    assert wait['status']=='INDEPENDENT_TERMINAL_AUDIT_ACCEPTED' and zero(wait['actual_audit_returncode'])
    assert zero(read(gate.A/'wait01/audit_exit.json')['actual_wait_returncode'])
    assert wait['result_sha256']==parent['nf2_gate']['result_sha256'] and wait['complete_sha256']==nf2['complete_sha256']
    assert launch['plan_sha256']==PLAN_SHA and launch['approval_pins'][str(F/'parent_review.json')]==PARENT_SHA
    owner=launch['owner'];prop=owner['properties']
    assert owner['pid']==1604833 and prop['MainPID']=='1604833' and prop['Id']==UNIT
    assert [prop[k] for k in ('LoadState','ActiveState','SubState','RuntimeMaxUSec','KillMode','Restart')]==['loaded','active','running','4h 40min','control-group','no']
    assert prop['ControlGroup'].endswith('/'+UNIT) and prop['ControlGroup'] in [l.split(':',2)[-1] for l in owner['cgroup'].splitlines()]
    ledger=read(Path(plan['image'])/'image.json');snapfile=Path(ledger['snapshot'])/'snapshot.json';snap=read(snapfile)
    assert sha(Path(plan['image'])/'image.json')==IMAGE_SHA
    assert sha(snapfile)==plan['snapshot_sha256']==ledger['snapshot_sha256']
    assert snap['state']=='SEALED' and len(snap['files'])==539 and len(ledger['files'])==66
    assert all(pins[p]==h for p,h in ledger['files'].items())
    assert all(pins[str(Path(snap['root'])/p)]==h for p,h in snap['files'].items())
    assert sha(Path(plan['image'])/'_build/vcs/simulator.conf')==ledger['configuration_sha256']=='6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785'
    assert [c['id'] for c in plan['cases']]==NAMES and [t for c in plan['cases'] for t in c['trials']]==list(range(96))
    assert sum(c['checks'] for c in plan['cases'])==284816 and sum(c['checkpoints'] for c in plan['cases'])==sum(c['traps'] for c in plan['cases'])==168
    trace=Path(snap['root'])/'verification/ara_verify/trace.py';assert str(trace) in pins
    return plan,pins,ledger,trace


def prepare():
    assert not (HERE/'prepared.json').exists()
    host=read(HERE/'host01/status.json');assert host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==0
    verify(host['pins']);assert sha(HERE/'host01/log.txt')==host['log_sha256']
    plan,pins,_,trace=static_identity();elf_reader=load(u.SUPPORT,'nf7_elf_reader');specs={}
    for c in plan['cases']:
        d=Path(c['source']);symbols=read(d/'soc.symbols.json')
        code={str(int(m[1],16)):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',(d/'soc.dis').read_text(),re.M)}
        get,actual=elf_reader.elf(c['elf']);assert sha(c['elf'])==c['sha256']
        for name,pc in symbols.items():assert actual[name][0]==pc
        for pc,insn in code.items():assert int.from_bytes(get(int(pc),4 if insn&3==3 else 2),'little')==insn
        assert code[str(symbols['fault_0_pc'])]==0xcd056c07 and code[str(symbols['fault_1_pc'])]==0xcd056c27
        specs[c['id']]=dict(symbols=symbols,code=code)
    for n in ('audit.py','wait_terminal.py','test_host.py','README.md','host01/status.json','host01/log.txt'):
        p=HERE/n
        if p.suffix=='.py':ast.parse(p.read_text(),filename=str(p))
        add(pins,{str(p):sha(p)})
    verify(pins)
    save(HERE/'prepared.json',dict(status='PREPARED_NOT_STARTED_REQUIRES_PARENT_AUTHORIZATION',plan_sha256=PLAN_SHA,
        parent_sha256=PARENT_SHA,launch_sha256=LAUNCH_SHA,pins=pins,specs=specs,trace_module=str(trace),
        wait_seconds=18000,audit_timeout_seconds=7200,case_audit_timeout_seconds=600,service_timeout_seconds=27000,
        no_retry=True,groups=24,trials=96,checks=284816,checkpoints=168,pagefaults=72,ecalls=96,
        active_CSV_reads=0,reference_execution=False,DUT_launches=0,watcher_started=False))
    print('PREPARED_NOT_STARTED',sha(HERE/'prepared.json'),flush=True)


def admission(prepared_sha,complete_sha):
    assert sha(HERE/'prepared.json')==prepared_sha and sha(P/'complete.json')==complete_sha
    prepared=read(HERE/'prepared.json');verify(prepared['pins'])
    plan,pins,ledger,_=static_identity()
    add(pins,prepared['pins']);add(pins,{str(HERE/'prepared.json'):prepared_sha,str(P/'complete.json'):complete_sha})
    done,run,summary=read(P/'complete.json'),read(P/'replay/run.json'),read(P/'replay/summary.json')
    complete_fields(plan,done,run,summary)
    assert run['simv']==ledger['simv']
    argv=run['invocation'];assert argv[:2]==[str(F/'replay.py'),'run'] and '--authorize-run' in argv
    for opt,want in (('--out',str(P)),('--plan-sha256',PLAN_SHA),('--parent-review',str(F/'parent_review.json')),('--parent-review-sha256',PARENT_SHA)):
        assert argv[argv.index(opt)+1]==want
    start=read(P/'launch.json')['started'];assert start<=done['finished']<start+16800
    expected={str(P/n) for n in ('launch.json','replay/run.json','replay/summary.json')}
    sys.path.insert(0,str(F));workerchecker=load(F/'checker.py','nf7_sealed_artifact_schema')
    for c,r in zip(plan['cases'],summary):
        root=P/'replay/tests'/c['id'];assert r['artifact_dir']==str(root)
        assert sha(root/'input.elf')==c['sha256']
        inputs=read(root/'inputs.json')
        assert inputs['binary']==dict(source=c['elf'],path=str(root/'input.elf'),sha256=c['sha256'])
        assert inputs['simv']==dict(path=ledger['simv'],image_sha256=ledger['files'])
        command=dict(command=[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),
            '+TESTCASE='+c['id'],'+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')],cwd=str(root/'work'))
        assert read(root/'command.json')==command
        child_fields(r,read(root/'child_outcome.unvalidated.json'),command,sha(root/'command.json'))
        report=read(root/'observer.json');workerchecker.observer_gate(report,c)
        assert read(root/'strict_original.json')==dict(status='STRICT_NF7_GROUP_PASS_M6',runtime_id=c['id'],trials=c['trials'],
            historical_source=c['original_name'],observer=report,child_outcome_sha256=sha(root/'child_outcome.unvalidated.json'))
        oc=read(root/'observer.command.json')
        assert Path(oc['command'][0]).resolve()==Path(sys.executable).resolve()
        assert oc['command'][1:]==['-B',str(F/'observer.py'),'check','--group',str(c['group']),'--csv',str(root/'commit_trace.csv'),'--out',str(root/'observer.json')]
        assert oc['cwd']==str(F) and elapsed(oc['remaining_group_s'],2700)
        assert not (root/'observer.stderr').read_text().strip() and (root/'observer.stdout').read_text().strip()=='NF7_CSV_ORACLE_PASS'
        for p in (root/'console.log',root/'work/run.vcs.log'):
            text=p.read_text();workerchecker.log_gate(text)
            assert text.count('IX_SV39_PASS')==1 and workerchecker.common.SUCCESS in text and '$finish' in text
        for n in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log','commit_trace.csv','trace_summary.json',
                  'child_outcome.unvalidated.json','observer.command.json','observer.stdout','observer.stderr','observer.json','strict_original.json'):
            expected.add(str(root/n))
    assert set(done['evidence_pins'])==expected;add(pins,done['evidence_pins'])
    assert not (P/'complete.tmp').exists()
    assert not any(re.search(r'first[ _-]?(?:failure|error)|abort|cancel|timeout',p.name,re.I) for p in P.rglob('*') if p.is_file())
    workerchecker.log_gate((P/'service.log').read_text());add(pins,{str(P/'service.log'):sha(P/'service.log')})
    verify(pins)
    return prepared,plan,pins


def case_audit(prepared_sha,complete_sha,name):
    assert sha(HERE/'prepared.json')==prepared_sha and sha(P/'complete.json')==complete_sha and sha(P/'plan.json')==PLAN_SHA
    admitted=read(HERE/'terminal01/admission.json')
    assert admitted['complete_sha256']==complete_sha and admitted['prepared_sha256']==prepared_sha
    prepared,plan=read(HERE/'prepared.json'),read(P/'plan.json')
    case=next(c for c in plan['cases'] if c['id']==name);spec=prepared['specs'][name];root=P/'replay/tests'/name
    target=HERE/'terminal01'/name;target.mkdir();started=time.monotonic()
    sys.path.insert(0,str(REF));oracle=load(REF/'csv_oracle.py','nf7_frozen_oracle')
    d=Path(case['source']);cfg=read(d/'cases.json')
    strict=oracle.Checker(spec['symbols'],cfg,read(d/'status.json'),read(case['ledger']))
    transport=load(u.TRANSPORT,'nf7_lossless_rows');code={int(k):v for k,v in spec['code'].items()}
    class Observer(transport.Observer):
        def __init__(self):
            self.count=Counter();self.before=hashlib.sha256();self.after=hashlib.sha256();self.pcs=Counter()
        def observe(self,row):
            self.count['rows']+=1;self.count[row['event']]+=1
            if row['event']=='retire':
                pc,insn=int(row['pc'],16),int(row['insn'],16)
                assert code.get(pc)==insn,('Actual ELF PC/code mismatch',hex(pc),hex(insn))
                self.pcs[pc]+=1
            strict.row(row)
    observer=Observer();trace=load(Path(prepared['trace_module']),'nf7_frozen_generic_trace')
    class Reader:
        def __init__(self,stream):self.reader=csv.DictReader(stream);self.fieldnames=self.reader.fieldnames
        def __iter__(self):return observer.rows(self.reader)
    trace.csv=SimpleNamespace(DictReader=Reader)
    generic=trace.validate_trace(root/'commit_trace.csv');report=strict.finish()
    assert observer.count['rows']==observer.count['unmodified_delivered_rows']==generic['rows']
    assert observer.before.digest()==observer.after.digest() and observer.count['retire']==generic['retire_count']
    assert observer.pcs[spec['symbols']['check']]==report['checks']==case['checks']
    assert json.loads(json.dumps(report))==read(root/'observer.json')==read(root/'strict_original.json')['observer']
    assert dict(generic,status='VALID')==read(root/'trace_summary.json')
    causes=[v for c in cfg for v in ([c['expected_cause'],9] if c['expected_cause'] is not None else [9])]
    assert [t['values'][0] for t in report['traps']]==causes
    assert report['trials']==case['trials']
    save(target/'result.json',dict(status='INDEPENDENT_ONE_CSV_ACCEPTED',name=name,csv_parses=1,generic=generic,observer=report,
        child_outcome=read(root/'child_outcome.unvalidated.json'),csv_sha256=admitted['pins'][str(root/'commit_trace.csv')],
        actual_pc_counts={hex(k):v for k,v in observer.pcs.items()},
        lossless=dict(rows=observer.count['rows'],delivered=observer.count['unmodified_delivered_rows'],
            before_sha256=observer.before.hexdigest(),after_sha256=observer.after.hexdigest()),audit_seconds=time.monotonic()-started))
    print('INDEPENDENT_ONE_CSV_ACCEPTED',name,flush=True)


def terminal(prepared_sha,complete_sha):
    target=HERE/'terminal01';target.mkdir();started=time.monotonic();child=None
    def cancelled(sig,frame):raise RuntimeError('Offline audit signal '+str(sig))
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    try:
        prepared,plan,pins=admission(prepared_sha,complete_sha)
        save(target/'admission.json',dict(status='WHOLE24_ADMITTED_NOT_AUDIT_PASS',prepared_sha256=prepared_sha,complete_sha256=complete_sha,pins=pins))
        results=[];exits=[]
        for c in plan['cases']:
            name=c['id'];cmd=[sys.executable,'-B',str(HERE/'audit.py'),'case','--authorize-terminal-audit',
                '--prepared-sha256',prepared_sha,'--complete-sha256',complete_sha,'--name',name]
            with (target/(name+'.stdout')).open('x') as stdout,(target/(name+'.stderr')).open('x') as stderr:
                child=subprocess.Popen(cmd,cwd=HERE,stdout=stdout,stderr=stderr)
                save(target/(name+'.invocation.json'),dict(pid=child.pid,parent_pid=os.getpid(),command=cmd,started=time.time()))
                rc=child.wait(timeout=prepared['case_audit_timeout_seconds'])
            record=dict(name=name,pid=child.pid,actual_wait_returncode=rc,time=time.time(),stdout_sha256=sha(target/(name+'.stdout')),stderr_sha256=sha(target/(name+'.stderr')))
            save(target/(name+'.exit.json'),record);exits.append(record)
            assert zero(rc),('First audit failure; no retry or further CSV',name,rc)
            result=read(target/name/'result.json');assert result['name']==name and result['status']=='INDEPENDENT_ONE_CSV_ACCEPTED'
            results.append(result)
        trials=[t for r in results for t in r['observer']['trials']]
        stats=dict(csv_files=len(results),csv_parses=sum(r['csv_parses'] for r in results),
            rows=sum(r['generic']['rows'] for r in results),retired_rows=sum(r['generic']['retire_count'] for r in results),
            checks=sum(r['observer']['checks'] for r in results),checkpoints=sum(len(r['observer']['checkpoints']) for r in results),
            pagefaults=sum(t['values']['0'] in (13,15) for r in results for t in r['observer']['traps']),
            ecalls=sum(t['values']['0']==9 for r in results for t in r['observer']['traps']))
        assert trials==list(range(96)) and [stats[k] for k in ('csv_files','csv_parses','checks','checkpoints','pagefaults','ecalls')]==[24,24,284816,168,72,96]
        verify(pins);assert sha(P/'complete.json')==complete_sha
        save(target/'verified_pins.json',pins)
        save(target/'result.json',dict(status=ACCEPT,accepted=True,plan_sha256=PLAN_SHA,parent_sha256=PARENT_SHA,
            launch_sha256=LAUNCH_SHA,image_sha256=IMAGE_SHA,prepared_sha256=prepared_sha,complete_sha256=complete_sha,
            groups=results,case_audit_exits=exits,trials=trials,aggregate=stats,pins_verified=len(pins),original_plan_pins=878,
            pins_pre_post_unchanged=True,no_retry=True,outer_service_returncode=None,outer_service_terminal_observed=False,
            actual_nf2_prerequisite=read(F/'parent_review.json')['nf2_gate'],
            group_bound_evidence='Sealed worker2700s timers joined/sticky abort; no independently persisted group wallclock duration',
            oracle_scope='Original fractional tails/guards/memory/partial-field/trap/retry/CSR oracle, no new CSR readback',
            reference_substituted_for_DUT=False,original_linux_ELF_replay=False,audit_seconds=time.monotonic()-started))
        print(ACCEPT,sha(target/'result.json'),flush=True)
    except BaseException as error:
        if child is not None and child.poll() is None:child.kill();child.wait()
        save(target/'firstfailure.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),time=time.time()))
        raise


if __name__=='__main__':
    assert __debug__
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','terminal','case'))
    p.add_argument('--authorize-terminal-audit',action='store_true');p.add_argument('--prepared-sha256');p.add_argument('--complete-sha256');p.add_argument('--name');a=p.parse_args()
    if a.mode=='prepare':
        assert not a.authorize_terminal_audit and not a.prepared_sha256 and not a.complete_sha256 and not a.name
        prepare()
    else:
        assert a.authorize_terminal_audit and a.prepared_sha256 and a.complete_sha256
        if a.mode=='case':case_audit(a.prepared_sha256,a.complete_sha256,a.name)
        else:
            assert not a.name
            terminal(a.prepared_sha256,a.complete_sha256)
