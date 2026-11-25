#!/usr/bin/env python3
"""Frozen M4 Q4 firmware with exhaustive target comparisons and bounded UART."""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
QBS = HERE.parent / 'operator_eval_20261115/qbs'
COMPARE = HERE.parent / 'operator_eval_20261115/projection_real'
PARENTS = {
    'native': ('native', 'ac2882e3f507ba01d63f75763e96b6c6dea5a7a051159ed7ca8a2b6d780a3a36'),
    'rvv': ('x32', '09d29ade598deb0cc8e6ec434fb120e17b9f5c9596169b59552fd5650b24180e'),
}
SCHEMA = 'power-q4-m4-compact-20261117-v2'
KINDS = ('GUARD', 'Q8', 'PACK', 'OUT')
COUNTS = (640, 9344, 9344, 256)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old = load(QBS / 'check.py', 'compact_qbs_fields')
perf_tool = load(ROOT / 'hardware/scripts/qbs/summarize_qbs_perf.py', 'compact_qbs_perf')
require, sha = old.require, old.digest
PERF_FIELDS = perf_tool.IDENTITY_FIELDS | perf_tool.FULL_FIELDS | perf_tool.PROBE_FIELDS | set('''
busy_cycles read_ranges translations ar r_beats payload_bytes store_wait_cycles
read_backpressure_cycles tiles weight_bytes activation_bytes useful_pairs pair_capacity
dot_active_cycles fp_uop_issue fp_table_occ_sum fp_table_occ_max fp_table_full_cycles
accumulator_updates commit_groups commit_backpressure_cycles activation_access
context_fill_count context_reuse_count context_reuse_block_count context_read_bytes
activation_axi_bytes_saved context_replay_cycles context_replay_compute_overlap_cycles
context_validation_fault_count'''.split())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    require(pins, 'Empty pins')
    for path, digest in pins.items():
        require(sha(path) == digest, 'Input drift: ' + path)


def parent(mode):
    suffix, digest = PARENTS[mode]
    directory = OUT / ('operator_qbs_prepare_20261115_q4_m4_%s_01' % suffix)
    require(sha(directory / 'build.json') == digest, 'Frozen parent receipt drift')
    m = json.loads((directory / 'build.json').read_text())
    require(m['state'] == 'BUILT_NOT_EXECUTED' and m['post_pins_match'] and
            not m['rtl_executed'] and m['reused_objects'] == 0, 'Parent build contract')
    require(sha(m['source_pins']) == m['source_pins_sha256'] and
            sha(m['elf']) == m['elf_sha256'], 'Parent firmware drift')
    pins = json.loads(Path(m['source_pins']).read_text())
    verify(pins)
    pins[str(directory / 'build.json')] = digest
    pins[str(directory / 'source-pins.json')] = m['source_pins_sha256']
    # Commands are not part of the old inventory; bind them in this successor.
    pins[str(directory / 'commands.json')] = sha(directory / 'commands.json')
    require((m['case']['m'], m['case']['n'], m['case']['k'], m['case']['tile'],
             m['case']['profile'], m['case']['reuse']) == (4, 64, 2048, 4, 1, 'direct'),
            'Wrong parent shape/path')
    return directory, m, pins


def trial_source(source):
    start = source.index('__attribute__((noinline, noclone))\nstatic void eval_trial')
    end = source.index('\n}', start) + 2
    return source[start:end]


def compact_main(source):
    original = trial_source(source)
    first = source.index('static unsigned bits(')
    last = source.index('int main(void)', first)
    source = source[:first] + '''#include "compare.h"
extern const unsigned char compact_q8[], compact_packed[], compact_output[];
static const unsigned char compact_guards[10*GUARD] = {[0 ... 10*GUARD-1] = 0xa5};
''' + source[last:]
    first = source.index('    for (unsigned j=0; j<10; ++j) {\n      printf("OPQ_GUARD')
    last = source.index('\n  }\n  printf("OPQ_DONE', first)
    source = source[:first] + '''    const void *actual[] = {guards[t], q8_snap[t], packed_snap[t], out_snap[t]};
    const void *expected[] = {compact_guards, compact_q8, compact_packed, compact_output};
    const unsigned count[] = {10*GUARD, AB, AB, M*N};
    const char *names[] = {"GUARD", "Q8", "PACK", "OUT"};
    for (unsigned j=0; j<4; ++j) {
      format_comparison c = format_compare(actual[j], expected[j], count[j], j==3,
          j==3 && EVAL_RVV, 0.0002f, 0.0002f);
      errors += c.mismatches != 0;
      printf("OPQC_CHECK trial=%u kind=%s count=%u mismatches=%u first=%u expected_hash=%u "
        "actual_hash=%u raw_differences=%u first_actual=%u first_expected=%u\\n",
        t,names[j],c.count,c.mismatches,c.first,c.expected_hash,c.actual_hash,
        c.raw_differences,c.first_actual,c.first_expected);
    }
    format_comparison power = format_compare(out_snap[t], compact_output, M*N,
        1, 1, 0.0002f, 0.0002f);
    unsigned finite=0;
    float max_abs=0, max_ratio=0;
    for (unsigned i=0; i<M*N; ++i) {
      float a=out_snap[t][i], e;
      memcpy(&e,compact_output+4*i,4);
      if (isfinite(a) && isfinite(e)) {
        ++finite;
        float delta=fabsf(a-e), ratio=delta/(0.0002f+0.0002f*fabsf(e));
        if (delta>max_abs) max_abs=delta;
        if (ratio>max_ratio) max_ratio=ratio;
      }
    }
    printf("OPQC_POWER trial=%u count=%u finite=%u mismatches=%u first=%u "
      "max_abs_bits=%u max_ratio_bits=%u\\n",t,power.count,finite,power.mismatches,
      power.first,format_bits(max_abs),format_bits(max_ratio));''' + source[last:]
    # The function and all snapshot code before the late print loop remain unchanged.
    require(trial_source(source) == original, 'Timed function changed')
    return source


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def golden_checks(directory):
    blobs = [b'\xa5' * 640, *[(directory / 'data' / name).read_bytes() for name in
             ('expected_q8.bin', 'expected_packed.bin', 'expected.bin')]]
    require(list(map(len, blobs)) == [640, 9344, 9344, 1024], 'Golden dimensions')
    return {kind: dict(count=count, expected_hash=fnv(blob))
            for kind, count, blob in zip(KINDS, COUNTS, blobs)}


def elf_check(path):
    raw = path.read_bytes()
    require(raw[:7] == b'\x7fELF\x02\x01\x01', 'Expected ELF64')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(h[1:4] == (2, 243, 1) and h[9] == 56, 'ELF header')
    segments = [struct.unpack_from('<IIQQQQQQ', raw, h[5]+i*h[9]) for i in range(h[10])]
    loads = [p for p in segments if p[0] == 1]
    require(loads and all(p[3] == p[4] and 0x80000000 <= p[3] < p[3]+p[6] <= 0x800f0000
                         and p[5] <= p[6] and p[2]+p[5] <= len(raw) for p in loads),
            'ELF outside 1 MiB L2 / 64 KiB runtime stack reserve')
    return [dict(address=p[3], file_bytes=p[5], memory_bytes=p[6]) for p in loads]


def object_section(path, name):
    raw = Path(path).read_bytes()
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, h[6]+i*h[11]) for i in range(h[12])]
    names = sections[h[13]]
    strings = raw[names[4]:names[4]+names[5]]
    matches = [s for s in sections if strings[s[0]:strings.index(b'\0', s[0])].decode() == name]
    require(len(matches) == 1, 'Missing/duplicate hot section: ' + name)
    s = matches[0]
    return raw[s[4]:s[4]+s[5]]


def build(mode, output=None):
    require(mode in PARENTS, 'Unknown mode')
    output = Path(output or OUT / ('power_q4_m4_compact_20261117_%s_02' % mode)).absolute()
    require(output == output.resolve() and output.parent == OUT.resolve() and
            re.fullmatch(r'power_q4_m4_compact_20261117_' + mode + r'_[A-Za-z0-9_.-]+', output.name)
            and not output.exists(), 'Fresh owned signoff output required')
    directory, previous, pins = parent(mode)
    for key in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'LIBRARY_PATH',
                'LD_PRELOAD', 'LD_LIBRARY_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'CFLAGS', 'LDFLAGS'):
        require(not os.environ.get(key), 'Compiler environment injection: ' + key)
    output.mkdir()
    (output / 'inputs').mkdir()
    shutil.copytree(directory / 'data', output / 'data')
    for name in ('config.h', 'link.ld'):
        shutil.copyfile(directory / name, output / name)
    require(re.findall(r'L2\s*:\s*ORIGIN\s*=\s*0x80000000,\s*LENGTH\s*=\s*0x00100000',
                       (output / 'link.ld').read_text()), 'Parent is not 1 MiB L2')
    commands = {r['label']: r['argv'] for r in json.loads((directory / 'commands.json').read_text())}
    original = Path(commands['compile-main'][commands['compile-main'].index('-c')+1])
    require(pins.get(str(original)) == sha(original), 'Parent main source not pinned')
    source = original.read_text()
    main = output / 'inputs/main.c'
    main.write_text(compact_main(source))
    for path in (Path(__file__).resolve(), HERE / 'test_q4_m4_compact.py',
                 COMPARE / 'compare.h', COMPARE / 'compare_test.c', Path(old.__file__), Path(perf_tool.__file__)):
        pins[str(path)] = sha(path)
    shutil.copyfile(COMPARE / 'compare.h', output / 'compare.h')
    references = output / 'inputs/compact_refs.S'
    assembly = ['.section .rodata.compact_refs,"a",@progbits']
    for symbol, name in (('compact_q8', 'expected_q8.bin'), ('compact_packed', 'expected_packed.bin'),
                         ('compact_output', 'expected.bin')):
        assembly += ['.balign 64', '.global ' + symbol, symbol + ':',
                     '.incbin ' + json.dumps(str(output / 'data' / name))]
    references.write_text('\n'.join(assembly + ['.section .note.GNU-stack,"",@progbits']) + '\n')
    env = dict(PATH='/usr/bin:/bin', HOME=str(output), LC_ALL='C', TZ='UTC', PYTHONDONTWRITEBYTECODE='1')
    executed = []

    def run(label, argv):
        argv = list(map(str, argv))
        proc = subprocess.run(argv, cwd=output, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=120)
        (output / (label + '.log')).write_bytes(proc.stdout)
        executed.append(dict(label=label, argv=argv, returncode=proc.returncode))
        require(proc.returncode == 0, label + ': ' + proc.stdout[-2000:].decode(errors='replace'))

    argv = list(commands['compile-main'])
    argv = [('-I' + str(output)) if a == '-I' + str(directory) else a for a in argv]
    argv[argv.index('-c')+1] = str(main)
    argv[argv.index('-o')+1] = str(output / 'main.o')
    argv[argv.index('-MF')+1] = str(output / 'main.d')
    run('compile-main', argv)
    hot = object_section(output / 'main.o', '.text.eval_trial')
    require(hot == object_section(directory / 'main.o', '.text.eval_trial'),
            'Timed eval_trial object bytes changed')
    dependencies = shlex.split((output / 'main.d').read_text().replace('\\\n', ' ').split(':', 1)[1])
    for name in dependencies:
        path = Path(name)
        if not path.is_relative_to(output):
            require(pins.get(str(path)) == sha(path), 'New/unpinned compiler dependency: ' + str(path))
    ref_args = argv[:argv.index('-MD')]
    run('compile-compact-refs', [*ref_args, '-c', references, '-o', output / 'compact_refs.o'])
    link = list(commands['link'])
    reused = {a: sha(a) for a in link if a.endswith('.o') and a != str(directory / 'main.o')}
    require(all(pins.get(p) == digest for p, digest in reused.items()), 'Unpinned reused object')
    link = [str(output / 'main.o') if a == str(directory / 'main.o') else
            '-Wl,-Map=' + str(output / 'link.map') if a.startswith('-Wl,-Map=') else a for a in link]
    link[link.index('-T')+1] = str(output / 'link.ld')
    link[link.index('-o')+1] = str(output / 'operator.elf')
    link.insert(link.index('-Wl,--gc-sections'), str(output / 'compact_refs.o'))
    run('link', link)
    cc = Path(argv[0])
    objdump = cc.with_name(cc.name.replace('gcc', 'objdump'))
    run('disassembly', [objdump, '-d', '-M', 'no-aliases,numeric', output / 'operator.elf'])
    nm = cc.with_name(cc.name.replace('gcc', 'nm'))
    pins[str(nm)] = sha(nm)
    run('symbols', [nm, '--defined-only', '-n', output / 'operator.elf'])
    segments = elf_check(output / 'operator.elf')
    reader = load(HERE.parent / 'resident_rvv/qk_shared/qk_boundary/elf.py', 'compact_elf')
    pins[str(Path(reader.__file__))] = sha(reader.__file__)
    parsed = reader.contract((output / 'operator.elf').read_bytes())
    wanted_entries = dict(eval_trial=2, quantize_row_q8_K=8)
    wanted_entries.update(dict(qbs_execute_with_options=2, qbs_native_execute_command=4)
                          if mode == 'native' else dict(q4k_gemm_32x4=4))
    entries = {}
    for line in (output / 'symbols.log').read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] in wanted_entries:
            address = int(parts[0], 16)
            word = parsed['words'][address]
            entries[parts[2]] = dict(pc=address, insn=word if word & 3 == 3 else word & 0xffff,
                                    expected_calls=wanted_entries[parts[2]])
    require(set(entries) == set(wanted_entries), 'Missing hot-path ELF entries')
    # Independently bind the embedded new reference symbols to their parent golden bytes.
    raw = (output / 'operator.elf').read_bytes()
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    ph = [struct.unpack_from('<IIQQQQQQ', raw, h[5]+i*h[9]) for i in range(h[10])]
    for symbol, name in (('compact_q8', 'expected_q8.bin'), ('compact_packed', 'expected_packed.bin'),
                         ('compact_output', 'expected.bin')):
        addr = reader.pc(parsed, symbol)
        blob = (directory / 'data' / name).read_bytes()
        matches = [p for p in ph if p[0] == 1 and p[3] <= addr and addr+len(blob) <= p[3]+p[5]]
        require(len(matches) == 1, 'Golden symbol load bounds')
        offset = matches[0][2] + addr - matches[0][3]
        require(raw[offset:offset+len(blob)] == blob, 'Embedded golden mismatch')
    verify(pins)
    data_identity = {p.name: sha(p) for p in (output / 'data').iterdir() if p.is_file()}
    require(data_identity == {p.name: sha(p) for p in (directory / 'data').iterdir() if p.is_file()},
            'Parent input/layout/golden changed')
    pins.update({str(p): sha(p) for p in output.rglob('*') if p.is_file()})
    save(output / 'source-pins.json', pins)
    save(output / 'commands.json', executed)
    report = dict(schema=SCHEMA, state='BUILT_NOT_EXECUTED', mode=mode,
        parent=dict(path=str(directory), receipt_sha256=PARENTS[mode][1]),
        case=previous['case'], build_id=previous['build_id'], plan=previous['plan'],
        numeric_contract=previous['numeric_contract'], flag_seeds=previous['flag_seeds'],
        sdk_policy=previous['sdk_policy'], sdk_commit=previous['sdk_commit'],
        llama_commit=previous['llama_commit'], provenance=previous['provenance'],
        timing_contract=previous['timing_contract'],
        eval_trial_source_sha256=hashlib.sha256(trial_source(source).encode()).hexdigest(),
        eval_trial_source_byte_identical=True, snapshot_code_unchanged=True,
        eval_trial_object_bytes_identical=True, eval_trial_object_sha256=hashlib.sha256(hot).hexdigest(),
        hot_path_entries=entries, original_quantization_and_matmul_objects=True, softdiv_used=False,
        power_numeric_contract=dict(atol=0.0002, rtol=0.0002, all_values_finite=True,
            scope='Independent relative-power eligibility only; strict checks and original failures retained'),
        data_identity=data_identity, golden_checks=golden_checks(output),
        comparison='Exhaustive per-element target comparisons, not hash-only; copied projection_real compare.h',
        compare_header_sha256=sha(output / 'compare.h'), compact_records=8, power_records=2,
        reused_objects=reused, rebuilt_objects=['main.o', 'compact_refs.o'],
        source_pins=str(output / 'source-pins.json'), source_pins_sha256=sha(output / 'source-pins.json'),
        post_pins_match=True, elf=str(output / 'operator.elf'), elf_sha256=sha(output / 'operator.elf'),
        l2_bytes=1048576, load_segments=segments,
        stack_contract='Unchanged frozen crt0 reads CTRL DRAM end; parent SoC must expose 0x80100000. '
                       'Load image leaves >=64 KiB at top of 1 MiB L2.',
        target_executed=False, rtl_executed=False, performance_measured=False,
        protocol_checked=False, image_checked=False, power_acceptance=False,
        original_worker_reclassified=False)
    entry = dict(id='power_q4_m4_compact_' + mode, category='qbs', elf=report['elf'],
        elf_sha256=report['elf_sha256'], source_pins=report['source_pins'], timeout_seconds=10800,
        plusargs=['+QBS_PERF'] if mode == 'native' else [],
        checker=[str(Path(sys.executable).resolve()), '-B', str(Path(__file__).resolve()), 'check',
                 '--build', str(output), '--log', '{log}', '--output', '{result}'])
    save(output / 'runner-manifest.json', dict(cases=[entry]))
    save(output / 'manifest.json', dict(cases=[entry]))
    power_entry = dict(entry)
    power_entry['checker'] = [str(Path(sys.executable).resolve()), '-B', str(Path(__file__).resolve()),
        'eligibility', '--build', str(output), '--log', '{log}', '--commit', '{run}/commit.csv',
        '--output', '{result}']
    power_entry['checker_success_state'] = 'POWER_ELIGIBLE'
    save(output / 'power-manifest.json', dict(cases=[power_entry],
        scope='Scoped relative-power eligibility, NOT strict numerical PASS or protocol/image acceptance'))
    report['artifacts'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
    save(output / 'build.json', report)
    return report


def receipt(directory):
    directory = Path(directory).resolve(strict=True)
    m = json.loads((directory / 'build.json').read_text())
    require(m['schema'] == SCHEMA and m['state'] == 'BUILT_NOT_EXECUTED' and
            m['eval_trial_source_byte_identical'] and m['post_pins_match'] and
            not m['rtl_executed'] and not m['target_executed'], 'Successor build contract')
    require(sha(m['source_pins']) == m['source_pins_sha256'] and sha(m['elf']) == m['elf_sha256'],
            'Successor identity drift')
    verify(json.loads(Path(m['source_pins']).read_text()))
    require(m['artifacts'] == {str(p): sha(p) for p in directory.rglob('*')
                              if p.is_file() and p.name != 'build.json'}, 'Artifact drift')
    require(golden_checks(directory) == m['golden_checks'], 'Golden checks drift')
    mode = m['mode']
    require(mode in PARENTS, 'Unknown receipt mode')
    suffix, digest = PARENTS[mode]
    frozen = OUT / ('operator_qbs_prepare_20261115_q4_m4_%s_01' % suffix)
    require(m['parent'] == dict(path=str(frozen), receipt_sha256=digest) and
            sha(frozen / 'build.json') == digest, 'Receipt parent drift')
    original = json.loads((frozen / 'build.json').read_text())
    require(all(m[k] == original[k] for k in ('case', 'build_id', 'plan', 'numeric_contract',
                'flag_seeds', 'sdk_policy', 'sdk_commit', 'llama_commit', 'timing_contract')),
            'Inherited contract drift')
    require(m['data_identity'] == {p.name: sha(p) for p in (directory / 'data').iterdir() if p.is_file()} ==
            {p.name: sha(p) for p in (frozen / 'data').iterdir() if p.is_file()}, 'Input/layout identity drift')
    hot = object_section(directory / 'main.o', '.text.eval_trial')
    require(hot == object_section(frozen / 'main.o', '.text.eval_trial') and
            hashlib.sha256(hot).hexdigest() == m['eval_trial_object_sha256'] and
            not m['softdiv_used'] and m['original_quantization_and_matmul_objects'], 'Hot kernel identity drift')
    return m


def validate_perf(perf, trials, native):
    require(len(perf) == (4 if native else 0), 'Missing/extra QBS commands')
    if not native:
        return
    require(all(set(p) == PERF_FIELDS for p in perf), 'QBS_PERF field schema')
    require(not perf_tool.validate(perf), 'QBS_PERF schema/accounting validation')
    for index, p in enumerate(perf):
        require(p['seq'] == index+1 and p['success'] == 1 and all(p[k] == 0 for k in
            ('fault', 'validation_fault', 'validation_error', 'read_fault', 'context_validation_fault_count')),
            'Native command failure/sequence')
        require((p['m'], p['n'], p['vlen'], p['lanes'], p['weight_bytes'], p['activation_bytes'],
                 p['useful_pairs'], p['tiles']) == (4, 32, 1024, 4, 36864, 9344, 262144, 64),
                'Command geometry/work mismatch')
        require(p['pair_capacity'] == 32*p['dot_active_cycles'] == p['useful_pairs'] and
                p['probe_compute_without_dot_issue_cycles']+p['dot_active_cycles'] ==
                p['phase_compute_cycles']+p['phase_overlap_cycles'] and
                p['busy_cycles'] > 0 and p['phase_fault_cycles'] == 0, 'Native compute accounting')
        require(all(p[k] == 0 for k in ('activation_access', 'context_fill_count', 'context_reuse_count',
                'activation_axi_bytes_saved')), 'Unexpected context lifecycle')
    for trial, r in enumerate(trials):
        require(sum(p['busy_cycles'] for p in perf[trial*2:trial*2+2]) <= r['t4']-r['t3'],
                'Engine busy exceeds execute ROI')


def power_records(text):
    records, clean = [], []
    for line in text.splitlines():
        if line.startswith('OPQC_POWER '):
            records.append(old.fields(line, 'OPQC_POWER '))
        else:
            clean.append(line)
    require(len(records) == 2, 'Two exhaustive finite/error summaries required')
    for t, r in enumerate(records):
        require(set(r) == set('trial count finite mismatches first max_abs_bits max_ratio_bits'.split()),
                'Power numeric schema')
        require(all(isinstance(v, int) and 0 <= v <= 0xffffffff for v in r.values()) and
                (r['trial'], r['count'], r['finite'], r['mismatches'], r['first']) ==
                (t, 256, 256, 0, 0xffffffff), 'Nonfinite/out-of-tolerance power output')
        for key in ('max_abs_bits', 'max_ratio_bits'):
            value = struct.unpack('<f', struct.pack('<I', r[key]))[0]
            require(value >= 0 and value < float('inf'), 'Nonfinite/negative error summary')
            r[key.replace('_bits', '')] = value
        require(r['max_ratio'] <= 1.000001, 'Power normalized error exceeds tolerance')
    return '\n'.join(clean), records


def _parse_log(text, m, power=False):
    native = m['mode'] == 'native'
    require(len(text) <= 262144, 'Compact log exceeds bounded checker limit')
    perf, records = [], []
    for line in text.splitlines():
        if re.search(r'\bUVM_(?:ERROR|FATAL)\b', line):
            require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*', line), 'UVM error')
        terminal = power and re.search(r'Core Test \*\*\* FAILED \*\*\* \(tohost = 1\)', line)
        require(not re.search(r'(?i)(Error[-:]|Fatal:|Assertion failed|\$fatal|\bTIMEOUT\b|\bTIMED OUT\b)', line) and
                (not re.search(r'\bFAILED\b', line) or terminal),
                'Simulator error/timeout')
        if '[QBS_PERF]' in line:
            require(native and not records and line.startswith('[QBS_PERF] '), 'Late/unexpected QBS_PERF')
            perf.append(old.fields(line, '[QBS_PERF] '))
        elif 'OPQ' in line:
            prefix = line.split(' ', 1)[0] + ' '
            require(prefix in ('OPQ_META ', 'OPQ_TRIAL ', 'OPQC_CHECK ', 'OPQ_DONE '), 'Unknown compact record')
            records.append((prefix, old.fields(line, prefix, ('id', 'kind'))))
    terminals = re.findall(r'Core Test \*\*\* (SUCCESS|FAILED) \*\*\* \(tohost = ([0-9]+)\)', text)
    if not power:
        require(terminals == [('SUCCESS', '0')], 'Missing/duplicate/nonzero EOC')
    require(len(records) == 12, 'Missing/extra compact records')
    cursor = 0

    def take(prefix):
        nonlocal cursor
        require(records[cursor][0] == prefix, 'Record order')
        r = records[cursor][1]
        cursor += 1
        return r

    require(take('OPQ_META ') == dict(id=m['build_id'], m=4, n=64, k=2048, profile=1,
                                      rvv=int(not native), trials=2), 'Metadata mismatch')
    trials, comparisons, strict_failures = [], [], 0
    for t in range(2):
        r = take('OPQ_TRIAL ')
        require(set(r) == set('trial status commands context eligible coop quant_fcsr fcsr vcsr vstart'.split()) |
                {'t%d' % i for i in range(6)}, 'Trial schema')
        require(r['trial'] == t and r['status'] == 0 and r['commands'] == (2 if native else 0) and
                r['context'] == r['eligible'] == 0 and r['coop'] in ((0, 1) if native else (0,)),
                'SDK status/commands/capability mismatch')
        require(r['vcsr'] == 2 and r['vstart'] == 0 and r['quant_fcsr'] & ~3 == 0, 'Vector/quant flags')
        seed = m['flag_seeds'][t]
        require(r['fcsr'] == m['plan']['flags'] | seed if native else r['fcsr'] in (seed, seed | 1),
                'Lost/new/sticky flags')
        stamps = [r['t%d' % i] for i in range(6)]
        require(all(0 <= a < b < 2**64 for a, b in zip(stamps, stamps[1:])), 'Phase boundaries')
        if trials:
            require(r['t0'] > trials[-1]['t5'] and r['coop'] == trials[-1]['coop'], 'Repeat overlap/drift')
        trials.append(r)
        for kind in KINDS:
            c = take('OPQC_CHECK ')
            require(set(c) == set('trial kind count mismatches first expected_hash actual_hash raw_differences first_actual first_expected'.split()),
                    'Comparison schema')
            require(c['trial'] == t and c['kind'] == kind and all(isinstance(v, int) and 0 <= v <= 0xffffffff
                    for k, v in c.items() if k != 'kind'), 'Comparison integer range/scope')
            require(all(c[k] == value for k, value in m['golden_checks'][kind].items()) and
                    c['mismatches'] <= c['count'] and c['raw_differences'] <= c['count'], 'Comparison identity/count')
            if power and kind != 'GUARD':
                if c['mismatches']:
                    require(c['first'] < c['count'], 'Missing first mismatch')
                    strict_failures += 1
                else:
                    require(c['first'] == 0xffffffff and c['first_actual'] == c['first_expected'] == 0,
                            'Invalid passing comparison')
                if kind != 'OUT' or native:
                    require(c['mismatches'] == c['raw_differences'], 'Exact mismatch accounting')
                if not c['raw_differences']:
                    require(c['actual_hash'] == c['expected_hash'], 'Unreported raw difference')
            else:
                require(c['mismatches'] == c['first_actual'] == c['first_expected'] == 0 and
                        c['first'] == 0xffffffff, 'Exhaustive comparison failed')
            if kind == 'GUARD' or (not power and (kind != 'OUT' or native)):
                require(c['actual_hash'] == c['expected_hash'] and c['raw_differences'] == 0,
                        'Exact byte/value comparison mismatch')
            elif not power:
                require(c['raw_differences'] > 0 or c['actual_hash'] == c['expected_hash'],
                        'Inconsistent RVV raw summary')
            comparisons.append(c)
    require(take('OPQ_DONE ') == dict(errors=strict_failures if power else 0), 'Target error footer')
    if power:
        require(terminals == [('FAILED', '1') if strict_failures else ('SUCCESS', '0')],
                'Completion is not solely the retained strict numerical failure')
    validate_perf(perf, trials, native)
    return dict(state='POWER_ELIGIBLE' if power else 'PASS', trials=trials, commands=perf,
        comparisons=comparisons, strict_numerical_state='FAIL' if strict_failures else 'PASS',
        strict_failure_records=strict_failures, output_values_checked=512,
        q8_bytes_checked=18688, packed_bytes_checked=18688, guard_bytes_checked=1280,
        exhaustive_target_comparisons=True, hash_only_validation=False,
        protocol_checked=False, image_checked=False, execution_path_checked=False,
        power_acceptance=False, original_worker_reclassified=False)


def parse_log(text, m):
    if m.get('power_records') == 2:
        text, _ = power_records(text)
    return _parse_log(text, m)


def commit_work(path, m):
    expected = m['hot_path_entries']
    starts = {v['pc']: (name, v) for name, v in expected.items()}
    counts, markers, previous, last_order = Counter(), 0, -1, -1
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and {'cycle', 'event', 'order', 'pc', 'insn', 'trap'} <= set(reader.fieldnames),
                'Commit CSV schema')
        for r in reader:
            require(None not in r and all(v is not None for v in r.values()), 'Malformed commit record')
            cycle = int(r['cycle'])
            require(cycle >= previous and int(r['trap']) == 0, 'Commit cycle order/architectural trap')
            previous = cycle
            if r['event'] != 'retire':
                continue
            order = int(r['order'])
            require(order == last_order + 1, 'Incomplete/discontinuous retire trace')
            last_order = order
            pc, word = int(r['pc'], 16), int(r['insn'], 16)
            if pc in starts:
                name, entry = starts[pc]
                require(word == entry['insn'], 'Hot entry instruction differs from pinned ELF')
                counts[name] += 1
            markers += word == 0xc0002073
    require(dict(counts) == {name: e['expected_calls'] for name, e in expected.items()} and markers == 4,
            'Incomplete/extra quantization/matmul/trial work')
    return dict(entry_counts=dict(counts), roi_markers=markers, traps=0, retired=last_order+1)


def eligibility(text, m, commit):
    require(m['eval_trial_object_bytes_identical'] and not m['softdiv_used'], 'Original hot path required')
    clean, numeric = power_records(text)
    result = _parse_log(clean, m, power=True)
    result.update(power_numeric_summaries=numeric, commit_work=commit_work(commit, m),
        relative_power_eligible=True, execution_path_checked=True,
        strict_failure_preserved=True, original_numerical_result_reclassified=False,
        scope='Relative-power eligibility with finite bounded error ONLY; not strict numerical PASS, '
              'RTL correctness signoff, fixed-FDIV acceptance, protocol/image or measured power acceptance')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build', allow_abbrev=False)
    p.add_argument('--mode', choices=PARENTS, required=True)
    p.add_argument('--output', type=Path)
    p = sub.add_parser('check', allow_abbrev=False)
    for key in ('build', 'log', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    p = sub.add_parser('eligibility', allow_abbrev=False)
    for key in ('build', 'log', 'commit', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'build':
            r = build(args.mode, args.output)
            print(json.dumps({k: r[k] for k in ('state', 'elf', 'elf_sha256')}))
            return 0
        require(args.log.stat().st_size <= 262144, 'Compact log exceeds bounded checker limit')
        m = receipt(args.build)
        text = args.log.read_text()
        result = (eligibility(text, m, args.commit) if args.command == 'eligibility' else parse_log(text, m))
        result.update(build_sha256=sha(args.build / 'build.json'), log_sha256=sha(args.log))
        if args.command == 'eligibility':
            result['commit_sha256'] = sha(args.commit)
    except Exception as exc:
        result = dict(state='FAIL', error=str(exc), power_acceptance=False, original_worker_reclassified=False)
    if args.command in ('check', 'eligibility'):
        save(args.output, result)
    print(json.dumps(result))
    return result['state'] not in ('PASS', 'POWER_ELIGIBLE')


if __name__ == '__main__':
    raise SystemExit(main())
