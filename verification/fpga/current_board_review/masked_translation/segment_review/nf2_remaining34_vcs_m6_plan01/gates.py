"""Fail-closed terminal prerequisites. Prepare never reads the running pilot."""
from pathlib import Path
from checker import HERE,REF,READY_SHA,IMAGE_SHA,read,sha,require,common

PILOT=HERE.parent/'nf2_remaining4_01/prepared01'
PILOT_PLAN='7a644bfd57e314649a92a6512cd6c994c49f7e9b656f0caaa5e172ec0e4d9c55'
PILOT_ELF='cd2aa14f5251bf32353bf256b5c64e9035dc0ed266688bece78f7c691ac234d2'
PILOT_IDS=['u0_s0_b1_m2_f1','u1_s1_b3_m2_f0','u0_s1_b5_m3_f1','u1_s0_b1_m3_f0']
PILOT_NAME='nf2_remaining4_sv39'
PILOT_AUDIT_STATUS='INDEPENDENT_M6_NF2_FOUR_SOURCE_CASES_ACCEPTED_NOT_LINUX'
PILOT_PASS='PASS_M6_NF2_REMAINING4_SV39_NOT_LINUX'
PILOT_CONTRACT=dict(plan_sha256=PILOT_PLAN,elf_sha256=PILOT_ELF,image_sha256=IMAGE_SHA,
                    required_status=PILOT_AUDIT_STATUS,required_cases=PILOT_IDS,
                    actual_persisted_numeric_rc_required=True,checked_only_at_authorized_run=True)

def numeric_zero(value):return type(value) is int and value==0

def pilot_fields(audit,complete,run,child):
    require(audit['status']==PILOT_AUDIT_STATUS and audit['accepted'] is True and
            audit['cases']==PILOT_IDS and audit['plan_sha256']==PILOT_PLAN and
            audit['elf_sha256']==PILOT_ELF and audit['image_sha256']==IMAGE_SHA and
            audit['pins_pre_post_unchanged'] is True and audit['raw_logs_firsterror_veto_pass'] is True,
            'Exact independent pilot acceptance required')
    require(complete['status']==PILOT_PASS and complete['plan_sha256']==PILOT_PLAN and
            complete['aborted'] is False and complete['pins_unchanged'] is True and
            numeric_zero(complete['retries']) and not complete.get('error') and len(complete['results'])==1,
            'Pilot actual terminal/noabort, not console-only or recovered metadata')
    r=complete['results'][0]
    require(r['name']==PILOT_NAME and r['status']=='PASS' and numeric_zero(r['returncode']) and
            0<r['elapsed_s']<=6300 and not r['reason'],'Pilot persisted result numeric0')
    require(run['status']=='COMPLETE' and run['tests']==[PILOT_NAME] and run['status_counts']=={'PASS':1}
            and run['jobs']==1 and run['timeout_s']==6300 and run['completed_at'], 'Pilot runner COMPLETE')
    require(child['schema']=='UNVALIDATED_CHILD_OUTCOME_V1' and child['architectural_acceptance'] is False and
            all(child[k]==r[k] for k in ('name','status','returncode','elapsed_s','reason','artifact_dir')) and
            numeric_zero(child['returncode']) and not child.get('command_read_error'),
            'Pilot actual durable child outcome, not control-flow implied returncode')
    require(audit['child_outcome']==child and numeric_zero(audit['child_returncode']) and
            audit['strict']['status']=='NF2_CSV_ORACLE_PASS' and audit['strict']['cases']==list(range(4)),
            'Pilot independent raw/strict child binding')

def pilot_gate(path,digest):
    require(path and digest and sha(path)==digest,'Pinned actual pilot audit required; never wait/poll')
    require(path.parent.parent==HERE.parent/'nf2_remaining4_terminal_audit01',
            'Actual original pilot auditor result directory required')
    audit=read(path);complete=read(PILOT/'complete.json');run=read(PILOT/'replay/run.json')
    root=PILOT/'replay/tests'/PILOT_NAME
    child=read(root/'child_outcome.unvalidated.json')
    pilot_fields(audit,complete,run,child)
    require(sha(PILOT/'plan.json')==PILOT_PLAN and sha(PILOT/'complete.json')==audit['complete_sha256'] and
            complete['results']==read(PILOT/'replay/summary.json'),'Pilot real file identity/summary')
    pins=read(path.with_name('verified_pins.json'))
    for p in (PILOT/'complete.json',root/'child_outcome.unvalidated.json',root/'commit_trace.csv',
              root/'command.json',root/'input.elf'):
        require(pins.get(str(p))==sha(p),'Pilot independent raw pin absent/drift: '+str(p))
    require(child['command_sha256']==sha(root/'command.json') and child['command']==read(root/'command.json') and
            read(root/'strict_prefix.json')['child_outcome_sha256']==sha(root/'child_outcome.unvalidated.json'),
            'Pilot child command/strict report binding')
    pins.update(complete['evidence_pins']);common.base.verify_pins(pins)
    pins.update({str(path):digest,str(path.with_name('verified_pins.json')):sha(path.with_name('verified_pins.json'))})
    return pins

REFERENCE_AUDIT=HERE.parent/'nf2_remaining34_reference_audit01'
REFERENCE_AUDIT_SHA='e5db50970a48445a7ff8f65c6ca3a457fc47dbdc7216cd65ec1202e691c7e478'
REFERENCE_REVIEW_SHA='e418fcbf76d581738ef08aeec87ca758cf3458238e6836bfc3dc59bb04ea823e'

def reference_fields(audit,ready):
    require(audit['schema']=='nf2_remaining34_independent_reference_audit_v1' and
            audit['status']=='ACCEPTED_REFERENCE34_NOT_DUT' and audit['READY_sha256']==READY_SHA and
            audit['nonraw_pins_pre_post_equal'] is True and audit['reference_only'] is True and
            audit['DUT_started'] is False and audit['PASS40'] is False and audit['blockers']==[],
            'Actual independent reference-only acceptance')
    require(len(audit['groups'])==len(ready['groups'])==9,'All nine reference groups required')
    for a,g in zip(audit['groups'],ready['groups']):
        require(a['id']==g['id'] and a['status']=='REFERENCE_ACCEPTED' and
                a['commits']==g['parsed_spike_records'] and a['checks']==g['checks'] and
                a['soc_elf_sha256']==g['soc_elf']['sha256'],'Independent group/ELF/count mismatch')

def accepted_reference():
    require(REFERENCE_REVIEW_SHA and sha(REFERENCE_AUDIT/'REVIEW.md')==REFERENCE_REVIEW_SHA and
            sha(REFERENCE_AUDIT/'audit.json')==REFERENCE_AUDIT_SHA,'Final independent REVIEW/audit pins required')
    audit=read(REFERENCE_AUDIT/'audit.json');ready=read(REF/'READY.json')
    reference_fields(audit,ready)
    pins={str(REFERENCE_AUDIT/'REVIEW.md'):REFERENCE_REVIEW_SHA,str(REFERENCE_AUDIT/'audit.json'):REFERENCE_AUDIT_SHA,
          str(REFERENCE_AUDIT/'REVIEW.json'):'c42c213c70756661f13ee27ce1192c918dd6f9093f40e26214e23afce1c4c514',
          str(REFERENCE_AUDIT/'source_audit.json'):audit['source_audit_sha256'],
          str(REFERENCE_AUDIT/'audit.py'):audit['audit_script_sha256'],
          str(REFERENCE_AUDIT/'pins_pre.json'):audit['pins_sha256']}
    pins.update({str(REFERENCE_AUDIT/(g['id']+'.json')):g['audit_sha256'] for g in audit['groups']})
    common.base.verify_pins(pins)
    expected={**ready['pins'],str(REF/'READY.json'):READY_SHA}
    require(read(REFERENCE_AUDIT/'pins_pre.json')['pins']==expected and audit['pins_count']==len(expected),
            'Independent full source/reference pin set mismatch')
    source=read(REFERENCE_AUDIT/'source_audit.json')
    require(source['status']=='SOURCE34_VERIFIED' and source['count']==34 and
            [c['id'] for c in source['cases']]==[c for g in ready['groups'] for c in g['cases']],
            'Independent source membership/order')
    return pins
