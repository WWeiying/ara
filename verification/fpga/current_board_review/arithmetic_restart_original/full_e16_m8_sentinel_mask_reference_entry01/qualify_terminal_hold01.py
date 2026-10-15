"""Metadata-only qualification; original READY remains unchanged."""
from context import *
from reference02 import verify,durable
folder=HERE/'reference01'
verify(read(folder/'preflight_pins.json'))
ready=read(HERE/'READY.json');result=read(folder/'result.json')
require(ready['reference_sha256']==sha(folder/'result.json'),'Original terminal result pin')
require(ready['actual_reference_rc']==ready['actual_audit_rc']==0 and result['firmware_to_HTIF']<=3000000,
    'Actual original successful reference and cost')
durable(HERE/'TERMINAL_QUALIFICATION_HOLD01.json',dict(
    status='HOLD_CAPACITY3_DYNAMIC_CONTINUITY_NOT_YET_CHECKED',original_READY_preserved=True,
    original_READY_sha256=sha(HERE/'READY.json'),reference_result_sha256=sha(folder/'result.json'),
    actual_reference_execution_sha256=sha(folder/'execution.json'),
    actual_audit_execution_sha256=sha(folder/'audit_execution.json'),
    firmware_to_HTIF=result['firmware_to_HTIF'],calls=result['calls'],results=result['results'],
    guards=result['guards'],vstart_zero=result['vstart_zero'],packed_output_reads=result['packed_output_reads'],
    actual_reference=read(folder/'execution.json'),actual_audit=read(folder/'audit_execution.json'),
    missing_gate='capacity PC0/1/2 contiguous once, actual rd and VL/VTYPE context; original checks only PC1 rd512',
    raw_sha256_from_original_audit=result['raw_sha256'],raw_rehashed_or_reparsed=False,
    gold_ID_reads_claim='109575 is static positive CFG evidence only, not dynamic audit count',
    current_pins_unchanged=True,reference_attempts=1,DUT_runs=0,
    final_independent_acceptance=False,no_Spike_retry=True))
print('QUALIFICATION_HOLD',sha(HERE/'TERMINAL_QUALIFICATION_HOLD01.json'),
    'original_READY',sha(HERE/'READY.json'))
