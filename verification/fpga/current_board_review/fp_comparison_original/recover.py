#!/usr/bin/env python3
"""Inventory original FP-comparison records and recover hash-exact C revision."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
CAMP = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
TOOLS = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
OLD = '3652ca2d4f3f7b63995234bf624514dfb318db9cd781aeee0a7533d6c564491c'
CURRENT = '03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad'
CC = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def save(p, obj):
    p.write_text(json.dumps(obj, indent=2) + '\n')


def main():
    out = HERE / 'provenance01'
    out.mkdir(parents=True, exist_ok=False)
    pins = {}

    def pin(p, expected=None):
        digest = sha(p)
        assert expected is None or digest == expected, str(p)
        pins[str(p)] = digest
        return digest

    source = TOOLS / 'fp_compare_oracle.c'
    pin(source, CURRENT)
    removed = ['#ifndef UNBOXED_COMPARISONS\n#define UNBOXED_COMPARISONS 0\n#endif\n',
               '            /* Quiet-NaN payloads have identical comparison/exception semantics. */\n'
               '            if(UNBOXED_COMPARISONS && op>=4)bi=14;\n']
    old = source.read_text()
    for part in removed:
        assert old.count(part) == 1
        old = old.replace(part, '')
    recovered = out / 'fp_compare_oracle_3652.c'
    recovered.write_text(old)
    assert sha(recovered) == OLD
    save(out / 'recovery.json', dict(input=str(source), input_sha256=CURRENT,
        removed_exact_text=removed, recovered_sha256=OLD,
        method='Inverse of two later unboxed additions; exact historical manifest SHA, not behavioral inference'))
    audit = CAMP / 'all_failure_scope_audit02/audit.json'
    pin(audit)
    originals = [x for x in read(audit)['cases'] if x['status'] == 'failed'
                 and x['name'].startswith('rvv_fp_compare_')]
    assert len(originals) == 237
    manifests = []
    for p in sorted(CAMP.glob('*/manifest.json')):
        d = read(p)
        sources = d.get('source_sha256', {})
        if isinstance(sources, dict) and 'fp_compare_oracle.c' in sources:
            manifests.append((p, d))
    rows = []
    for record in originals:
        matches = [(p, d, c) for p, d in manifests for c in d.get('cases', [])
                   if c['name'] == record['name'] and c['sha256'] == record['sha256']]
        assert matches, record['name']
        p, d, c = matches[0]
        pin(p)
        release = Path(record['releases'][0])
        pin(release)
        elf = release.parent / 'binaries' / record['name']
        pin(elf, record['sha256'])
        asm = p.parent / (record['name'] + '.S')
        pin(asm)
        for h in ('fixtures.h', 'operations.h'):
            pin(p.parent / f'e{c["sew"]}' / h)
        h = d['source_sha256']['fp_compare_oracle.c']
        rows.append(dict(name=record['name'], family=record['family'], original_elf=str(elf),
            sha256=record['sha256'], manifest=str(p), assembly=str(asm), sew=c['sew'], lmul=c['lmul'],
            source_c_sha256=h, source_status='HASH_EXACT_RECOVERED' if h == OLD else
            'HASH_EXACT_PRESENT' if h == CURRENT else 'NOT_RECOVERED',
            evidence=record['evidence'], defines=dict(SEW=c['sew'], UNMASKED_COMPARISONS=int(d.get('unmasked', False)),
                RESTART_COMPARISONS=int(d.get('restart_tested', False)), UNBOXED_COMPARISONS=int(d.get('unboxed_scalar', False)),
                DESTINATION_KIND={'v24':0,'v8':1,'v16':2,'v0':3}[d.get('destination','v24')])) )
    reduced = []
    for name in ('rvv_small_fp_compare02', 'rvv_small_fp_compare_reconstructed01',
                 'rvv_detail_fp_compare01', 'rvv_compare_uncovered01'):
        p = CAMP / name / 'manifest.json'
        pin(p)
        for c in read(p)['cases']:
            pin(CAMP / name / 'binaries' / c['name'], c['sha256'])
            for fn, digest in c['scenario_sources'].items():
                pin(CAMP / name / c['name'] / fn, digest)
            reduced.append(dict(archive=name, **c))
    assert len({c['original_name'] for c in reduced}) == 237
    save(out / 'parents.json', rows)
    save(out / 'singles.json', reduced)
    save(out / 'inventory.json', dict(original_failed_parents=len(rows),
        nonrestart=sum(not r['defines']['RESTART_COMPARISONS'] for r in rows),
        restart=sum(bool(r['defines']['RESTART_COMPARISONS']) for r in rows),
        families=dict(collections.Counter(r['family'] for r in rows)),
        source_status=dict(collections.Counter(r['source_status'] for r in rows)),
        child_records=len(reduced), unique_child_parents=len({r['original_name'] for r in reduced}),
        archives=dict(collections.Counter(r['archive'] for r in reduced)),
        limitation='Child reductions are not additional independent failures; reconstructed labels retained verbatim.'))
    # Rebuild the priority original, not the already passing 50-call derivative.
    row = next(r for r in rows if r['name'] == 'rvv_fp_compare_unmasked_alias_v8_e16_m8')
    binary = out / 'original_rebuilt.elf'
    cmd = [str(CC), '-Os', '-march=rv64gcv', '-mabi=lp64d', '-nostdlib', '-static', '-ffreestanding',
           '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
           '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s', '-Wall', '-Wextra', '-Werror',
           *['-D'+k+'='+str(v) for k,v in row['defines'].items()],
           '-I'+str(Path(row['manifest']).parent / 'e16'), str(recovered), row['assembly'], '-o', str(binary)]
    save(out / 'original_rebuild.command.json', cmd)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    (out / 'original_rebuild.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0
    save(out / 'original_rebuild.json', dict(original=row['original_elf'], original_sha256=row['sha256'],
        rebuilt_sha256=sha(binary), byte_identical=sha(binary) == row['sha256']))
    assert sha(binary) == row['sha256'], 'Original ELF identity not recovered'
    pin(CC.resolve())
    pin(Path(__file__))
    save(out / 'pins.json', pins)
    print(json.dumps(read(out / 'inventory.json')))
    print('ORIGINAL_E16_M8_ELF_BYTE_IDENTICAL')


if __name__ == '__main__':
    main()
