#!/usr/bin/env python3
"""Fail-closed SmolLM2 numerical, payload, CSR and replay-work checks."""
import argparse
from collections import Counter
import csv
import importlib.util
import json
import math
from pathlib import Path
import re
import struct
import tarfile

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('smollm_regression_contract', HERE/'build.py')
contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contract)
require, sha = contract.require, contract.sha
PERF_FIELDS = set(('seq id command success fault validation_fault validation_error read_fault '
    'context_ready busy_cycles full refill load release v2_full v2_refill v2_row_load '
    'v2_column_load v2_column_panel v2_logical_column v2_k_view_bank_cycles '
    'v2_bank_conflict_cycles v2_rejected q_external_bytes kv_external_bytes replay_bytes '
    'replay_backpressure_cycles read_ranges translations ar r_beats read_payload_bytes '
    'store_wait_cycles read_backpressure_cycles read_outstanding_occ_sum '
    'read_outstanding_max read_outstanding_full_cycles').split())
SUMMARY_FIELDS = PERF_FIELDS-set(('seq id command success fault validation_fault validation_error '
    'read_fault context_ready').split()) | set('records success_records fault_records validation_fault_records'.split())
SCHEMAS = {
    'SHAPE': set('d qheads kvheads tokens capacity tile vlenb'.split()),
    'TRIAL': set(('trial arm begin returned end fcsr vcsr vstart initial_fcsr initial_vcsr '
                  'initial_vstart groups errors').split()),
    'MEMORY': set('trial query_hash guard_hash guard_bytes'.split()),
    'OUT': set('trial index bits'.split()),
    'DATA': set('data_hash data_bytes query_f32_hash key_hash value_hash mask_hash checks errors'.split()),
    'DONE': set('trials errors'.split()),
}
HEX_KEYS = set('bits data_hash query_hash guard_hash query_f32_hash key_hash value_hash mask_hash'.split())


def verify_build(build_dir):
    directory = Path(build_dir).resolve()
    m = json.loads((directory/'build.json').read_text())
    require(m['schema'] == contract.SCHEMA and m['state'] == 'BUILT_NOT_EXECUTED' and
            all(m[k] is False for k in ('target_executed', 'rtl_executed', 'performance_measured',
                                        'hardware_changed', 'old_runtime_objects_reused')),
            'Build schema/execution state mismatch')
    require((m['sdk_head'], m['sdk_tree'], m['common_tree']) ==
            (contract.SDK_COMMIT, contract.SDK_TREE, contract.COMMON_TREE) and
            all(m[k] is True for k in ('sdk_unmodified', 'dirty_asm_excluded',
                                       'all_runtime_objects_recompiled')), 'SDK provenance mismatch')
    require(m['shape'] == contract.SHAPE and m['order'] == contract.ORDER and
            m['image_contract'] == contract.IMAGE and m['fixed_image_sha256'] == contract.FIXED_IMAGE_SHA and
            m['initial_csr'] == dict(fcsr=0, vcsr=0, vstart=0), 'Shape/order/image/CSR mismatch')
    require(m['toolchain'] == dict(target=str(contract.CC.resolve()), host=str(contract.HOST_CC.resolve()),
                                   zcc=False), 'Unreviewed toolchain')
    require(m['work'] == dict(per_call_commands=[209, 92, 92, 209], total_commands=602), 'Work contract drift')
    require(m['environment'] == dict(AKV_PAIR_HEADS='0/1/1/0 local fixture; all other names NULL'),
            'Unexpected selector fixture contract')
    data = directory/'data'
    require(m['data'] == str(data) and m['capture'] == str(contract.CAPTURE), 'Wrong selected capture')
    blobs, capture_pins, provenance = contract.read_capture()
    require(m['provenance'] == provenance, 'Capture provenance/scope drift')
    for name, raw in blobs.items():
        require((data/(name+'.bin')).read_bytes() == raw, 'Materialized head mapping/data drift: '+name)
    native = data/'native_golden.bin'
    require(len(native.read_bytes()) == 768, 'Native oracle size mismatch')
    require(m['memory_expected'] == contract.memory_expected(blobs, native.read_bytes()), 'Memory/FNV mismatch')
    require(m['golden'] == dict(captured=str(data/'decode_golden.bin'),
        captured_sha256=sha(data/'decode_golden.bin'), native_tile64=str(native),
        native_tile64_sha256=sha(native), capture_atol=0.003, capture_rtol=0.02,
        native_atol=0.0002, native_rtol=0.003), 'Golden identity/tolerance drift')
    require(m['native_reference'] == dict(source_origin=contract.SDK_COMMIT+':'+contract.REFERENCE_SOURCE,
        source_sha256=contract.REFERENCE_SHA, parameterization='D64/H3/T5/cap256/scale0.125; no backend linked'),
        'Independent reference origin drift')
    elf, pinfile = directory/'akv_pair_smollm.elf', directory/'source-pins.json'
    require(m['elf'] == str(elf) and elf.read_bytes()[:4] == b'\x7fELF' and
            sha(elf) == m['elf_sha256'] and m['source_pins'] == str(pinfile) and
            sha(pinfile) == m['source_pins_sha256'], 'ELF/source inventory identity mismatch')
    pins = json.loads(pinfile.read_text())
    required = {**capture_pins, **{str(HERE/n): sha(HERE/n) for n in contract.OWN_FILES}}
    require(all(pins.get(p) == h for p, h in required.items()), 'Missing sealed capture/owned source')
    require(not any(str(HERE.parent/n) in pins for n in ('build.py', 'main.c', 'check.py', 'run.py',
                                                       'README.md', 'test_eval.py', 'test_owner.py')),
            'Regression must not seal mutable owner/main-bench files')
    for inventory in (pins, m['artifacts']):
        require(isinstance(inventory, dict) and inventory, 'Empty source/artifact inventory')
        for p, digest in inventory.items():
            require(Path(p).is_file() and not Path(p).is_symlink() and
                    re.fullmatch('[0-9a-f]{64}', digest) is not None and sha(p) == digest,
                    'Source/artifact pin drift: '+p)
    archive = directory/'inputs/sdk-785084122.tar'
    require(m['sdk_archive'] == str(archive) and sha(archive) == m['sdk_archive_sha256'] == contract.ARCHIVE_SHA,
            'Exact committed archive identity drift')
    with tarfile.open(archive) as tar:
        archived_files = {str(archive)}
        for member in tar.getmembers():
            require((member.isfile() or member.isdir()) and not Path(member.name).is_absolute() and
                    '..' not in Path(member.name).parts, 'Unsafe SDK archive')
            if member.isfile():
                archived_files.add(str(directory/'inputs'/member.name))
                raw = tar.extractfile(member).read()
                require((directory/'inputs'/member.name).read_bytes() == raw,
                        'SDK/common no longer matches exact archive')
    require({str(p) for p in (directory/'inputs').rglob('*') if p.is_file()} == archived_files,
            'Extra/missing input outside frozen archive')
    inputs, sdk = directory/'inputs', directory/'inputs/software/akv'
    require(m['SDKpins'] == {str(p.relative_to(inputs)): sha(p) for p in sdk.rglob('*') if p.is_file()} and
            m['SDKpins'], 'SDK file inventory drift')
    for base in (inputs, data):
        for p in base.rglob('*'):
            if p.is_file():
                require(pins.get(str(p)) == sha(p) and m['artifacts'].get(str(p)) == sha(p),
                        'Unpinned archive/runtime/data input')
    require((directory/'expected.h').read_text() == contract.expected_header(m['memory_expected']) and
            (directory/'data.S').read_text() == contract.data_assembly(data), 'Generated payload/header drift')
    common = inputs/'apps/common'
    sources = [HERE/'main.c', directory/'data.S', *[common/n for n in contract.COMMON],
               *[sdk/'src'/n for n in contract.TARGET_SDK]]
    objects = [str(directory/('%02d_%s.o' % (i, src.stem))) for i, src in enumerate(sources)]
    require(m['objects'] == objects and m['objects_recompiled'] == len(objects) == 16,
            'Old/missing runtime object')
    commandfile = directory/'commands.json'
    require(m['compile_commands'] == str(commandfile), 'Missing command inventory')
    commands = json.loads(commandfile.read_text())
    require(all(c['returncode'] == 0 and c['cwd'] == str(directory) for c in commands), 'Failed compiler command')
    compiles = [c['argv'] for c in commands if c['label'].startswith('compile-')]
    require(len(compiles) == 16, 'Incomplete fresh native compiles')
    for argv, src, obj in zip(compiles, sources, objects):
        require(argv[0] == str(contract.CC) and argv.count('-c') == argv.count('-o') == 1 and
                argv[argv.index('-c')+1] == str(src) and argv[argv.index('-o')+1] == obj and
                [a for a in argv if a.startswith('-march=')] == ['-march=rv64gcv_zfh_zvfh'] and
                all(f in argv for f in ('-fno-fast-math', '-ffp-contract=off', '-DAKV_REFILL_OVERLAP=0')) and
                not any('HOST_TEST' in a or a in ('-ffast-math', '-Ofast', '-ffp-contract=fast') for a in argv),
                'Target compile source/FP/ISA/fixture mismatch')
    links = [c['argv'] for c in commands if c['label'] == 'link']
    require(len(links) == 1 and all(links[0].count(o) == 1 for o in objects) and
            [s for s in links[0] if s.endswith('.o')] == objects, 'Foreign/missing object at link')
    for p in [str(elf), str(pinfile), str(commandfile), *objects]:
        require(m['artifacts'].get(p) == sha(p), 'Unpinned mandatory build artifact')
    return m


def parse_fields(text, schema):
    row = {}
    for token in text.split():
        require(token.count('=') == 1, 'Malformed key=value')
        key, value = token.split('=')
        require(key in schema and key not in row, 'Unknown/duplicate field: '+key)
        pattern = '[0-9a-fA-F]{8}' if key == 'bits' else '[0-9a-fA-F]{16}' if key in HEX_KEYS else '[0-9]+'
        require(re.fullmatch(pattern, value) is not None, 'Malformed counter/hex: '+key)
        row[key] = int(value, 16 if key in HEX_KEYS else 10)
        require(row[key] <= (1 << 64)-1, 'Unsigned counter overflow')
    require(set(row) == schema, 'Missing record field')
    return row


def classify_simulator(text):
    summaries = Counter()
    for line in text.splitlines():
        if re.search(r'\bUVM_(ERROR|FATAL)\b', line):
            match = re.fullmatch(r'\s*(UVM_ERROR|UVM_FATAL)\s*:\s*0\s*', line)
            require(match is not None, 'UVM event/nonzero/malformed severity')
            summaries[match[1]] += 1
        require(not re.search(r'Fatal:|Error:|Error-|\b(?:FAIL|FAILED|TIMEOUT)\b|\$fatal', line, re.I),
                'Simulator/firmware failure')
    require(summaries == dict(UVM_ERROR=1, UVM_FATAL=1), 'Missing/duplicate zero UVM summaries')
    require(re.findall(r'Core Test \*\*\* SUCCESS \*\*\* \(tohost = ([0-9]+)\)', text) == ['0'],
            'Missing/duplicate/nonzero EOC')
    require(text.find('AKV_SMOL_DONE ') < text.find('Core Test *** SUCCESS ***'), 'Early EOC')


def firmware_records(text):
    result, sequence = {}, []
    for line in text.splitlines():
        if 'AKV_SMOL_' not in line:
            continue
        require(line.startswith('AKV_SMOL_') and ' ' in line, 'Malformed firmware prefix')
        tag, fields = line[len('AKV_SMOL_'):].split(' ', 1)
        require(tag in SCHEMAS, 'Unknown/failure firmware tag')
        row = parse_fields(fields, SCHEMAS[tag])
        result.setdefault(tag, []).append(row)
        sequence.append((tag, row))
    expected = [('SHAPE', {})]
    for trial in range(4):
        expected += [('TRIAL', dict(trial=trial)), ('MEMORY', dict(trial=trial))]
        expected += [('OUT', dict(trial=trial, index=i)) for i in range(192)]
    expected += [('DATA', {}), ('DONE', {})]
    require(len(sequence) == len(expected) and all(t == et and all(r.get(k) == v for k, v in values.items())
            for (t, r), (et, values) in zip(sequence, expected)), 'Missing/duplicate/out-of-order firmware data')
    return result


def check_log(text, captured, native, memory):
    classify_simulator(text)
    rows = firmware_records(text)
    require(rows['SHAPE'] == [dict(d=64, qheads=3, kvheads=1, tokens=5, capacity=256, tile=64, vlenb=128)],
            'Unexpected model/group shape')
    require(rows['DONE'] == [dict(trials=4, errors=0)], 'Firmware did not pass')
    payload = {k: memory[k] for k in ('data_hash', 'data_bytes', 'query_f32_hash', 'key_hash', 'value_hash', 'mask_hash')}
    require(rows['DATA'] == [dict(payload, checks=1, errors=0)], 'Final original-capacity payload readback mismatch')
    require(len(captured) == len(native) == 768, 'Golden extent mismatch')
    goldens = [struct.unpack('<192f', b) for b in (captured, native)]
    bits = [r['bits'] for r in rows['OUT']]
    elapsed, returned, maxima = [], [], [0.0, 0.0]
    fcsr = rows['TRIAL'][0]['fcsr']
    for t, arm in enumerate(contract.ORDER):
        r = rows['TRIAL'][t]
        require(r['arm'] == arm and r['groups'] == 1 and r['errors'] == 0 and
                r['initial_fcsr'] == r['initial_vcsr'] == r['initial_vstart'] == 0,
                'Admission/arm/group/initial CSR mismatch')
        require(r['fcsr'] == fcsr and fcsr & ~3 == 0 and r['vcsr'] == r['vstart'] == 0,
                'Exact fflags/rounding/vcsr/vstart mismatch')
        require(0 < r['begin'] < r['returned'] < r['end'] and
                (not t or rows['TRIAL'][t-1]['end'] < r['begin']), 'Bad/overlapping ROI')
        elapsed.append(r['end']-r['begin'])
        returned.append(r['returned']-r['begin'])
        require(rows['MEMORY'][t] == dict(trial=t, query_hash=memory['query_hash'],
            guard_hash=memory['guard_hash'], guard_bytes=memory['guard_bytes']), 'Query/unused workspace/guard mismatch')
        require(bits[t*192:(t+1)*192] == bits[:192], 'ABBA raw output bits differ')
        for i, value in enumerate(bits[t*192:(t+1)*192]):
            actual = struct.unpack('<f', struct.pack('<I', value))[0]
            require(math.isfinite(actual), 'Nonfinite output')
            for j, (atol, rtol) in enumerate(((0.003, 0.02), (0.0002, 0.003))):
                expected = goldens[j][i]
                error = abs(actual-expected)
                require(math.isfinite(expected) and error <= atol+rtol*abs(expected), 'Independent golden mismatch')
                maxima[j] = max(maxima[j], error)
    generic, paired = (elapsed[0]+elapsed[3])/2, (elapsed[1]+elapsed[2])/2
    return dict(state='LOG_CHECKED', measured_total_cycles=elapsed, measured_to_return_cycles=returned,
        final_drain_cycles=[a-b for a, b in zip(elapsed, returned)], generic_mean_cycles=generic,
        candidate_mean_cycles=paired, generic_over_candidate=generic/paired,
        candidate_over_generic=paired/generic, cycle_reduction_fraction=1-paired/generic,
        fcsr=fcsr, fflags=fcsr & 31, vcsr=0, vstart=0, output_values_checked=768,
        max_abs_error_capture=maxima[0], max_abs_error_native_tile64=maxima[1],
        guard_fingerprints_checked=4, full_data_hash_checks=1, performance_acceptance=False)


def expected_commands():
    result = []
    def row(code, **values):
        record = dict(command=code, full=0, refill=0, load=0, release=0, v2_full=0, v2_refill=0,
            v2_row_load=0, v2_column_load=0, v2_column_panel=0, v2_logical_column=0,
            q_external_bytes=0, kv_external_bytes=0, replay_bytes=0, read_ranges=0, translations=0,
            v2_bank_conflict_cycles=0, v2_k_view_bank_cycles=0)
        record.update(values)
        return record
    for arm in contract.ORDER:
        result.append(row(4, v2_full=1, q_external_bytes=384, kv_external_bytes=1280, read_ranges=14))
        if arm:
            result += [row(6, v2_column_load=1, v2_column_panel=1, v2_logical_column=4,
                           v2_k_view_bank_cycles=1, replay_bytes=40) for _ in range(16)]
        result += [row(6, v2_column_load=1, v2_logical_column=1, v2_k_view_bank_cycles=1,
                       replay_bytes=10) for _ in range(64 if arm else 192)]
        result += [row(2, v2_row_load=1, load=1, replay_bytes=128) for _ in range(10 if arm else 15)]
        result.append(row(3, release=1))
    return result


def check_hardware_work(text):
    expected, rows, summaries = expected_commands(), [], []
    totals = Counter()
    for line in text.splitlines():
        require('QBS_PERF' not in line, 'Unrelated QBS work in regression')
        if '[AKV_PERF]' in line:
            require(line.startswith('[AKV_PERF] '), 'Malformed native work prefix')
            row = parse_fields(line[len('[AKV_PERF] '):], PERF_FIELDS)
            index = len(rows)
            require(index < len(expected) and row['seq'] == index+1 and
                    all(row[k] == v for k, v in expected[index].items()), 'Native command order/work mismatch')
            require(row['success'] == 1 and row['busy_cycles'] > 0 and
                    all(row[k] == 0 for k in ('fault', 'validation_fault', 'validation_error',
                                             'read_fault', 'v2_rejected')), 'Native fault/rejection')
            require(row['context_ready'] == int(row['command'] != 3) and
                    row['read_payload_bytes'] == row['q_external_bytes']+row['kv_external_bytes']+
                    (64 if row['v2_full'] else 0), 'Lifecycle/reader payload mismatch')
            for k in SUMMARY_FIELDS-{'records', 'success_records', 'fault_records', 'validation_fault_records'}:
                totals[k] = max(totals[k], row[k]) if k == 'read_outstanding_max' else totals[k]+row[k]
            rows.append(row)
        elif '[AKV_PERF_SUMMARY]' in line:
            require(line.startswith('[AKV_PERF_SUMMARY] '), 'Malformed native summary prefix')
            summaries.append(parse_fields(line[len('[AKV_PERF_SUMMARY] '):], SUMMARY_FIELDS))
        else:
            require('AKV_PERF' not in line, 'Unknown/malformed native work record')
    require(len(rows) == len(expected) == 602, 'Missing/extra native work')
    summary = dict(totals, records=602, success_records=602, fault_records=0, validation_fault_records=0)
    require(summaries == [summary], 'Missing/duplicate/inconsistent hardware summary')
    sizes, calls, offset = [209, 92, 92, 209], [], 0
    for t, size in enumerate(sizes):
        batch = rows[offset:offset+size]
        calls.append(dict(trial=t, arm=contract.ORDER[t], commands=size,
            busy_cycles=sum(r['busy_cycles'] for r in batch), full=1, refill=0, release=1,
            k_single_commands=64 if contract.ORDER[t] else 192,
            k_panel4_commands=16 if contract.ORDER[t] else 0,
            v_row_d64_commands=10 if contract.ORDER[t] else 15))
        offset += size
    return dict(commands=602, per_call_commands=sizes, calls=calls, totals=summary)


def check_run(log_path, build_dir):
    path, directory = Path(log_path).resolve(), Path(build_dir).resolve()
    build = verify_build(directory)
    text = path.read_text()
    result = check_log(text, Path(build['golden']['captured']).read_bytes(),
        Path(build['golden']['native_tile64']).read_bytes(), build['memory_expected'])
    work = check_hardware_work(text)
    require(all(c['busy_cycles'] <= elapsed for c, elapsed in zip(work['calls'], result['measured_total_cycles'])),
            'Native busy work exceeds complete-call ROI')
    result.update(state='PASS', work=work, full_call_count=4, order=contract.ORDER,
        scope='One existing real SmolLM2 group: KV0/Q0,1,2 D64/H3/T5/cap256; ABBA; no positive-speedup prerequisite',
        provenance=build['provenance'], image_contract=build['image_contract'],
        fixed_image_sha256=build['fixed_image_sha256'], build_sha256=sha(directory/'build.json'),
        elf_sha256=build['elf_sha256'], source_pins_sha256=build['source_pins_sha256'],
        log_sha256=sha(path), independent_vector_work_checked=False, independent_protocol_checked=False,
        acceptance_scope='Numerical/CSR/payload/native-work only; runner must separately check fixed image, '
                         'vector signatures and independent UVM. No board/whole-model acceptance.')
    return result


def expected_vector_signatures():
    values = []
    for arm in contract.ORDER:
        values += ([0x0205745b]*16+[0x0005745b]*64 if arm else [0x0005745b]*192)
        values += [0x0005345b]*(10 if arm else 15)
    return values


def check_vector_workcounts(vector_trace_path, build_dir):
    build = verify_build(build_dir)
    path, values, counts, configs, last = Path(vector_trace_path), [], Counter(), 0, -1
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        required = set('cycle event insn nr_lanes vlen_bits'.split())
        require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)) and
                required <= set(reader.fieldnames), 'Vector trace schema mismatch')
        for row in reader:
            require(None not in row and all(row[k] is not None for k in required), 'Malformed vector row')
            require(re.fullmatch('[0-9]+', row['cycle']) is not None, 'Malformed vector cycle')
            cycle = int(row['cycle'])
            require(last <= cycle < 1 << 64 and (row['nr_lanes'], row['vlen_bits']) == ('4', '1024'),
                    'Vector cycle/image mismatch')
            last = cycle
            configs += row['event'] == 'config'
            require(row['event'] != 'reset', 'Unexpected vector reset')
            if row['event'] != 'alloc':
                continue
            require(re.fullmatch('[0-9a-fA-F]{8}', row['insn']) is not None, 'Malformed vector instruction')
            insn = int(row['insn'], 16)
            if insn & 0x707f not in (0x305b, 0x705b):
                continue
            require(insn in (0x0205745b, 0x0005745b, 0x0005345b), 'Unexpected replay signature/dimension')
            values.append(insn)
            counts[{0x0205745b:'k_panel4_commands', 0x0005745b:'k_single_commands',
                    0x0005345b:'v_row_d64_commands'}[insn]] += 1
    require(configs == 1 and values == expected_vector_signatures() and
            counts == dict(k_single_commands=512, k_panel4_commands=32, v_row_d64_commands=50),
            'Independent vector signature/order/work mismatch')
    return dict(counts=dict(counts), replay_commands=594, native_commands_with_lifecycle=602,
        per_call_commands=[209, 92, 92, 209], ordered_signatures_checked=True,
        trace_sha256=sha(path), elf_sha256=build['elf_sha256'])


if __name__ == '__main__':
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
