"""Freeze actual new entry only; does not launch or regenerate the oracle."""
from context import *
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
symbols,code,helpers,machine=artifacts()
profile=read(HERE/'PROFILE.json')
host=read(HERE/'HOST02.json');receipt=read(HERE/'host02_execution.json')
require(host['status']=='PASS_SHORT_HOST_NOT_FULLSTREAM' and host['tests']==18 and host['errors']==host['failures']==0,'Short exact successor Host')
require(receipt['actual_wait_returncode']==0 and not receipt['timed_out'],'Actual short Host wait0')
require(read(HERE/'host02_preflight.json')==read(HERE/'host02_postflight.json'),'Actual short Host pins')
require(profile['elf_sha256']==ELF_SHA and [len(p['events']) for p in profile['seed_profiles']]==[2944]*3,'Actual complete seed store profiles')
require(len(profile['initializer'])==129 and sorted((e['offset'],e['size']) for e in profile['initializer'])==[(i,8) for i in range(0,1024,8)]+[(1024,2)],'Exact actual1026B initializer')
pins=dict(read(OLD/'entry.json')['pins'])
pins.update(read(SOFT/'INPUT_PINS.json'))
pins[str(OLD/'entry.json')]=sha(OLD/'entry.json')
pins[str(A/'full_e16_mf4_prepare01/model.py')]=sha(A/'full_e16_mf4_prepare01/model.py')
for module in list(sys.modules.values()):
    f=getattr(module,'__file__',None)
    if f and '/ara_dsa_signoff_integration/' in str(f):pins[str(Path(f).resolve())]=sha(f)
for root in (HERE,SOFT):
    for p in root.rglob('*'):
        if p.is_file() and p.name!='ENTRY.json' and '__pycache__' not in p.parts:pins[str(p.resolve())]=sha(p)
for name in ('ARTIFACT_COST_REVIEW.md','artifact_cost_review.json','SOURCE_DIFF_REVIEW.md'):
    p=A/'e8_m8_sentinel_mask_static_review01'/name;pins[str(p)]=sha(p)
pins[str(SPIKE)]=sha(SPIKE)
for p,h in pins.items():require(sha(p)==h,'Consumed input drift '+p)
save(HERE/'ENTRY.json',dict(status='PREPARED_ONLY_NOT_EXECUTED_AWAIT_INDEPENDENT_REVIEW_AND_EXPLICIT_PARENT',
    schema='e8_m8_sentinel_reference_entry01',pins=pins,pin_count=len(pins),
    SEW=8,LMUL='m8',CAP=1024,vtype=3,calls=4095,results=4193280,guards=8190,
    returned_vstart_zero=4095,helper_instructions=53235,source_helper_memory_retirements=20475,
    checked_output_bytes=1026,actual_output_reads=528255,whole_output_words_each=128,tail_read_bytes=2,
    physical_input_bytes_each=1024,extra_input_BSS_bytes=0,helper_output_offset=1,
    physical_registers_each_group=8,mask_bytes=128,all_mask_bits_meaningful=1024,
    actual_seed_stores=8832,mask_groups=1575,mask_stores=25200,
    capacity3_PC_code=helpers['capacity'],capacity_observed_required_once_consecutive=True,
    scalar_comparator_instruction_visits_required=1686072,ID_loads_required=69615,
    gold_loads_required=109575,constant_materialization_instructions_required=209340,
    shared_shadow=True,source_profile_sha256=sha(HERE/'PROFILE.json'),
    ABI_frame_bytes=304,ABI_unknown_save_pcs=profile['abi_unknown_save_pcs'],
    BSS_pc=profile['bss_pc'],EOFPARK_pc=profile['park_pc'],
    spike_ELF=str(ELF),spike_ELF_sha256=ELF_SHA,soc_ELF_sha256=sha(SOFT/'soc/program.elf'),
    spike_path=str(SPIKE),spike_sha256=sha(SPIKE),
    executor=str(HERE/'reference02.py'),executor_sha256=sha(HERE/'reference02.py'),
    checker=str(HERE/'reference_check02.py'),checker_sha256=sha(HERE/'reference_check02.py'),
    short_host_sha256=sha(HERE/'HOST02.json'),actual_host_execution_sha256=sha(HERE/'host02_execution.json'),
    original_failed_host_execution_sha256=sha(HERE/'host01_execution.json'),old_failure_preserved=True,
    source_entry_sha256=sha(OLD/'entry.json'),software_READY_sha256=sha(SOFT/'SOFTWARE_READY.json'),
    actual_software_review_sha256=sha(A/'e8_m8_sentinel_mask_static_review01/artifact_cost_review.json'),
    hard_reference_steps=4000000,reference_timeout_s=120,max_raw_bytes=768*1024**2,audit_timeout_s=600,
    firmware_gate_to_HTIF=3000000,one_attempt=True,reference_invocations=0,DUT_authorized=False,
    parent_execution_authorization_present=False,execution_requires_explicit_future_parent_file=True,
    independent_review_schema=dict(status='NO_BLOCKER_EXACT_REFERENCE_ENTRY_ONLY',one_attempt=True,DUT_authorized=False,entry_sha256='actual_this_entry_SHA256')))
print('ENTRY',sha(HERE/'ENTRY.json'),'pins',len(pins))
