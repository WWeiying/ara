#!/usr/bin/env python3
"""Fail-closed ABBA correctness/work checker. PASS does not require a speedup."""
import argparse
import csv
import importlib.util
import json
import math
import re
import struct
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('akv_pair_eval_contract', HERE / 'build.py')
contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contract)
require, sha = contract.require, contract.sha
ORDER = contract.ORDER
PERF_FIELDS = set(('seq id command success fault validation_fault validation_error read_fault '
    'context_ready busy_cycles full refill load release v2_full v2_refill v2_row_load '
    'v2_column_load v2_column_panel v2_logical_column v2_k_view_bank_cycles '
    'v2_bank_conflict_cycles v2_rejected q_external_bytes kv_external_bytes replay_bytes '
    'replay_backpressure_cycles read_ranges translations ar r_beats read_payload_bytes '
    'store_wait_cycles read_backpressure_cycles read_outstanding_occ_sum '
    'read_outstanding_max read_outstanding_full_cycles').split())
SUMMARY_FIELDS = PERF_FIELDS - set('seq id command success fault validation_fault validation_error '
    'read_fault context_ready'.split()) | set('records success_records fault_records validation_fault_records'.split())
SCHEMAS = {
    'SHAPE': set('d qheads kvheads tokens capacity tile vlenb'.split()),
    'TRIAL': set(('trial arm begin returned end fcsr vcsr vstart initial_fcsr initial_vcsr '
                  'initial_vstart groups errors').split()),
    'MEMORY': set('trial query_hash guard_hash guard_bytes'.split()),
    'OUT': set('trial index bits'.split()),
    'DATA': set('data_hash data_bytes checks errors'.split()),
    'DONE': set('trials errors'.split()),
}


def verify_build(build_dir):
    directory = Path(build_dir).resolve()
    m = json.loads((directory / 'build.json').read_text())
    require(type(m['schema']) is int and m['schema'] == 1 and m['state'] == 'BUILT_NOT_EXECUTED' and
            m['target_executed'] is False and m['rtl_executed'] is False and
            m['performance_measured'] is False, 'Build schema/state mismatch')
    require(m['sdk_head'] == contract.SDK_COMMIT and m['sdk_tree'] == contract.SDK_TREE and
            m['common_tree'] == contract.COMMON_TREE and m['sdk_unmodified'] is True and
            m['dirty_asm_excluded'] is True and m['all_runtime_objects_recompiled'] is True,
            'Not the exact archive-pinned native SDK')
    require(m['shape'] == contract.SHAPE and m['order'] == ORDER and
            m['image_contract'] == contract.IMAGE and
            m['initial_csr'] == dict(fcsr=0, vcsr=0, vstart=0), 'Shape/order/CSR/image mismatch')
    require(m['data'] == str(contract.DATA) and m['capture'] == str(contract.CAPTURE),
            'Not the accepted real input')
    require(m['toolchain'] == dict(target=str(contract.CC.resolve()),
            host=str(contract.HOST_CC), zcc=False), 'Toolchain mismatch')
    data_pins = contract.validate_data()
    require(m['memory_expected'] == contract.memory_expected(), 'Memory contract mismatch')
    elf, pinfile = Path(m['elf']), Path(m['source_pins'])
    require(elf == directory / 'akv_pair_eval.elf' and elf.read_bytes()[:4] == b'\x7fELF' and
            sha(elf) == m['elf_sha256'], 'ELF identity mismatch')
    require(pinfile == directory / 'source-pins.json' and sha(pinfile) == m['source_pins_sha256'],
            'Source pin inventory drift')
    pins = json.loads(pinfile.read_text())
    required = {**data_pins, **{str(HERE / n): sha(HERE / n) for n in contract.OWN_FILES}}
    require(all(pins.get(p) == digest for p, digest in required.items()), 'Missing mandatory input pin')
    require(not any(str(HERE / n) in pins for n in ('run.py', 'README.md', 'test_owner.py')),
            'Build must not seal owner files; runner pins them separately')
    for inventory in (pins, m['artifacts']):
        require(isinstance(inventory, dict) and inventory, 'Empty identity inventory')
        for p, digest in inventory.items():
            require(Path(p).is_file() and re.fullmatch('[0-9a-f]{64}', digest) and sha(p) == digest,
                    'Input/artifact drift: ' + p)
    archive = Path(m['sdk_archive'])
    require(archive == directory / 'inputs/sdk-785084122.tar' and
            sha(archive) == m['sdk_archive_sha256'], 'Archive identity mismatch')
    sdk = directory / 'inputs/software/akv'
    actual_sdk = {str(p.relative_to(directory / 'inputs')): sha(p)
                  for p in sdk.rglob('*') if p.is_file()}
    require(actual_sdk == m['SDKpins'] and actual_sdk, 'Archived SDK file inventory mismatch')
    with contract.tarfile.open(archive) as tar:
        for member in tar.getmembers():
            require(member.isfile() or member.isdir(), 'Unexpected archive link')
            if member.isfile():
                p = directory / 'inputs' / member.name
                require(p.is_relative_to(directory / 'inputs') and '..' not in Path(member.name).parts and
                        sha(p) == contract.hashlib.sha256(tar.extractfile(member).read()).hexdigest(),
                        'SDK/runtime differs from original archive')
    for p in (directory / 'inputs').rglob('*'):
        if p.is_file():
            require(pins.get(str(p)) == sha(p) and m['artifacts'].get(str(p)) == sha(p),
                    'Missing SDK/runtime archive pin')
    golden = m['golden']
    require(golden == dict(captured=str(contract.DATA / 'decode_golden.bin'),
        captured_sha256=contract.DATA_SHA['decode_golden'],
        native_tile64=str(directory / 'native_golden.bin'), native_tile64_sha256=contract.NATIVE_SHA,
        capture_atol=0.003, capture_rtol=0.02, native_atol=0.0002, native_rtol=0.003),
        'Numerical reference/threshold mismatch')
    require(sha(golden['captured']) == golden['captured_sha256'] and
            sha(golden['native_tile64']) == contract.NATIVE_SHA, 'Golden drift')
    require(m['objects_recompiled'] == len(m['objects']) == len(set(m['objects'])) == 16,
            'Incomplete fresh object build')
    commands_path = directory / 'commands.json'
    require(m['compile_commands'] == str(commands_path) and str(commands_path) in m['artifacts'],
            'Missing full compiler commands')
    commands = json.loads(commands_path.read_text())
    require(all(c['returncode'] == 0 and c['cwd'] == str(directory) for c in commands),
            'Incomplete compiler commands')
    compiles = [c for c in commands if c['label'].startswith('compile-')]
    require(len(compiles) == 16 and {c['argv'][-1] for c in compiles} == set(m['objects']),
            'Missing object compile provenance')
    common = directory / 'inputs/apps/common'
    sources = [HERE / 'main.c', directory / 'data.S',
               *[common / n for n in ('crt0.S', 'printf.c', 'string.c', 'serial.c',
                                      'util.c', 'print_trap_cause.c')],
               *[sdk / 'src' / n for n in ('akv_runtime.c', 'akv_decode.c', 'akv_features.c',
                   'akv_prefill_reference.c', 'akv_native_riscv.c', 'akv_v2_native_riscv.c',
                   'akv_v2_attention_rvv.S', 'akv_attention_rvv.S')]]
    require([c['argv'][c['argv'].index('-c')+1] for c in compiles] == list(map(str, sources)),
            'Not all objects compiled from the exact archive/caller sources')
    for c in compiles:
        require(c['argv'][0] == str(contract.CC.resolve()) and '-c' in c['argv'] and
                '-DAKV_REFILL_OVERLAP=0' in c['argv'] and
                '-DAKV_PAIR_HOST_TEST' not in c['argv'], 'Not a native target compilation')
    for depfile in directory.glob('*.d'):
        require(str(depfile) in m['artifacts'], 'Unpinned compiler dependency inventory')
        for p in contract.dependency_inputs(depfile):
            require(pins.get(str(p)) == sha(p), 'Missing compiler header/source pin')
    for name in ('expected.h', 'data.S', 'link.ld', 'native_golden.bin'):
        require(pins.get(str(directory / name)) == sha(directory / name), 'Missing generated input pin')
    for p in [str(elf), str(pinfile), str(archive), *m['objects'], str(directory / 'native_golden.bin')]:
        require(m['artifacts'].get(p) == sha(p), 'Missing mandatory artifact: ' + p)
    return m


def classify_simulator(log):
    summaries = Counter()
    for number, line in enumerate(log.splitlines(), 1):
        if re.search(r'\bUVM_(ERROR|FATAL)\b', line):
            match = re.fullmatch(r'[ \t]*(UVM_ERROR|UVM_FATAL)[ \t]*:[ \t]*0[ \t]*', line)
            require(match is not None, 'UVM event/nonzero or malformed summary at line ' + str(number))
            summaries[match[1]] += 1
        require(not re.search(r'Fatal:|Error:|Error-|\bFAILED\b|\bTIMEOUT\b|\btimeout\b|\$fatal', line),
                'Simulator failure/timeout at line ' + str(number))
    success = re.findall(r'Core Test \*\*\* SUCCESS \*\*\* \(tohost = ([0-9]+)\)', log)
    require(success == ['0'], 'Missing/duplicate/nonzero successful EOC')
    return dict(strict_zero_summary_lines=dict(summaries), nonzero_summaries=0, events=0)


def parse_fields(text, schema, hex_keys=()):
    row = {}
    for token in text.split():
        require(token.count('=') == 1, 'Malformed record field')
        key, value = token.split('=')
        require(key not in row and key in schema, 'Duplicate/unknown field: ' + key)
        pattern = '[0-9a-fA-F]{8}' if key == 'bits' else (
            '[0-9a-fA-F]{16}' if key in hex_keys else '[0-9]+')
        require(re.fullmatch(pattern, value) is not None, 'Invalid field: ' + key)
        row[key] = int(value, 16 if key in hex_keys else 10)
        require(row[key] <= (1 << 64)-1, 'Counter overflow')
    require(set(row) == schema, 'Missing record field: ' + str(schema-set(row)))
    return row


def records(log):
    rows = {}
    sequence = []
    for line in log.splitlines():
        if 'AKV_PAIR_' not in line:
            continue
        require(line.startswith('AKV_PAIR_') and ' ' in line, 'Malformed firmware record')
        tag, fields = line[len('AKV_PAIR_'):].split(' ', 1)
        require(tag in SCHEMAS, 'Unexpected/failure firmware record: ' + tag)
        row = parse_fields(fields, SCHEMAS[tag], ('bits', 'data_hash', 'query_hash', 'guard_hash'))
        rows.setdefault(tag, []).append(row)
        sequence.append((tag, row))
    expected = [('SHAPE', {})]
    for t in range(4):
        expected += [('TRIAL', dict(trial=t)), ('MEMORY', dict(trial=t))]
        expected += [('OUT', dict(trial=t, index=i)) for i in range(256)]
    expected += [('DATA', {}), ('DONE', {})]
    require(len(sequence) == len(expected) and all(tag == etag and
        all(row.get(k) == v for k, v in values.items())
        for (tag, row), (etag, values) in zip(sequence, expected)),
        'Missing/duplicate/out-of-order firmware records')
    return rows


def check_log(log, captured, native, memory_expected):
    severity = classify_simulator(log)
    rows = records(log)
    require(rows['SHAPE'] == [dict(d=128, qheads=2, kvheads=1, tokens=137,
            capacity=256, tile=64, vlenb=128)], 'Shape mismatch')
    require(rows['DONE'] == [dict(trials=4, errors=0)], 'Firmware errors/noncompletion')
    require(rows['DATA'] == [dict(data_hash=memory_expected['data_hash'],
            data_bytes=memory_expected['data_bytes'], checks=1, errors=0)], 'Full data readback mismatch')
    require(len(captured) == len(native) == 1024, 'Golden size mismatch')
    gold = [struct.unpack('<256f', value) for value in (captured, native)]
    output_bits = [r['bits'] for r in rows['OUT']]
    elapsed, returned, maxima = [], [], [0.0, 0.0]
    fc = rows['TRIAL'][0]['fcsr']
    for t, arm in enumerate(ORDER):
        trial, memory = rows['TRIAL'][t], rows['MEMORY'][t]
        require(trial['arm'] == arm and trial['groups'] == 1 and trial['errors'] == 0,
                'Firmware/admission/group/arm failure')
        require(trial['initial_fcsr'] == trial['initial_vcsr'] == trial['initial_vstart'] == 0,
                'Arms did not start from the same zero CSR')
        require(trial['fcsr'] == fc and fc & ~3 == 0 and
                trial['vcsr'] == trial['vstart'] == 0, 'CSR/fflags mismatch')
        require(0 < trial['begin'] < trial['returned'] < trial['end'], 'Invalid complete-call timing')
        if t:
            require(rows['TRIAL'][t-1]['end'] < trial['begin'], 'Overlapping trials')
        elapsed.append(trial['end']-trial['begin'])
        returned.append(trial['returned']-trial['begin'])
        require(memory == dict(trial=t, query_hash=memory_expected['query_hash'],
                guard_hash=memory_expected['guard_hash'], guard_bytes=memory_expected['guard_bytes']),
                'Query/guards/inactive workspace readback mismatch')
        bits = output_bits[t*256:(t+1)*256]
        require(bits == output_bits[:256], 'Candidate/generic raw output bits differ')
        for i, value in enumerate(bits):
            actual = struct.unpack('<f', struct.pack('<I', value))[0]
            require(math.isfinite(actual), 'Nonfinite output')
            for j, (atol, rtol) in enumerate(((0.003, 0.02), (0.0002, 0.003))):
                expected = gold[j][i]
                require(math.isfinite(expected), 'Nonfinite golden')
                error = abs(actual-expected)
                maxima[j] = max(maxima[j], error)
                require(error <= atol + rtol*abs(expected), 'Numerical mismatch')
    generic, candidate = (elapsed[0]+elapsed[3])/2, (elapsed[1]+elapsed[2])/2
    return dict(state='LOG_CHECKED', measured_total_cycles=elapsed,
        measured_to_return_cycles=returned, final_drain_cycles=[a-b for a, b in zip(elapsed, returned)],
        generic_mean_cycles=generic, candidate_mean_cycles=candidate,
        candidate_over_generic=candidate/generic, generic_over_candidate=generic/candidate,
        cycle_reduction_fraction=1-candidate/generic,
        paired_candidate_over_generic=[elapsed[1]/elapsed[0], elapsed[2]/elapsed[3]],
        order=ORDER, fcsr=fc, vcsr=0, vstart=0, max_abs_error_capture=maxima[0],
        max_abs_error_native_tile64=maxima[1], uvm_severity_classification=severity,
        output_values_checked=1024, guard_fingerprints_checked=4, full_data_hash_checks=1,
        performance_acceptance=False)


def expected_commands():
    commands = []

    def command(code, **values):
        row = dict(command=code, v2_full=0, v2_refill=0, v2_row_load=0, v2_column_load=0,
            v2_column_panel=0, v2_logical_column=0, full=0, refill=0, load=0, release=0,
            q_external_bytes=0, kv_external_bytes=0, replay_bytes=0)
        row.update(values)
        return row

    for arm in ORDER:
        for tile, count in enumerate((64, 64, 9)):
            commands.append(command(4 if tile == 0 else 5,
                v2_full=int(tile == 0), v2_refill=int(tile != 0),
                q_external_bytes=512 if tile == 0 else 0, kv_external_bytes=count*128*2*2))
            columns = 32 if arm else 256
            commands += [command(6, v2_column_load=1, v2_column_panel=arm,
                v2_logical_column=4 if arm else 1, replay_bytes=count*2*(4 if arm else 1))
                for _ in range(columns)]
            commands += [command(2, v2_row_load=1, load=1, replay_bytes=256)
                         for _ in range(count*(1 if arm else 2))]
        commands.append(command(3, release=1))
    return commands


def check_hardware_work(log):
    classify_simulator(log)
    expected, rows, summaries = expected_commands(), [], []
    totals = Counter()
    for line in log.splitlines():
        if '[AKV_PERF]' in line:
            require(line.startswith('[AKV_PERF] '), 'Malformed AKV performance prefix')
            row = parse_fields(line[len('[AKV_PERF] '):], PERF_FIELDS)
            index = len(rows)
            require(index < len(expected) and row['seq'] == index+1, 'Extra/out-of-order command seq')
            require(all(row[k] == value for k, value in expected[index].items()),
                    'Wrong native command work/payload at seq ' + str(index+1))
            require(row['success'] == 1 and row['busy_cycles'] > 0 and
                    all(row[k] == 0 for k in ('fault', 'validation_fault', 'validation_error',
                                             'read_fault', 'v2_rejected')), 'AKV fault/rejected command')
            require(row['context_ready'] == int(row['command'] != 3), 'Resident lifecycle mismatch')
            require(row['read_payload_bytes'] == row['q_external_bytes']+row['kv_external_bytes'] +
                    (64 if row['v2_full'] else 0), 'Reader payload/descriptor byte mismatch')
            for key in SUMMARY_FIELDS - {'records', 'success_records', 'fault_records', 'validation_fault_records'}:
                if key == 'read_outstanding_max':
                    totals[key] = max(totals[key], row[key])
                else:
                    totals[key] += row[key]
            rows.append(row)
        elif '[AKV_PERF_SUMMARY]' in line:
            require(line.startswith('[AKV_PERF_SUMMARY] '), 'Malformed summary prefix')
            summaries.append(parse_fields(line[len('[AKV_PERF_SUMMARY] '):], SUMMARY_FIELDS))
    require(len(rows) == len(expected) == 2566, 'Missing native commands; require +AKV_PERF')
    summary = dict(totals, records=2566, success_records=2566, fault_records=0, validation_fault_records=0)
    require(summaries == [summary], 'Missing/duplicate/inconsistent AKV summary; require +AKV_SUMMARY')
    sizes = [1046, 237, 237, 1046]
    calls, offset = [], 0
    for t, size in enumerate(sizes):
        batch = rows[offset:offset+size]
        calls.append(dict(trial=t, arm=ORDER[t], commands=size,
            busy_cycles=sum(row['busy_cycles'] for row in batch),
            full=1, refill=2, release=1, k_column_commands=0 if ORDER[t] else 768,
            k_panel4_commands=96 if ORDER[t] else 0, v_row_commands=137 if ORDER[t] else 274))
        offset += size
    return dict(commands=2566, complete_calls=4, per_call_commands=sizes,
                calls=calls, totals=summary)


def check_run(log_path, build_dir):
    log_path, build_dir = Path(log_path).resolve(), Path(build_dir).resolve()
    build = verify_build(build_dir)
    text = log_path.read_text()
    result = check_log(text, Path(build['golden']['captured']).read_bytes(),
                       Path(build['golden']['native_tile64']).read_bytes(), build['memory_expected'])
    work = check_hardware_work(text)
    require(all(call['busy_cycles'] <= elapsed for call, elapsed in
                zip(work['calls'], result['measured_total_cycles'])), 'Native work exceeds complete-call ROI')
    result.update(state='PASS', work=work, full_call_count=4,
        scope='One real Qwen3 F16 KV0/Q0,1 group; D128/GQA2/T137/cap256/tile64; ABBA',
        build=str(build_dir / 'build.json'), build_sha256=sha(build_dir / 'build.json'),
        elf_sha256=build['elf_sha256'], source_pins_sha256=build['source_pins_sha256'],
        log=str(log_path), log_sha256=sha(log_path), image_contract=build['image_contract'],
        independent_vector_work_checked=False, independent_protocol_checked=False,
        acceptance_scope='Correctness/native work only. Runner must check image, vector signatures and UVM. '
                         'Cycles/ratios are observations, not a speedup acceptance.')
    return result


def expected_vector_signatures():
    result = []
    for arm in ORDER:
        for count in (64, 64, 9):
            result += [0x0205745b if arm else 0x0005745b]*(32 if arm else 256)
            result += [0x0205345b]*(count*(1 if arm else 2))
    return result


def check_vector_workcounts(vector_trace_path, build_dir):
    build = verify_build(build_dir)
    path = Path(vector_trace_path)
    counts, actual, configs = Counter(), [], 0
    last_cycle = -1
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        required = set('cycle event insn nr_lanes vlen_bits'.split())
        require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)) and
                required <= set(reader.fieldnames), 'Vector trace schema mismatch')
        for row in reader:
            require(None not in row and all(row[k] is not None for k in required), 'Malformed vector row')
            require(re.fullmatch('[0-9]+', row['cycle']) is not None, 'Invalid vector cycle')
            cycle = int(row['cycle'])
            require(cycle >= last_cycle, 'Vector trace cycle/reset drift')
            last_cycle = cycle
            require((row['nr_lanes'], row['vlen_bits']) == ('4', '1024'), 'Vector image mismatch')
            if row['event'] == 'config':
                configs += 1
            require(row['event'] != 'reset', 'Unexpected mid-run vector reset')
            if row['event'] != 'alloc':
                continue
            require(re.fullmatch('[0-9a-fA-F]{8}', row['insn']) is not None, 'Invalid vector instruction')
            insn = int(row['insn'], 16)
            if insn & 0x707f not in (0x305b, 0x705b):
                continue
            require(insn in (0x0005745b, 0x0205745b, 0x0205345b), 'Unexpected replay instruction signature')
            actual.append(insn)
            counts[{0x0005745b: 'k_column_commands', 0x0205745b: 'k_panel4_commands',
                    0x0205345b: 'v_row_commands'}[insn]] += 1
    require(configs == 1 and actual == expected_vector_signatures(),
            'Independent vector command signature/order/count mismatch: ' + str(counts))
    require(counts == dict(k_column_commands=1536, k_panel4_commands=192, v_row_commands=822),
            'Independent replay work formula mismatch')
    return dict(counts=dict(counts), replay_commands=2550, native_commands_with_lifecycle=2566,
                per_call_commands=[1046, 237, 237, 1046], ordered_signatures_checked=True,
                trace_sha256=sha(path), elf_sha256=build['elf_sha256'])


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    directory = args.build.parent if args.build.name == 'build.json' else args.build
    result = check_run(args.log, directory)
    result['vector_workcounts'] = check_vector_workcounts(args.trace, directory)
    result['independent_vector_work_checked'] = True
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
