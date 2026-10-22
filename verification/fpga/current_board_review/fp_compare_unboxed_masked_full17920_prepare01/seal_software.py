"""Metadata-only software artifact seal, not reference/DUT admission."""
import json
from pathlib import Path
from prepare import HERE, OLD, PARENT, ASSEMBLY, sha, save
import host_adapter

assert not (HERE/'SOFTWARE_READY.json').exists()
assert host_adapter.build()==(HERE/'build01/host/host.c').read_text()
original=(HERE/'source/original/parent.c').read_text()
baseline=(HERE/'source/original_host.c').read_text()
body=original[original.index('void probe_main('):original.index('__asm__(".global _start')]
actual=baseline[baseline.index('void original_probe_main('):baseline.index('\nvoid *original_area(')]
assert actual.strip()==body.replace('void probe_main(','void original_probe_main(',1).strip()
host=json.loads((HERE/'finish01/HOST_RESULT.json').read_text())
assert host['status']=='FULL_ORIGINAL_C_EQ_HOST_AND_UBTRAP_PASS'
cost=json.loads((HERE/'linked01/RESULT.json').read_text())
assert cost['status']=='STATIC_COST_GATE_PASS_PENDING_REFERENCE_ADMISSION'
paths=list(HERE.glob('*.py'))
for directory in ('source','build01','finish01','linked01'):
    paths += [p for p in (HERE/directory).rglob('*') if p.is_file()]
paths += [HERE/'source_status.json',HERE/'model.json',HERE/'helper_identity.json',
    OLD/'prepare_source.py',OLD/'packed_core.h',OLD/'compile01/execute.py',
    OLD/'compile01/host.c',OLD/'compile01/inspect_linked.py',
    OLD/'source_model02/helper_identity.json',PARENT,ASSEMBLY]
pins={str(p.resolve()):sha(p) for p in paths}
for origin in ('source_status.json','build01/inputs_before.json','finish01/inputs_before.json','linked01/inputs_before.json'):
    data=json.loads((HERE/origin).read_text())
    previous=data['pins'] if origin=='source_status.json' else data
    for path,digest in previous.items():
        assert sha(path)==digest,'Actual input drift '+path
        if str(Path(path).resolve()) in pins:
            assert pins[str(Path(path).resolve())]==digest
        pins[str(Path(path).resolve())]=digest
for backend in ('soc','spike'):
    wait=json.loads((HERE/'build01'/backend/'compile.wait.json').read_text())
    assert wait['actual_wait_exit']==0 and not wait['timed_out']
save(HERE/'SOFTWARE_READY.json',dict(status='MASKED_FULL17920_SOFTWARE_COMPILED_COST_PASS_REFERENCE_NOT_RUN',
    historical_parent='rvv_fp_compare_unboxed_e16_mf4',original_elf_sha256=sha(PARENT),
    defines=dict(SEW=16,UNMASKED_COMPARISONS=0,UNBOXED_COMPARISONS=1,RESTART_COMPARISONS=0,DESTINATION_KIND=0),
    calls=17920,result_bits=286720,guards=35840,flags=17920,vstarts=17920,
    records=8960,record_bytes=71680,full_original_C_body_preserved_in_Host=True,
    native_original_C_full_pairs=6,UBtrap_full_pairs=2,targeted_Host_rejects=5,
    masked_static_helper_encodings=185,dynamic_helpers=326144,fresh_stores=734720,
    output_LWU=17920,mode_record_LD=8960,FP_committed_payload_calls_required=10752,
    necessary_memory_owners=89600,necessary_VL_nonzero_targets=15360,VL0_optional_targets=2560,
    backends=cost['backends'],pin_count=len(pins),pins=pins,
    prior_UBSan_missing_runtime_failure_preserved=True,compiled_backend_attempts=dict(soc=1,spike=1),
    firmware_count_measured=False,reference_executed=False,DUT_executed=False,
    next_gate='Independent artifact review and parent approval of one bounded full reference; no VCS permission'))
print('SOFTWARE_READY',sha(HERE/'SOFTWARE_READY.json'),'pins',len(pins),flush=True)
