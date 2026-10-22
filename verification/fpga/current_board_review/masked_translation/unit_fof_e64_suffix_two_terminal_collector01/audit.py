"""Terminal metadata/pin audit only. Never imports or reruns CSV semantic checkers."""
import hashlib
import json
from pathlib import Path
import re
import sys
import time

H=Path(__file__).resolve().parent
W=H.parent/'unit_fof_e64_suffix_two_vcs_m9_plan01'
P=W/'prepared01'
PLAN='3bc80c42d8e6bf7f722d81184ef8fc4bcac099e2518547292f5172665324e949'
IMAGE='48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
REVIEW='eb3c560dee1650dc0f84f032375713b96108e1e7a3e47e2871d8cad23eceed90'
ENVELOPE='6cffabaa8a0169d8fabece820684f0d9530e3083a8bb2ca8bbb497c56475355a'
NAMES=['unit_fof_e64_scenario1','unit_fof_e64_scenario2']
PASS='PASS_INDEPENDENT_M9_UNIT_FOF_TWO_TERMINAL_NOT_LINUX'
BAD=re.compile(r'\bRVV_[A-Z0-9_]*FAIL\b|UNIT_FOF_E64_SUFFIX_FAIL|BOARD_CASE_FAIL|'
    r'BOARD_REPLAY_(?:TRAP|MISMATCH|SERVICE_FAIL|VLEN_FAIL)|'
    r'\b(?:FAIL|FAILED|ABORT|MISMATCH|SKIP)\b|Error-\[|Fatal[-:]|'
    r'\bUVM_FATAL\b(?![ \t]*:[ \t]*0\b)',re.I)

def need(ok,why):
    if not ok:raise ValueError(why)
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def save(p,v):
    import os
    with Path(p).open('x') as f:
        json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def zero(v):return type(v) is int and v==0
def verify(pins):
    for p,h in pins.items():need(sha(p)==h,'Pin drift: '+p)

def admission():
    need(sha(P/'plan.json')==PLAN and sha(P/'service_launch.json')==ENVELOPE,'Plan/launch envelope identity')
    plan,done,service=read(P/'plan.json'),read(P/'complete.json'),read(P/'service_exit.json')
    need(set(service)=={'EXIT_CODE','EXIT_STATUS','SERVICE_RESULT','recorded_unix_s'} and
         (service['EXIT_CODE'],service['EXIT_STATUS'],service['SERVICE_RESULT'])==('exited','0','success'),
         'Actual systemd exit is not exited/0/success')
    need(done['status']=='PASS_M9_UNIT_FOF_E64_TWO_ORIGINAL_SINGLES_NOT_LINUX'
         and done['plan_sha256']==PLAN and done['image_sha256']==IMAGE
         and done['aborted'] is False and done['pins_unchanged'] is True and zero(done['retries']),
         'Actual worker terminal scope/status/abort/retries')
    need(type(service['recorded_unix_s']) in (int,float) and service['recorded_unix_s']>=done['finished'],
         'Systemd hook must follow worker terminal')
    need([c['id'] for c in plan['cases']]==NAMES and plan['jobs']==2 and plan['timeout_s']==1800
         and plan['service_timeout_s']==4200 and plan['image_sha256']==IMAGE,'Exact bounded2 plan')
    need(len(done['results'])==2 and [r['name'] for r in done['results']]==NAMES,'Exact2 terminal membership')
    for r in done['results']:
        need(r['status']=='PASS' and zero(r['returncode']) and not r['reason']
             and 0<r['elapsed_s']<=1800,'Actual per-member child PASS0/budget')
    run=read(P/'replay/run.json')
    need(run['status']=='COMPLETE' and run['status_counts']=={'PASS':2} and run['tests']==NAMES
         and run['jobs']==2 and run['seed']==1 and run['timeout_s']==1800
         and run['code_coverage'] is False and run['commit_trace'] is True and run['completed_at'],
         'Actual COMPLETE generic runner')
    need(read(P/'replay/summary.json')==done['results'],'Terminal/summary disagreement')
    image=Path(plan['image']);ledger=read(image/'image.json')
    need(sha(image/'image.json')==IMAGE and run['simv']==ledger['simv'],'Exact frozen M9')
    review=H.parent/'unit_fof_e64_suffix_two_review02/result.json'
    need(sha(review)==REVIEW,'Independent admission identity')
    r=read(review)
    need(r['decision']=='NO_BLOCKER' and r['blockers']==[] and r['plan_sha256']==PLAN,'Actual no-blocker review')
    envelope=read(P/'service_launch.json')
    launch=read(P/'launch_command.json')
    need(launch['service_launch_sha256']==ENVELOPE and launch['review_sha256']==REVIEW,'Actual launch binding')
    command=[str(review) if x=='TESLA_REVIEW' else REVIEW if x=='TESLA_REVIEW_SHA' else x
             for x in envelope['command_template']]
    need(launch['command']==command and '--property=ExecStopPost='+envelope['ExecStopPost'] in command,
         'Actual pinned ExecStopPost launch')
    need(zero(read(P/'systemd_run_receipt.json')['actual_systemd_run_returncode']),'Actual systemd submission')
    return plan,done,service,ledger

def case(n):
    plan,done,service,ledger=admission()
    c=plan['cases'][n-1];r=done['results'][n-1]
    root=P/'replay/tests'/c['id'];spec=plan['specs'][str(n)]
    need(r['artifact_dir']==str(root) and spec['scenario']==n and spec['backend']=='soc'
         and 'tohost' not in spec['symbols'],'Actual member/SoC backend')
    need(sha(root/'input.elf')==sha(c['elf'])==c['sha256']==spec['elf_sha256'],'Source/private ELF identity')
    inputs=read(root/'inputs.json')
    need(inputs['binary']==dict(path=str(root/'input.elf'),sha256=c['sha256'],source=c['elf']),
         'Exact private ELF provenance')
    need(inputs['simv']==dict(path=ledger['simv'],image_sha256=ledger['files']),'Actual image provenance')
    command=read(root/'command.json')
    need(command==dict(cwd=str(root/'work'),command=[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1',
        '+PRELOAD='+str(root/'input.elf'),'+TESTCASE='+c['id'],'+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')]),
        'Exact actual execution command')
    for name,schema in [('monitor_outcome.unvalidated.json','UNVALIDATED_MONITOR_OUTCOME_V1'),
                        ('child_outcome.unvalidated.json','UNVALIDATED_CHILD_OUTCOME_V1')]:
        v=read(root/name)
        need(v['schema']==schema and v['architectural_acceptance'] is False and zero(v['returncode'])
             and v['elapsed_s']==r['elapsed_s'] and v['command_sha256']==sha(root/'command.json'),
             'Numeric-first actual outcome')
        if name.startswith('monitor'):
            need(v['timed_out'] is False and v['failure_seen'] is False and v['abort_set'] is False,
                 'Numeric monitor timeout/failure/abort')
        else:need(v['name']==c['id'] and v['status']=='PASS' and not v['reason'],'Actual child identity/status')
    for name in ('console.log','work/run.vcs.log'):
        text=(root/name).read_text()
        need(not BAD.search(text),'Raw failure veto '+name)
        need(text.splitlines().count('UNIT_FOF_E64_SUFFIX_PASS')==1
             and 'Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish' in text,'Exact raw markers/finish')
    original=read(root/'strict_original.json');s=read(root/'strict_csv.json');g=original['generic']
    need(original['strict']==s and original['csv_sha256']==done['evidence_pins'][str(root/'commit_trace.csv')],
         'Strict/generic artifact consistency and full CSV hash binding')
    need(read(root/'trace_summary.json')==dict(g,status='VALID'),'Saved generic protocol evidence equality')
    need(g['cvx_exception_count']==0 and g['architecture_request_count']>0
         and g['backend_uop_alloc_count']==g['backend_uop_done_count']>=4
         and g['cvx_request_count']==g['cvx_response_count']
         and (s['rows'],s['retired'],s['last_cycle'])==(g['rows'],g['retire_count'],g['last_cycle']),
         'Complete generic protocol and count agreement')
    exact=dict(status='PASS_UNIT_FOF_E64_SUFFIX',scenario=n,sew=64,checks=5481,
        original_helper_instructions=11,capacity_instructions=3,target_attempts=1,
        returned_vl=8,post_helper_vl=8,allowed_undefined_indices=[],output_allocation=130,
        data_bytes=8192,page_table_bytes=12288,mask_bytes=16,original_guards=[0,9],ctrl=[0],
        target_architectural_exceptions=0,memory_owner_count=4,helper_owner_count=3,
        source_active_elements=4,source_masked_elements=4,lifecycle_successor='source-bound-four-memory-owners01')
    need(all(s[k]==v for k,v in exact.items()),'Full unchanged source oracle dimensions/context')
    need([(x['phase'],x['bytes'],x['checks']) for x in s['checkpoints']]==[(0,21840,2726),(1,21832,5467)],
         'Both complete scalar checkpoints')
    need(s['actions']==['checkpoint0','enter_s','helper','younger','handler','return_m','checkpoint1'],'Source order')
    rec=s['actual_handler_csrs'];sy=spec['symbols']
    want=[9,sy['fx_ecall'],0,0x800,(8<<60)|((sy['fx_pages']+8192)>>12),8,24,0,117,5]
    need(len(rec)==1 and all((rec[0][str(i)]&0x8000031888 if i==3 else rec[0][str(i)])==v
                            for i,v in enumerate(want)),'Exact completion trap/CSR context')
    sites=[('old_vd',1,0x0205fc07),('mask',2,0x02b60007),
           ('target',3,0x00057c07 if n==1 else 0x01057c07),('result',9,0x0205fc27)]
    owners=s['memory_owners'];need(len(owners)==4,'Four required owners')
    seen=set();allocations=0
    for a,(name,i,op) in zip(owners,sites):
        need((a['site'],a['pc'],a['insn'],a['vl'],a['vtype'],a['vstart'],a['trap'])==
             (name,spec['helper'][i],op,8,24,0,0) and a['seq'] not in seen,'Exact source owner identity')
        seen.add(a['seq'])
        need(a['cycle']<=a['request_cycle']<=a['response_cycle']<=a['retire_context']['cycle'],'Owner frontend timing')
        need(a['retire_context']==dict(pc=a['pc'],insn=op,cycle=a['retire_context']['cycle'],vl=8,vtype=24,vstart=0),
             'Owner actual retirement context')
        alloc={(v['vid'],v['cycle']) for v in a['allocations']}
        completed={(v['vid'],v['allocated']) for v in a['completions']}
        need(alloc and alloc==completed and len(alloc)==len(a['allocations'])==len(a['completions']),
             'Nonempty exact backend pairing per owner')
        need(all(0<=v['vid']<8 and a['cycle']<=v['allocated']<=v['cycle'] for v in a['completions']),
             'Backend VID/timing')
        allocations+=len(alloc)
    need(allocations==s['memory_allocations']<=g['backend_uop_alloc_count'],'Backend owner coverage count')
    result=dict(status='PASS_CASE_METADATA_AND_PINS_NOT_CSV_REPARSE',name=c['id'],child_returncode=0,
        elapsed_s=r['elapsed_s'],generic=g,checks=s['checks'],owners=owners,output_words=130,
        original_result_elements=8,original_guards=2,undefined_suffix_waivers=0,
        producer_checker_execution='in-process successful return; no separate numeric wait exists',
        CSV_semantic_reparsed=False,raw_logs_vetoed=2)
    save(H/f'case{n}.json',result)

if __name__=='__main__':
    try:case(int(sys.argv[1]))
    except BaseException as error:
        save(H/f'case{sys.argv[1]}_failure.json',dict(status='NOT_ACCEPTED',firstcause=repr(error)))
        raise
