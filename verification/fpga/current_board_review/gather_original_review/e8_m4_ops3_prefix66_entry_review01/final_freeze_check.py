#!/usr/bin/env python3
"""Final frozen metadata/pin check; reuse accepted raw identity without rereading raw."""
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
G=OUT.parent
W=G/'e8_m4_ops3_prefix66_vcs_m6_plan01'
P=W/'prepared01'
REF=G/'e8_m4_ops3_prefix66_prepare01'
A=G/'e8_m4_ops3_prefix66_reference_audit01'


def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            result.update(chunk)
    return result.hexdigest()


def require(value,message):
    if not value:
        raise ValueError(message)


def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')


def main():
    require(not (OUT/'decision02.json').exists() and not (OUT/'verified_input_pins02.json').exists(),
            'Exclusive final metadata review only')
    expected={'plan.json':'5de3a259e330825548009fbe17a4f80da34c3a6b816b495a695564621ea4ddbb',
        'ready.json':'bd3cb160c92ba1869819f2f8effa25a584975eaaefa61861e9ba43777d4625e4',
        'dryrun_gate.json':'af64e76213337a0a4e89b767fe3dd08ce501e9ba0ec0182cf786766f3b0f9742'}
    for name,digest in expected.items():
        require(sha(P/name)==digest,'Supplied final metadata changed: '+name)
    host_sha='21ae2b05eec4da2ffbc3cf5c3443246e84a09c928b710e7ff4f929b2fe0813b0'
    require(sha(W/'host03.json')==host_sha,'Final Host03 changed')
    prior=json.loads((OUT/'audit.json').read_text())
    require(sha(OUT/'audit.json')=='1e4225433ee76362e8d2d82558641251766462ed0ac11c7e15ab3439ad20a7b3'
            and prior['plan_sha256']==expected['plan.json'] and prior['plan_pins_verified']==744,
            'Previous complete entry/pin audit changed')
    for name,digest in prior['reviewed_artifacts'].items():
        require(sha(Path(name))==digest,'Entry-reviewed code/metadata changed: '+name)
    plan=json.loads((P/'plan.json').read_text())
    independent=json.loads((A/'audit.json').read_text())
    require(sha(A/'audit.json')==prior['independent_audit_sha256'],'Independent accepted audit changed')
    raw=REF/'reference/commits.log'
    checked=0
    for name,digest in plan['pins'].items():
        path=Path(name)
        if path==raw:
            require(digest==independent['raw_sha256'],'Retained raw pin linkage changed')
            stat=path.stat()
            current=[stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]
            require(current==independent['raw_stat'],'Frozen accepted raw stat changed; no raw reread')
        else:
            require(sha(path)==digest,'Final non-raw input pin drift: '+name)
            checked+=1
    require(checked==743 and len(plan['pins'])==744,'Final pin coverage differs')
    require(sha(P/'plan.json')==expected['plan.json'],'Disk plan changed during final review')
    save(OUT/'verified_input_pins02.json',plan['pins'])
    decision=dict(status='ACCEPTED_PREPARED_ENTRY_PLAN_ONLY_NOT_DUT',
        decision='ACCEPT_PREPARED_PLAN_FOR_PARENT_AUTHORIZATION',new_blockers=[],
        plan_path=str(P/'plan.json'),plan_sha256=expected['plan.json'],
        ready_sha256=expected['ready.json'],dryrun_gate_sha256=expected['dryrun_gate.json'],
        host03_sha256=host_sha,host_tests=55,host_failures=0,host_errors=0,
        verified_input_pins_path=str(OUT/'verified_input_pins02.json'),
        verified_input_pins_sha256=sha(OUT/'verified_input_pins02.json'),plan_pins=744,
        current_non_raw_pins_hashed=743,raw_pins_reused=1,raw_content_read_this_review=False,
        raw_reuse=dict(previous_full_entry_audit_sha256=sha(OUT/'audit.json'),
                      accepted_independent_raw_sha256=independent['raw_sha256'],
                      unchanged_device_inode_size_mtime_ctime=True),
        unit=plan['unit'],jobs=1,case_timeout_s=5400,outer_timeout_s=6600,reserved_slots=0,
        direct_worker_owner_contract_reviewed=True,runtime_resource_admission_still_required=True,
        runtime_MainPID_cgroup_not_queried_or_preclaimed=True,
        source_label=prior['source_label'],runtime_id=prior['runtime_id'],scope=prior['scope'],
        reference_ready_sha256=plan['reference_ready_sha256'],
        independent_audit_sha256=plan['independent_audit_sha256'],
        independent_review_sha256=plan['independent_review_sha256'],
        independent_execution_sha256=plan['independent_execution_sha256'],
        original_parent_gate_compatible=True,parent_authorization_still_required=True,
        expected_parent_authorization_fields=prior['parent_authorization_contract'],
        entry_report_sha256=sha(OUT/'REPORT.md'),worker_sha256=sha(W/'replay.py'),
        checker_sha256=sha(W/'checker.py'),DUT_PASS_claim=False,DUT_or_Host_or_reference_started=False,
        producer_or_old_sealed_inputs_edited=False,unknown_stall_closed=False,full_child_accepted=False)
    save(OUT/'decision02.json',decision)
    print(decision['status'],'DECISION_SHA='+sha(OUT/'decision02.json'),
          'VERIFIED_PINS_SHA='+decision['verified_input_pins_sha256'])


if __name__=='__main__':
    main()
