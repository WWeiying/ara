"""Bind original terminal plus the focused capacity supplement; no raw IO."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;R=HERE.parent
sys.path.insert(0,str(R))
from context import read,sha,require
from reference02 import durable,verify
pre=read(HERE/'preflight.json');verify(pre['pins'])
post=read(HERE/'postflight.json')
require(pre['pins']==post['pins'] and pre['raw_stat']==post['raw_stat'],'Original raw stat and pin chain')
host=read(HERE/'HOST.json');execution=read(HERE/'host_execution.json')
require(host['positive']==1 and host['negatives']==19 and execution['actual_wait_returncode']==0
    and not execution['timed_out'],'Actual small parse and negative Host child')
require(read(HERE/'host_preflight.json')==read(HERE/'host_postflight.json'),'Small Host pins')
pins=dict(pre['pins'])
for p in HERE.iterdir():
    if p.is_file() and p.name!='READY.json':pins[str(p)]=sha(p)
durable(HERE/'READY.json',dict(status='CAPACITY_SUPPLEMENT_READY_COMBINED_INDEPENDENT_REVIEW_PENDING',
    pins=pins,original_READY_sha256=sha(R/'READY.json'),
    original_result_sha256=sha(R/'reference01/result.json'),supplement_result_sha256=sha(HERE/'result.json'),
    focused_rg_execution_sha256=sha(HERE/'execution.json'),small_parser_Host_execution_sha256=sha(HERE/'host_execution.json'),
    raw_hash_inherited_not_recomputed=pre['inherited_raw_sha256'],
    original_capacity_gap_preserved=True,firmware_gate='firmware_to_HTIF<=3000000',
    firmware_to_HTIF=2540955,reference_attempts=1,focused_native_rg_scans=1,full_raw_numeric_parses=1,
    calls=4095,results=2096640,guards=8190,packed_output_reads=528255,helper_instructions=53235,
    typed_output_bytes=1028,capacity_instruction_counts=[1,1,1],VTYPE=11,VL=512,DUT_runs=0,
    final_independent_acceptance=False))
print('SUPPLEMENT_READY',sha(HERE/'READY.json'),len(pins))
