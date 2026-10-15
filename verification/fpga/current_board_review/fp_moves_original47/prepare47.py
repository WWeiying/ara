#!/usr/bin/env python3
"""Exact archived 47 FP-move singles: source/runtime port and host/Spike only."""
import argparse
from collections import Counter
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'integration'
sys.path.insert(0, str(BASE))
import prepare

CAMP = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
ARCH = CAMP / 'rvv_small_fp_moves01'
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
ISA = 'rv64gcv_zvfh_zvl1024b'
TARGET = {2: 'vfslide1up.vf v24,v8,ft0,v0.t', 3: 'vfslide1down.vf v24,v8,ft0,v0.t',
          4: 'vfslide1up.vf v24,v8,ft0', 5: 'vfslide1down.vf v24,v8,ft0', 6: 'vfmv.s.f v24,ft0'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def run(command, log, expected=0, timeout=60):
    prepare.save(Path(str(log) + '.command.json'), list(map(str, command)))
    start = time.monotonic()
    with log.open('x') as stream:
        result = subprocess.run(list(map(str, command)), stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    require(result.returncode == expected, f'{log}: exit {result.returncode}, expected {expected}')
    return time.monotonic() - start


def cap(sew, lmul):
    return (1024 // sew) // int(lmul[2:]) if lmul.startswith('mf') else (1024 // sew) * int(lmul[1:])


def target(dis, op):
    block = re.search(rf'^[0-9a-f]+ <op_{op}>:\n(.*?)(?=^[0-9a-f]+ <|\Z)', dis, re.M | re.S)
    require(block is not None, 'Missing target function')
    matches = []
    for line in block[1].splitlines():
        match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.*)', line)
        if match and ' '.join(match[3].split()) == TARGET[op]:
            matches.append(dict(pc='0x' + match[1], opcode=match[2], instruction=TARGET[op]))
    require(len(matches) == 1, 'Ambiguous/missing actual target instruction')
    return matches[0]


def provenance():
    pins = {}
    def pin(path, expected=None):
        digest = prepare.sha(path)
        require(expected is None or digest == expected, 'Source identity drift: ' + str(path))
        pins[str(path)] = digest
    pin(ARCH / 'manifest.json', 'e517533db5227820bbce08f6230f32b904d1d0a02169178e99d4f98221495d52')
    manifest = json.loads((ARCH / 'manifest.json').read_text())
    pin(ARCH / 'original_board_report.json', manifest['original_report_sha256'])
    symptoms_path = CAMP / 'rvv_move_symptoms02/symptoms.json'
    pin(symptoms_path, 'dacc94e171ac5e8baa2fd0c4674e8283ca772fda32d5d7347234dcf55f5c07a9')
    symptoms = json.loads(symptoms_path.read_text())
    for record in symptoms['reports']:
        pin(symptoms_path.parent / record['frozen'], record['sha256'])
    for filename, digest in manifest['source_sha256'].items():
        if filename != 'reduce_fp_moves.py':
            pin(SOURCE / filename, digest)
    reducer_path = SOURCE / 'repro/reduce_fp_moves.py'
    pin(reducer_path, '2407d5672efb54250eae027ba6ba1fde9193f7760482cff9daf0d31867a6f2d6')
    for name in ('reference_512.json', 'reference_1024.json'):
        pin(ARCH / name)
    reducer = module('archived_reduce_fp_moves', SOURCE / 'repro/reduce_fp_moves.py')
    board = json.loads((ARCH / 'original_board_report.json').read_text())
    records = []
    for item in manifest['cases']:
        name, sew, lmul = item['name'], item['sew'], item['lmul']
        op, = item['operation_ids']
        single = ARCH / name
        symptom, = [s for s in symptoms['cases'] if s['single_name'] == name]
        require(symptom['confirmed'] and symptom['measured_trigger'] == item['measured_stimulus'], 'Historical symptom mismatch')
        original_manifest = CAMP / f'rvv_fp_move_partitions02/op{op}/manifest.json'
        pin(original_manifest)
        parent, = [c for c in json.loads(original_manifest.read_text())['cases'] if c['name'] == item['original_name']]
        require(parent['sha256'] == item['original_elf_sha256'], 'Original parent identity mismatch')
        original_elf = original_manifest.parent / 'overlay/opt/ara-tests' / item['original_name']
        pin(original_elf, item['original_elf_sha256'])
        archived_elf = ARCH / 'binaries' / name
        pin(archived_elf, item['sha256'])
        for filename, digest in item['scenario_sources'].items():
            pin(single / filename, digest)
        require((single / 'scenario.c').read_text() == reducer.single_trial((SOURCE / 'fp_move_oracle.c').read_text(), item['measured_stimulus']), 'Archived C differs from original generator')
        require((single / 'scenario.S').read_text() == reducer.fp_moves.assembly(sew, lmul, True), 'Archived assembly differs from original generator')
        old, = [r for r in board['results'] if r['name'] == item['original_name']]
        require(old['status'] == 'failed' and item['original_failure_detail'] in old['output'], 'Original measured failure absent')
        dis = subprocess.check_output([str(CC.with_name(CC.name.removesuffix('gcc') + 'objdump')), '-d', str(archived_elf)], text=True, timeout=15)
        records.append(dict(**item, cap=cap(sew, lmul), symptom=symptom, original_elf=str(original_elf),
                            archived_elf=str(archived_elf), archived_target=target(dis, op)))
    require(len(records) == 47 and Counter(r['operation_ids'][0] for r in records) == {2: 1, 3: 1, 4: 15, 5: 15, 6: 15}, 'Wrong original membership')
    shapes = {(16, x) for x in ('mf4', 'mf2', 'm1', 'm2', 'm4', 'm8')}
    shapes |= {(32, x) for x in ('mf2', 'm1', 'm2', 'm4', 'm8')}
    shapes |= {(64, x) for x in ('m1', 'm2', 'm4', 'm8')}
    for op in (4, 5, 6):
        require({(r['sew'], r['lmul']) for r in records if r['operation_ids'] == [op]} == shapes, 'Shape membership differs')
    for record in records:
        op = record['operation_ids'][0]
        require(record['measured_stimulus'] == dict(op=op, seed=0, scalar=0, invalid_box=0, vl=2,
                                                  mask=0, sticky=0, vstart=1, actual_flags=0, errors=1), 'Unexpected measured tuple')
        if op in (2, 3):
            require((record['sew'], record['lmul']) == (16, 'mf4'), 'Wrong masked-slide original')
    for path in (Path(__file__), HERE / 'host_fixture.c', HERE.parent / 'fp_moves/focused.py',
                 BASE / 'prepare.py', BASE / 'run.py', CC.resolve(), SPIKE):
        pin(path)
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        pin(BASE / name)
    return dict(pins=pins, records=records, original_manifest=manifest,
                reducer_identity=dict(archived_sha256=manifest['source_sha256']['reduce_fp_moves.py'],
                                      current_equivalence_checker_sha256=prepare.sha(reducer_path),
                                      archived_generator_bytes_recovered=False,
                                      qualifier='Current prefix-capable reducer is not the archived generator; all47 generated C/S checked byte-identical to archive'),
                scope='47 archived measured singles, not original 21504-case parent matrices or Linux replay',
                manifest_board_reproduction_confirmed=manifest['board_reproduction_confirmed'],
                later_symptoms_all47_confirmed=True)


def host(prepared, out, records):
    directory = out / 'host'
    directory.mkdir()
    results = []
    for record in records:
        name, sew, capacity = record['name'], record['sew'], record['cap']
        op, = record['operation_ids']
        case = prepared / name
        exe = directory / name
        command = ['/usr/bin/cc', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-tree-vectorize',
                   f'-DSEW={sew}', f'-DCAP={capacity}', f'-DORIGINAL_OP={op}', '-DRESTART_MOVES=1', '-DDETAIL_MOVES=1',
                   f'-DMOVE_OP_MASK={1 << op}', f'-DCASE_MAIN={name}_main', '-I' + str(case / 'original'),
                   case / 'case.c', HERE / 'host_fixture.c', '-o', exe]
        run(command, directory / (name + '.compile.log'))
        patterns = [int(x, 16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)', (case / 'original/inputs.h').read_text())]
        require(len(patterns) == 16, 'Wrong original FP input table')
        words = [patterns[i % 16] for i in range(capacity)] + [patterns[(3*i+11) % 16] for i in range(capacity)]
        scalar = ((1 << 64) - 1) ^ ((1 << sew) - 1)
        data = b''.join(x.to_bytes(sew // 8, 'little') for x in words) + bytes([255])*128 + scalar.to_bytes(8, 'little')
        digest = 14695981039346656037
        for byte in data:
            digest = ((digest ^ byte) * 1099511628211) & ((1 << 64) - 1)
        expected_call = f'HOST_CALL op={op} cap={capacity} vl=2 vstart=1 input_hash={digest:016x}'
        for mutation in range(7):
            log = directory / (name + f'.mutation{mutation}.log')
            run([exe, str(mutation)], log, expected=int(mutation != 0))
            text = log.read_text()
            require(text.splitlines().count(expected_call) == 1, 'Original input/setup mismatch')
            require((f'RVV_FP_MOVE_PASS sew={sew} cases=1 errors=0' in text) == (mutation == 0), 'Oracle result mismatch')
            if mutation:
                require('RVV_FP_MOVE_FAIL' in text, 'Original oracle did not reject mutation')
            results.append(dict(name=name, mutation=mutation, expected_exit=int(mutation != 0), input_hash=f'{digest:016x}', status='PASS'))
    prepare.save(out / 'host.json', dict(status='PASS', results=results,
                  scope='47 host input/oracle checks plus282 negative checks; no RTL execution'))


def build(prepared, out, records):
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror', '-nostdlib', '-static',
             '-Wl,--build-id=none', '-Wl,--gc-sections', '-T', prepared / 'replay.ld']
    maps = {}
    for backend in ('soc', 'spike'):
        directory = out / backend
        directory.mkdir()
        entries = {}
        for record in records:
            name, sew = record['name'], record['sew']
            op, = record['operation_ids']
            case = prepared / name
            elf = directory / (name + '.elf')
            defines = [f'-DSEW={sew}', '-DRESTART_MOVES=1', '-DDETAIL_MOVES=1', f'-DMOVE_OP_MASK={1 << op}']
            if backend == 'spike':
                defines.append('-DSPIKE_REFERENCE=1')
            run([CC, *flags, *defines, '-I' + str(case / 'original'), case / 'case.c', case / 'original/scenario.S',
                 case / 'main.c', prepared / 'startup.S', prepared / 'runtime.c', '-lgcc', '-o', elf], directory / (name + '.compile.log'))
            dis = directory / (name + '.dis')
            run([CC.with_name(CC.name.removesuffix('gcc') + 'objdump'), '-d', elf], dis)
            actual = target(dis.read_text(), op)
            require(actual['opcode'] == record['archived_target']['opcode'], 'Target opcode changed')
            require(re.search(rf'\bjal\s+[0-9a-f]+ <op_{op}>', dis.read_text()) is not None, 'Target not called directly')
            nm = subprocess.check_output([str(CC.with_name(CC.name.removesuffix('gcc') + 'nm')), str(elf)], text=True)
            symbols = {n: int(a, 16) for a, _, n in (line.split() for line in nm.splitlines())}
            require(symbols['__bss_end'] < 0x800f0000, 'Runtime memory limit exceeded')
            prepare.save(directory / (name + '.symbols.json'), symbols)
            maps.setdefault(name, dict(archived=record['archived_target']))[backend] = dict(**actual,
                elf_sha256=prepare.sha(elf), disassembly_sha256=prepare.sha(dis))
            entries[name] = dict(path=str(elf), sha256=prepare.sha(elf), cases=[name], configurations=1,
                                 pass_markers=[f'RVV_FP_MOVE_PASS sew={sew} cases=1 errors=0',
                                               f'BOARD_CASE_PASS {name}', 'BOARD_REPLAY_PASS'])
        prepare.save(directory / 'programs.json', dict(schema_version=1, backend='vcs-soc' if backend == 'soc' else 'spike-htif',
                     programs=entries, prepared=str(prepared), provenance_sha256=prepare.sha(prepared / 'provenance.json'),
                     compiler=dict(path=str(CC), sha256=prepare.sha(CC)), vcs_started=False))
    prepare.save(out / 'address_map.json', maps)
    return maps


def reference(out, records, maps):
    directory = out / 'reference'
    directory.mkdir()
    results = []
    for record in records:
        name = record['name']
        elf = out / 'spike' / (name + '.elf')
        symbols = json.loads((out / 'spike' / (name + '.symbols.json')).read_text())
        debug = directory / (name + '.cmd')
        debug.write_text(f'until pc 0 {maps[name]["spike"]["pc"][2:]}\n'
                         'pc 0\ninsn 0\nreg 0 vl\nreg 0 vstart\n'
                         f'until pc 0 {symbols["replay_exit"]:x}\nreg 0 a0\nreg 0 minstret\n'
                         f'str {symbols["replay_log"]:x}\nrs\n')
        log = directory / (name + '.log')
        seconds = run([SPIKE, '-d', '--debug-cmd=' + str(debug), '--isa=' + ISA, '-m2', elf], log)
        text = log.read_text()
        values = re.findall(r'^0x([0-9a-f]{16})$', text, re.M)
        require(len(values) == 5, 'Missing target/exit reference fields')
        require([int(x, 16) for x in values[:4]] == [int(maps[name]['spike']['pc'], 16), 2, 1, 0], 'Target PC/VL/vstart/exit mismatch')
        for marker in (f'RVV_FP_MOVE_PASS sew={record["sew"]} cases=1 errors=0', f'BOARD_CASE_PASS {name}', 'BOARD_REPLAY_PASS'):
            require(marker in text, 'Reference completion missing')
        require(not re.search(r'RVV_FP_MOVE_FAIL|BOARD_CASE_FAIL|BOARD_REPLAY_(?:TRAP|\w*FAIL)|illegal instruction', text, re.I), 'Reference failure marker')
        results.append(dict(name=name, status='PASS', isa=ISA, instructions_to_replay_exit=int(values[4], 16),
                            elapsed_s=seconds, target=maps[name]['spike'], vl=2, vstart=1, log_sha256=prepare.sha(log)))
    prepare.save(out / 'reference.json', dict(status='SPIKE_47_PASS_NOT_DUT', results=results, spike_sha256=prepare.sha(SPIKE)))
    return results


def main(out):
    out = out.resolve()
    require(out.is_relative_to(HERE) and out != HERE and not out.exists(), 'Fresh owned output required')
    evidence = provenance()
    focused = module('tesla_fp_moves_focused', HERE.parent / 'fp_moves/focused.py')
    out.mkdir()
    prepared = out / 'prepared'
    prepared.mkdir()
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(BASE / name, prepared / name)
    prepare.save(out / 'original_provenance.json', evidence)
    for record in evidence['records']:
        name = record['name']
        case = prepared / name
        original = case / 'original'
        original.mkdir(parents=True)
        for filename in record['scenario_sources']:
            shutil.copyfile(ARCH / name / filename, original / filename)
        old = (original / 'scenario.c').read_text()
        new = focused.adapt(old, name, 2, 1)
        oracle = old[old.index('        unsigned long control='):old.index('        ++cases;')]
        require(oracle in new, 'Original complete oracle altered')
        (case / 'case.c').write_text(new)
        (case / 'adaptation.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='original/scenario.c', tofile='case.c')))
        (case / 'main.c').write_text('\n'.join(['extern void replay_text(const char *);',
            'extern volatile unsigned long replay_case;', f'extern int {name}_main(void);',
            'int main(void) { unsigned long vlenb; __asm__ volatile("csrr %0,vlenb":"=r"(vlenb));',
            'if(vlenb!=128) { replay_text("BOARD_REPLAY_VLEN_FAIL\\n"); return 90; }', 'replay_case=1;',
            f'replay_text("BOARD_CASE_BEGIN {name}\\n");', f'int rc={name}_main();',
            f'if(rc) {{ replay_text("BOARD_CASE_FAIL {name}\\n"); return rc; }}',
            f'replay_text("BOARD_CASE_PASS {name}\\nBOARD_REPLAY_PASS\\n"); return 0;', '}']) + '\n')
    prepare.save(prepared / 'provenance.json', dict(schema_version=1,
        original_provenance_sha256=prepare.sha(out / 'original_provenance.json'),
        cases=[dict(id=r['name'], sew=r['sew'], lmul=r['lmul'], op=r['operation_ids'][0], cap=r['cap'], configurations=1) for r in evidence['records']],
        full_oracle_unchanged=True, archived_assembly_unchanged=True,
        files={str(p.relative_to(prepared)): prepare.sha(p) for p in prepared.rglob('*') if p.is_file()}))
    try:
        host(prepared, out, evidence['records'])
        print('HOST_47_POSITIVE_282_NEGATIVE_PASS', flush=True)
        maps = build(prepared, out, evidence['records'])
        results = reference(out, evidence['records'], maps)
        for path, digest in evidence['pins'].items():
            require(prepare.sha(Path(path)) == digest, 'Source drift after preparation: ' + path)
        prepare.check(prepared)
        counts = [r['instructions_to_replay_exit'] for r in results]
        status = dict(status='HOST_SPIKE_47_PASS_READY_NOT_DUT', original_singles=47, slide_singles=32, insertion_singles=15,
                      instructions=dict(min=min(counts), max=max(counts), total=sum(counts)),
                      soc_programs=str(out / 'soc/programs.json'), VCS_launched=False, RTL_modified=False, image_built=False)
        prepare.save(out / 'status.json', status)
        print(json.dumps(status, indent=2))
    except Exception as error:
        prepare.save(out / 'failure.json', dict(status='NOT_PASS', error=str(error)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    main(parser.parse_args().out)
