"""Closed metadata/identity review only; never opens CSV or reference raw."""
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = HERE.parent
W = A / 'full_e32_m4_block_vcs_m9_plan01'
P = W / 'prepared01'
NAME = 'arithmetic_original_e32_m4_full5985_packed'
T = P / 'replay/tests' / NAME
PLAN = '7dcf6503906b5c50e09e9fa6d681f0664d3f69c3fae31095606621863ec2e5cc'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    plan, end = read(P/'plan.json'), read(P/'complete.json')
    report = read(T/'strict_original.json')
    strict, generic, owners = (report[k] for k in ('strict', 'generic', 'owner_coverage'))
    collector, collector_exit = read(P/'collector_result.json'), read(P/'collector_exit.json')
    service, child = read(P/'service_exit.json'), read(T/'child_outcome.unvalidated.json')
    event = read(W/'terminal_event01/notification.json')
    event_exit = read(W/'terminal_event01/wait_exit.json')
    require(sha(P/'plan.json') == PLAN == end['plan_sha256'] == collector['plan_sha256'] == event['plan_sha256'], 'Plan identity')
    require(end['status'] == 'PASS_M9_FULL_ORIGINAL_E32_M4_5985_CALLS_NOT_LINUX' and end['aborted'] is False
            and end['pins_unchanged'] is True and type(end['retries']) is int and end['retries'] == 0, 'Whole worker acceptance')
    require([service[k] for k in ('SERVICE_RESULT', 'EXIT_CODE', 'EXIT_STATUS')] == ['success', 'exited', '0'], 'Actual service exit')
    require(service['kind'] == 'SYSTEMD_EXEC_STOP_POST_ACTUAL_ENVIRONMENT', 'No GC inference')
    require(type(child['returncode']) is int and child['returncode'] == 0
            and all(child[k] is False for k in ('timed_out', 'failure_seen', 'cancelled'))
            and 0 < child['elapsed_s'] <= 10800, 'Actual child outcome')
    require(len(end['results']) == 1 and end['results'][0]['name'] == NAME
            and end['results'][0]['status'] == 'PASS' and type(end['results'][0]['returncode']) is int
            and end['results'][0]['returncode'] == 0 and not end['results'][0]['reason']
            and end['results'][0]['elapsed_s'] == child['elapsed_s'], 'Exact one-case membership')
    require(type(collector_exit['actual_wait_returncode']) is int and collector_exit['actual_wait_returncode'] == 0
            and collector_exit['timed_out'] is False and collector_exit['retries'] == 0, 'Actual collector wait')
    require(collector['status'] == 'ACCEPTED_M9_ORIGINAL_E32_M4_FULL5985_NOT_LINUX'
            and collector['pins_pre_post_unchanged'] is True and collector['csv_semantic_reparses'] == 0, 'Collector acceptance')
    require(event['status'] == 'TERMINAL_COLLECTOR_ACCEPTED' and type(event_exit['exit_code']) is int
            and event_exit['exit_code'] == 0, 'Actual event outcome')
    for name, digest in event['metadata_sha256'].items():
        require(sha(P/name) == digest and read(P/name) == event['metadata'][name], 'Event metadata identity '+name)
    require(sha(T/'strict_original.json') == collector['strict_report_sha256'] == event['strict_report_sha256']
            and sha(P/'complete.json') == collector['complete_sha256'], 'Closed report identity')
    require(report == event['strict_report'], 'Event strict snapshot')
    expected = dict(calls=5985, results=766080, guards=11970, returned_vstart_zero=5985,
                    helper_instructions=77805, packed_output_reads=389025, fresh_output_bytes_each_call=520,
                    FP_calls=1890, FP_input_scalar_writes=483840, FP_source_reads=15120,
                    expected_reads=124041, ID_reads=53865, cache_hits=33123, cache_misses=14757,
                    actual_BEQ_comparisons=389025, original_seed_scalar_writes=1104,
                    mask_clear_stores=35280, mask_bit_stores=154350)
    require(strict['status'] == 'FULL5985_ACTUAL_RVFI_ACCEPTED_NOT_LINUX'
            and all(strict[k] == v for k, v in expected.items()) and strict['routine_counts'] == [5985]*13
            and strict['full_order'] is True and strict['partitioned'] is False, 'Full original/lifecycle scope')
    require(report['strict_csv_parses'] == 1 and (strict['rows'], strict['retired'], strict['last_cycle']) ==
            (generic['rows'], generic['retire_count'], generic['last_cycle']) and generic['cvx_exception_count'] == 0, 'Lossless producer parse')
    require(generic['cvx_request_count'] == generic['cvx_response_count'] == generic['architecture_request_count'] == 65837
            and generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] == 33687, 'Complete protocol')
    model_path = A/'full_e32_m4_source_model01/generated01/calls.json'
    model = read(model_path)
    ledger = strict['call_ledger']
    require(len(model) == len(ledger) == 5985 and str(model_path) in plan['pins'], 'Bound original membership')
    helpers = plan['specs']['rvv_matrix_e32_m4']['backend']['helpers']
    target_required = []
    for i, (source, actual) in enumerate(zip(model, ledger)):
        require(actual['ordinal'] == i and actual['original_ordinal'] == source['ordinal'] == i+1, 'Call order')
        require(all(actual[k] == source[k] for k in ('seed', 'op', 'vl', 'mode')) and actual['vstart'] == source['start'], 'Original tuple')
        require(actual['reads'] == list(range(65)) and actual['returned_vstart'] == 0, 'All65 actual reads and vstart')
        target = helpers['op_'+str(source['op'])][8]
        require((actual['target_pc'], actual['target_insn']) == (target['pc'], target['insn']), 'Actual target identity')
        vi2 = source['op'] == 19 and source['vl'] <= 2
        if source['op'] == 19:
            require(target['insn'] == 0x38813c57, 'Exact VI2 eligibility')
        target_required.append(source['start'] < source['vl'] and not vi2)
    owner_ledger = owners['owner_ledger']
    require(len(owner_ledger) == 65837 and not owners['harmless_configuration_replay_arch_orders'], 'Whole owner ledger')
    counts = Counter()
    per_call = [[] for _ in model]
    for order, item in enumerate(owner_ledger):
        require(item['arch_order'] == order and type(item['alloc']) is int and item['alloc'] == item['done'] >= 0, 'Owner balance/order')
        counts['alloc'] += item['alloc']
        if item['call'] is None:
            require(order < 2 and item['kind'] == 'configuration' and item['required'] is False and item['alloc'] == 0, 'Bootstrap owner')
            continue
        call, index = item['call'], item['helper_index']
        require(0 <= call < 5985, 'Owner call range')
        per_call[call].append(index)
        site = helpers['op_'+str(model[call]['op'])][index]
        require((item['pc'], item['insn']) == (site['pc'], site['insn']), 'Helper PC/code ownership')
        kind = 'memory' if index in (1, 2, 3, 4, 11) else 'target' if index == 8 else 'configuration'
        needed = kind == 'memory' or kind == 'target' and target_required[call]
        require(item['kind'] == kind and item['required'] is needed, 'Exact owner qualification')
        require(item['alloc'] > 0 if needed else item['alloc'] == 0, 'Required/empty actual owners')
        if needed:
            counts[kind] += 1
            if kind == 'target' and model[call]['op'] == 24:
                counts['op24'] += 1
        if index == 8:
            require(item['retire_order'] == ledger[call]['target_retire']-1, 'Target retirement association')
    require(all(x == [0,1,2,3,4,5,7,8,9,10,11] for x in per_call), 'Every helper owner in original order')
    require(dict(counts) == dict(alloc=33687, memory=29925, target=3762, op24=117), 'All required owners')
    require(all(owners[k] == v for k,v in plan['owner_counts'].items()), 'Owner summary vs frozen plan')
    require(owners['baseline_vstart_noops'] == 2205 and owners['additional_exact_VI2_noops'] == 18, 'No broad sliding waiver')
    require(report['actual_csv_sha256'] == collector['csv_sha256'] == end['evidence_pins'][str(T/'commit_trace.csv')], 'Inherited closed CSV identity')
    pin_sets = [plan['pins'], end['evidence_pins'], end['approval_pins']]
    pins = {}
    for group in pin_sets:
        for path, digest in group.items():
            require(path not in pins or pins[path] == digest, 'Conflicting pins')
            pins[path] = digest
    inherited, verified = {}, 0
    for path, digest in pins.items():
        f = Path(path)
        if f.suffix in ('.csv', '.fsdb') or f.suffix == '.log' and f.stat().st_size > 1024*1024:
            inherited[path] = dict(sha256=digest, bytes=f.stat().st_size, basis='Sealed producer/collector verification; not reread')
        else:
            require(sha(f) == digest, 'Current nonraw pin drift '+path)
            verified += 1
    result = dict(status='ACCEPTED_M9_E32_M4_FULL5985_METADATA_REVIEW_NOT_LINUX',
        review_method='Independent closed metadata/identity/complete call-and-owner ledger check; no CSV or reference raw read',
        plan_sha256=PLAN, input_pins=len(plan['pins']), unique_input_evidence_approval_pins=len(pins),
        independently_rehashed_nonraw_pins=verified, inherited_raw_pins=inherited,
        actual_simulator_returncode=child['returncode'], actual_simulator_elapsed_s=child['elapsed_s'],
        actual_service=service, actual_collector=collector_exit, actual_event_wait=event_exit,
        scope=expected, rows=generic['rows'], retired_rows=generic['retire_count'], last_cycle=generic['last_cycle'],
        helper_windows=5985, owner_ledger_rows=len(owner_ledger), complete_owner_counts=dict(counts),
        baseline_vstart_noops=2205, additional_exact_VI2_noops=18,
        complete_sha256=sha(P/'complete.json'), collector_result_sha256=sha(P/'collector_result.json'),
        strict_report_sha256=sha(T/'strict_original.json'), csv_sha256=report['actual_csv_sha256'],
        report_source_pins={str(p):sha(p) for p in [P/'plan.json',P/'complete.json',P/'collector_result.json',
            P/'collector_exit.json',P/'service_exit.json',W/'terminal_event01/notification.json',
            W/'terminal_event01/wait_exit.json',T/'strict_original.json',Path(__file__)]},
        new_csv_semantic_parses=0, reference_reruns=0, DUT_reruns=0,
        fflags_scope='Original has no dedicated fflags oracle; no added post-restore CSR readback claim',
        original_Linux_historical_stall_closed=False,
        arithmetic_union=dict(accepted_shapes=18,total_shapes=22,accepted_calls=86940,remaining_shapes=4,remaining_calls=20160))
    with (HERE/'result.json').open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({k:result[k] for k in ('status','input_pins','unique_input_evidence_approval_pins',
        'independently_rehashed_nonraw_pins','rows','retired_rows','complete_owner_counts')},indent=2))


if __name__ == '__main__':
    main()
