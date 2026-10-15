#!/usr/bin/env python3
"""Read-only sealed entry identity/schema checks; never imports producer workers."""
import ast
import hashlib
import json
from pathlib import Path
import shlex

OUT = Path(__file__).resolve().parent
G = OUT.parent
WORKER = G/'e8_m4_ops3_prefix66_vcs_m6_plan01'
P = WORKER/'prepared01'
REF = G/'e8_m4_ops3_prefix66_prepare01'
A = G/'e8_m4_ops3_prefix66_reference_audit01'
PLAN_SHA = '5de3a259e330825548009fbe17a4f80da34c3a6b816b495a695564621ea4ddbb'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text())


def merge(*tables):
    result={}
    for table in tables:
        for path,digest in table.items():
            require(path not in result or result[path]==digest,'Pin conflict: '+path)
            result[path]=digest
    return result


def main():
    require(not (OUT/'audit.json').exists(),'Exclusive new audit output; no repeat')
    require(sha(P/'plan.json')==PLAN_SHA,'Actual disk plan differs')
    plan=read(P/'plan.json')
    host=read(WORKER/'host03.json')
    require((host['status'],host['tests'],host['failures'],host['errors'])==
            ('PASS_HOST_ONLY_NOT_DUT',55,0,0),'Actual Host03 record differs')
    for name,digest in host['pins'].items():
        require(sha(Path(name))==digest,'Host03 pin differs: '+name)
    for name,digest in plan['pins'].items():
        require(sha(Path(name))==digest,'Plan pin differs: '+name)
    require(len(plan['pins'])==744,'Actual plan pin count differs')
    oldready,ready,proof=read(REF/'READY.json'),read(REF/'READY02.json'),read(REF/'original_linux_rebuild02/proof.json')
    require(ready['soc_elf']==oldready['soc_elf'] and ready['spike_elf']==oldready['spike_elf'],
            'Retained ELF identities differ')
    audit,execution=read(A/'audit.json'),read(A/'execution.json')
    require(audit['status']=='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT' and
            execution['returncode']==0 and type(execution['returncode']) is int and
            execution['timed_out'] is False and execution['retries']==0,'Actual independent execution differs')
    require(audit['ready_sha256']==sha(REF/'READY02.json')==plan['reference_ready_sha256'] and
            sha(A/'audit.json')==plan['independent_audit_sha256'] and
            sha(A/'REVIEW.md')==plan['independent_review_sha256'] and
            sha(A/'execution.json')==plan['independent_execution_sha256'], 'Independent acceptance links differ')
    reference=read(REF/'reference/reference.json')
    require(sha(REF/'reference/reference.json')==ready['reference_sha256'] and
            reference['commit_sha256']==audit['raw_sha256'] and
            reference['commit_sha256']!=ready['reference_sha256'],'Raw/report linkage differs')
    required=merge(host['pins'],oldready['pins'],ready['pins'],proof['pins'],
                   read(REF/'baseline_pins.json'),read(A/'verified_input_pins.json'),read(A/'auditor_pins.json'))
    for p in [WORKER/n for n in ('replay.py','checker.py','newscope.py','test_host.py','host03.json')]:
        required[str(p)]=sha(p)
    for p in [REF/'READY02.json',REF/'original_linux_rebuild02/proof.json']+[
            A/n for n in ('audit.json','REVIEW.md','execution.json','execution_started.json',
                          'verified_input_pins.json','auditor_pins.json')]:
        required[str(p)]=sha(p)
    require(all(plan['pins'].get(p)==d for p,d in required.items()),'Plan missing transitive acceptance/code pins')
    original=Path(proof['original_linux_elf'])
    rebuilt=Path(proof['rebuilt_linux_elf'])
    require(original.read_bytes()==rebuilt.read_bytes() and
            sha(original)==proof['original_linux_elf_sha256']==proof['rebuilt_linux_elf_sha256'],
            'Exact original Linux binary identity differs')
    case,spec=plan['case'],plan['spec']
    require((case['id'],case['original_name'])==('gather_prefix_e8_m4_ops3','rvv_permute_restart_e8_m4_ops3'),
            'Source/runtime ids differ')
    require(case['elf']==ready['soc_elf']['path'] and case['sha256']==ready['soc_elf']['sha256'] and
            sha(Path(case['elf']))==case['sha256'],'Actual case ELF differs')
    require((spec['sew'],spec['lmul'],spec['capacity'],spec['physical_predicate_bytes'])==(8,4,512,128),
            'Actual plan shape/physical storage differs')
    sourceproof=read(REF/'source_elf_proof.json')
    require(spec['routine']==sourceproof['soc_routine'] and len(spec['routine'])==13 and
            [r['insn'] for r in spec['routine']]==[r['insn'] for r in sourceproof['original_routine']],
            'Original13 m4 helper differs')
    require(spec['capacity_vset']['insn']=='0022f557' and spec['park']['insn']=='a001' and
            spec['exit_address']==0xd0000000 and len(spec['code'])==840,'ELF capacity/exit/code spec differs')
    require((ready['capacity'],ready['calls'],ready['predecessors'],ready['physical_predicate_bytes'],
             ready['setup_values_per_call'],ready['setup_bytes_per_call'],ready['fullcap_results'],
             ready['guards'],ready['oracle_loads'],ready['helper_instruction_count'],ready['endpoint'])==
            (512,66,65,128,2178,2690,33792,132,33924,858,[0,3,0,4,0,1]),'Reference scope differs')
    require((plan['jobs'],plan['timeout_s'],plan['service_timeout_s'],plan['reserved_slots'])==(1,5400,6600,0),
            'Fixed actual plan budgets differ')
    require(plan['status']=='PREPARED_NOT_RUN' and all(plan[k] is True for k in
            ('no_build','no_retry','no_fsdb','no_code_coverage','no_ucli','unvalidated_numeric_outcome_before_postcheck')),
            'Actual no-run/failstop contract differs')
    image=Path(plan['image']);ledger=read(image/'image.json')
    require(plan['image_sha256']==sha(image/'image.json')==
            'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0','M6 image differs')
    require(plan['snapshot_sha256']==ledger['snapshot_sha256']==
            '3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438' and
            ledger['configuration_sha256']=='6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785',
            'Frozen M6 snapshot/config differs')
    required_image=merge(ledger['files'],{str(Path(ledger['snapshot'])/'sources'/n):d for n,d in
        read(Path(ledger['snapshot'])/'snapshot.json')['files'].items()})
    require(all(plan['pins'].get(p)==d for p,d in required_image.items()),'Missing frozen M6 transitive pins')
    launch=read(P/'ready.json')
    require(launch['plan_sha256']==PLAN_SHA and launch['vcs_started'] is False and
            launch['parent_approval']=='UNRESOLVED','Actual launch readiness differs')
    command=launch['command']
    require(command==['/usr/bin/python3','-B',str(WORKER/'replay.py'),'run','--image',str(image),
        '--out',str(P),'--authorize-run','--plan-sha256',PLAN_SHA,
        '--parent-review','UNRESOLVED_PARENT_REVIEW_JSON','--parent-review-sha256','UNRESOLVED_PARENT_REVIEW_SHA256'],
        'Worker direct command differs')
    unit='ara-gather-e8m4-vi31-prefix66-m6-01.service'
    service=['systemd-run','--user','--unit='+unit,'--property=RuntimeMaxSec=6600',
        '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(WORKER),
        '--property=StandardOutput=append:'+str(P/'service.log'),
        '--property=StandardError=append:'+str(P/'service.log'),*command]
    require(plan['unit']==unit and shlex.split(launch['service_command'])==service,'Actual systemd command differs')
    dry=read(P/'dryrun_gate.json')
    require(dry['status']=='DRYRUN_ONLY_NO_DUT' and dry['plan_sha256']==PLAN_SHA and
            dry['jobs']==1 and dry['cases']==[case['id']] and dry['VCS_started'] is False and
            dry['build_invoked'] is False,'Actual dryrun gate differs')
    for name,digest in dry['evidence_pins'].items():
        require(sha(Path(name))==digest,'Dryrun evidence pin differs: '+name)
    dryroot=P/'dryrun/tests'/case['id']
    drycommand=read(dryroot/'command.json')
    require(drycommand==dict(command=[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1',
        '+PRELOAD='+case['elf'],'+TESTCASE='+case['id'],'+NO_FSDB',
        '+COMMIT_TRACE='+str(dryroot/'commit_trace.csv')],cwd=str(dryroot/'work')),'Actual dryrun command differs')
    drysummary=read(P/'dryrun/summary.json')
    require(len(drysummary)==1 and drysummary[0]['name']==case['id'] and
            drysummary[0]['status']=='DRY_RUN' and drysummary[0]['returncode'] is None,'Actual dryrun result differs')
    require(not any((dryroot/n).exists() for n in ('console.log','commit_trace.csv','work/run.vcs.log')),
            'Dryrun has simulator evidence')
    require(sha(P/'plan.json')==PLAN_SHA,'Plan changed during review')
    output=dict(status='APPROVED_ENTRY_PLAN_NOT_DUT_OR_LAUNCH_AUTHORIZATION',decision='ALLOW_PARENT_AUTHORIZATION',
        plan_path=str(P/'plan.json'),plan_sha256=PLAN_SHA,unit=unit,plan_pins_verified=744,
        host_report_sha256=sha(WORKER/'host03.json'),host_tests=55,host_failures=0,host_errors=0,
        readiness_sha256=plan['reference_ready_sha256'],independent_audit_sha256=plan['independent_audit_sha256'],
        independent_review_sha256=plan['independent_review_sha256'],independent_execution_sha256=plan['independent_execution_sha256'],
        image_sha256=plan['image_sha256'],snapshot_sha256=plan['snapshot_sha256'],
        source_label=case['original_name'],runtime_id=case['id'],soc_elf_sha256=case['sha256'],
        jobs=1,case_budget_s=5400,outer_budget_s=6600,scope=dict(calls=66,predecessors=65,capacity=512,
        physical_predicate_bytes=128,logical_mask_bytes=64,setup_values=2178,setup_bytes=2690,
        fullcap_results=33792,guards=132,helper_instructions=858),
        earlier_entry_blockers_resolved=True,new_blockers=[],parent_authorization_pending=True,
        parent_authorization_contract=dict(decision='AUTHORIZE_E8M4_VI31_PREFIX66_M6_ONCE',plan_sha256=PLAN_SHA,
            unit=unit,budget_risk_accepted=True,reference_ready_sha256=plan['reference_ready_sha256'],
            independent_audit_sha256=plan['independent_audit_sha256']),
        no_Host_reference_DUT_runs=True,reference_raw_reparsed=False,no_live_process_or_service_query=True,
        original_or_producer_inputs_edited=False,unknown_historical_stall_closed=False,full_child_accepted=False,
        reviewed_artifacts={str(p):sha(p) for p in [P/'plan.json',P/'ready.json',P/'dryrun_gate.json',
            WORKER/'replay.py',WORKER/'checker.py',WORKER/'newscope.py',WORKER/'test_host.py',WORKER/'host03.json']})
    with (OUT/'audit.json').open('x') as stream:
        json.dump(output,stream,indent=2);stream.write('\n')
    print(output['status'],'PLAN_SHA='+PLAN_SHA,'AUDIT_SHA='+sha(OUT/'audit.json'))


if __name__=='__main__':
    main()
