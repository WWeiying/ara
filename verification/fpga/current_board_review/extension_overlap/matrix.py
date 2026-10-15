#!/usr/bin/env python3
"""Prepare same-source extension derivatives and Spike references, never run RTL."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from adapter import HERE, BASE, CAMPAIGN, PARENT, SOURCE, PINS, CC, SPIKE, inside, prepare

SHAPES = [
    (16, 2, 2, '9235360ef269649313c2a1ba84450b438fb07d3f056383194e11d574c4472152'),
    (32, 2, 2, '02e686908df9e5fd0e18e176d1cc11e99fd1cd0d202a06b654435727c5edef91'),
    (64, 2, 2, 'f7b208331d638c64117856c716623b15e4b9e53aef01f8382996a00d823372b8'),
    (32, 4, 4, 'e243364f114a90d42db9b67f0fb7bb0e71dce18a97b68c9357d8adf450e0ed76'),
    (64, 4, 4, '71dd19a1bd0fff6b2a61934b9dd6aef916ce133298cabd02b0c0ccc5682e3d05'),
    (64, 8, 8, 'ddbcc3262d7f77456ec5cb669232041533b4a6bd57c8523e6ddd4690ab5e297b'),
]


def cases(sew, regs, factor):
    cap = regs * 128 // (sew // 8)
    boundary = (regs - regs // factor) * 128 // (sew // 8)
    rows = []

    def add(label, op, mode=0, start=0, vl=cap-1, unmasked=0, seed=0):
        rows.append(dict(label=label, op=op, mode=mode, start=start,
                         vl=vl, unmasked=unmasked, seed=seed))

    for op in (2, 3):
        for mode in range(4):
            add(f'overlap_op{op}_mask{mode}', op, mode)
    add('unsigned_unmasked_prefix1', 2, start=1, unmasked=1)
    add('signed_unmasked_prefix1', 3, start=1, unmasked=1)
    add('unsigned_masked_prefix1', 2, mode=2, start=1)
    add('signed_masked_word_prefix', 3, mode=3, start=64//sew)
    add('unsigned_unmasked_register_prefix', 2, start=128//(sew//8), unmasked=1)
    add('signed_unmasked_overlap_prefix', 3, start=boundary+1, unmasked=1)
    add('unsigned_masked_overlap_prefix', 2, mode=2, start=boundary+1)
    add('signed_masked_register_prefix', 3, mode=3, start=128//(sew//8))
    add('empty_prestart', 2, start=cap-1, unmasked=1)
    add('zero_vl', 3, vl=0)
    add('full_unsigned_unmasked', 2, vl=cap, unmasked=1)
    add('full_signed_sparse_seed1', 3, mode=2, vl=cap, seed=1)
    add('disjoint_unsigned_masked_prefix', 0, mode=2, start=1)
    add('disjoint_signed_unmasked_prefix', 1, start=1, unmasked=1)
    add('last_nonoverlapping_destination_element', 2, vl=boundary)
    add('first_overlapping_destination_element', 3, vl=boundary+1)
    assert len(rows) == 24
    return cap, rows


def derivative_assembly(original):
    # Preserve the original four functions byte-for-byte; add separately named
    # restart/mask variants with identical setup and readback ordering.
    body = original[original.index('.global op_0'):]
    variants = []
    for suffix in ('masked', 'unmasked'):
        text = re.sub(r'\bop_([0-3])\b', rf'op_\1_{suffix}', body)
        text, count = re.subn(r'^(v[zs]ext\.vf[248] .*)$',
                             r'csrw vstart,a5\n\1', text, flags=re.M)
        if count != 4:
            raise ValueError('unexpected source assembly')
        if suffix == 'unmasked':
            text = text.replace(',v0.t', '')
        variants.append(text)
    return original + '\n' + '\n'.join(variants)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    out = inside(args.out)
    out.mkdir(parents=True, exist_ok=False)
    prepared = out / 'prepared'
    prepared.mkdir()
    parent = prepare.check(PARENT)
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(PARENT / name, prepared / name)
    if prepare.sha(SOURCE / 'scenario.c') != PINS['scenario.c']:
        raise ValueError('original oracle drift')
    shutil.copyfile(SOURCE / 'scenario.c', prepared / 'source_oracle.c')
    records, names, markers = [], [], {}
    for sew, regs, factor, digest in SHAPES:
        name = f'extension_e{sew}_m{regs}_vf{factor}'
        original = prepared / name / 'original'
        original.mkdir(parents=True)
        source = CAMPAIGN / 'rvv_extensions01' / ('rvv_' + name + '.S')
        if prepare.sha(source) != digest:
            raise ValueError('source assembly drift: ' + str(source))
        shutil.copyfile(source, original / 'source.S')
        text = source.read_text()
        (original / 'scenario.S').write_text(derivative_assembly(text))
        shutil.copyfile(HERE / 'matrix.c', original.parent / 'case.c')
        cap, rows = cases(sew, regs, factor)
        header = [f'#define EXPECTED_CAP {cap}', 'static const struct trial trials[] = {']
        for row in rows:
            header.append('    {' + ', '.join(str(row[k]) for k in
                ('op', 'mode', 'start', 'vl', 'unmasked', 'seed')) + '},')
        header.append('};')
        (original / 'test_cases.h').write_text('\n'.join(header) + '\n')
        prepare.save(original / 'cases.json', rows)
        records.append(dict(id=name, assembly='scenario.S', include_combined=True,
            defines=[f'SEW={sew}', f'FACTOR={factor}', f'DEST_REGS={regs}',
                     f'SOURCE_REGS={regs//factor}', f'matrix_main={name}_main'],
            original_assembly=str(source), original_assembly_sha256=digest,
            scope='same-source direct derivative, not original Linux ELF', cases=rows))
        names.append(name)
        markers[name] = f'EXTENSION_MATRIX_PASS sew={sew} factor={factor} cases=24 errors=0'
    provenance = dict(schema_version=1, vlen=1024, nr_lanes=4, cases=records,
        generator_sha256=prepare.sha(Path(__file__)), driver_sha256=prepare.sha(HERE / 'matrix.c'),
        original_oracle_sha256=PINS['scenario.c'], no_original_inputs_changed=True,
        parent_provenance_sha256=prepare.sha(PARENT / 'provenance.json'),
        parent_runtime_sha256={n: parent['files'][n] for n in ('startup.S', 'runtime.c', 'replay.ld')},
        helper_sha256={n: prepare.sha(BASE / n) for n in ('prepare.py', 'run.py')})
    provenance['files'] = {str(p.relative_to(prepared)): prepare.sha(p)
                           for p in prepared.rglob('*') if p.is_file()}
    prepare.save(prepared / 'provenance.json', provenance)
    prepare.EXTENSIONS = names
    prepare.ORACLE_MARKERS.update(markers)
    for backend in ('spike', 'soc'):
        prepare.compile_programs(prepared, out / backend, CC, backend == 'spike')
    results = []
    for name in [*names, 'all']:
        elf = out / 'spike' / (name + '.elf')
        nm = subprocess.check_output([str(CC.with_name(CC.name.removesuffix('gcc') + 'nm')),
                                      str(elf)], text=True)
        symbols = {n: a for a, _, n in (line.split() for line in nm.splitlines())}
        debug = out / (name + '.cmd')
        debug.write_text('until pc 0 ' + symbols['replay_exit'] + '\nreg 0 a0\nstr '
                         + symbols['replay_log'] + '\nrs\n')
        command = [str(SPIKE), '-d', '--debug-cmd=' + str(debug),
                   '--isa=rv64gcv_zvl1024b', '-m2', str(elf)]
        log_path = out / (name + '.log')
        with log_path.open('w') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=30)
        text = log_path.read_text()
        expected = list(markers.values()) if name == 'all' else [markers[name]]
        passed = result.returncode == 0 and all(m in text for m in expected)
        results.append(dict(name=name, status='PASS' if passed else 'FAIL',
            returncode=result.returncode, command=command, elf_sha256=prepare.sha(elf),
            log_sha256=prepare.sha(log_path), pass_markers=expected))
    prepare.save(out / 'reference.json', dict(results=results, total_unique_cases=144,
        combined_repeat_cases=144, spike_sha256=prepare.sha(SPIKE),
        status='PASS' if all(r['status'] == 'PASS' for r in results) else 'FAIL',
        rtl_executed=False, rtl_built=False, original_measurement01_unchanged=True))
    print(json.dumps([(r['name'], r['status']) for r in results]))
    if any(r['status'] != 'PASS' for r in results):
        raise RuntimeError('matrix reference failed')


if __name__ == '__main__':
    main()
