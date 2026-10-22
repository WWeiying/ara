"""Frozen identities and conditional terminal metadata gates; no active CSV reads."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
G=HERE.parent
W=G/'e8_m4_ops3_prefix66_vcs_m6_plan01'
P=W/'prepared01'
REF=G/'e8_m4_ops3_prefix66_prepare01'
A=G/'e8_m4_ops3_prefix66_reference_audit01'
NAME='gather_prefix_e8_m4_ops3'
LABEL='rvv_permute_restart_e8_m4_ops3'
UNIT='ara-gather-e8m4-vi31-prefix66-m6-01.service'
PLAN_SHA='5de3a259e330825548009fbe17a4f80da34c3a6b816b495a695564621ea4ddbb'
AUTH_SHA='aa3e67aae86d329775d9de53b039b9ad960d3fc859351a616dddd915bd36a548'
PASS='PASS_M6_ORIGINAL_E8M4_VI31_PREFIX66_NOT_FULL_CHILD'
WORKER_PID=1586443
ROOT=P/'replay/tests'/NAME
TRANSPORT=G.parent/'ordered_reduction/original_remaining9_terminal_audit01/observer.py'
TRANSPORT_SHA='7d15ce50da9918fa9b1d3bb1cea59871b4312385576da1fd6c8d5940dbad650f'


def require(value,message):
    if not value: raise ValueError(message)


def read(path): return json.loads(Path(path).read_text())


def stat_identity(path):
    s=Path(path).stat()
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1048576),b''): h.update(data)
    return h.hexdigest()


def save(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')
        stream.flush()
        import os
        os.fsync(stream.fileno())


def verify(pins,skip=()):
    for name,digest in pins.items():
        if name not in skip: require(sha(name)==digest,'Pinned input changed: '+name)


def static_gate():
    require(sha(P/'plan.json')==PLAN_SHA,'Original disk plan SHA differs')
    plan=read(P/'plan.json')
    require(len(plan['pins'])==744 and plan['unit']==UNIT and
            (plan['jobs'],plan['timeout_s'],plan['service_timeout_s'],plan['reserved_slots'])==(1,5400,6600,0),
            'Fixed actual scope/budgets differ')
    require(plan['case']['id']==NAME and plan['case']['original_name']==LABEL and
            (plan['spec']['sew'],plan['spec']['lmul'],plan['spec']['capacity'],
             plan['spec']['physical_predicate_bytes'])==(8,4,512,128),'Actual source/runtime/m4 scope differs')
    require(plan['reference_ready_sha256']==sha(REF/'READY02.json')==
            '11aec353de588baa6981aa0e46757b76efdbcf7c0656585d5174e96aca523ebc' and
            plan['independent_audit_sha256']==sha(A/'audit.json')==
            '3a9c52768d5244fdc803779ee58744fa243e6946bdddfd953b574d62b0942a4d', 'Accepted source/reference differs')
    accepted=read(A/'audit.json');raw=REF/'reference/commits.log';stat=raw.stat()
    require(plan['pins'][str(raw)]==accepted['raw_sha256'] and
            [stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]==accepted['raw_stat'],
            'Frozen reference raw identity/stat differs')
    verify(plan['pins'],skip=(str(raw),))  # Reuse accepted raw hash; never reparse/re-read it here.
    require(sha(W/'parent_review.json')==AUTH_SHA,'Actual parent authorization changed')
    auth=read(W/'parent_review.json')
    require(auth['decision']=='AUTHORIZE_E8M4_VI31_PREFIX66_M6_ONCE' and auth['plan_sha256']==PLAN_SHA
            and auth['unit']==UNIT and auth['budget_risk_accepted'] is True and
            auth['reference_ready_sha256']==plan['reference_ready_sha256'] and
            auth['independent_audit_sha256']==plan['independent_audit_sha256'],'Parent authorization scope differs')
    require(sha(TRANSPORT)==TRANSPORT_SHA,'Mature lossless transport changed')
    return plan


def terminal_gate():
    # No CSV is read until all terminal metadata and numeric outcome gates pass.
    plan=static_gate()
    require((P/'complete.json').is_file(),'Worker ended without terminal complete')
    digest=sha(P/'complete.json');done=read(P/'complete.json')
    require(done['status']==PASS and done['plan_sha256']==PLAN_SHA and done['aborted'] is False and
            done['pins_unchanged'] is True and type(done['retries']) is int and done['retries']==0
            and not done.get('error') and done['full_child_acceptance'] is False and
            done['Linux_execution'] is False,'Actual whole1 terminal is not acceptable PASS')
    summary=read(P/'replay/summary.json');run=read(P/'replay/run.json')
    require(len(summary)==1 and summary==done['results'],'Actual PASS1 result mismatch')
    r=summary[0]
    require(r['name']==NAME and r['kind']=='app' and r['status']=='PASS' and
            type(r['returncode']) is int and r['returncode']==0 and not r['reason'] and
            0<r['elapsed_s']<=5400 and r['artifact_dir']==str(ROOT),'Actual numeric case rc/budget/path differs')
    require(run['status']=='COMPLETE' and run['status_counts']=={'PASS':1} and run['tests']==[NAME] and
            run['completed_at'] and run['jobs']==1 and run['timeout_s']==5400 and run['seed']==1 and
            run['commit_trace'] is True and run['code_coverage'] is False,'Actual COMPLETE contract differs')
    ledger=read(Path(plan['image'])/'image.json')
    require(run['simv']==ledger['simv'],'Actual frozen simulator differs')
    child=read(ROOT/'child_outcome.unvalidated.json');classified=read(ROOT/'runner_result.unvalidated.json')
    command=[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+str(ROOT/'input.elf'),
             '+TESTCASE='+NAME,'+NO_FSDB','+COMMIT_TRACE='+str(ROOT/'commit_trace.csv')]
    require(child['schema']=='UNVALIDATED_MONITOR_OUTCOME_V1' and child['architectural_acceptance'] is False
            and child['name']==NAME and child['source_label']==LABEL and
            type(child['returncode']) is int and child['returncode']==0 and
            child['timed_out'] is False and child['failure_seen'] is False and
            0<child['elapsed_s']<=5400 and child['timeout_s']==5400 and
            child['command']==command and child['cwd']==str(ROOT/'work') and
            child['console_path']==str(ROOT/'console.log'),'Actual durable monitor tuple not numeric0/no-timeout/no-failure')
    require(classified['name']==NAME and classified['status']=='PASS' and type(classified['returncode']) is int
            and classified['returncode']==0 and not classified['reason'] and
            classified['elapsed_s']==child['elapsed_s']==r['elapsed_s'] and
            classified['artifact_dir']==str(ROOT),'Later runner classification cannot substitute for monitor outcome')
    require(read(ROOT/'command.json')==dict(command=command,cwd=str(ROOT/'work')),'Exact private runtime command differs')
    provenance=read(ROOT/'child_command.provenance.json')
    require(provenance['command_path']==str(ROOT/'command.json') and
            provenance['command_sha256']==sha(ROOT/'command.json') and
            provenance['command']==read(ROOT/'command.json'),'Durable command provenance differs')
    require(sha(ROOT/'input.elf')==plan['case']['sha256'],'Private ELF changed')
    inputs=read(ROOT/'inputs.json')
    require(inputs['binary']==dict(source=plan['case']['elf'],path=str(ROOT/'input.elf'),sha256=plan['case']['sha256'])
            and inputs['simv']==dict(path=ledger['simv'],image_sha256=ledger['files']),'Actual ELF/image provenance differs')
    launch=read(P/'launch.json');props=launch['owner']['properties']
    require(launch['plan_sha256']==PLAN_SHA and launch['owner']['pid']==WORKER_PID and
            props['MainPID']==str(WORKER_PID) and props['Id']==UNIT and props['Restart']=='no' and
            props['KillMode']=='control-group' and props['RuntimeMaxUSec']=='1h 50min',
            'Actual launch owner/unit/bounds differ')
    require(launch['started']<=done['finished']<=launch['started']+6600,
            'Actual terminal exceeds frozen outer time budget')
    require(launch['approval_pins']=={str(W/'parent_review.json'):AUTH_SHA},'Actual parent approval pin differs')
    names=['input.elf','inputs.json','command.json','console.log','work/run.vcs.log','commit_trace.csv',
           'trace_summary.json','strict_prefix.json','child_outcome.unvalidated.json',
           'runner_result.unvalidated.json','child_command.provenance.json']
    expected={str(P/n) for n in ('launch.json','replay/run.json','replay/summary.json')}
    expected.update(str(ROOT/n) for n in names)
    require(set(done['evidence_pins'])==expected and len(expected)==14,'Exact terminal evidence membership differs')
    require(not (ROOT/'first_cause.json').exists() and not (P/'first_cause.json').exists(),'Latched failure cannot PASS')
    verify(done['evidence_pins'],skip=(str(ROOT/'commit_trace.csv'),))
    require(sha(P/'complete.json')==digest,'Terminal changed during gates')
    return plan,done,digest
