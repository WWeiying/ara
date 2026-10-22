"""Summarize existing short-host, compile and static linked CFG evidence only."""
from pathlib import Path
from collections import Counter
import hashlib,importlib.util,json
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
spec=importlib.util.spec_from_file_location('linked',HERE/'linked_cfg_cost.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
cost=read(HERE/'LINKED_COST.json')
for name in ('preparation','cfg'):
    receipt=read(HERE/(name+'_execution.json'))
    m.require(receipt['returncode']==0 and not receipt['timed_out'],'Actual bounded phase exit0')
m.require(cost['source_pins_unchanged'],'Consumed source unchanged')
for p,h in read(HERE/'INPUT_PINS.json').items():m.require(sha(Path(p))==h,'Post source drift '+p)
summary={}
for backend,v in cost['compiled'].items():
    funcs=m.parse(HERE/backend/'program.dis')
    pc={r['pc']:r for rows in funcs.values() for r in rows}
    main=Counter()
    for a,n in v['main_PC_visits'].items():main[pc[int(a,16)]['op']]+=n
    cmp=Counter()
    for a,n in v['comparator_PC_visits'].items():cmp[pc[int(a,16)]['op']]+=n
    loads=('ld','lw','lwu','lh','lhu','lb','lbu')
    stores=('sd','sw','sh','sb')
    old_cmp=1846845
    summary[backend]=dict(elf_sha256=v['elf_sha256'],whole_positive_CFG_upper=v['whole_positive_CFG_upper'],
        comparator_success_instructions=v['terms']['comparator'],
        comparator_instructions_saved_vs_exact_old451=old_cmp-v['terms']['comparator'],
        scalar_comparator_loads_including_literals_and_stack=v['comparator_metrics']['all_scalar_loads'],
        comparator_memory=v['comparator_metrics'],
        whole_main_loads=sum(main[x] for x in loads),whole_main_stores=sum(main[x] for x in stores),
        main_opcode_visits=dict(main),comparator_opcode_visits=dict(cmp),
        scope=dict(calls=4095,results=4193280,guards=8190,returned_vstart=4095,output_reads=528255,
            whole_output_words_per_call=128,tail_bytes=2,physical_input_bytes_each=1024,
            CAP=1024,SEW=8,vtype=3,physical_registers=8,helper_instructions=53235,
            mask_groups=1575,mask_bytes=128,mask_stores=25200),
        all_helper_arguments_verified=True,all_seed_inputs_verified_at_each_call=True,
        full_fresh_output_verified=True,all_mask_store_values_and_epochs_verified=True,
        static_helper_instruction_count=v['original_helper_static_instructions'],
        extra_RVV=v['extra_RVV'],stack_gap=v['stack_gap'],main_frame_bytes=v['main_frame_bytes'])
pins={str(p):sha(p) for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.h','.c','.json','.md')}
for b in ('soc','spike'):
    for p in (HERE/b).iterdir():
        if p.is_file():pins[str(p)]=sha(p)
status='SOFTWARE_COST_GATE_PASS_PENDING_INDEPENDENT_ARTIFACT_REVIEW_NOT_REFERENCE_NOT_DUT' if cost['cost_gate_3M'] else 'HOLD_STATIC_POSITIVE_CFG_EXCEEDS_3M_NOT_RTL'
result=dict(status=status,backends=summary,source_pins_unchanged=True,pins=pins,
    actual_preparation_exit=read(HERE/'preparation_execution.json'),actual_static_CFG_exit=read(HERE/'cfg_execution.json'),
    short_host=read(HERE/'short_host.log.exit.json'),positive_ordinals_zero_based=[0,1365,2730,4094,9,45,1257,1278,1299],
    short_positive_cases=9,short_each_byte_output_negatives=9234,mask_byte_negatives=384,wrong_mode_negatives=6,
    short_Host_boundary_only_not_original_fullstream=True,fullstream_Host_runs=0,compile_attempts_per_backend=1,
    reference_runs=0,VCS_runs=0,actual_firmware_measured=False,
    no_3hour_runtime_guarantee=True,immutable_original_case_fallback=True,
    positive_CFG_hypotheses=['all original helpers return vstart0','actual vector outputs equal original immutable gold'],
    failure_path_cost_bound_claimed=False)
save(HERE/'SOFTWARE_READY.json',result)
lines=['# e8/m8 Actual Software Cost','',status,'',
    'Short C/UB: 9 real-ordinal positives, 9234 output byte negatives (including both byte guards and the protected2B tail),384 full128B mask byte negatives and6 wrong-mode negatives. No fullstream Host or ELF execution.',
    '','| Backend | Positive CFG upper | Comparator instructions | Comparator instructions saved vs old451/call | Comparator scalar loads (all) | Literal-pool loads | Stack gap |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for b,v in summary.items():
    lines.append('| %s | %d | %d | %d | %d | %d | %d |'%(b,v['whole_positive_CFG_upper'],v['comparator_success_instructions'],v['comparator_instructions_saved_vs_exact_old451'],v['scalar_comparator_loads_including_literals_and_stack'],v['comparator_memory']['literal_pool_loads'],v['stack_gap']))
lines+=['','Actual CFG counts every executed instruction in the linked success path, including constant rematerialization, branch/join/setup and spills. It includes main, original helpers and printing/startup allowance. Main load/store totals and per-PC visits are retained. Gold load savings alone are not a total-memory or runtime claim.',
    '','Geometry is e8: a/b each1024B only, no extra e16 BSS shadow; out+1, SH/LHU2B tail, vtype3. Full4095 source history and inputs checked at each linked helper call. All528255 output reads and full128B masks remain.',
    '','This is static linked CFG, conditional on successful original vector results, not architectural reference or DUT acceptance. No new firmware count or <3h guarantee exists. Original artifacts/failures and compiler flags remain unchanged; no flags search, reference or VCS was run.']
with (HERE/'COST_REPORT.md').open('x') as f:f.write('\n'.join(lines)+'\n')
print(status)
for b,v in summary.items():print(b,v['whole_positive_CFG_upper'],v['scalar_comparator_loads_including_literals_and_stack'])
