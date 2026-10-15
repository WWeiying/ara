"""Seal completed software/reference evidence; never executes an ELF or raw parser."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
from prepare import HERE,read,save,sha,require

root=HERE/'rvv_matrix_e16_mf4';ref=root/'reference01'
require(sha(HERE/'bound.json')=='7d1aff0edd00c583e6214b78b44eb3b1d8ba5a910a7f2de6056c9566255f6938','Frozen bound')
b=read(HERE/'bound.json');proof=read(root/'sourceproof.json')
for path,digest in b['pins'].items():require(sha(path)==digest,'Input drift '+path)
execution=read(ref/'execution.json');audit=read(ref/'audit_process_exit.json');report=read(ref/'reference.json')
require(type(execution['returncode']) is int and execution['returncode']==0 and not execution['timeout'] and
        execution['elapsed_s']<=120 and type(audit['returncode']) is int and audit['returncode']==0 and
        not audit['timeout'] and audit['elapsed_s']<=600,'Actual bounded process exits')
require(not (ref/'not_completed.json').exists() and report['status']=='FULL_ORIGINAL_REFERENCE_PASS_NOT_DUT' and
        report['source_full_order'] and not report['partitioned'] and report['full_raw_parses']==1 and
        [report[k] for k in ('calls','results','guards','vstart_checks','helper_instructions')]==[4095,65520,8190,4095,53235],
        'Complete authentic reference required')
require(proof['original_sha256']=='e538572bcf13bd7338647f5a7e5b7bfc8627f1ee04598d8fb0283a76926b998c' and
        proof['backends']['soc']['sha256']=='509e072989f6e661ec1fcf899c9ea944b43f29f643960032928f9d723505a5b6' and
        proof['backends']['spike']['sha256']=='a6c082ecbc312d33be27c9c5374023113c9d1c811ae681f1a62d3d50a9d02430',
        'Original and exact runtime ELF identities')
pins=dict(b['pins']);pins[str(HERE/'bound.json')]=sha(HERE/'bound.json')
for path in ref.iterdir():
    if path.name=='commits.log':
        require(path.stat().st_size==report['raw_bytes']==execution['raw_bytes'],'Raw size binding')
        pins[str(path)]=report['raw_sha256']
    elif path.is_file():pins[str(path)]=sha(path)
pins[str(Path(__file__).resolve())]=sha(Path(__file__).resolve())
slow=5922683/10026.130593086127
projected=report['firmware_through_htif']/slow*1.2
require(projected<10800,'Measured-rate projection exceeds original fixed budget')
save(HERE/'READY.json',dict(status='FULL_ORIGINAL_E16_MF4_REFERENCE_PASS_NOT_DUT_PENDING_INDEPENDENT_REVIEW',
     shape='rvv_matrix_e16_mf4',source_C_text_recovered=False,binary_equivalent_original_reconstruction=True,
     original_linux_sha256=proof['original_sha256'],soc_sha256=proof['backends']['soc']['sha256'],
     spike_sha256=proof['backends']['spike']['sha256'],totals=dict(calls=4095,results=65520,guards=8190,vstart_checks=4095),
     helper_instructions=53235,operations=25,seeds=3,cap=16,vlenb=128,physical_mask_bytes=128,
     actual_Spike_execution=execution,actual_full_reference_audit_exit=audit,
     full_raw_parses=1,reference_retries=0,reference_report_sha256=sha(ref/'reference.json'),
     evidence_pins=pins,software_host_positive=1,software_host_negative=8,BSS_gate_negative=11,
     firmware_through_htif=report['firmware_through_htif'],
     cost=dict(measured_M6_e32_firmware_per_second=slow,reference_instructions=report['firmware_through_htif'],
               projected_M6_with20percent_s=projected,simulator_limit_s=10800,worker_limit_s=12000,
               service_limit_s=13200,projection_not_measured_e16_runtime=True,completion_guaranteed=False),
     DUT_runs=0,new_RTL_image_builds=0,independent_review_pending=True))
print('READY_SHA',sha(HERE/'READY.json'),'PINS',len(pins),'PROJECTED_S',projected,flush=True)
