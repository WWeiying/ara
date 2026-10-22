#!/usr/bin/env python3
"""Port archived large-offset slide fixtures without changing their workload."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'integration'
sys.path.insert(0, str(BASE))
import prepare

ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_verified_handoff03')
RUNTIME = Path('/tmp/current-board-integration-fast01/prepared')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')


def build(out):
    prepare.check(RUNTIME)
    out.mkdir(parents=True, exist_ok=False)
    prepared = out / 'prepared'
    prepared.mkdir()
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(RUNTIME / name, prepared / name)
    cases, identities = [], []
    for width, lmul in ((8, 'm4'), (8, 'm8'), (16, 'm8')):
        for sequence in (False, True):
            name = f'e{width}_{lmul}_' + ('sequence' if sequence else 'single')
            dirname = (f'rvv_small_slide_seq_e{width}_{lmul}_s0_m3' if sequence
                       else f'rvv_small_slide_e{width}_{lmul}_s0_m0')
            source = ARCHIVE / ('rvv_slide_sequence01' if sequence else 'rvv_small_slide04') / dirname
            record = json.loads((source / 'case.json').read_text())
            case = record['case']
            hashes = case['scenario_sources']
            for filename, expected in hashes.items():
                if prepare.sha(source / filename) != expected:
                    raise ValueError('archived source mismatch: ' + str(source / filename))
            for filename, key in (('original.elf', 'original_elf_sha256'),
                                  ('scenario.elf', 'sha256')):
                if prepare.sha(source / filename) != case[key]:
                    raise ValueError('archived ELF mismatch: ' + str(source / filename))
            original = prepared / name / 'original'
            original.mkdir(parents=True)
            for filename in ('scenario.c', 'operations.S', 'operations.h', 'case.json'):
                shutil.copyfile(source / filename, original / filename)
            adapted = prepare.adapt((source / 'scenario.c').read_text(), name)
            (original.parent / 'case.c').write_text(adapted)
            count = 4 if sequence else 1
            prepare.ORACLE_MARKERS[name] = f'RVV_PERMUTE_PASS sew={width} cases={count} errors=0'
            cases.append(dict(id=name, assembly='operations.S', defines=[f'SEW={width}'],
                              include_combined=True))
            identities.append(dict(id=name, source=str(source), record=record,
                                   record_sha256=prepare.sha(source / 'case.json'),
                                   source_sha256=hashes,
                                   adaptation='Linux entry/write/exit only; original loops, data and checks retained'))
    provenance = dict(schema_version=1, cases=cases, identities=identities,
                      vlen=1024, nr_lanes=4,
                      scope='original arithmetic source ports, not original Linux ELF execution',
                      helper_sha256=prepare.sha(BASE / 'prepare.py'),
                      adapter_sha256=prepare.sha(Path(__file__)),
                      runtime_provenance_sha256=prepare.sha(RUNTIME / 'provenance.json'))
    provenance['files'] = {str(p.relative_to(prepared)): prepare.sha(p)
                           for p in prepared.rglob('*') if p.is_file()}
    prepare.save(prepared / 'provenance.json', provenance)
    prepare.EXTENSIONS = [c['id'] for c in cases]
    for backend in ('soc', 'spike'):
        prepare.compile_programs(prepared, out / backend, CC, backend == 'spike')
    reference(out, out / 'reference')


def reference(out, report):
    provenance = prepare.check(out / 'prepared')
    programs = json.loads((out / 'spike/programs.json').read_text())
    if programs['provenance_sha256'] != prepare.sha(out / 'prepared/provenance.json'):
        raise ValueError('ELF provenance mismatch')
    report.mkdir(parents=True, exist_ok=False)
    results = []
    for case in provenance['cases']:
        name = case['id']
        elf = out / 'spike' / (name + '.elf')
        if prepare.sha(elf) != programs['programs'][name]['sha256']:
            raise ValueError('ELF hash mismatch: ' + name)
        command = [str(SPIKE), '--isa=rv64gcv_zvfh_zvl1024b', '-m2',
                   str(elf)]
        with (report / (name + '.log')).open('w') as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        # The sealed Spike runtime logs to RAM and reports main's result via
        # HTIF. Unlike SoC UART execution, it does not print PASS to stdout.
        passed = process.returncode == 0
        results.append(dict(name=name, command=command, returncode=process.returncode,
                            status='PASS' if passed else 'FAIL'))
        prepare.save(report / 'results.json', dict(spike_sha256=prepare.sha(SPIKE),
            scope='source-level oracle exit via HTIF; not an RTL result', results=results))
        if not passed:
            raise RuntimeError('reference failed: ' + name)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reference-only', action='store_true')
    parser.add_argument('--reference-out', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(HERE):
        parser.error('use an independent output under large_offset_slide/')
    if args.reference_only:
        report = args.reference_out.resolve() if args.reference_out else out / 'reference02'
        if not report.is_relative_to(HERE):
            parser.error('reference output must stay in this test directory')
        reference(out, report)
    else:
        build(out)
