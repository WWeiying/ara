"""Explicit actual Hilbert terminal schema, not a Boolean attestation."""
from pathlib import Path
import checker as c
REPORT=c.HERE.parent/'full_e16_m2_source_review01/REFERENCE_TERMINAL_REVIEW01.json'
REPORT_SHA='608be8817853052b1aa11086248b6f16ddf1a4c8ae46dd07a6aa1c968be85919'
def validate(report,ready,result,execution,audit,preflight):
    c.require(report['status']=='ACCEPTED_REFERENCE_TERMINAL_METADATA_ONLY_NOT_DUT' and report['accepted'] is True and
        report['READY_sha256']==c.READY_SHA and report['entry_sha256']==ready['entry_sha256'] and
        report['result_sha256']==ready['reference_sha256'] and
        report['execution_sha256']==ready['actual_reference_execution_sha256'] and
        report['audit_execution_sha256']==ready['actual_audit_execution_sha256'] and
        report['fresh_input_pins']==len(preflight) and report['pin_drift']==[],
        'Actual independent terminal payload identity')
    for key,actual in (('actual_reference_wait',execution),('actual_audit_wait',audit)):
        claimed=report[key]
        c.require(type(claimed['returncode'])is int and claimed['returncode']==actual['actual_wait_returncode']==0 and
            claimed['elapsed_s']==actual['elapsed_s'] and claimed['timed_out']==actual['timed_out']==False and
            claimed['retries']==actual['retries']==0,'Actual independent numeric provenance')
    scope=report['scope']
    c.require([scope[k] for k in ('calls','results','guards','returned_vstart','helper_instructions','packed_reads',
        'mask_groups','seed_scalar_writes')]==[4095,524160,8190,4095,53235,135135,1575,1104] and
        scope['helper_instruction_counts']==result['helper_instruction_counts']==[4095]*13,
        'Actual independent full source scope')
    c.require([scope[k] for k in ('SEW','LMUL','CAP','vtype','output_bytes','tail_bytes',
        'observed_register_bytes','vlm_bytes','physical_registers')]==[16,'m2',128,9,260,4,256,16,2],
        'Actual typed16 physical/output/predicate scope')
    counts=report['counts']
    c.require(counts['firmware_to_HTIF']==result['firmware_to_HTIF']==ready['firmware']==1072555 and
        counts['boot']==result['boot']==5 and counts['park']==result['post_HTIF_park_rows'] and
        counts['whole_raw']==result['whole_raw_rows'] and
        counts['whole_raw']==counts['firmware_to_HTIF']+counts['boot']+counts['park'] and
        counts['EOF_checked'] is True and result['EOF_checked'] is True and
        result['pins_pre_post_unchanged'] is True and result['raw_parse_count']==1,
        'Actual independent EOF and full raw boundary counts')
    raw=report['raw_evidence']
    c.require(raw['producer_sha256']==result['raw_sha256'] and raw['producer_bytes']==result['raw_bytes'] and
        raw['reviewer_raw_reads']==raw['reviewer_semantic_parses']==0 and
        report['DUT_acceptance'] is False and report['worker_entry_admission'] is False and
        report['Linux_stall_closed'] is False,'Qualified source acceptance, not DUT/worker permission')
def verify(binding,ready):
    path=Path(binding['path'])
    c.require(path==REPORT and binding['sha256']==REPORT_SHA and c.sha(path)==REPORT_SHA and
        binding['READY_sha256']==c.READY_SHA,'Exact actual terminal report')
    report=c.read(path);root=c.REF/'reference01';preflight=c.read(root/'preflight_pins.json')
    c.require(report['preflight_pins_sha256']==c.sha(root/'preflight_pins.json'),'Actual preflight ledger binding')
    validate(report,ready,c.read(root/'result.json'),c.read(root/'execution.json'),c.read(root/'audit_execution.json'),preflight)
    c.common.base.verify_pins(preflight)
