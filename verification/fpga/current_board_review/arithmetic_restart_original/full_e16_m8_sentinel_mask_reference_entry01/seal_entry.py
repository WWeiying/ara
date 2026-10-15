"""Freeze exact actual entry without reference execution or oracle regeneration."""
from context import *
symbols,code,helpers,_=artifacts()
oldentry=read(OLD/'entry02.json');pins=dict(oldentry['pins'])
pins.update(read(SOFT/'INPUT_PINS.json'))
for module in list(sys.modules.values()):
    f=getattr(module,'__file__',None)
    if f and '/ara_dsa_signoff_integration/' in str(f):pins[str(Path(f).resolve())]=sha(f)
pins[str(A/'full_e16_mf4_prepare01/model.py')]=sha(A/'full_e16_mf4_prepare01/model.py')
for root in (HERE,SOFT):
    for p in root.rglob('*'):
        if p.is_file() and p.name not in ('ENTRY.json',) and '__pycache__' not in p.parts:
            pins[str(p.resolve())]=sha(p)
pins[str(OLD/'entry02.json')]=sha(OLD/'entry02.json')
for p,h in pins.items():require(sha(p)==h,'Actual inherited/current pin drift '+p)
host=read(HERE/'HOST02.json');receipt=read(HERE/'host02_execution.json')
require(host['status']=='PASS_SHORT_HOST_NOT_FULLSTREAM' and host['tests']==13 and
    host['errors']==host['failures']==0 and receipt['returncode']==0 and not receipt['timed_out'],'Actual short Host')
require(read(HERE/'host02_preflight.json')==read(HERE/'host02_postflight.json'),'Actual Host code pins')
profile=read(HERE/'PROFILE02.json')
save(HERE/'ENTRY.json',dict(status='PREPARED_NOT_EXECUTED',schema='sentinel_mask_reference_entry01',
    SEW=16,LMUL='m8',CAP=512,vtype=11,calls=4095,results=2096640,guards=8190,
    checked_bytes=1028,tail_bytes=4,physical_registers=8,packed_output_reads=528255,
    helper_instructions=53235,source_helper_memory_retirements=20475,
    new_ELF=str(ELF),new_ELF_sha256=ELF_SHA,pins=pins,
    original_source_entry_sha256=sha(OLD/'entry02.json'),software_READY_sha256=sha(SOFT/'SOFTWARE_READY.json'),
    profile_sha256=sha(HERE/'PROFILE02.json'),ABI_frame_bytes=304,
    actual_first_init_pc=profile['initializer'][0]['pc'],actual_BSS_pc=profile['bss_pc'],
    actual_EOFPARK_pc=profile['park_pc'],hard_reference_steps=4000000,reference_timeout_s=120,
    max_raw_bytes=768*1024**2,audit_timeout_s=600,cost_target=3000000,
    one_attempt=True,DUT_authorized=False,reference_invocations=0,
    parent_conditional_authorization='Current task: exact independent ENTRY NO_BLOCKER then ONE bounded reference and ONE audit; not DUT',
    short_Host_sha256=sha(HERE/'HOST02.json'),actual_Host_execution_sha256=sha(HERE/'host02_execution.json'),
    executor=str(HERE/'reference.py'),executor_sha256=sha(HERE/'reference.py')))
print('ENTRY',sha(HERE/'ENTRY.json'),'pins',len(pins),flush=True)
