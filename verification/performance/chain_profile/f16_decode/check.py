#!/usr/bin/env python3
"""Fail-closed numerical/CSR/guard/timing checker; protocol remains independent."""
import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import struct
from collections import Counter
from pathlib import Path

ORDER = [0, 1, 1, 0]
PHASES = ['full', 'qk', 'scale_mask_softmax', 'pv',
          'refill', 'qk', 'scale_mask_softmax', 'pv',
          'refill', 'qk', 'scale_mask_softmax', 'pv', 'release_output']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify_build(path):
    manifest = json.loads(path.read_text())
    require(manifest['state'] == 'BUILT_NOT_EXECUTED', 'Not a prepared build')
    require(sha(manifest['elf']) == manifest['elf_sha256'], 'ELF drift')
    pins = Path(manifest['source_pins'])
    require(sha(pins) == manifest['source_pins_sha256'], 'Pin inventory drift')
    for p, digest in json.loads(pins.read_text()).items():
        require(Path(p).is_file() and sha(p) == digest, 'Input drift: ' + p)
    for p, digest in manifest['artifacts'].items():
        require(Path(p).is_file() and sha(p) == digest, 'Artifact drift: ' + p)
    require(manifest['shape']['tile_lengths'] == [64, 64, 9] and
            manifest['shape']['valid_tokens'] == 137 and manifest['order'] == ORDER,
            'Shape/order mismatch')
    return manifest


def records(log):
    rows = {}
    for line in log.splitlines():
        if not line.startswith('CHAIN_F16_'):
            continue
        fields = line.split()
        tag = fields[0][len('CHAIN_F16_'):]
        require(tag in ('SHAPE', 'TRIAL', 'SPAN', 'OUT', 'CAL', 'EMPTY', 'MEMORY', 'DONE'),
                'Unexpected/failure record: ' + line)
        row = {}
        for field in fields[1:]:
            require(field.count('=') == 1, 'Malformed field')
            k, v = field.split('=')
            require(k not in row, 'Duplicate field')
            row[k] = int(v, 16 if k == 'bits' or k.endswith('_hash') else 10)
        rows.setdefault(tag, []).append(row)
    return rows


def indexed(rows, fields, expected):
    result = {}
    for row in rows:
        key = tuple(row[k] for k in fields)
        require(key not in result, 'Duplicate record: ' + str(key))
        result[key] = row
    require(set(result) == set(expected), 'Missing/extra records for ' + str(fields))
    return result


def check_log(log, captured, native, memory_expected):
    data = records(log)
    require(data.get('SHAPE') == [dict(d=128, qheads=2, kvheads=1, tokens=137,
                capacity=256, tile=64, vlenb=128)], 'Shape mismatch')
    require(data.get('DONE') == [dict(trials=4, errors=0)], 'Missing/failed terminal')
    trials = indexed(data.get('TRIAL', []), ['trial'], [(t,) for t in range(4)])
    spans = indexed(data.get('SPAN', []), ['trial', 'slot'],
                    [(t, i) for t in range(4) for i in range(13)])
    outputs = indexed(data.get('OUT', []), ['trial', 'index'],
                      [(t, i) for t in range(4) for i in range(256)])
    memory = indexed(data.get('MEMORY', []), ['trial'], [(t,) for t in range(4)])
    for t in range(4):
        require(memory[t,] == dict(trial=t, **memory_expected),
                'Input/conversion/guards readback fingerprint mismatch')
    calibration = indexed(data.get('CAL', []), ['sample'], [(s,) for s in range(8)])
    empty = indexed(data.get('EMPTY', []), ['sample', 'slot'],
                    [(s, i) for s in range(8) for i in range(13)])
    require(len(captured) == len(native) == 1024, 'Golden size')
    gold = [struct.unpack('<256f', g) for g in (captured, native)]
    max_error = [0.0, 0.0]
    elapsed, returned, partitions = [], [], []
    reference_bits = [outputs[0, i]['bits'] for i in range(256)]
    fc = trials[0,]['fcsr']
    for t, profile in enumerate(ORDER):
        row = trials[t,]
        require(row['profile'] == profile and row['groups'] == 1 and row['errors'] == 0,
                'Failed trial/admission/guards/workcount')
        require(row['fcsr'] == fc and row['fcsr'] & ~3 == 0 and
                row['vcsr'] == row['vstart'] == 0, 'CSR failure')
        require(0 < row['begin'] < row['returned'] < row['end'], 'Missing final drain window')
        if t:
            require(trials[t-1,]['end'] < row['begin'], 'Overlapping trials')
        elapsed.append(row['end'] - row['begin'])
        returned.append(row['returned'] - row['begin'])
        require([outputs[t, i]['bits'] for i in range(256)] == reference_bits,
                'Baseline/profile output not bit-identical')
        for i in range(256):
            bits = outputs[t, i]['bits']
            require(0 <= bits <= 0xffffffff, 'Invalid output bits')
            actual = struct.unpack('<f', struct.pack('<I', bits))[0]
            require(math.isfinite(actual), 'Nonfinite output')
            for j, (atol, rtol) in enumerate(((0.003, 0.02), (0.0002, 0.003))):
                require(math.isfinite(gold[j][i]), 'Nonfinite golden')
                error = abs(actual - gold[j][i])
                max_error[j] = max(max_error[j], error)
                require(error <= atol + rtol * abs(gold[j][i]), 'Numerical mismatch')
        previous, total, phases = row['begin'], 0, Counter()
        for slot, phase in enumerate(PHASES):
            span = spans[t, slot]
            before, after = span['before'], span['after']
            if not profile:
                require(before == after == 0, 'Baseline was instrumented')
            else:
                require(previous <= before < after <= row['returned'], 'Invalid phase sequence/ROI')
                previous = after
                phases[phase] += after - before
                total += after - before
        if profile:
            partitions.append(dict(trial=t, issue_side_cycles=dict(phases),
                outside_spans=elapsed[t]-total, final_drain=row['end']-row['returned'],
                observed_phase_counts=dict(Counter(PHASES))))
    for s in range(8):
        require(calibration[s,]['total'] > 0, 'Missing calibration')
        require(all(0 < empty[s, i]['cycles'] < calibration[s,]['total'] for i in range(13)),
                'Invalid empty stamp cost')
    baseline = statistics.mean([elapsed[t] for t in (0, 3)])
    profile = statistics.mean([elapsed[t] for t in (1, 2)])
    return dict(state='LOG_CHECKED_PENDING_INDEPENDENT_PROTOCOL', trials=4,
        measured_total_cycles=elapsed, measured_to_return_cycles=returned,
        baseline_mean=baseline, profile_mean=profile,
        probe_delta_cycles=profile-baseline, probe_delta_fraction=(profile-baseline)/baseline,
        empty_probe_batch_cycles=[calibration[s,]['total'] for s in range(8)],
        empty_interval_median=statistics.median([r['cycles'] for r in empty.values()]),
        phase_profiles=partitions, max_abs_error_capture=max_error[0],
        max_abs_error_native_tile64=max_error[1], fcsr=fc,
        workcounts=dict(full=1, refill=2, qk=3, scale_mask_softmax=3, pv=3, release_output=1),
        workcount_scope='Observed C phase completions in profile; hardware command counts require trace',
        interpretation='Signed ABBA perturbation includes probe stores, codegen and scheduling/cache effects. '
                       'Empty calibration is not an exact correction; no subtraction from phase totals. '
                       'Phase stamps are issue-side, not exclusive hardware execution/stall attribution.')


def expected_commands():
    commands = []
    for _ in range(4):
        for tile, count in enumerate((64, 64, 9)):
            commands.append(dict(command=4 if tile == 0 else 5,
                v2_full=int(tile == 0), v2_refill=int(tile != 0), v2_row_load=0,
                v2_column_load=0, load=0, release=0, v2_logical_column=0,
                q_external_bytes=512 if tile == 0 else 0,
                kv_external_bytes=count*128*2*2, replay_bytes=0))
            commands += [dict(command=6, v2_full=0, v2_refill=0, v2_row_load=0,
                v2_column_load=1, load=0, release=0, v2_logical_column=1,
                q_external_bytes=0, kv_external_bytes=0, replay_bytes=count*2)] * (2*128)
            commands += [dict(command=2, v2_full=0, v2_refill=0, v2_row_load=1,
                v2_column_load=0, load=1, release=0, v2_logical_column=0,
                q_external_bytes=0, kv_external_bytes=0, replay_bytes=256)] * (2*count)
        commands.append(dict(command=3, v2_full=0, v2_refill=0, v2_row_load=0,
            v2_column_load=0, load=0, release=1, v2_logical_column=0,
            q_external_bytes=0, kv_external_bytes=0, replay_bytes=0))
    return commands


def check_hardware_work(log):
    expected = expected_commands()
    rows = []
    totals = Counter()
    for line in log.splitlines():
        require(not re.search(r'(?:UVM_FATAL|UVM_ERROR)\s*:', line) and
                not any(word in line for word in ('Fatal:', 'Error:', 'TIMEOUT')),
                'Simulator failure/timeout')
        if not line.startswith('[AKV_PERF] '):
            continue
        row = {}
        for token in line[len('[AKV_PERF] '):].split():
            require(token.count('=') == 1, 'Malformed AKV performance record')
            k, v = token.split('=')
            require(k not in row and re.fullmatch('[0-9]+', v), 'Invalid AKV counter')
            row[k] = int(v)
        index = len(rows)
        require(index < len(expected) and row['seq'] == index + 1, 'Extra/out-of-order AKV command')
        require(all(row.get(k) == v for k, v in expected[index].items()),
                'Wrong command work/shape at seq ' + str(index + 1))
        require(row['success'] == 1 and row['busy_cycles'] > 0 and
                all(row[k] == 0 for k in ('fault', 'validation_fault', 'validation_error',
                    'read_fault', 'full', 'refill', 'v2_column_panel', 'v2_rejected')),
                'AKV fault/legacy/experimental work')
        require(row['context_ready'] == int(row['command'] != 3), 'Resident lifecycle mismatch')
        for k in ('v2_full', 'v2_refill', 'v2_row_load', 'v2_column_load', 'release',
                  'q_external_bytes', 'kv_external_bytes', 'replay_bytes', 'busy_cycles'):
            totals[k] += row[k]
        rows.append(row)
    require(len(rows) == len(expected), 'Missing FULL/REFILL/QK/PV/release work evidence; require +AKV_PERF')
    return dict(complete_calls=4, commands=len(rows), totals=dict(totals),
                call_busy_cycles=[sum(row['busy_cycles'] for row in rows[t*1046:(t+1)*1046])
                                  for t in range(4)],
                per_call_commands=1046, full_per_call=1, refill_per_call=2,
                k_columns_per_call=768, v_rows_per_call=274, release_per_call=1)


def check_run(log_path: Path, build_dir: Path) -> dict:
    log_path, build_dir = Path(log_path).resolve(), Path(build_dir).resolve()
    build_path = build_dir / 'build.json'
    build = verify_build(build_path)
    require(build['shape']['query_head_indices'] == [0, 1] and
            build['shape']['kv_head_index'] == 0 and build['shape']['kv_heads'] == 1,
            'Not the single real KV0/GQA2 group')
    text = log_path.read_text()
    result = check_log(text, Path(build['golden']['captured']).read_bytes(),
                       Path(build['golden']['native_tile64']).read_bytes(), build['memory_expected'])
    work = check_hardware_work(text)
    require(all(busy <= elapsed for busy, elapsed in
                zip(work['call_busy_cycles'], result['measured_total_cycles'])),
            'Native work exceeds complete-call ROI')
    result.update(state='PASS', scope='One captured Qwen3 F16 Decode KV head0/Q heads0,1; D128/GQA2/137/tile64',
        complete_calls=4, full_call_count=4, phase=result['phase_profiles'], work=work,
        overhead=dict(delta_cycles=result['probe_delta_cycles'],
                      delta_fraction=result['probe_delta_fraction'],
                      empty_batch_cycles=result['empty_probe_batch_cycles'],
                      empty_interval_median=result['empty_interval_median']),
        guard_fingerprints_checked=4, output_values_checked=1024,
        build=str(build_path), build_sha256=sha(build_path), elf_sha256=build['elf_sha256'],
        source_pins_sha256=build['source_pins_sha256'], log=str(log_path), log_sha256=sha(log_path),
        image_contract=build['image_contract'], independent_protocol_checked=False,
        current_soc_identity_checked=False,
        acceptance_scope='Functional/profile PASS only; main runner separately checks SoC image and protocol')
    return result


def check_vector_workcounts(path):
    counts = Counter()
    with path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['event'] == 'config':
                require((int(row['nr_lanes']), int(row['vlen_bits'])) == (4, 1024), 'Trace image mismatch')
            if row['event'] != 'alloc':
                continue
            insn = int(row['insn'], 16)
            # kcol v8 (rs1=a0), resident V row v8:v9 (rs1=a0).
            if insn == 0x0005745b: counts['k_column_commands'] += 1
            elif insn == 0x0205345b: counts['v_row_commands'] += 1
    require(counts == Counter(k_column_commands=4*3*2*128, v_row_commands=4*2*137),
            'Vector workcounts mismatch: ' + str(counts))
    return dict(counts)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--log', type=Path, required=True)
    p.add_argument('--trace', type=Path)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = check_run(args.log, args.build.parent)
    if args.trace:
        result['vector_workcounts'] = check_vector_workcounts(args.trace)
        result['trace_sha256'] = sha(args.trace)
    if args.output:
        out = args.output.resolve()
        require(out.parent.name.startswith('chain_f16_') and
                '_20261107_' in out.parent.name and not out.exists(), 'Output ownership/freshness')
        out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
