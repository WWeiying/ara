"""Metadata-only wall-risk ledger; no raw/ELF execution, compiler or full Host."""
import hashlib,json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent;A=HERE.parent
OLD=A/'full_e8_m8_block_unrolled01';SOFT=A/'full_e8_m8_sentinel_mask_software01'
REF=A/'full_e8_m8_sentinel_mask_reference_entry01'
PREFIX=A/'full_e8_m8_timeout_analysis01/closed_prefix01'
RECEIPT=A/'full_e8_m8_block_vcs_m9_plan01/prepared01/replay/tests/arithmetic_original_e8_m8_full4095_block/child_outcome.unvalidated.json'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,msg):
    if not ok:raise ValueError(msg)
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
paths=[RECEIPT,PREFIX/'run01/result.json',PREFIX/'REPORT.md',OLD/'sequence.json',
    OLD/'reference01/result.json',SOFT/'LINKED_COST.json',SOFT/'SOFTWARE_READY.json',
    REF/'READY.json',REF/'reference01/result.json',
    A/'e8_m8_sentinel_mask_reference_terminal_review01/result.json',
    A/'m8_sentinel_mask_static_review_hilbert01/WATCHDOG_CANDIDATE_REVIEW.md']
pins={str(p):sha(p) for p in paths}
old=read(RECEIPT);p=read(PREFIX/'run01/result.json');rows=read(OLD/'sequence.json')
require(old['returncode']==255 and old['timed_out'] and old['elapsed_s']>10800,'Actual old timeout, not PASS')
require(p['status']=='DIAGNOSTIC_ONLY_PARTIAL_EOF_NOT_PASS' and p['source_counters']==dict(checks=2601,elements=2663424,errors=0)
    and not p['full4095_complete'] and not p['final_simulator_cycle_known'],'Qualified original closed prefix only')
checkpoints=p['source_counter_checkpoints'];deltas={};prior=0;observed={}
def key(r):return tuple(r[k] for k in ('op','li','mode','si','vl','start'))
for cp in checkpoints:
    ordinal=cp['value'];cycle=int(cp['cycle']);row=rows[ordinal-1]
    observed[ordinal]=cycle-prior
    if row['seed']==0:deltas[key(row)]=cycle-prior
    prior=cycle
require(len(checkpoints)==2601 and len(deltas)==1365,'Exact closed checkpoint/source mapping')
remaining=sum(deltas[key(r)] for r in rows[2601:])
total=p['last_cycle']+remaining
wall_proxy=total/p['last_cycle']*old['elapsed_s']
newref=read(REF/'reference01/result.json');oldref=read(OLD/'reference01/result.json')
ratio=newref['firmware_to_HTIF']/oldref['firmware_to_HTIF']
need=1-10800/wall_proxy
newmetrics=read(SOFT/'LINKED_COST.json')['compiled']['soc']
oldcmp=4095*275;newcmp=newmetrics['comparator_metrics']['all_scalar_loads']
cmpfraction=(oldcmp-newcmp)/oldcmp
samples=[]
for event in p['top_owner_lifetimes']:
    if event['alloc']['insn']=='02060c27':
        ordinal=event['alloc']['call_entered']
        samples.append(dict(call=ordinal,store_cycles=event['cycles'],checkpoint_cycles=observed[ordinal],
            fraction=event['cycles']/observed[ordinal]))
        if len(samples)==5:break
value=dict(status='HOLD_RUNTIME_GATE_NO_DUT_AUTHORIZATION',reference_prerequisite_satisfied=True,
    reference_review=str(paths[-2]),reference_review_sha256=sha(paths[-2]),reference_READY_sha256=sha(REF/'READY.json'),
    old_actual_monitor=old,old_prefix_calls=2601,remaining_calls=1494,full_scope_calls=4095,
    old_recorded_cycle=p['last_cycle'],old_retired=p['retired'],actual_final_simtime_known=False,
    remaining_same_source_seed0_cycle_proxy=remaining,full_scope_cycle_proxy=total,
    full_scope_wall_proxy_s=wall_proxy,proxy_is_not_upper_or_lower_bound=True,
    old_reference_to_HTIF=oldref['firmware_to_HTIF'],old_reference_to_exit=oldref['firmware_to_exit'],
    new_reference_to_HTIF=newref['firmware_to_HTIF'],new_reference_to_exit=newref['firmware_to_exit'],
    firmware_reduction_fraction=1-ratio,firmware_scaled_wall_proxy_s=wall_proxy*ratio,
    reduction_required_for_case10800=need,
    old_comparator_scalar_loads=oldcmp,new_comparator_scalar_loads=newcmp,
    comparator_load_reduction=oldcmp-newcmp,comparator_load_reduction_fraction=cmpfraction,
    illustrative_comparator_load_time_share_needed_if_only_those_loads_improve=need/cmpfraction,
    interpretation_of_share='Sensitivity only: ignores ALU/mask changes, nonuniform costs, vector/host scheduling; not a bound',
    comparator_instructions_old=1846845,comparator_instructions_new=newmetrics['terms']['comparator'],
    new_comparator_literal_or_stack_loads=newmetrics['comparator_metrics']['other_loads_including_literal_pool_and_stack'],
    new_main_scalar_loads=60249,new_main_scalar_stores=584467,old_whole_main_memory_count_measured_here=False,
    unchanged_required_helper_memory_instructions=20475,
    unchanged_complete_output_store_instruction='02060c27',unchanged_output_store_bytes_each_call=1024,
    unchanged_full_group_input_bytes_each=1024,unchanged_fresh_output_bytes_each=1026,
    unchanged_actual_output_reads=528255,unchanged_mask_full_bytes_per_group=128,
    illustrative_recorded_same_instruction_store_samples=samples,
    watchdog_candidate_plusarg='+COMMIT_WATCHDOG=1000000',watchdog_candidate_not_yet_reviewed_for_this_worker=True,
    watchdog_progress='accepted req or resp, backend alloc or done, or RVFI retire; arch_start alone does not qualify',
    watchdog_fflush_overhead_unmeasured=True,watchdog_not_per_owner_liveness_proof=True,
    watchdog_is_not_runtime_reduction=True,
    budget=dict(case_s=10800,worker_s=12000,service_s=13200,jobs=1,reserved_slots=0,resource_cap=24,min_available_GiB=32),
    under3h_guaranteed=False,adequate_budget_evidence=False,DUT_authorized=False,DUT_started=False,
    prepared_plan_created=False,strict_worker_entry_review_completed=False,
    raw_reads=0,raw_hashes=0,raw_parses=0,reference_runs=0,compiler_runs=0,fullstream_Host_runs=0,
    old_failure_preserved=True,original_Linux_stall_closed=False,pins=pins)
save(HERE/'runtime_basis.json',value)
lines=['# e8/m8 Runtime Gate: HOLD','',
    'Decision: HOLD_RUNTIME_GATE_NO_DUT_AUTHORIZATION. Reference is independently accepted; that does not establish the unchanged10800s DUT budget. No executable worker plan or launch authorization is produced by this ledger.','',
    '## Actual Evidence','',
    '- Old monitor:255 / timed_out=true / %.6fs. Closed CSV diagnostic verifies2601 full source calls,1494 remain; no terminal simulator-cycle record exists. Original NOT_PASS and NOT_ACCEPTED are preserved.'%old['elapsed_s'],
    '- Closed prefix:1793564 retirements / cycle21859382. Existing seed0 same-tuple checkpoints imply%d additional cycles,%.1f total wall seconds (~%.2fh) using the crude recorded-cycle/wall ratio. This is a sensitivity proxy, not a bound or proof of progress throughout timeout.'%(remaining,wall_proxy,wall_proxy/3600),
    '- Exact same-boundary firmware-to-HTIF: old%d vs new%d (%.3f%% reduction). Scaling the above proxy by that ratio gives%.1fs (~%.2fh), still above10800. This is not an M9 prediction or guarantee.'%(oldref['firmware_to_HTIF'],newref['firmware_to_HTIF'],100*(1-ratio),wall_proxy*ratio,wall_proxy*ratio/3600),
    '- The illustrative proxy needs%.2f%% total improvement to reach10800s, substantially beyond the measured firmware reduction.'%(100*need),
    '','## Loads, Stores and Remaining Cost','',
    '- Actual old comparator:1126125 scalar loads (275 per call); new:707445 including all IDs/gold/output/literal/stack loads.418680 dictionary LDs disappear,37.18% of comparator loads; output528255 reads remain. New lowering has0 comparator literal/stack loads but209340 constant-materialization instructions. Comparator instructions decrease160773, not418680.',
    '- Actual new main has60249 scalar loads and584467 stores. No old whole-main load/store count is invented here. Mask128B/16SD each of1575 groups is unchanged in footprint; the loop/control code is what changed.',
    '- All20475 helper memory operations remain. In particular02060c27 still stores the full1024B output group on all4095 calls after full-capacity vset, independent of the active target VL. a/b1024B inputs, fresh1026B output and full128B masks remain unchanged. Those costs cannot be removed by specializing scalar gold reads.',
    '- Closed metadata records the same late output-store owner taking6156 cycles. Matched checkpoint intervals for the first five retained samples follow; these are observations, not a universal per-call lower bound.']
for s in samples:lines.append('  call%d: store%d / checkpoint%d cycles (%.1f%%).'%(s['call'],s['store_cycles'],s['checkpoint_cycles'],100*s['fraction']))
lines+=['','- Under an intentionally simplified model where only comparator-load time improves, about%.1f%% of total old time would need to be that component. This is not a proof: other scalar savings, per-load latency, host/system load, vector/cache scheduling and possible old silent suffix are unknown. It nevertheless gives no sound <=3h admission basis.'%(100*need/cmpfraction),
    '','## Watchdog Candidate and Safe State','',
    'Exactly+COMMIT_WATCHDOG=1000000 can improve observation, not reduce the workload or extend budgets. Progress means retire/accepted req-resp/backend alloc-done; arch_start alone is not progress. fflush is not fsync. Repeated scalar progress may hide an individual stuck owner; per-owner checks remain mandatory. Fixed local memory service is not a formal arbitration/translation gap bound. Per-progress fflush has unmeasured wall cost. The old6352-cycle observed event gap is not an exhaustive maximum.',
    '',
    'Current safe action is HOLD before DUT admission. Do not shrink4095, retry the old run, change timeouts/flags/RTL, or infer a hardware deadlock from the timeout. Any worker source preparation remains non-executing and must carry this explicit runtime HOLD into Hilbert review. A future run needs new credible wall-cost evidence or separate explicit parent runtime-risk admission; neither exists here.',
    '',
    'This calculation only reads sealed small JSON/Markdown and source sequence metadata. It does not stat/read/hash/parse raw, run Host/reference/compiler/simulator, or inspect any active task. Input paths and hashes are in runtime_basis.json.']
with (HERE/'RUNTIME_RISK.md').open('x') as f:f.write('\n'.join(lines)+'\n')
print(value['status'],wall_proxy,wall_proxy*ratio)
