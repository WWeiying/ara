#!/usr/bin/env python3
"""Audit the archived 83 gather singles and prepare eight unchanged-oracle ports."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
INTEGRATION = HERE.parent / 'integration'
CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
ARCHIVE = CAMPAIGN / 'rvv_verified_handoff03/rvv_small_gather02'
FROZEN = Path('/home/wangwy/fpga_runs/current_board_memory_candidate03/frozen')
SELECTED = (
    'e16_m1_ops0', 'e8_mf8', 'e16_mf4', 'e16_m1_ops1',
    'e32_m1_ops2', 'e64_m1_ops3', 'e32_m8_ops20', 'e64_m8_ops0',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def audit():
    manifest = json.loads((ARCHIVE / 'source_manifest.json').read_text())
    symptoms = json.loads((ARCHIVE / 'symptoms.json').read_text())
    original = json.loads((ARCHIVE / 'original_report.json').read_text())['report']
    board = json.loads((ARCHIVE / 'board_report.json').read_text())
    by_original = {r['name']: r for r in original['results']}
    by_board = {r['name']: r for r in board['results']}
    by_symptom = {r['name']: r for r in symptoms['cases']}
    assert len(manifest['cases']) == symptoms['confirmed'] == 83
    assert symptoms['pending'] == 0
    assert sha(ARCHIVE / 'original_report.json') == manifest['original_report_sha256']
    assert sha(ARCHIVE / 'source_manifest.json') == symptoms['manifest_sha256']
    assert sha(ARCHIVE / 'board_report.json') == symptoms['report_sha256']
    records = []
    for case in manifest['cases']:
        name = case['name']
        folder = ARCHIVE / name
        evidence = json.loads((folder / 'case.json').read_text())
        assert evidence['case'] == case and evidence['evidence'] == by_symptom[name]
        assert by_symptom[name]['confirmed'] and by_symptom[name]['status'] == 'failed'
        assert by_symptom[name]['tuple'] == case['selected_trial']
        assert case['configurations'] == 1 and case['original_rebuild_byte_identical']
        for file, digest in case['scenario_sources'].items():
            assert sha(folder / file) == digest, (name, file)
        assert sha(folder / 'scenario.elf') == case['sha256']
        assert sha(folder / 'original.elf') == case['original_elf_sha256']
        raw_original = by_original[case['original_name']]
        raw_board = by_board[name]
        assert raw_original['status'] == raw_board['status'] == 'failed'
        assert case['original_failure_detail'] in raw_original['output']
        assert case['original_failure_detail'] in raw_board['output']
        marker = f"RVV_PERMUTE_FAIL sew={case['sew']} cases=1 errors=1"
        assert marker in raw_board['output'] and raw_board['exit_code'] == 1
        suffix = name.removeprefix('rvv_small_gather_restart_')
        records.append(dict(case=case, source_directory=str(folder),
                            raw_original=raw_original, raw_board=raw_board,
                            selected=suffix in SELECTED))
    keys = [(r['case']['sew'], r['case']['lmul'], r['case']['selected_trial']['op'])
            for r in records]
    assert len(set(keys)) == 83
    masku = Path('hardware/src/masku/masku.sv')
    pinned = json.loads((FROZEN / 'snapshot.json').read_text())['files'][str(masku)]
    assert sha(ROOT / masku) == sha(FROZEN / 'sources' / masku) == pinned
    result = dict(scope='83 authentic measured single trials; no DUT acceptance',
                  confirmed=83, distinct_shape_opcode_keys=83,
                  parent_records=3, partition_records=80,
                  manifest_sha256=sha(ARCHIVE / 'source_manifest.json'),
                  symptoms_sha256=sha(ARCHIVE / 'symptoms.json'),
                  original_report_sha256=sha(ARCHIVE / 'original_report.json'),
                  board_report_sha256=sha(ARCHIVE / 'board_report.json'),
                  candidate03_snapshot_sha256=sha(FROZEN / 'snapshot.json'),
                  masku_sha256=pinned, records=records)
    save(HERE / 'inventory83.json', result)
    return records


def prepare(records):
    sys.path.insert(0, str(INTEGRATION))
    from prepare import adapt
    out = HERE / 'prepared01'
    out.mkdir(exist_ok=False)
    selected = []
    for suffix in SELECTED:
        record, = [r for r in records if r['case']['name'].endswith('_' + suffix)]
        case = record['case']
        identity = 'gather_' + suffix
        folder = out / identity / 'original'
        folder.mkdir(parents=True)
        for file in case['scenario_sources']:
            shutil.copyfile(Path(record['source_directory']) / file, folder / file)
        shutil.copyfile(Path(record['source_directory']) / 'case.json', folder / 'case.json')
        # Only the existing integration Linux entry/I/O/exit adapter is applied.
        (folder.parent / 'case.c').write_text(adapt((folder / 'scenario.c').read_text(), identity))
        selected.append(dict(id=identity, source_directory=record['source_directory'],
                             original_case=case, assembly='operations.S',
                             defines=[f"SEW={case['sew']}", 'RESTART_PERMUTATIONS=1',
                                      f"PERMUTE_OP_MASK={1 << case['selected_trial']['op']}"],
                             pass_markers=[f'BOARD_CASE_PASS {identity}', 'BOARD_REPLAY_PASS',
                                           f"RVV_PERMUTE_PASS sew={case['sew']} cases=1 errors=0"]))
    for file in ('runtime.c', 'startup.S', 'replay.ld'):
        shutil.copyfile(INTEGRATION / file, out / file)
    provenance = dict(cases=selected, vlen=1024, nr_lanes=4,
                      scope='architectural source ports, not Linux ELF replay',
                      generator_sha256=sha(Path(__file__)),
                      adapter_sha256=sha(INTEGRATION / 'prepare.py'),
                      files={str(p.relative_to(out)): sha(p)
                             for p in sorted(out.rglob('*')) if p.is_file()})
    save(out / 'provenance.json', provenance)
    return out, provenance


def build(prepared, provenance, backend):
    cc = (ROOT / 'install/riscv-gcc/bin/riscv64-unknown-elf-gcc').resolve(strict=True)
    out = HERE / (backend + '01')
    out.mkdir(exist_ok=False)
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
             '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-msmall-data-limit=0',
             '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror']
    if backend == 'spike':
        flags.append('-DSPIKE_REFERENCE=1')
    commands = []

    def execute(command):
        commands.append(list(map(str, command)))
        subprocess.run(command, check=True, timeout=30)
        save(out / 'commands.json', commands)

    common = []
    for file in ('startup.S', 'runtime.c'):
        obj = out / (file + '.o')
        execute([cc, *flags, '-c', prepared / file, '-o', obj])
        common.append(obj)
    programs = {}
    for case in provenance['cases']:
        identity = case['id']
        folder = prepared / identity
        assembly = folder / 'original/operations.S'
        symbols = re.findall(r'^\.global\s+(\w+)\s*$', assembly.read_text(), re.MULTILINE)
        defines = ['-D' + d for d in case['defines']]
        defines += [f'-D{s}={identity}_{s}' for s in symbols]
        defines += ['-I' + str(folder / 'original')]
        objects = []
        for index, source in enumerate((folder / 'case.c', assembly)):
            obj = out / f'{identity}_{index}.o'
            execute([cc, *flags, *defines, '-c', source, '-o', obj])
            objects.append(obj)
        main = out / (identity + '_main.c')
        main.write_text(
            'extern void replay_text(const char *);\n'
            'extern volatile unsigned long replay_case;\n'
            f'extern int {identity}_main(void);\n'
            'int main(void) { unsigned long vlenb;\n'
            '__asm__ volatile("csrr %0,vlenb" : "=r"(vlenb));\n'
            'if (vlenb != 128) { replay_text("BOARD_REPLAY_VLEN_FAIL\\n"); return 90; }\n'
            f'replay_case=1; replay_text("BOARD_CASE_BEGIN {identity}\\n");\n'
            f'if ({identity}_main()) {{ replay_text("BOARD_CASE_FAIL {identity}\\n"); return 1; }}\n'
            f'replay_text("BOARD_CASE_PASS {identity}\\nBOARD_REPLAY_PASS\\n"); return 0; }}\n')
        elf = out / (identity + '.elf')
        execute([cc, *flags, '-nostdlib', '-static', '-Wl,--build-id=none',
                 '-Wl,--gc-sections', '-T', prepared / 'replay.ld', main,
                 *common, *objects, '-lgcc', '-o', elf])
        programs[identity] = dict(path=str(elf), sha256=sha(elf),
                                  pass_markers=case['pass_markers'])
    save(out / 'programs.json', dict(programs=programs,
                                   backend='vcs-soc' if backend == 'soc' else 'spike-htif',
                                   compiler=dict(path=str(cc), sha256=sha(cc)),
                                   prepared=str(prepared),
                                   provenance_sha256=sha(prepared / 'provenance.json'),
                                   vcs_started=False))
    return programs


def reference(programs):
    sys.path.insert(0, str(ROOT / 'verification'))
    from ara_verify.spike_probe import check_spike_vstart, probe_paths
    spike = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
    cc, source = probe_paths(ROOT)
    out = HERE / 'reference01'
    out.mkdir(exist_ok=False)
    assert check_spike_vstart(spike, cc, out / 'vstart_probe', source)['status'] == 'PASS'
    results = []
    for name, program in programs.items():
        command = [str(spike), '--isa=rv64gcv_zvl1024b', '-m2', program['path']]
        begin = time.monotonic()
        with (out / (name + '.log')).open('w') as stream:
            completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=15)
        results.append(dict(name=name, command=command, returncode=completed.returncode,
                            status='PASS' if completed.returncode == 0 else 'FAIL',
                            elapsed_s=time.monotonic()-begin, elf_sha256=program['sha256']))
    save(out / 'reference.json', dict(scope='Spike HTIF self-oracle exit checks, not DUT/trace equivalence',
                                     spike_sha256=sha(spike), results=results))
    assert all(r['returncode'] == 0 for r in results)


if __name__ == '__main__':
    records = audit()
    prepared, provenance = prepare(records)
    build(prepared, provenance, 'soc')
    reference(build(prepared, provenance, 'spike'))
    print('83 records hash-audited; eight SoC ports built; eight Spike self-oracles PASS')
