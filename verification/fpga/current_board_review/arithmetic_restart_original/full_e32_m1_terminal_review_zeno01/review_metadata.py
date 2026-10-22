"""Metadata-only terminal binding; never opens CSV or commit logs."""
import hashlib,json,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
A=HERE.parent
P=A/'full_e32_m1_packed_vcs_m9_plan01/prepared01'
PLAN='fca9ceb8502f806b939e473030e3cbf3c92d00d55fca04d2087bc948c260ae2c'
ID='arithmetic_original_e32_m1_full5985_packed'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,msg):
    if not ok:raise ValueError(msg)
result=dict(status='NOT_ACCEPTED_METADATA_REVIEW',CSV_reads=0,reference_raw_reads=0,waiter_used=False,
    target_already_present=True,original_Linux_historical_stall_closed=False)
pins={}
try:
    plan=read(P/'plan.json');end=read(P/'complete.json');col=read(P/'collector_result.json')
    service=read(P/'service_exit.json');cx=read(P/'collector_exit.json')
    require(sha(P/'plan.json')==PLAN and col['plan_sha256']==end['plan_sha256']==PLAN,'Exact original plan')
    require(col['status']=='ACCEPTED_M9_ORIGINAL_E32_M1_FULL5985_NOT_LINUX','Collector NOT_ACCEPTED')
    require(end['status']=='PASS_M9_FULL_ORIGINAL_E32_M1_5985_CALLS_NOT_LINUX' and not end['aborted'] and end['pins_unchanged'] and end['retries']==0,'Whole worker actual PASS')
    require([service[k] for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')]==['success','exited','0'] and service==col['actual_service'],'Actual service numeric0')
    require(type(cx['actual_wait_returncode']) is int and cx['actual_wait_returncode']==0 and not cx['timed_out'] and cx['retries']==0 and cx['pid']==col['pid'],'Actual collector wait0')
    require(len(plan['cases'])==len(end['results'])==1 and plan['cases'][0]['id']==ID,'Sole exact case')
    case=plan['cases'][0];child=end['results'][0];root=P/'replay/tests'/ID
    require(child['name']==ID and child['status']=='PASS' and type(child['returncode']) is int and child['returncode']==0 and not child['reason'],'Actual child result')
    monitor=read(root/'child_outcome.unvalidated.json')
    require(monitor==col['actual_monitor'] and type(monitor['returncode']) is int and monitor['returncode']==0 and not any(monitor[k] for k in ('timed_out','failure_seen','cancelled')) and monitor['elapsed_s']==child['elapsed_s'],'Numeric monitor before checks')
    require(0<child['elapsed_s']<=plan['case_timeout_s']==10800,'Unextended simulation budget')
    require(sha(P/'complete.json')==col['complete_sha256'] and sha(root/'strict_original.json')==col['strict_report_sha256'],'Terminal metadata hashes')
    report=read(root/'strict_original.json');s=report['strict'];g=report['generic'];o=report['owner_coverage']
    require([s[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads')]==[5985,191520,11970,5985,77805,101745] and s['routine_counts']==[5985]*13,'Full source counts')
    require(s['fresh_output_bytes_each_call']==136 and s['FP_calls']==1890 and s['FP_input_scalar_writes']==120960 and s['mask_clear_stores']==35280 and s['mask_bit_stores']==38955 and s['full_order'] and not s['partitioned'],'FP every-call fresh/mask/history')
    ledger=s['call_ledger']
    require(len(ledger)==5985 and all(x['ordinal']==i and x['original_ordinal']==i+1 and x['reads']==list(range(17)) and x['returned_vstart']==0 for i,x in enumerate(ledger)),'All original ordinals/full136B reads/vstart')
    require(set(x['op'] for x in ledger)==set(range(35)) and set(x['seed'] for x in ledger)=={0,1,2},'35ops three seeds')
    require((s['rows'],s['retired'],s['last_cycle'])==(g['rows'],g['retire_count'],g['last_cycle']) and report['strict_csv_parses']==1,'Same single closed strict/generic parse')
    summary=read(root/'trace_summary.json')
    require(summary['status']=='VALID' and all(summary[k]==v for k,v in g.items()),'Frozen generic summary')
    require(g['cvx_request_count']==g['cvx_response_count']==g['architecture_request_count']==g['vector_retire_count']==65837 and g['cvx_exception_count']==0 and g['backend_uop_alloc_count']==g['backend_uop_done_count']==33687,'Complete actual protocol')
    require(all(o[k]==v for k,v in plan['owner_counts'].items()),'Source-derived owner contract')
    owners=o['owner_ledger']
    require(len(owners)==65837 and len({x['arch_order'] for x in owners})==65837 and all(x['alloc']==x['done'] and (not x['required'] or x['alloc']>0) for x in owners),'Every actual/required owner paired')
    mem=[x for x in owners if x['kind']=='memory' and x['required']]
    targets=[x for x in owners if x['kind']=='target' and x['required']]
    require(len(mem)==29925 and len(targets)==3762 and all({x['helper_index'] for x in mem if x['call']==i}=={1,2,3,4,11} for i in range(5985)),'Per-call five memory owners, not aggregate only')
    require(sum(ledger[x['call']]['op']==24 for x in targets)==117,'Required op24 target owners')
    require(report['actual_csv_sha256']==col['csv_sha256']==end['evidence_pins'][str(root/'commit_trace.csv')],'Raw hash chain without reopening raw')
    allpins=dict(plan['pins']);allpins.update(end['evidence_pins']);allpins.update(end['approval_pins'])
    excluded={}
    for name,digest in allpins.items():
        path=Path(name)
        if path.suffix in ('.csv','.log'):
            excluded[name]=digest
            continue
        require(sha(path)==digest,'Current nonraw pin drift: '+name)
        pins[name]=digest
    require(sha(root/'input.elf')==case['sha256']==sha(Path(case['elf'])),'Exact plan/private ELF')
    for path in (P/'plan.json',P/'complete.json',P/'collector_result.json',P/'collector_exit.json',P/'service_exit.json',root/'child_outcome.unvalidated.json',root/'strict_original.json',root/'trace_summary.json',Path(__file__)):
        pins[str(path)]=sha(path)
    result.update(status='ACCEPTED_M9_E32_M1_FULL5985_METADATA_ONLY_NOT_LINUX',plan_sha256=PLAN,
        calls=5985,results=191520,guards=11970,vstart_zero=5985,packed_output_reads=101745,helper_instructions=77805,
        FP_calls=1890,FP_input_scalar_writes=120960,required_memory_owners=29925,required_target_owners=3762,
        actual_monitor=monitor,actual_service=service,actual_collector_exit=cx,
        strict_report_sha256=col['strict_report_sha256'],private_ELF_sha256=case['sha256'],
        current_nonraw_pin_count=len(pins),pins=pins,raw_and_log_pins_not_rehashed=excluded,
        raw_pin_authority='Frozen producer/collector pre-post pins and closed strict/generic hash chain; not independently re-read',
        no_new_DUT_or_reference=True)
except BaseException as error:
    result['firstcause']=type(error).__name__+': '+str(error)
result['finished']=time.time()
with (HERE/'REVIEW.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print({k:v for k,v in result.items() if k in ('status','firstcause','current_nonraw_pin_count')})
raise SystemExit(result['status']!='ACCEPTED_M9_E32_M1_FULL5985_METADATA_ONLY_NOT_LINUX')

