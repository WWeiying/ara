"""Read-only NF2 terminal prerequisite; actual admission is future-launch only."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
G = HERE.parents[3]
A = G/'masked_translation/segment_review/nf2_remaining34_terminal_audit01'
P = A.parent/'nf2_remaining34_vcs_m6_plan01/prepared01'
PREPARED_SHA = 'a3e7eeb651860e2510faf9b08670b16185786f29c15161004bc2e511e516a4e9'
PLAN_SHA = 'b2fb0d810d7004769a18c7b0527e14b013979791ace008edb4155240126bb586'
AUDIT_SHA = '7e4182189fcb56b267b78f754c1662b9766a0704a4c99e12953f5390e8c8ad26'
WAIT_SHA = '508519c678d319f897f9ccb7bc6c5f3a04d4523bbd3c16f4ae76d8b974381afd'
IMAGE_SHA = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
ACCEPT = 'INDEPENDENT_M6_NF2_34_PLUS_J4_ACCEPTED_40_WITH_PINNED_PILOT_NOT_LINUX'
NAMES = [f'nf2_remaining34_g{i:02d}' for i in range(1,10)]+['nf2_j4_m6']


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''): digest.update(data)
    return digest.hexdigest()


def read(path): return json.loads(Path(path).read_text())


def integer(value, expected): return type(value) is int and value == expected


def contract():
    return dict(audit_prepared_path=str(A/'prepared.json'),audit_prepared_sha256=PREPARED_SHA,
        audit_module_path=str(A/'audit.py'),audit_module_sha256=AUDIT_SHA,
        wait_module_path=str(A/'wait_terminal.py'),wait_module_sha256=WAIT_SHA,
        nf2_plan_path=str(P/'plan.json'),nf2_plan_sha256=PLAN_SHA,
        result_path=str(A/'terminal01/result.json'),expected_status=ACCEPT,
        runtime_members=NAMES,actual_gate_only_at_authorized_launch=True)


def static_pins():
    # These are sealed preparation/module identities, not live terminal artifacts.
    pins = {str(A/'prepared.json'):PREPARED_SHA,str(A/'audit.py'):AUDIT_SHA,
            str(A/'wait_terminal.py'):WAIT_SHA,str(P/'plan.json'):PLAN_SHA}
    for path, digest in pins.items(): require(sha(path)==digest,'NF2 sealed static identity drift')
    prepared = read(A/'prepared.json')
    for path, digest in prepared['pins'].items():
        if Path(path).suffix == '.py':
            require(path not in pins or pins[path]==digest,'Conflicting module pin')
            pins[path]=digest
    return pins


def load_auditor():
    require(__debug__,'NF2 assertions must remain enabled')
    require(sha(A/'audit.py')==AUDIT_SHA and sha(A/'wait_terminal.py')==WAIT_SHA,'Auditor module drift')
    spec=importlib.util.spec_from_file_location('nf7_sealed_nf2_admission',A/'audit.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def bind_payload(g):
    fields={'decision','terminal_path','terminal_sha256','plan_sha256','audit_prepared_sha256',
            'result_path','result_sha256','verified_pins_sha256','audit_exit_sha256',
            'wait_complete_sha256','review_sha256'}
    require(set(g)==fields,'Exact independent NF2 evidence schema required; no text attestation')
    require(g['decision']=='TERMINAL_INDEPENDENTLY_ACCEPTED' and g['terminal_path']==str(P/'complete.json') and
            g['plan_sha256']==PLAN_SHA and g['audit_prepared_sha256']==PREPARED_SHA and
            g['result_path']==str(A/'terminal01/result.json'),'Fixed NF2 provenance required')
    pins={str(P/'plan.json'):PLAN_SHA,str(A/'prepared.json'):PREPARED_SHA,
          str(P/'complete.json'):g['terminal_sha256'],str(A/'terminal01/result.json'):g['result_sha256'],
          str(A/'terminal01/verified_pins.json'):g['verified_pins_sha256'],
          str(A/'terminal01/REVIEW.md'):g['review_sha256'],
          str(A/'wait01/audit_exit.json'):g['audit_exit_sha256'],
          str(A/'wait01/complete.json'):g['wait_complete_sha256']}
    for path,digest in pins.items(): require(sha(path)==digest,'NF2 evidence hash mismatch: '+path)
    return pins


def independent_payload(g, auditor, prepared, plan, admitted_pins):
    result=read(A/'terminal01/result.json');verified=read(A/'terminal01/verified_pins.json')
    require(result['status']==ACCEPT and result['accepted'] is True,'Independent NF2 result not accepted')
    require(result['plan_sha256']==PLAN_SHA and result['parent_sha256']==auditor.PARENT_SHA and
            result['prepared_sha256']==PREPARED_SHA and result['complete_sha256']==g['terminal_sha256'] and
            result['image_sha256']==IMAGE_SHA,'Stale or wrong-image independent result')
    require(result['pins_pre_post_unchanged'] is True and verified==admitted_pins and
            integer(result['pins_verified'],len(verified)) and integer(result['original_plan_pins'],1240),
            'Full independent verified pins must equal freshly admitted evidence')
    require(result['source_coverage']==prepared['coverage'] and result['no_retry'] is True and
            result['prior_pilot_audit_sha256']==plan['pilot_audit_sha256'],'Independent coverage/retry drift')
    for key,value in [('source_failures_this_batch',36),('prior_pilot_source_failures',4),
                      ('distinct_failed_sources_current_M6',40),('positive_controls_separate',2)]:
        require(integer(result[key],value),'Independent count drift: '+key)
    require(result['outer_service_returncode'] is None and result['outer_service_terminal_observed'] is False and
            result['Linux_signalframe_proved'] is False and result['original_linux_ELF_replay'] is False and
            result['reference_substituted_for_DUT'] is False,'Unsupported completion/scope claim')
    names=[c['id'] for c in plan['cases']]
    require(names==NAMES and [c['name'] for c in result['cases']]==names and
            [x['name'] for x in result['case_audit_exits']]==names,'Exact independent all10 membership')
    extra={}
    for case,item,exit_record in zip(plan['cases'],result['cases'],result['case_audit_exits']):
        name=case['id'];root=P/'replay/tests'/name
        require(item['status']=='INDEPENDENT_ONE_CSV_ACCEPTED' and integer(item['csv_parses'],1),
                'Partial/nonaccepted case audit')
        require(item==read(A/'terminal01'/name/'result.json') and
                exit_record==read(A/'terminal01'/(name+'.exit.json')) and
                integer(exit_record['actual_wait_returncode'],0),'Actual per-case audit result/exit required')
        require(item['source_cases']==case['source_cases'] and item['positive_controls']==case.get('positive_controls',[]) and
                item['observer']==read(root/'strict_original.json')['observer'] and
                item['child_outcome']==read(root/'child_outcome.unvalidated.json') and
                item['csv_sha256']==verified[str(root/'commit_trace.csv')],'Independent case/evidence mismatch')
        require(dict(item['generic'],status='VALID')==read(root/'trace_summary.json'),'Generic trace result mismatch')
        loss=item['lossless']
        require(loss['rows']==loss['delivered']==item['generic']['rows'] and
                loss['before_sha256']==loss['after_sha256'],'Lossless oracle delivery missing')
        for filename in (name+'.stdout',name+'.stderr'):
            digest=exit_record['stdout_sha256' if filename.endswith('.stdout') else 'stderr_sha256']
            path=A/'terminal01'/filename;require(sha(path)==digest,'Case audit output drift');extra[str(path)]=digest
        for path in (A/'terminal01'/name/'result.json',A/'terminal01'/(name+'.exit.json')):extra[str(path)]=sha(path)
    stats=result['aggregate'];cases=result['cases']
    expected=dict(csv_files=10,csv_parses=10,rows=sum(i['generic']['rows'] for i in cases),
        retired_rows=sum(i['generic']['retire_count'] for i in cases),checks=sum(i['observer']['checks'] for i in cases),
        checkpoints=sum(len(i['observer']['checkpoints']) for i in cases),
        pagefaults=sum(t['values']['0'] in (13,15) for i in cases for t in i['observer']['traps']),
        ecalls=sum(t['values']['0']==9 for i in cases for t in i['observer']['traps']))
    require(set(stats)==set(expected) and all(integer(stats[k],v) for k,v in expected.items()),'Independent aggregate incomplete')
    exit_record=read(A/'wait01/audit_exit.json');wait=read(A/'wait01/complete.json')
    invocation=read(A/'wait01/audit_invocation.json')
    require(integer(exit_record['actual_wait_returncode'],0) and integer(wait['actual_audit_returncode'],0) and
            wait['status']=='INDEPENDENT_TERMINAL_AUDIT_ACCEPTED' and wait['no_retry'] is True,
            'Actual independent audit wait() success required')
    require(wait['result_sha256']==g['result_sha256'] and wait['review_sha256']==g['review_sha256'] and
            wait['complete_sha256']==g['terminal_sha256'],'Wait terminal not bound to actual result')
    require(type(exit_record['pid']) is int and exit_record['pid']>0 and exit_record['pid']==invocation['pid'] and
            invocation['complete_sha256']==g['terminal_sha256'] and invocation['prepared_sha256']==PREPARED_SHA,
            'Audit exit/invocation identity mismatch')
    command=invocation['command']
    require(Path(command[0]).resolve()==Path(sys.executable).resolve() and command[1:]==[
        '-B',str(A/'audit.py'),'terminal','--authorize-terminal-audit','--prepared-sha256',PREPARED_SHA,
        '--complete-sha256',g['terminal_sha256']],'Unexpected independent auditor invocation')
    for filename,key in [('audit.stdout.log','stdout_sha256'),('audit.stderr.log','stderr_sha256')]:
        path=A/'wait01'/filename;require(sha(path)==exit_record[key],'Audit process log drift');extra[str(path)]=sha(path)
    extra[str(A/'wait01/audit_invocation.json')]=sha(A/'wait01/audit_invocation.json')
    return extra


def check(g, auditor=None):
    pins=bind_payload(g)
    # Reject nonaccepted/stale review before admission may hash terminal CSVs.
    result=read(A/'terminal01/result.json')
    require(result['status']==ACCEPT and result['accepted'] is True and
            result['complete_sha256']==g['terminal_sha256'] and result['image_sha256']==IMAGE_SHA,
            'Independent result is not the accepted current terminal')
    auditor=auditor or load_auditor()
    prepared,plan,admitted=auditor.admission(PREPARED_SHA,g['terminal_sha256'])
    extra=independent_payload(g,auditor,prepared,plan,admitted)
    auditor.add(pins,admitted);auditor.add(pins,extra);auditor.verify(pins)
    return pins


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--parent-review',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(check(read(args.parent_review)['nf2_gate']),sort_keys=True))


if __name__=='__main__':main()
