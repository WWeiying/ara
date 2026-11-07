#!/usr/bin/env python3
"""Recheck accepted current-SoC runs and reconcile call, engine and cycle evidence."""
import argparse
from collections import Counter
import csv
import importlib.util
import json
from pathlib import Path
import re
import statistics
import sys

sys.dont_write_bytecode = True
from build_soc import HERE, OUT, digest, require, save, verify

WAIT = ('no_outstanding', 'response_idle', 'r_transfer', 'r_blocked')
PHASES = ('setup', 'activation', 'weight', 'compute', 'overlap', 'drain',
          'scheduler', 'commit', 'fault', 'terminal')
BOUNDARY = re.compile(r'^\[CHAIN_BOUNDARY\] cycle=([0-9]+) insn=([0-9a-f]{8}) '
                      r'qbs_fire=([01]) qbs_terminal=([01]) '
                      r'akv_fire=([01]) akv_terminal=([01])$', re.M)


def mean(rows, field):
    return statistics.mean(row[field] for row in rows)


def q6_summary(measured):
    trials = measured['trials']
    require(len(trials) == 2, 'Expected first/repeat trials')
    result = []
    for trial in trials:
        commands = trial['commands']
        p = trial['complete_slice_partition_cycles']
        require(sum(p.values()) == trial['timing']['total'], 'Complete-call partition mismatch')
        totals = Counter()
        for cmd in commands:
            strict = {k: cmd['probe_weight_wait_' + k + '_cycles'] for k in WAIT}
            require(sum(strict.values()) == cmd['weight_prefetch_wait_cycles'],
                    'Strict wait classification does not partition WAIT_WEIGHT')
            require(sum(cmd['phase_' + k + '_cycles'] for k in PHASES) == cmd['busy_cycles'],
                    'Engine phases do not partition busy')
            require(cmd['dot_active_cycles'] + cmd['probe_compute_without_dot_issue_cycles'] ==
                    cmd['phase_compute_cycles'] + cmd['phase_overlap_cycles'],
                    'Compute issue/no-issue mismatch')
            totals.update(cmd)
        busy = totals['busy_cycles']
        call = trial['timing']['total']
        weight = totals['weight_bytes']
        # Payload-only lower bound at the pinned 128-bit QBS AXI interface;
        # this is neither DDR bandwidth nor an achievable complete-call time.
        weight_beats = (weight + 15) // 16
        result.append(dict(trial=trial['trial'], total_cycles=call,
            complete_call_partition=dict(p),
            partition_fractions={k: v / call for k, v in p.items()},
            engine_busy_cycles=busy, exclusive_engine_phases={k: totals['phase_' + k + '_cycles']
                                                            for k in PHASES},
            strict_weight_wait={k: totals['probe_weight_wait_' + k + '_cycles'] for k in WAIT},
            strict_weight_wait_cycles=totals['weight_prefetch_wait_cycles'],
            strict_wait_fraction_of_busy=totals['weight_prefetch_wait_cycles']/busy,
            dot_issue_cycles=totals['dot_active_cycles'],
            dot_issue_fraction_of_busy=totals['dot_active_cycles']/busy,
            compute_without_dot_issue_cycles=totals['probe_compute_without_dot_issue_cycles'],
            tiles=totals['tiles'], no_issue_cycles_per_tile=totals['probe_compute_without_dot_issue_cycles']/totals['tiles'],
            useful_pairs=totals['useful_pairs'], pair_capacity=totals['pair_capacity'],
            weight_payload_bytes=weight, activation_logical_bytes=totals['activation_bytes'],
            activation_axi_bytes_saved=totals['activation_axi_bytes_saved'],
            read_payload_bytes=totals['payload_bytes'], read_bus_beats=totals['r_beats'],
            read_bus_bytes=16*totals['r_beats'], weight_only_ideal_bus_cycles=weight_beats,
            read_ar_slot_blocked_cycles=totals['probe_read_ar_slot_blocked_cycles'],
            read_ar_ready_blocked_cycles=totals['probe_read_ar_ready_blocked_cycles'],
            read_response_idle_cycles=totals['probe_read_response_idle_cycles'],
            read_sink_blocked_cycles=totals['probe_read_data_sink_blocked_cycles'],
            translation_wait_cycles=totals['probe_read_translation_wait_cycles'],
            context_start_blocked_cycles=totals['probe_context_start_blocked_cycles'],
            fp_input_blocked_cycles=totals['probe_fp_input_blocked_cycles'],
            result_blocked_cycles=totals['probe_profile_result_blocked_cycles'],
            commit_blocked_cycles=totals['commit_backpressure_cycles']))
    return dict(scope=measured['scope'], trials=result,
        original_payload_integrity=measured.get('original_payload_integrity'),
        mean_total_cycles=mean(result, 'total_cycles'),
        mean_complete_call_partition={k: statistics.mean(t['complete_call_partition'][k] for t in result)
                                      for k in result[0]['complete_call_partition']},
        interpretation='Call partition and engine phases are separately exclusive. Strict WAIT_WEIGHT is a subset '
                       'of engine activity, not another additive slice. Issue is not physical lane utilization. '
                       'Payload bus bound is not a measured DDR bound or removable stall budget.')


def f16_summary(measured):
    require(measured['complete_calls'] == 4 and len(measured['phase']) == 2,
            'Expected ABBA full-call experiment')
    profile, total = measured['phase'], measured['measured_total_cycles']
    phases = set(profile[0]['issue_side_cycles'])
    require(all(set(row['issue_side_cycles']) == phases for row in profile), 'Phase schema drift')
    for row in profile:
        require(sum(row['issue_side_cycles'].values()) + row['outside_spans'] == total[row['trial']],
                'F16 call partition mismatch')
        require(0 <= row['final_drain'] <= row['outside_spans'], 'Drain is not a subset of residual')
    interval = {k: statistics.mean(row['issue_side_cycles'][k] for row in profile) for k in sorted(phases)}
    interval['outside_spans'] = statistics.mean(row['outside_spans'] for row in profile)
    require(sum(interval.values()) == measured['profile_mean'], 'Averaged F16 partition mismatch')
    busy = measured['work']['call_busy_cycles']
    require(len(busy) == 4 and all(0 < b <= t for b, t in zip(busy, total)), 'Invalid engine busy')
    return dict(scope=measured['scope'], total_cycles=total,
        baseline_mean_cycles=measured['baseline_mean'], profile_mean_cycles=measured['profile_mean'],
        signed_probe_delta_cycles=measured['probe_delta_cycles'],
        signed_probe_delta_fraction=measured['probe_delta_fraction'],
        mean_issue_side_partition=interval,
        issue_side_fractions={k: v/measured['profile_mean'] for k, v in interval.items()},
        final_drain_mean_cycles=statistics.mean(row['final_drain'] for row in profile),
        engine_busy_cycles_per_call=busy,
        engine_busy_fraction_per_call=[b/t for b, t in zip(busy, total)],
        hardware_work=measured['work'], observed_empty_probe_median_cycles=measured['empty_interval_median'],
        reconciled_command_costs=measured.get('reconciled_command_costs'),
        interpretation='Issue-side intervals are exclusive CPU phase intervals, not exclusive engine or stall times. '
                       'AKV busy overlaps these intervals. Final drain is already inside outside_spans. '
                       'Signed ABBA delta is observed perturbation, not an exact correction to subtract.')


def boundaries(text, expected):
    opened, rows = {}, {'qbs': [], 'akv': []}
    previous = -1
    for m in BOUNDARY.finditer(text):
        cycle = int(m[1])
        require(cycle > previous, 'Duplicate or unordered boundary cycle')
        previous = cycle
        for engine, fire, done in (('qbs', int(m[3]), int(m[4])), ('akv', int(m[5]), int(m[6]))):
            require(not (fire and done), 'Ambiguous same-engine boundary')
            if fire:
                require(engine not in opened, 'Overlapping engine commands')
                opened[engine] = cycle
            if done:
                require(engine in opened, 'Terminal without command fire')
                begin = opened.pop(engine)
                require(cycle > begin, 'Invalid engine lifetime')
                rows[engine].append(dict(fire=begin, terminal=cycle, cycles=cycle-begin))
    require(not opened, 'Unfinished engine boundary')
    for engine, busy in expected.items():
        require([row['cycles'] for row in rows[engine]] == busy,
                engine + ' boundary lifetimes disagree with native busy counter')
    require(all(engine in expected or not values for engine, values in rows.items()),
            'Unexpected engine command')
    return rows


def prefix(path):
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 1000, 'Incomplete bounded cycle window')
    start = int(rows[0]['cycle'])
    for i, row in enumerate(rows):
        require(int(row['cycle']) == start+i, 'Cycle window is not contiguous')
        require(all(row[k] in ('0', '1') for k in row if k not in ('cycle', 'insn')),
                'Unknown/nonbinary cycle signal')
    counts = Counter()
    for row in rows:
        for k in ('qbs_busy', 'akv_busy', 'wait_weight', 'tile_start', 'tile_done'):
            counts[k] += int(row[k])
        for channel in ('ar', 'r'):
            counts[channel+'_transfer'] += int(row[channel+'_valid']) & int(row[channel+'_ready'])
        counts['front_present_not_ready'] += int(row['front_valid']) & (1-int(row['front_ready']))
    return dict(start_cycle=start, cycles=1000, signal_counts=dict(counts),
        ar_r_signal_scope='QBS reader AXI only; these signals do not observe AKV or total SoC memory traffic',
        scope='First execution-command presentation only; not a full-call occupancy estimate. '
              'Front not-ready includes asynchronous command lifetime, not just admission stall.')


def root_window(text):
    rows = []
    for line in text.splitlines():
        if not line.startswith('[QBS_ROOT] '):
            continue
        row = {}
        for item in line[len('[QBS_ROOT] '):].split():
            require(item.count('=') == 1, 'Malformed root trace field')
            key, value = item.split('=')
            require(key not in row and re.fullmatch(r'[0-9]+(?:/[0-9]+)?', value),
                    'Duplicate/unknown root trace value')
            row[key] = tuple(map(int, value.split('/'))) if '/' in value else int(value)
        require(row['c'] == len(rows), 'Root trace sequence mismatch')
        rows.append(row)
    require(len(rows) == 200, 'Incomplete root cycle window')
    counts = Counter()
    for row in rows:
        require(all(row[k] in (0, 1) for k in ('wait', 'istart', 'idone')), 'Unknown root control')
        if row['wait']:
            key = 'no_outstanding' if not row['bfifo'] else (
                'response_idle' if not row['r'][0] else 'r_transfer' if row['r'][1] else 'r_blocked')
            counts['strict_wait_'+key] += 1
        for k in ('ar', 'r', 'data'):
            require(len(row[k]) == 2 and all(v in (0, 1) for v in row[k]), 'Unknown root handshake')
            counts[k+'_transfer'] += row[k][0] & row[k][1]
    return dict(cycles=200, begin='Cycle after first integer tile launch', counts=dict(counts),
                tile_starts=[r['c'] for r in rows if r['istart']],
                tile_completions=[r['c'] for r in rows if r['idone']],
                scope='One prefix window; global WAIT_WEIGHT counters are authoritative for the whole command.')


def f16_engine_work(text, lifetimes, calls=4, per_call=1046):
    commands = []
    names = {2: 'value_row', 3: 'release', 4: 'full', 5: 'refill', 6: 'key_column'}
    observed = ('ar', 'r_beats', 'read_payload_bytes', 'store_wait_cycles',
                'read_backpressure_cycles', 'replay_backpressure_cycles',
                'v2_k_view_bank_cycles', 'v2_bank_conflict_cycles')
    for line in text.splitlines():
        if line.startswith('[AKV_PERF] '):
            fields = {}
            for token in line[len('[AKV_PERF] '):].split():
                require(token.count('=') == 1, 'Malformed AKV field')
                key, value = token.split('=')
                require(key not in fields and value.isdecimal(), 'Invalid AKV field')
                fields[key] = int(value)
            require(fields['command'] in names and fields['seq'] == len(commands)+1,
                    'Unexpected AKV command/order')
            commands.append(fields)
    require(len(commands) == len(lifetimes) == calls*per_call, 'Incomplete AKV command costs')
    result = []
    for trial in range(calls):
        selected = commands[trial*per_call:(trial+1)*per_call]
        events = lifetimes[trial*per_call:(trial+1)*per_call]
        counts, busy = Counter(), Counter()
        activity = {name: Counter() for name in names.values()}
        histogram = {name: Counter() for name in names.values()}
        for command, event in zip(selected, events):
            name = names[command['command']]
            require(command['busy_cycles'] == event['cycles'], 'AKV lifetime/cost mismatch')
            counts[name] += 1
            busy[name] += event['cycles']
            histogram[name][str(event['cycles'])] += 1
            for key in observed:
                activity[name][key] += command[key]
        gaps = [b['fire']-a['terminal'] for a, b in zip(events, events[1:])]
        require(all(g >= 0 for g in gaps), 'Overlapping AKV commands')
        envelope = events[-1]['terminal']-events[0]['fire']
        require(sum(busy.values())+sum(gaps) == envelope, 'AKV envelope partition mismatch')
        result.append(dict(trial=trial, commands=dict(counts), busy_by_command_cycles=dict(busy),
            busy_histogram_by_command={k: dict(v) for k, v in histogram.items()},
            observed_activity_by_command={k: dict(v) for k, v in activity.items()},
            first_fire_to_last_terminal_cycles=envelope, intercommand_gap_cycles=sum(gaps),
            interpretation='Envelope is partitioned into engine lifetimes and inter-command gaps. '
                           'Gaps include required RVV/scalar work and dependencies, not all removable overhead. '
                           'Full-call preparation/output outside the envelope remains separate.'))
    return result


def fnv1a64(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64)-1)
    return format(value, '016x')


def original_payload_integrity(text, build_dir, pins):
    build = json.loads((build_dir/'build.json').read_text())
    contract = build.get('input_integrity', {})
    require(contract.get('method') == 'fnv1a64-after-both-timed-calls-v1' and
            contract.get('entrypoint') == 'main -> q6_profile_body' and
            contract.get('memory_checked_after_both_calls') is True,
            'Original target input/weight integrity is not proved')
    expected = {'activation': ('input_f32.bin', 8192, 'profile_input'),
                'weight': ('weights_r4.bin', 107520, 'profile_weights')}
    require(set(contract['payloads']) == set(expected), 'Missing/extra integrity payload')
    for tag, (filename, size, symbol) in expected.items():
        item = contract['payloads'][tag]
        path = build_dir/'data'/filename
        require(item['path'] == str(path) and item['bytes'] == path.stat().st_size == size and
                item['symbol'] == symbol and item['expected_hash'] == fnv1a64(path.read_bytes()) and
                pins.get(str(path)) == digest(path), 'Independent payload identity/hash mismatch')
    wrapper = contract['wrapper']
    require(Path(wrapper['source']) == HERE/'q6_decode/input_integrity.c', 'Unexpected integrity source')
    for key in ('source', 'object', 'config'):
        path = Path(wrapper[key])
        require(path.is_file() and wrapper[key+'_sha256'] == digest(path) == pins.get(str(path)),
                'Integrity wrapper/config/object pin mismatch')
    command_file = build_dir/'commands.json'
    require(pins.get(str(command_file)) == digest(command_file), 'Integrity compile/link command drift')
    commands = json.loads(command_file.read_text())
    main = [c['argv'] for c in commands if c['label'] == 'compile-main']
    compiled = [c['argv'] for c in commands if '-c' in c['argv'] and
                c['argv'][c['argv'].index('-c')+1] == wrapper['source']]
    linked = [c['argv'] for c in commands if c['label'] == 'link']
    require(len(main) == 1 and main[0].count('-Dmain=q6_profile_body') == 1 and
            len(compiled) == 1 and not any(arg.startswith('-Dmain=') for arg in compiled[0]) and
            '-o' in compiled[0] and compiled[0][compiled[0].index('-o')+1] == wrapper['object'] and
            len(linked) == 1 and linked[0].count(wrapper['object']) == 1,
            'No independently linked post-call input integrity wrapper')
    pattern = re.compile(r'CHAIN_Q6_INPUT_INTEGRITY tag=(activation|weight) bytes=([0-9]+) '
                         r'expected=([0-9a-f]{16}) actual=([0-9a-f]{16})')
    observed, done = {}, False
    for line in text.splitlines():
        if line.startswith('CHAIN_Q6_INPUT_INTEGRITY_DONE'):
            require(not done and set(observed) == set(expected) and
                    line == 'CHAIN_Q6_INPUT_INTEGRITY_DONE errors=0', 'Incomplete/failed integrity footer')
            done = True
        elif line.startswith('CHAIN_Q6_INPUT_INTEGRITY'):
            match = pattern.fullmatch(line)
            require(match is not None and not done, 'Malformed/late integrity record')
            tag, count, reference, actual = match.groups()
            require(tag not in observed and int(count) == expected[tag][1] and
                    reference == actual == contract['payloads'][tag]['expected_hash'],
                    'Original target payload was changed or evidence was duplicated')
            observed[tag] = dict(bytes=int(count), expected=reference, actual=actual)
    require(done, 'Original target payload readback is missing')
    return dict(state='PASS', method=contract['method'], payloads=observed,
                bytes_checked=115712, after_both_timed_calls=True,
                scope='Architecturally visible target payload signatures against independently hashed frozen input files')


def accepted(directory, kind):
    receipt = directory / 'result.json'
    report = json.loads(receipt.read_text())
    require(report.get('state') == 'PASS' and report.get('kind') == kind and
            report.get('independent_protocol_checked') is True and
            report.get('post_pins_match') is True and report.get('performance_measured') is True,
            'No accepted current-SoC profiling result: ' + str(directory))
    inventory = directory / 'source-pins.json'
    require(digest(inventory) == report['source_pins_sha256'], 'Run inventory drift')
    verify(json.loads(inventory.read_text()))
    verify(report['artifacts'])
    log = directory / 'work/run.vcs.log'
    protocol = directory / 'work/uvm_result.json'
    proof = json.loads(protocol.read_text())
    require(proof.get('status') == 'PASS' and proof.get('issues') == [] and
            proof['log_sha256'] == digest(log) and proof['elf_sha256'] == report['software_sha256'] and
            proof['vector_trace_sha256'] == digest(directory / 'work/vector_trace.csv'),
            'Protocol identity/check mismatch')
    if kind == 'q6':
        identity = report['measured'].get('checker_identity')
        path = Path(identity['path']).resolve(strict=True) if identity else HERE / 'q6_decode/check.py'
        require(path in (HERE/'q6_decode/check.py', HERE/'q6_decode/check_successor.py'),
                'Unreviewed Q6 checker path')
        if identity:
            require(digest(path) == identity['sha256'] and
                    json.loads(inventory.read_text()).get(str(path)) == identity['sha256'],
                    'Q6 checker identity drift')
    else:
        path = HERE / 'f16_decode/check_successor.py'
    spec = importlib.util.spec_from_file_location('chain_reaudit_'+kind, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    measured = module.check_run(log, Path(report['build']))
    require(measured == report['measured'], 'Replayed checker disagrees with accepted measurement')
    if kind == 'q6':
        measured['original_payload_integrity'] = original_payload_integrity(
            log.read_text(), Path(report['build']), json.loads(inventory.read_text()))
    expected = {'qbs': [c['busy_cycles'] for t in measured['trials'] for c in t['commands']]} if kind == 'q6' else {}
    if kind == 'f16':
        expected['akv'] = [int(re.search(r'\bbusy_cycles=([0-9]+)', line)[1])
                           for line in log.read_text().splitlines() if line.startswith('[AKV_PERF] ')]
        # Independent instruction-allocation counts supplement terminal work records.
        measured['vector_command_work'] = module._load_predecessor().check_vector_workcounts(directory / 'work/vector_trace.csv')
    events = boundaries(log.read_text(), expected)
    if kind == 'f16':
        measured['reconciled_command_costs'] = f16_engine_work(log.read_text(), events['akv'])
    window = prefix(directory / 'work/boundary.csv')
    if kind == 'q6':
        window['reader_root'] = root_window(log.read_text())
    return report, measured, events, window


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--campaign', type=Path)
    selection.add_argument('--q6-run', type=Path)
    parser.add_argument('--f16-run', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    require(not out.exists() and out.is_relative_to(OUT.resolve()), 'Fresh independent report required')
    initial_pins = {str(Path(__file__)): digest(__file__)}
    if args.campaign:
        require(args.f16_run is None, 'Do not mix campaign and independent runs')
        campaign = args.campaign.resolve(strict=True)
        completed = json.loads((campaign / 'result.json').read_text())
        require(completed['state'] == 'PROFILE_RUNS_CHECKED', 'Campaign not checked/completed')
        verify(json.loads((campaign / 'source-pins.json').read_text()))
        initial_pins.update({str(p): digest(p) for p in (campaign/'result.json', campaign/'source-pins.json')})
        selected = {kind: campaign/kind for kind in ('q6', 'f16')}
        mode = 'checked_campaign'
    else:
        require(args.f16_run is not None, 'Both independently accepted runs required')
        selected = {'q6': args.q6_run.resolve(strict=True), 'f16': args.f16_run.resolve(strict=True)}
        mode = 'explicit_checked_runs; no change to original campaign status'
    reports, measurements, windows, events = {}, {}, {}, {}
    for kind in ('q6', 'f16'):
        reports[kind], measurements[kind], events[kind], windows[kind] = accepted(selected[kind], kind)
    require(reports['q6']['image_sha256'] == reports['f16']['image_sha256'] and
            reports['q6']['configuration'] == reports['f16']['configuration'], 'Image/config mismatch')
    result = dict(state='CURRENT_RUNS_RECONCILED', whole_model=False,
        image_sha256=reports['q6']['image_sha256'], configuration=reports['q6']['configuration'],
        q6=q6_summary(measurements['q6']), f16=f16_summary(measurements['f16']),
        bounded_windows=windows, boundaries=events, collection_mode=mode,
        selected_runs={kind: str(path) for kind, path in selected.items()},
        current_hardware_production_edits=False, interpretation='Two real-data full operator calls, not full layer/model performance.')
    out.mkdir()
    pins = dict(initial_pins)
    for kind in ('q6', 'f16'):
        p = selected[kind]/'result.json'
        pins[str(p)] = digest(p)
        pins.update(reports[kind]['artifacts'])
    save(out/'evidence-pins.json', pins)
    with (out/'call_partition.csv').open('x', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['workload', 'arm', 'phase', 'mean_cycles', 'fraction_of_call'])
        q = result['q6']
        for k, value in q['mean_complete_call_partition'].items():
            writer.writerow(['q6_decode', 'first_repeat', k, value, value/q['mean_total_cycles']])
        f = result['f16']
        for k, value in f['mean_issue_side_partition'].items():
            writer.writerow(['f16_decode', 'profile', k, value, value/f['profile_mean_cycles']])
    verify(pins)
    save(out/'result.json', result)
    print(json.dumps(dict(state=result['state'], output=str(out))), flush=True)


if __name__ == '__main__':
    main()
