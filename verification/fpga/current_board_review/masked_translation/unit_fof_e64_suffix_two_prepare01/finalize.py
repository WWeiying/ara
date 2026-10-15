"""Freeze completed software evidence only; cannot run a simulator."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import prepare as p

H=Path(__file__).resolve().parent
p.require(not (H/'READY.json').exists() and not (H/'input_pins.json').exists(),'Fresh finalization only')
binding=p.read(H/'M9_BINDING.json')
pins=dict(binding['pins'])
cases=[]
for stage in ('build','host','reference1','reference2'):
    receipt=p.read(H/(stage+'.wait.json'))
    p.require(type(receipt['actual_outer_wait_returncode']) is int and receipt['actual_outer_wait_returncode']==0,
              'Actual software outer wait '+stage)
host=p.read(H/'host01.json')
p.require(type(host['actual_wait_returncode']) is int and host['actual_wait_returncode']==0,'Actual Host rc')
p.require('Ran 14 tests' in (H/'host01.log').read_text() and (H/'host01.log').read_text().endswith('OK\n'),'Host14 receipt')
for i in (1,2):
    ref=H/f'reference_scenario{i}_01'
    sw=H/'software01'/f'scenario{i}'
    status=p.read(ref/'status.json')
    execution=p.read(ref/'execution.json')
    source=p.read(sw/'source_proof.json')
    for path in (sw/'input_pins.json',ref/'input_pins.json'):
        for name,digest in p.read(path).items():
            p.require(name not in pins or pins[name]==digest,'Conflicting evidence pin')
            pins[name]=digest
    p.require(status['status']=='REFERENCE_CHECKER_PASS_NOT_DUT' and status['pins_unchanged'] is True,'Reference status')
    p.require(type(execution['actual_wait_returncode']) is int and execution['actual_wait_returncode']==0
              and execution['timeout'] is False,'Actual numeric reference child wait')
    p.require(status['scenario']==i and status['commits']<=800000 and status['boot_commits']==5
              and status['htif']==[1] and status['scalar_checks']==5481,'Complete bounded reference')
    p.require(status['allowed_undefined_output_indices']==[] and status['output_checked_elements']==130
              and status['original_result_elements']==8,'Unreduced oracle')
    p.require(status['raw_sha256']==p.sha(ref/'spike.trace'),'Actual raw identity')
    p.require(not (ref/'not_completed.json').exists(),'No unresolved reference failure')
    cases.append(dict(id=p.CASES[i]['name'],scenario=i,sew=64,vl=8,vstart=0,mask_bytes=[15]+[0]*15,
        original_elf=p.CASES[i]['elf'],source_proof=str(sw/'source_proof.json'),
        soc_elf=source['backend']['soc']['elf'],soc_sha256=source['backend']['soc']['sha256'],
        spike_elf=source['backend']['spike']['elf'],spike_sha256=source['backend']['spike']['sha256'],
        soc_spec=str(sw/'soc.spec.json'),reference_status=str(ref/'status.json'),
        actual_records=status['commits'],firmware_through_htif=status['firmware_to_htif'],
        boot_records=status['boot_commits'],park_records=status['postexit_park'],
        scalar_checks=status['scalar_checks'],spike_seconds=execution['elapsed_s'],
        estimated_dut_seconds_at_273_per_s_plus20pct=status['commits']/273*1.2,
        original_result=[11,48,85,122,91,91,91,91],guards=[91,91],
        original_helper_instructions=11,capacity_instructions=3,undefined_output_exemptions=[]))
# Seal reuse provenance as well as executable imports and local outputs.
old=H.parent/'fof_original_two_singles01'
for path in (old/'fixture.c',old/'fixture.S',old/'fixture.h',old/'prepare.py',
             old/'recovery01/observer.py',H.parent/'fof_two_singles_vcs_m6_plan01/csv_check.py'):
    pins[str(path)]=p.sha(path)
for path in sorted(H.rglob('*')):
    if path.is_file():
        p.require('__pycache__' not in path.parts,'Unexpected mutable module cache')
        name=str(path);digest=p.sha(path)
        p.require(name not in pins or pins[name]==digest,'Prepared evidence changed')
        pins[name]=digest
p.verify(pins)
p.save(H/'input_pins.json',pins)
ready=dict(schema='UNIT_FOF_E64_SUFFIX_REFERENCE_READY_V1',
    status='HOST14_REFERENCE2_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT',
    original_cases=2,host_tests=14,cases=cases,image=binding['image'],image_sha256=binding['image_sha256'],
    image_pin_count=len(binding['pins']),all_pin_count=len(pins),
    input_pins=str(H/'input_pins.json'),input_pins_sha256=p.sha(H/'input_pins.json'),
    report=str(H/'REPORT.md'),report_sha256=p.sha(H/'REPORT.md'),
    frozen_image_only=True,DUT_launched=False,DUT_accepted=False,independent_review='PENDING_TESLA',
    reference_budget_records=800000,reference_budget_includes_boot_and_park=True,
    isa=p.ISA,ISA_argument_preserved=True,
    spike_exit='Actual HTIF store 1, child numeric0, parser outer numeric0',
    soc_exit='Actual ELF has no tohost; sd encoding00a2b023 PC80000072 to CTRLd0000000 value0',
    SoC_CSV_tests='Host artificial scalar rows with actual new SoC specs; no actual DUT trace yet',
    Linux_ABI_equivalence=False,parent_full_matrix_closed=False,
    required_before_DUT=['Tesla independent read-only approval','Parent launch authorization',
                         'Pinned replay worker with numeric child/abort/retry/raw failure veto gates'])
p.save(H/'READY.json',ready)
print(json.dumps(dict(status=ready['status'],ready_sha256=p.sha(H/'READY.json'),
                     pins_sha256=ready['input_pins_sha256'],report_sha256=ready['report_sha256'],
                     all_pin_count=len(pins)),indent=2))
