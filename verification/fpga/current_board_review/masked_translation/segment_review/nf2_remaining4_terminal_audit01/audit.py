"""Prepare without reading live artifacts; one explicitly admitted NF2 terminal parse."""
import argparse
import ast
from collections import Counter
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
F = HERE.parent/'nf2_remaining4_01'
P = F/'prepared01'
G = HERE.parents[2]
NAME = 'nf2_remaining4_sv39'
UNIT = 'ara-nf2-remaining4-m6-01.service'
PLAN_SHA = '7a644bfd57e314649a92a6512cd6c994c49f7e9b656f0caaa5e172ec0e4d9c55'
PARENT_SHA = 'e685f2ebe8af06cfefc0373281fe8d1a8c93e42274d05c4a77a0f8408d80ded6'
READY_SHA = 'd427f9c9846e0c59d9374efb6fbae020df08c8f6a4472ce740e05ddf4306aa2f'
IMAGE_SHA = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
PASS = 'PASS_M6_NF2_REMAINING4_SV39_NOT_LINUX'
ACCEPT = 'INDEPENDENT_M6_NF2_FOUR_SOURCE_CASES_ACCEPTED_NOT_LINUX'
TRANSPORT = G/'ordered_reduction/original_remaining9_terminal_audit01/observer.py'
TRANSPORT_SHA = '7d15ce50da9918fa9b1d3bb1cea59871b4312385576da1fd6c8d5940dbad650f'
SUPPORT = G/'merge_original_prefix98_terminal_audit01/support.py'
SUPPORT_SHA = '4ad5c6b27d60f62e36f406c809bf2aeb4a9f22822e02934f334c3c1a175c52a6'
IDS = ['u0_s0_b1_m2_f1','u1_s1_b3_m2_f0','u0_s1_b5_m3_f1','u1_s0_b1_m3_f0']


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda: stream.read(1048576), b''): h.update(b)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream: json.dump(value,stream,indent=2); stream.write('\n')


def add(pins, other):
    for p,h in other.items():
        assert p not in pins or pins[p]==h, ('conflicting pin',p)
        pins[p]=h


def verify(pins):
    for p,h in pins.items(): assert sha(p)==h, ('pin drift',p)


def load(path,name):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def static_identity():
    assert sha(P/'plan.json')==PLAN_SHA and sha(F/'READY.json')==READY_SHA
    assert sha(F/'parent_review.json')==PARENT_SHA
    plan,review=read(P/'plan.json'),read(F/'parent_review.json')
    assert plan['status']=='PREPARED_NOT_RUN' and len(plan['pins'])==700
    assert (plan['jobs'],plan['timeout_s'],plan['service_timeout_s'])==(1,6300,6900)
    assert plan['unit']==UNIT and plan['image_sha256']==IMAGE_SHA
    assert all(plan[k] is True for k in ('no_build','no_retry','no_fsdb'))
    assert plan['runtime_testcase']==NAME and plan['case']['id']==NAME
    assert [c['id'] for c in plan['spec']['cases']]==IDS
    assert review['decision']=='AUTHORIZE_NF2_REMAINING4_ONCE' and review['plan_sha256']==PLAN_SHA
    assert review['unit']==UNIT and review['cases']==IDS
    assert review['reference_ready_sha256']==READY_SHA and review['budget_risk_accepted'] is True
    assert review['independent_reference_accepted'] is True
    assert review['independent_reference_evidence']==plan['independent_reference_pins']
    pins=dict(plan['pins'])
    add(pins,{str(P/'plan.json'):PLAN_SHA,str(F/'parent_review.json'):PARENT_SHA,
              str(F/'READY.json'):READY_SHA,str(TRANSPORT):TRANSPORT_SHA,str(SUPPORT):SUPPORT_SHA})
    add(pins,review['independent_reference_evidence']); verify(pins)
    sys.path.insert(0,str(F))
    checker=load(F/'checker.py','sealed_nf2_terminal_checker')
    assert checker.specification()==plan['spec']
    u=load(SUPPORT,'nf2_terminal_elf_reader'); get,symbols=u.elf(plan['case']['elf'])
    assert sha(plan['case']['elf'])==plan['case']['sha256']==read(F/'READY.json')['soc_elf']['sha256']
    for name,value in plan['spec']['symbols'].items(): assert symbols[name][0]==value
    for pc,insn in plan['spec']['code'].items():
        width=4 if insn&3==3 else 2
        assert int.from_bytes(get(int(pc),width),'little')==insn
    image=Path(plan['image']); ledger=read(image/'image.json')
    assert sha(image/'image.json')==IMAGE_SHA
    snapshot=Path(ledger['snapshot'])/'snapshot.json'; snap=read(snapshot)
    assert sha(snapshot)==plan['snapshot_sha256']==ledger['snapshot_sha256']
    assert snap['state']=='SEALED' and len(snap['files'])==539 and len(ledger['files'])==66
    assert sha(image/'_build/vcs/simulator.conf')==ledger['configuration_sha256']=='6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785'
    assert sha(image/'_build/vcs/vcs_source_manifest.json')==ledger['manifest_sha256']
    add(pins,ledger['files']); add(pins,{str(Path(snap['root'])/p):h for p,h in snap['files'].items()})
    trace_path=Path(snap['root'])/'verification/ara_verify/trace.py'
    assert str(trace_path) in pins
    return plan,pins,checker,ledger,trace_path


def prepare():
    assert not (HERE/'prepared.json').exists()
    plan,pins,_,_,_=static_identity()
    for name in ('audit.py','wait_terminal.py','AUTHORIZATION.md'):
        p=HERE/name
        if p.suffix=='.py': ast.parse(p.read_text(),filename=str(p))
        add(pins,{str(p):sha(p)})
    save(HERE/'prepared.json',dict(status='PREPARED_CONDITIONAL_TERMINAL_AUDIT_NOT_DUT',
        plan_sha256=PLAN_SHA,parent_sha256=PARENT_SHA,pins=pins,cases=IDS,full_plan_pins=700,
        csv_reads=0,terminal_reads=0,reference_parses=0,Host_executed=False,DUT_executed=False,
        wait_seconds=7200,audit_timeout_seconds=1800,service_timeout_seconds=9300,no_retry=True))
    print('PREPARED',sha(HERE/'prepared.json'),flush=True)


def admission(prepared_sha,complete_sha=None):
    assert sha(HERE/'prepared.json')==prepared_sha
    prepared=read(HERE/'prepared.json'); verify(prepared['pins'])
    plan,pins,checker,ledger,trace_path=static_identity()
    add(pins,prepared['pins']); add(pins,{str(HERE/'prepared.json'):prepared_sha})
    actual_sha=sha(P/'complete.json')
    if complete_sha is not None: assert actual_sha==complete_sha
    done,run,summary=read(P/'complete.json'),read(P/'replay/run.json'),read(P/'replay/summary.json')
    assert done['status']==PASS and done['plan_sha256']==PLAN_SHA, 'Not exact full-scope PASS'
    assert done['aborted'] is False and done['pins_unchanged'] is True and not done.get('error')
    assert type(done['retries']) is int and done['retries']==0
    assert done['full_child_acceptance'] is False
    assert done['results']==summary and len(summary)==1
    result=summary[0]; root=P/'replay/tests'/NAME
    assert result['name']==NAME and result['kind']=='app' and result['status']=='PASS'
    assert type(result['returncode']) is int and result['returncode']==0 and not result['reason']
    assert 0<result['elapsed_s']<=6300 and result['artifact_dir']==str(root)
    assert run['status']=='COMPLETE' and run['tests']==[NAME] and run['status_counts']=={'PASS':1}
    assert run['jobs']==run['seed']==1 and run['timeout_s']==6300 and run['simv']==ledger['simv']
    assert run['commit_trace'] is True and run['input_snapshots'] is True and run['code_coverage'] is False
    assert run['contract_monitor'] is False and run['probe_kinds']==[]
    assert datetime.fromisoformat(run['completed_at'])>datetime.fromisoformat(run['created_at'])
    argv=run['invocation']
    assert argv[:2]==[str(F/'replay.py'),'run'] and '--authorize-run' in argv
    assert argv[argv.index('--plan-sha256')+1]==PLAN_SHA
    assert argv[argv.index('--parent-review')+1]==str(F/'parent_review.json')
    assert argv[argv.index('--parent-review-sha256')+1]==PARENT_SHA
    expected=[P/'launch.json',P/'replay/run.json',P/'replay/summary.json']+[root/n for n in
        ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log','commit_trace.csv','trace_summary.json','strict_prefix.json')]
    assert set(done['evidence_pins'])=={str(p) for p in expected}
    add(pins,done['evidence_pins']); add(pins,{str(P/'complete.json'):actual_sha})
    launch=read(P/'launch.json'); add(pins,launch['approval_pins'])
    assert launch['approval_pins'][str(F/'parent_review.json')]==PARENT_SHA
    assert launch['plan_sha256']==PLAN_SHA and launch['started']<=done['finished']<launch['started']+6900
    owner=launch['owner']; prop=owner['properties']
    assert prop['Id']==UNIT and prop['MainPID']==str(owner['pid']) and int(prop['MainPID'])>0
    assert (prop['LoadState'],prop['ActiveState'],prop['SubState'])==('loaded','active','running')
    assert prop['RuntimeMaxUSec']=='1h 55min' and prop['Restart']=='no' and prop['KillMode']=='control-group'
    assert prop['ControlGroup'].endswith('/'+UNIT) and prop['ControlGroup'] in [l.split(':',2)[-1] for l in owner['cgroup'].splitlines()]
    case=plan['case']
    assert sha(root/'input.elf')==case['sha256']
    assert read(root/'inputs.json')['binary']==dict(source=case['elf'],path=str(root/'input.elf'),sha256=case['sha256'])
    assert read(root/'inputs.json')['simv']==dict(path=ledger['simv'],image_sha256=ledger['files'])
    command=dict(command=[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),
                         '+TESTCASE='+NAME,'+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')],cwd=str(root/'work'))
    assert read(root/'command.json')==command
    strict=read(root/'strict_prefix.json'); child=read(root/'child_outcome.unvalidated.json')
    assert strict['status']=='NF2_CSV_ORACLE_PASS' and strict['cases']==list(range(4))
    assert [(p['case'],p['phase']) for p in strict['checkpoints']]==[(0,1),(0,2),(1,1),(1,2),(2,3),(2,2),(3,3),(3,2)]
    assert len(strict['traps'])==6 and [t['values']['0'] for t in strict['traps']]==[13,9,15,9,9,9]
    assert len(strict['alternate_protected_field'])==4 and all(type(v) is bool for v in strict['alternate_protected_field'])
    assert strict['alternate_protected_field'][2:]==[False,False]
    assert strict['checks']==3567-sum(strict['alternate_protected_field'])
    assert strict['refills']==[dict(case=1,halfwords=2048),dict(case=3,halfwords=2048)]
    assert strict['raw_child_outcome']=='child_outcome.unvalidated.json'
    child_sha=sha(root/'child_outcome.unvalidated.json')
    assert strict['child_outcome_sha256']==child_sha
    assert child['schema']=='UNVALIDATED_CHILD_OUTCOME_V1' and child['architectural_acceptance'] is False
    for k in ('name','status','returncode','elapsed_s','reason','artifact_dir'): assert child[k]==result[k]
    assert type(child['returncode']) is int and child['returncode']==0 and not child.get('command_read_error')
    assert child['command']==command and child['command_path']==str(root/'command.json')
    assert child['command_sha256']==sha(root/'command.json')
    add(pins,{str(root/'child_outcome.unvalidated.json'):child_sha})
    verify(pins)
    assert not (P/'complete.tmp').exists()
    assert not any(re.search(r'first[ _-]?(?:failure|error)|abort|cancel|timeout',p.name,re.I) for p in P.rglob('*') if p.is_file())
    assert sha(P/'complete.json')==actual_sha
    return actual_sha,plan,pins,checker,trace_path,strict,child


def terminal(prepared_sha,complete_sha):
    target=HERE/'terminal01'; assert not target.exists(), 'One offline audit only'
    target.mkdir(); started=time.monotonic()
    try:
        digest,plan,pins,checker,trace_path,producer,child=admission(prepared_sha,complete_sha)
        root=P/'replay/tests'/NAME
        for path in (root/'console.log',root/'work/run.vcs.log'):
            text=path.read_text()
            assert not checker.VETO.search(text) and not re.search(r'first[ _-]?(?:error|failure)|\b(?:TIMEOUT|CANCELLED|FATAL)\b',text,re.I)
            assert text.count('NF2_REMAINING4_SV39_PASS')==1 and checker.common.SUCCESS in text and '$finish' in text
        transport=load(TRANSPORT,'nf2_lossless_rows')
        strict=checker.csv_check.Checker(plan['spec']['symbols'],plan['spec']['code'])
        code={int(k):v for k,v in plan['spec']['code'].items()}
        class Observer(transport.Observer):
            def __init__(self):
                self.count=Counter(); self.before=hashlib.sha256(); self.after=hashlib.sha256()
                self.traps=[]; self.pc_count=Counter(); self.checks=0
            def observe(self,row):
                self.count['rows']+=1; self.count[row['event']]+=1
                if row['event']=='retire':
                    pc,insn=int(row['pc'],16),int(row['insn'],16)
                    assert code.get(pc)==insn, ('Actual ELF PC/code',hex(pc),hex(insn))
                    self.pc_count[pc]+=1
                    if pc==plan['spec']['symbols']['check']: self.checks+=1
                    if int(row['trap']): self.traps.append(dict(pc=hex(pc),insn=hex(insn),cycle=int(row['cycle'])))
                strict.row(row)
        observer=Observer()
        # Isolated module binding wraps DictReader; the frozen validator and every
        # original row remain unchanged. Expected NF2 exceptions retain its semantics.
        trace=load(trace_path,'sealed_nf2_generic_trace')
        class Reader:
            def __init__(self,stream):
                self.reader=csv.DictReader(stream); self.fieldnames=self.reader.fieldnames
            def __iter__(self): return observer.rows(self.reader)
        trace.csv=SimpleNamespace(DictReader=Reader)
        generic=trace.validate_trace(root/'commit_trace.csv')
        rebuilt=strict.finish()
        assert observer.count['rows']==observer.count['unmodified_delivered_rows']==generic['rows']
        assert observer.before.digest()==observer.after.digest()
        assert observer.checks==rebuilt['checks'] and generic['retire_count']==observer.count['retire']
        rebuilt.update(scope='Four original selected singles in real Sv39, not Linux signal-frame/full-parent acceptance',
            raw_child_outcome='child_outcome.unvalidated.json',child_outcome_sha256=sha(root/'child_outcome.unvalidated.json'))
        assert json.loads(json.dumps(rebuilt))==producer, 'Rebuilt full observer report differs'
        assert dict(generic,status='VALID')==read(root/'trace_summary.json')
        verify(pins)
        save(target/'verified_pins.json',pins)
        save(target/'result.json',dict(status=ACCEPT,accepted=True,cases=IDS,plan_sha256=PLAN_SHA,
            parent_sha256=PARENT_SHA,prepared_sha256=prepared_sha,complete_sha256=digest,image_sha256=IMAGE_SHA,
            elf_sha256=plan['case']['sha256'],pins_verified=len(pins),pins_pre_post_unchanged=True,full_plan_pins=700,
            generic=generic,strict=rebuilt,child_outcome=child,child_returncode=child['returncode'],child_elapsed_s=child['elapsed_s'],
            csv_parses=1,csv_sha256=pins[str(root/'commit_trace.csv')],raw_logs_firsterror_veto_pass=True,
            lossless=dict(rows=observer.count['rows'],delivered=observer.count['unmodified_delivered_rows'],
                before_sha256=observer.before.hexdigest(),after_sha256=observer.after.hexdigest()),
            actual_pc_counts={hex(k):v for k,v in observer.pc_count.items()},trapping_retirements=observer.traps,
            outer_service_returncode=None,outer_service_terminal_observed=False,reference_used_as_DUT_evidence=False,
            full_parent_acceptance=False,Linux_signalframe_proved=False,vector_payload_directly_observed=False,
            restore_evidence='Pinned firmware scalar restore-readback checks executed, not internal CSR signal capture',
            audit_seconds=time.monotonic()-started))
        print(ACCEPT,sha(target/'result.json'),flush=True)
    except BaseException as error:
        save(target/'not_accepted.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),complete_sha256=complete_sha))
        raise


if __name__=='__main__':
    assert __debug__
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('mode',choices=('prepare','terminal'))
    p.add_argument('--authorize-terminal-audit',action='store_true')
    p.add_argument('--prepared-sha256'); p.add_argument('--complete-sha256'); a=p.parse_args()
    if a.mode=='prepare':
        assert not a.authorize_terminal_audit and not a.prepared_sha256 and not a.complete_sha256
        prepare()
    else:
        assert a.authorize_terminal_audit and a.prepared_sha256 and a.complete_sha256
        terminal(a.prepared_sha256,a.complete_sha256)
