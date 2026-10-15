#!/usr/bin/env python3
"""Independent metadata-only terminal binding; no CSV or reference traversal."""
import hashlib
import json
from pathlib import Path
import re
import time

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
P=BASE/'prepared01'
EXPECTED='f616c9dc8223024ba56751cca54367672541d857e3d9f2a16c9e959171115746'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(v,msg):
    if not v:raise ValueError(msg)

started=time.time();plan=read(P/'plan.json');end=read(P/'complete.json');col=read(P/'collector_result.json')
need(sha(P/'plan.json')==EXPECTED==end['plan_sha256']==col['plan_sha256'],'Exact plan')
need(len(plan['cases'])==1,'Single membership');case=plan['cases'][0];root=P/'replay/tests'/case['id']
need(case['id']=='arithmetic_original_e16_m2_full4095_packed' and
     case['original_name']==case['shape']=='rvv_matrix_e16_m2','Runtime/historical identity')
spec=plan['specs'][case['shape']]
need(spec['config']==dict(id='rvv_matrix_e16_m2',sew=16,lmul='m2',cap=128,calls=4095),'Exact typed shape')
need(sha(root/'input.elf')==sha(case['elf'])==case['sha256']==
     '899f6d001d83da3153794fd264973fcc8094e4d2b25b0bd61391b816bb130dad','Actual source/private ELF')
need(end['status']=='PASS_M9_FULL_ORIGINAL_E16_M2_4095_CALLS_NOT_LINUX' and
     end['aborted'] is False and end['pins_unchanged'] is True and end['retries']==0,'Whole terminal')
need(col['status']=='ACCEPTED_M9_ORIGINAL_E16_M2_FULL4095_NOT_LINUX' and
     col['complete_sha256']==sha(P/'complete.json') and col['pins_pre_post_unchanged'] is True,'Collector binding')
monitor=read(root/'child_outcome.unvalidated.json');service=read(P/'service_exit.json');wait=read(P/'collector_exit.json')
need(type(monitor['returncode']) is int and monitor['returncode']==0 and
     all(monitor[k] is False for k in ('timed_out','failure_seen','cancelled')),'Actual clean numeric child')
need(len(end['results'])==1 and end['results'][0]['returncode']==0 and end['results'][0]['status']=='PASS' and
     end['results'][0]['name']==case['id'] and end['results'][0]['elapsed_s']==monitor['elapsed_s'] and
     0<monitor['elapsed_s']<=case['timeout_s']==10800,'One exact timed child')
need(service['kind']=='SYSTEMD_EXEC_STOP_POST_ACTUAL_ENVIRONMENT' and
     [service[k] for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')]==['success','exited','0'] and
     col['actual_service']==service and col['actual_monitor']==monitor,'Actual retained exit hook, not GC defaults')
need(type(wait['actual_wait_returncode']) is int and wait['actual_wait_returncode']==0 and
     wait['pid']==col['pid'] and wait['timed_out'] is False and wait['retries']==0,'Actual collector wait0')
command=read(root/'command.json')
need(monitor['command_sha256']==sha(root/'command.json') and monitor['command']==command['command'] and
     monitor['cwd']==command['cwd']==str(root/'work'),'Command/cwd binding')
need('+ntb_random_seed=1' in monitor['command'] and '+TESTCASE='+case['id'] in monitor['command'] and
     '+PRELOAD='+str(root/'input.elf') in monitor['command'],'Seed/runtime/preload')
image=Path(plan['image']);need(image.parent.parent.name=='current_board_memory_candidate09' and
     sha(image/'image.json')==plan['image_sha256'],'Frozen M9 image identity')
need(monitor['command'][0]==str(image/'_build/vcs/simv'),'Actual M9 executable command')
run=read(P/'replay/run.json');summary=read(P/'replay/summary.json');launch=read(P/'launch.json')
need(run['status']=='COMPLETE' and run['tests']==[case['id']] and run['status_counts']=={'PASS':1} and
     summary==end['results'],'Runner COMPLETE/exact one')
invocation=read(P/'launch_invocation.json');args=invocation['command']
need(invocation['plan_sha256']==EXPECTED and '--unit='+plan['unit'] in args and
     '--property=RuntimeMaxSec=13200' in args and '--property=Restart=no' in args and
     any(x.startswith('--property=ExecStopPost=') and str(BASE/'exit_hook.py') in x for x in args),
     'Actual unit and frozen exit hook launch')
need(sha(invocation['entry'])==invocation['entry_sha256']==end['approval_pins'][invocation['entry']], 'Actual entry review')
need(launch['owner']['properties']['Id']==plan['unit'] and launch['plan_sha256']==EXPECTED and
     read(P/'service_submission.json')['actual_wait_returncode']==0,'Actual launch receipt')
cc=read(P/'collector_command.json')
need(cc['collector_sha256']==sha(BASE/'collect.py')==plan['pins'][str(BASE/'collect.py')] and
     cc['command']==['/usr/bin/python3','-B',str(BASE/'collect.py'),'--out',str(P)],'Actual collector code/command')
report=read(root/'strict_original.json');s=report['strict'];g=report['generic'];owners=report['owner_coverage']
need(sha(root/'strict_original.json')==col['strict_report_sha256'],'Whole strict report digest')
want=dict(calls=4095,results=524160,guards=8190,returned_vstart_zero=4095,helper_instructions=53235,
          packed_output_reads=135135,fresh_output_bytes_each_call=260,typed_sentinel='005b',tail_read_bytes=4,
          physical_registers_each_group=2,vtype=9)
need(all(s[k]==v for k,v in want.items()) and s['routine_counts']==[4095]*13 and
     s['full_order'] is True and s['partitioned'] is False and report['strict_csv_parses']==1,'Full typed original scope')
need((s['rows'],s['retired'],s['last_cycle'])==(g['rows'],g['retire_count'],g['last_cycle']) and
     g['cvx_exception_count']==0 and g['cvx_request_count']==g['cvx_response_count']==45047 and
     g['backend_uop_alloc_count']==g['backend_uop_done_count']==23067,'Strict/generic protocol identity')
need(read(root/'trace_summary.json')==dict(g,status='VALID'),'Frozen generic summary identity')
seq=read(Path(case['elf']).parents[1]/'sequence.json');calls=s['call_ledger'];need(len(seq)==len(calls)==4095,'Full source sequence')
for i,(gold,call) in enumerate(zip(seq,calls)):
    need(call['ordinal']==i and call['original_ordinal']==gold['ordinal']==i+1 and
         all(call[k]==gold[k] for k in ('op','seed','vl','mode')) and call['vstart']==gold['start'] and
         call['reads']==list(range(33)) and call['returned_vstart']==0,'Every original call metadata')
    target=spec['backend']['helpers'][f'op_{gold["op"]}'][8]
    need((call['target_pc'],call['target_insn'])==(target['pc'],target['insn']),'Actual helper target mapping')
groups={i:[] for i in range(4095)};targets=[]
for item in owners['owner_ledger']:
    need(item['alloc']==item['done'] and (not item['required'] or item['alloc']>0),'Every required owner completed')
    if item['kind']=='memory':groups[item['call']].append(item)
    if item['kind']=='target':targets.append(item)
need(all([x['helper_index'] for x in v]==[1,2,3,4,11] and all(x['required'] for x in v) for v in groups.values()),'Five helpers per call')
need(len(targets)==4095,'All targets retained')
for item in targets:
    gold=seq[item['call']]
    required=gold['start']<gold['vl'] and not(gold['op']==19 and item['insn']==0x38813c57 and gold['vl']<=2)
    need(item['required']==required,'Exact VI2 eligibility, no general target waiver')
need(sum(x['required'] for x in targets)==2592 and
     sum(x['required'] and seq[x['call']]['op']==24 for x in targets)==117 and
     owners['compulsory_memory_owners']==20475 and owners['optional_slideup_targets']==18,'Owner aggregate scope')
for filename in ('console.log','work/run.vcs.log'):
    text=(root/filename).read_text()
    need(not re.search(r'\b(?:FAIL|FAILED|ERROR|TRAP|MISMATCH|ABORTED)\b',text,re.I),'Raw terminal failure veto')
text=(root/'console.log').read_text()
need(text.splitlines().count(case['pass_markers'][0])==1 and text.count('Core Test *** SUCCESS ***')==1 and '$finish' in text,'Original console oracle exit')
allpins=dict(plan['pins']);allpins.update(end['evidence_pins']);allpins.update(end['approval_pins'])
fresh={};inherited={}
for name,digest in allpins.items():
    path=Path(name)
    if path.suffix=='.csv' or path.stat().st_size>16*1024*1024:
        inherited[name]=dict(sha256=digest,size=path.stat().st_size,basis='Producer/collector pre-post verification; not rehashed')
    else:
        need(sha(path)==digest,'Current bounded pin drift: '+name);fresh[name]=digest
need(report['actual_csv_sha256']==col['csv_sha256']==allpins[str(root/'commit_trace.csv')],'Inherited same closed CSV identity')
for path in [P/n for n in ('plan.json','complete.json','collector_result.json','service_exit.json','collector_exit.json',
                          'collector_command.json','launch_invocation.json','service_submission.json')]+[HERE/'review.py']:
    fresh[str(path)]=sha(path)
result=dict(status='ACCEPTED_INDEPENDENT_TERMINAL_METADATA_M9_E16_M2_FULL4095_NOT_LINUX',
    full_source_scope_may_be_counted=True,scope=want,plan_sha256=EXPECTED,elf_sha256=case['sha256'],
    actual_simulator=monitor,actual_service=service,actual_collector_wait=wait,
    strict_report_sha256=sha(root/'strict_original.json'),csv_sha256=report['actual_csv_sha256'],
    csv_reads=0,semantic_reparses=0,new_tests=0,systemctl_queries=0,
    original_plan_pin_count=len(plan['pins']),fresh_checked_pin_count=len(fresh),inherited_large_pin_count=len(inherited),
    evidence_pins=fresh,inherited_large_pins=inherited,owner_counts=dict(memory=20475,targets=2592,op24=117,total=23067),
    original_linux_stall_closed=False,started=started,finished=time.time())
with (HERE/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:result[k] for k in ('status','fresh_checked_pin_count','inherited_large_pin_count')}))
print('result_sha256',sha(HERE/'result.json'))
