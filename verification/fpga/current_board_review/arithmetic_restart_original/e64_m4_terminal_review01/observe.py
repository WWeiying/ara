#!/usr/bin/env python3
"""One inotify attachment, then exact terminal metadata audit. Never opens raw."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
A = HERE.parent
SOURCE = A / 'full_e64_m4_vcs_m9_plan01/prepared01'
ENTRY = A / 'e64_m4_m9_entry_review01/result.json'
PLAN_SHA = 'b9eeb147d51b1b2d8438b49ecb66a6b3de4b4a18e309e07becb4128a76e90ea7'
ENTRY_SHA = '00e194c5adc315fb40d555346f7e2fe067f18d6361718390ee0c3d17de187180'
UNIT = 'ara-arithmetic-original-e64-m4-full5985-m9-01.service'
ID = 'arithmetic_original_e64_m4_full5985_sticky'
WAIT = A.parent / 'wait_terminal.py'
WAIT_SHA = 'cbc78208bc6464aad86a485f296006f17a31b272d9ef8332617a98caf2b45dd4'
ROOT = SOURCE / 'replay/tests' / ID
RAW = {ROOT / n for n in ('commit_trace.csv', 'console.log', 'work/run.vcs.log')}


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    path = Path(path)
    need(path not in RAW and path.suffix == '.json', 'Metadata JSON only')
    return json.loads(path.read_text())


def sha(path):
    path = Path(path)
    need(path not in RAW and path.suffix != '.csv', 'No raw/CSV reread or hash')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def zero(value):
    return type(value) is int and value == 0


def wait_file(path, seconds, name):
    command = [sys.executable, '-B', str(WAIT), str(path), '--timeout', str(seconds)]
    start = time.monotonic()
    with (HERE / (name + '.log')).open('x') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        rc = child.wait()
    save(HERE / (name + '.json'), dict(command=command, pid=child.pid,
         actual_wait_returncode=rc, elapsed_s=time.monotonic()-start,
         observer_bound_s=seconds, source_job_timeout_modified=False))
    return rc == 0


def audit():
    need(sha(SOURCE/'plan.json') == PLAN_SHA and sha(ENTRY) == ENTRY_SHA, 'Exact plan/entry')
    plan, entry = read(SOURCE/'plan.json'), read(ENTRY)
    need(entry['status'] == 'NO_BLOCKER_ENTRY_REVIEW' and entry['plan_sha256'] == PLAN_SHA and
         entry['pins'] == plan['pins'] and entry['scope'] == [ID], 'Exact reviewed pin chain')
    need(plan['unit'] == UNIT and plan['jobs'] == 1 and len(plan['cases']) == 1 and
         plan['cases'][0]['id'] == ID and plan['case_timeout_s'] == 10800, 'Unchanged sole scope/budget')
    image = Path(plan['image'])/'image.json'
    need(sha(image) == plan['image_sha256'] == entry['image_sha256'], 'Frozen M9 identity')
    collected, end, service, collector_exit = [read(SOURCE/n) for n in (
        'collector_result.json', 'complete.json', 'service_exit.json', 'collector_exit.json')]
    need(collected['status'] == 'ACCEPTED_M9_ORIGINAL_E64_M4_FULL5985_NOT_LINUX',
         'Collector did not accept: ' + str(collected.get('firstcause', collected['status'])))
    need(collected['plan_sha256'] == PLAN_SHA and collected['complete_sha256'] == sha(SOURCE/'complete.json') and
         collected['pins_pre_post_unchanged'] is True, 'Collector complete/pins binding')
    need(zero(collector_exit['actual_wait_returncode']) and collector_exit['timed_out'] is False and
         zero(collector_exit['retries']) and 0 < collector_exit['elapsed_s'] <= 300, 'Actual collector wait0')
    need(service['kind'] == 'SYSTEMD_EXEC_STOP_POST_ACTUAL_ENVIRONMENT' and
         [service[k] for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')] == ['success','exited','0'] and
         collected['actual_service'] == service, 'Actual whole service success/exited0, not GC defaults')
    need(end['status'] == 'PASS_M9_FULL_ORIGINAL_E64_M4_5985_CALLS_NOT_LINUX' and
         end['plan_sha256'] == PLAN_SHA and end['aborted'] is False and
         end['pins_unchanged'] is True and zero(end['retries']) and not end.get('error') and
         len(end['results']) == 1, 'Whole terminal PASS, no prefix/abort/retry')
    child = end['results'][0]
    raw = read(ROOT/'child_outcome.unvalidated.json')
    need(child['name'] == ID and child['status'] == 'PASS' and zero(child['returncode']) and
         not child['reason'] and 0 < child['elapsed_s'] <= 10800, 'Actual sole child0')
    need(raw['schema'] == 'UNVALIDATED_CHILD_OUTCOME_V2' and raw['architectural_acceptance'] is False and
         zero(raw['returncode']) and all(raw[k] is False for k in ('timed_out','failure_seen','cancelled')) and
         raw['elapsed_s'] == child['elapsed_s'] and collected['actual_monitor'] == raw, 'Numeric-first receipt')
    command = read(ROOT/'command.json')
    need(raw['command_sha256'] == sha(ROOT/'command.json') and raw['command'] == command['command'] and
         raw['cwd'] == command['cwd'] == str(ROOT/'work'), 'Actual command/private work')
    argv = raw['command']
    need(argv[0] == read(image)['simv'] and '+PRELOAD='+str(ROOT/'input.elf') in argv and
         '+TESTCASE='+ID in argv and '+COMMIT_TRACE='+str(ROOT/'commit_trace.csv') in argv and
         '+NO_FSDB' in argv, 'Exact original ELF/M9 command')
    need(sha(ROOT/'input.elf') == plan['cases'][0]['sha256'], 'Private original ELF')
    run = read(SOURCE/'replay/run.json')
    need(run['status'] == 'COMPLETE' and run['status_counts'] == {'PASS':1} and run['tests'] == [ID] and
         run['jobs'] == 1 and run['timeout_s'] == 10800 and run['completed_at'] and
         read(SOURCE/'replay/summary.json') == end['results'], 'Exact runner completion')
    report = read(ROOT/'strict_original.json')
    strict, generic, owners = report['strict'], report['generic'], report['owner_coverage']
    counts = {'calls':5985, 'results':383040, 'guards':11970, 'returned_vstart_zero':5985,
              'helper_instructions':77805, 'packed_output_reads':395010,
              'expected_dictionary_reads':395010, 'dictionary_ID_reads':53865,
              'sticky_equal_BEQ':395010, 'FP_calls':1890, 'FP_input_stores':241920,
              'mask_groups':2205, 'mask_clear_stores':35280, 'mask_bit_stores':77175,
              'source_seed_stores':552, 'fresh_output_bytes_each_call':528,
              'physical_registers_each_group':4, 'vtype':26}
    need(all(type(strict[k]) is int and strict[k] == v for k,v in counts.items()) and
         strict['status'] == 'FULL5985_ACTUAL_RVFI_ACCEPTED_NOT_LINUX' and
         strict['routine_counts'] == [5985]*13 and strict['full_order'] is True and
         strict['partitioned'] is False and strict['typed_sentinel'] == '000000000000005b', 'Full source/freshness counts')
    source = read(A/'full_e64_m4_source_model01/generated01/calls.json')
    ledger = strict['call_ledger']
    spec = plan['specs']['rvv_matrix_e64_m4']
    need(len(source) == len(ledger) == 5985, 'All5985 original ledger rows')
    for i, (row, gold) in enumerate(zip(ledger, source)):
        target = spec['backend']['helpers'][f'op_{gold["op"]}'][8]
        need(row['ordinal'] == i and row['original_ordinal'] == i+1 and
             all(row[k] == gold[k] for k in ('op','seed','vl','mode')) and row['vstart'] == gold['start'] and
             row['returned_vstart'] == 0 and row['reads'] == list(range(66)) and
             row['target_pc'] == target['pc'] and row['target_insn'] == target['insn'], 'Original call/whole66 reads '+str(i+1))
    need(report['strict_csv_parses'] == 1 and (strict['rows'], strict['retired'], strict['last_cycle']) ==
         (generic['rows'], generic['retire_count'], generic['last_cycle']) and
         generic['cvx_exception_count'] == 0 and generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] > 0 and
         generic['cvx_request_count'] == generic['cvx_response_count'] > 0, 'Same full trace/generic completion')
    need(owners['status'] == 'EVERY_NECESSARY_RETIRED_OWNER_COMPLETED' and
         [owners[k] for k in ('compulsory_memory_owners','required_target_owners','minimum_required_owners',
                             'required_op24_memory_targets','optional_slideup_targets')] == [29925,3762,33687,117,18], 'Exact derived owner totals')
    by_call = {i:[] for i in range(5985)}
    targets = []
    for owner in owners['owner_ledger']:
        need(type(owner['alloc']) is int and owner['alloc'] == owner['done'] and owner['alloc'] >= 0 and
             (not owner['required'] or owner['alloc'] > 0), 'Actual owner alloc/done/required')
        if owner['kind'] == 'memory':
            by_call[owner['call']].append(owner['helper_index'])
        elif owner['kind'] == 'target':
            targets.append(owner)
    need(all(v == [1,2,3,4,11] for v in by_call.values()) and
         [x['call'] for x in targets] == list(range(5985)) and sum(x['required'] for x in targets) == 3762,
         'Every original memory/target owner, including endpoints')
    need(collected['strict_report_sha256'] == sha(ROOT/'strict_original.json') and
         collected['csv_sha256'] == report['actual_csv_sha256'] == end['evidence_pins'][str(ROOT/'commit_trace.csv')] and
         read(ROOT/'trace_summary.json')['status'] == 'VALID', 'Collector/strict/closed raw identity chain')
    verified = {}
    for pins in (plan['pins'], end['approval_pins'], end['evidence_pins']):
        for name, digest in pins.items():
            path = Path(name)
            if path in RAW:
                need(path.is_file(), 'Referenced closed raw missing')
                continue
            need(sha(path) == digest, 'Pin drift '+name)
            verified[name] = digest
    need(end['approval_pins'].get(str(ENTRY)) == ENTRY_SHA and
         all(str(path) in end['evidence_pins'] for path in RAW), 'Entry/raw evidence pins present')
    need(sha(SOURCE/'plan.json') == PLAN_SHA and sha(ENTRY) == ENTRY_SHA, 'Late identity check')
    return dict(status='ACCEPTED_M9_FULL5985_INDEPENDENT_TERMINAL_METADATA_NOT_LINUX',
                plan_sha256=PLAN_SHA, entry_sha256=ENTRY_SHA, actual_service=service,
                actual_monitor=raw, actual_collector_exit=collector_exit, full_counts=counts,
                first_call=ledger[0], last_call=ledger[-1], generic=generic,
                necessary_memory_owners=29925, necessary_target_owners=3762,
                verified_nonraw_pins=verified, raw_hashes_bound_not_reread={str(p):end['evidence_pins'][str(p)] for p in RAW},
                terminal_hashes={n:sha(SOURCE/n) for n in ('complete.json','service_exit.json','collector_result.json','collector_exit.json')},
                oracle_basis='Pinned producer single full strict/generic pass plus actual successful collector; no semantic reparse',
                no_fflags_oracle_claim=True, historical_Linux_closed=False)


def main():
    result = dict(status='NOT_ACCEPTED', raw_reads=0, semantic_reparses=0, DUT_runs=0,
                  observer_pid=os.getpid(), started=time.time(), source_runtime_modified=False,
                  observer_sha256=sha(Path(__file__)), waiter_sha256=sha(WAIT))
    try:
        need(sha(WAIT) == WAIT_SHA, 'Exact existing inotify helper')
        save(HERE/'attachment.json', dict(status='INOTIFY_WAIT_NOT_ACCEPTANCE', pid=os.getpid(),
             target=str(SOURCE/'collector_result.json'), existing_observer_matches_at_initial_check=0,
             plan_sha256=PLAN_SHA, waiter_sha256=WAIT_SHA, observer_timeout_s=14400))
        if not wait_file(SOURCE/'collector_result.json', 14400, 'collector_result_wait'):
            result['status'] = 'OBSERVATION_TIMEOUT_OR_ERROR_NOT_DUT_RESULT'
        else:
            # Result is published before the hook persists the actual child-wait receipt.
            need(wait_file(SOURCE/'collector_exit.json', 360, 'collector_exit_wait'), 'Collector numeric receipt absent; no acceptance')
            result.update(audit())
    except Exception as error:
        result['firstcause'] = type(error).__name__+': '+str(error)
    if sha(Path(__file__)) != result['observer_sha256']:
        result.update(status='NOT_ACCEPTED', firstcause='Observer source changed during wait')
    result['finished'] = time.time()
    save(HERE/'result.json', result)
    accepted = result['status'] == 'ACCEPTED_M9_FULL5985_INDEPENDENT_TERMINAL_METADATA_NOT_LINUX'
    with (HERE/'REVIEW.md').open('x') as stream:
        stream.write('# e64/m4 Independent Terminal Review\n\n')
        stream.write('Verdict: **'+result['status']+'**.\n\n')
        stream.write('Exact plan: `'+PLAN_SHA+'`. Original service: `'+UNIT+'`.\n\n')
        if accepted:
            stream.write('Actual service success/exited0; actual simulator rc0 / '+str(result['actual_monitor']['elapsed_s'])+'s; actual collector wait0.\n\n')
            stream.write('All5985 continuous original calls,383040 results,11970 guards,77805 helpers,395010 actual and expected reads,241920 fresh FP stores,35280 mask clears and77175 cumulative bit stores retained. All call tuples and66-word coverage,including first/last,match the original source ledger.29925 memory and3762 necessary target owners complete; all actual generic tokens pair.\n\n')
            stream.write('Plan/entry/image/privateELF and nonraw evidence pins independently rehashed. CSV and simulator consoles were NOT reopened: their hashes are bound through the frozen producer and successful collector chain. Raw veto and semantic validity rely on those reviewed original gates,not a new trace scan.\n\n')
        else:
            stream.write('First cause: '+str(result.get('firstcause',result['status']))+'. No timeout/prefix is accepted.\n\n')
        stream.write('No DUT/reference/build/restart,CPU polling or active CSV reads. No original source,log,helper or result modified. No explicit fflags oracle or original Linux closure is claimed.\n\n')
        stream.write('Detailed receipts/counts/pins: result.json SHA256 `'+sha(HERE/'result.json')+'`.\n')
    print(result['status'], flush=True)
    return 0 if accepted else 1


if __name__ == '__main__':
    raise SystemExit(main())
