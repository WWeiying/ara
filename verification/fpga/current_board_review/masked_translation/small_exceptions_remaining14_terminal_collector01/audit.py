"""Terminal metadata/pin audit only. Never imports or reruns CSV semantic checkers."""
import hashlib
import json
from pathlib import Path
import re
import sys
import time

H=Path(__file__).resolve().parent
W=H.parent/'small_exceptions_remaining14_vcs_m9_plan01'
P=W/'prepared01'
PLAN='165c12dfee46c7949de188aedf779f914e8ee76260290017b2636e3fa168108f'
IMAGE='48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
BINDING=json.loads((H/'binding.json').read_text())
REVIEW=BINDING['review_sha256']
ENVELOPE=BINDING['service_launch_sha256']
MEMBERS=[(w,s) for w in (8,16,32) for s in ((1,2,3,5) if w==8 else (0,1,2,3,5))]
NAMES=[f'small_exceptions_e{w}_sc{s}' for w,s in MEMBERS]
PASS='PASS_INDEPENDENT_M9_SMALL_EXCEPTIONS14_TERMINAL_NOT_LINUX'
BAD=re.compile(r'\bRVV_[A-Z0-9_]*FAIL\b|SMALL_EXCEPTIONS_14_FAIL|BOARD_CASE_FAIL|'
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
    need(done['status']=='PASS_M9_SMALL_EXCEPTIONS14_ORIGINAL_SINGLES_NOT_LINUX'
         and done['plan_sha256']==PLAN and done['image_sha256']==IMAGE
         and done['aborted'] is False and done['pins_unchanged'] is True and zero(done['retries']),
         'Actual worker terminal scope/status/abort/retries')
    need(type(service['recorded_unix_s']) in (int,float) and service['recorded_unix_s']>=done['finished'],
         'Systemd hook must follow worker terminal')
    need([c['id'] for c in plan['cases']]==NAMES and plan['jobs']==8 and plan['timeout_s']==1800
         and plan['service_timeout_s']==7200 and plan['image_sha256']==IMAGE,'Exact bounded14 plan')
    need(len(done['results'])==14 and [r['name'] for r in done['results']]==NAMES,'Exact14 terminal membership')
    for r in done['results']:
        need(r['status']=='PASS' and zero(r['returncode']) and not r['reason']
             and 0<r['elapsed_s']<=1800,'Actual per-member child PASS0/budget')
    run=read(P/'replay/run.json')
    need(run['status']=='COMPLETE' and run['status_counts']=={'PASS':14} and run['tests']==NAMES
         and run['jobs']==8 and run['seed']==1 and run['timeout_s']==1800
         and run['code_coverage'] is False and run['commit_trace'] is True and run['completed_at'],
         'Actual COMPLETE generic runner')
    need(read(P/'replay/summary.json')==done['results'],'Terminal/summary disagreement')
    image=Path(plan['image']);ledger=read(image/'image.json')
    need(sha(image/'image.json')==IMAGE and run['simv']==ledger['simv'],'Exact frozen M9')
    review=Path(BINDING['review_path'])
    need(sha(review)==REVIEW,'Independent admission identity')
    r=read(review)
    need(r['decision']=='NO_BLOCKER' and r['blockers']==[] and r['plan_sha256']==PLAN,'Actual no-blocker review')
    envelope=read(P/'service_launch.json')
    launch=read(P/'launch_command_takeover.json')
    need(launch['envelope_sha256']==ENVELOPE and launch['review_sha256']==REVIEW,'Actual parent takeover launch binding')
    command=[str(review) if x=='TESLA_REVIEW' else REVIEW if x=='TESLA_REVIEW_SHA' else x
             for x in envelope['command_template']]
    need(launch['command']==command and '--property=ExecStopPost='+envelope['ExecStopPost'] in command,
         'Actual pinned ExecStopPost launch')
    submission=read(P/'systemd_run_takeover.json')
    need(zero(submission['actual_returncode']) and submission['submission_only_not_worker_exit'] is True,
         'Actual parent systemd submission; worker exit checked independently')
    return plan,done,service,ledger

def case(n):
    plan,done,service,ledger=admission()
    c=plan['cases'][n-1];r=done['results'][n-1]
    root=P/'replay/tests'/c['id'];spec=plan['specs'][c['id']]
    sew,sc=MEMBERS[n-1];width=sew//8;vtype={8:0,16:8,32:16}[sew]
    need(r['artifact_dir']==str(root) and spec['scenario']==sc and spec['sew']==sew and spec['backend']=='soc'
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
        need(text.splitlines().count('SMALL_EXCEPTIONS_14_PASS')==1
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
    exact=dict(status='PASS_SMALL_EXCEPTIONS_14',scenario=sc,sew=sew,checks=5477 if sc==0 else 5481,
        original_helper_instructions=11,capacity_instructions=3,target_attempts=1,
        returned_vl=4 if sc==0 else 8,post_helper_vl=8,allowed_undefined_indices=[5,6,7,8] if sc==0 else [],output_allocation=130,
        data_bytes=8192,page_table_bytes=12288,mask_bytes=16,original_guards=[0,9],ctrl=[0],
        target_architectural_exceptions=0,memory_owner_count=4,helper_owner_count=3,
        source_active_elements=8 if sc==0 else 4 if sc in (1,2) else 0,source_masked_elements=0 if sc==0 else 4 if sc in (1,2) else 8,lifecycle_successor='source-bound-four-memory-owners01')
    need(all(s[k]==v for k,v in exact.items()),'Full unchanged source oracle dimensions/context')
    need([(x['phase'],x['bytes'],x['checks']) for x in s['checkpoints']]==[(0,20800+130*width,2726),(1,20792+(126 if sc==0 else 130)*width,5463 if sc==0 else 5467)],
         'Both complete scalar checkpoints')
    need(s['actions']==['checkpoint0','enter_s','helper','younger','handler','return_m','checkpoint1'],'Source order')
    rec=s['actual_handler_csrs'];sy=spec['symbols']
    want=[9,sy['fx_ecall'],0,0x800,(8<<60)|((sy['fx_pages']+8192)>>12),8,vtype,0,117,5]
    need(len(rec)==1 and all((rec[0][str(i)]&0x8000031888 if i==3 else rec[0][str(i)])==v
                            for i,v in enumerate(want)),'Exact completion trap/CSR context')
    wcode={8:0,16:5,32:6}[sew]<<12
    sites=[('old_vd',1,0x02058c07|wcode),('mask',2,0x02b60007),
           ('target',3,(0x00050c07 if sc in (1,3) else 0x01050c07)|wcode),('result',9,0x02058c27|wcode)]
    need(s['abi_policy']=='exact_ELF_main_and_handler_first_spills_no_reset_defaults'
         and s['opaque_main_registers']==[8,9,18,19,20,21,22,23,24,25,26,27]
         and set(s['opaque_handler_registers'])<=set([7,28,29,30,31])
         and s['handler_restored']==[1,5,6,7,28,29,30,31,10,11,12,13,14,15,16,17]
         and set(map(int,s['handler_saved']))==set(s['handler_restored'])
         and s['completion_ecall']['pc']==sy['fx_ecall'], 'Complete exact ABI receipt')
    owners=s['memory_owners'];need(len(owners)==4,'Four required owners')
    seen=set();allocations=0
    for a,(name,i,op) in zip(owners,sites):
        need((a['site'],a['pc'],a['insn'],a['vl'],a['vtype'],a['vstart'],a['trap'])==
             (name,spec['helper'][i],op,8,vtype,0,0) and a['seq'] not in seen,'Exact source owner identity')
        seen.add(a['seq'])
        need(a['cycle']<=a['request_cycle']<=a['response_cycle']<=a['retire_context']['cycle'],'Owner frontend timing')
        need(a['retire_context']==dict(pc=a['pc'],insn=op,cycle=a['retire_context']['cycle'],vl=8,vtype=vtype,vstart=0),
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
        original_result_elements=8,original_guards=2,undefined_suffix_waivers=4 if sc==0 else 0,
        producer_checker_execution='in-process successful return; no separate numeric wait exists',
        CSV_semantic_reparsed=False,raw_logs_vetoed=2)
    save(H/f'case{n}.json',result)

if __name__=='__main__':
    try:case(int(sys.argv[1]))
    except BaseException as error:
        save(H/f'case{sys.argv[1]}_failure.json',dict(status='NOT_ACCEPTED',firstcause=repr(error)))
        raise
