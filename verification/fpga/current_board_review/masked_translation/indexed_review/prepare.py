#!/usr/bin/env python3
"""Inventory the archived NF7 replay geometry; this is not an RTL test."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path

CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
TOOLS = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/'
             'ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
NAME = 'rvv_fault_replay_segment_nf7_indexed_e32_mf2'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cases():
    result = []
    for unmapped, store, boundary, mode, split in itertools.product(
            range(2), range(2), (1, 3, 5), range(4), range(2)):
        mask = (255, 0xaa, 0x24, 0)[mode]
        base = 4096 - (boundary * 7 + (3 if split else 0)) * 4
        slots = [((i + 1) % boundary if i < boundary else boundary
                  if i == boundary else
                  boundary + 1 + (i - boundary) % (8 - boundary - 1))
                 for i in range(8)]
        addresses = [[base + slot * 28 + f * 4 for f in range(7)]
                     for slot in slots]
        active = [i for i in range(8) if (mask >> i) & 1]
        fault = next((i for i in active
                      if any(a >= 4096 for a in addresses[i])), None)
        permitted = [] if fault is None else [
            {'field': f, 'offset': a}
            for f, a in enumerate(addresses[fault]) if a >= 4096]
        assert sorted(slots) == list(range(8))
        assert len({a for row in addresses for a in row}) == 56
        assert all(0 <= a < 8192 and a % 4 == 0
                   for row in addresses for a in row)
        assert fault == next((i for i in range(boundary, 8)
                              if (mask >> i) & 1), None)
        result.append(dict(
            trial=len(result), unmapped=unmapped, store=store,
            boundary=boundary, mode=mode, split=split, mask=mask,
            base_offset=base, index_offsets=[s * 28 for s in slots],
            field_offsets=addresses, expected_vstart=fault,
            expected_cause=None if fault is None else 15 if store else 13,
            allowed_fault_addresses=permitted,
            completed_active_prefix=[] if fault is None else [
                i for i in active if i < fault]))
    assert len(result) == 96
    assert sum(c['expected_vstart'] is not None for c in result) == 72
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    if args.out.exists():
        raise SystemExit('Output already exists; preserve previous evidence')
    archive = CAMPAIGN / 'rvv_recovery12_indexed_failure01'
    evidence = json.loads((archive / 'evidence.json').read_text())
    elf, asm = archive / NAME, archive / (NAME + '.S')
    assert sha(elf) == evidence['case']['sha256']
    assert sha(asm) == evidence['assembly_sha256']
    generator = TOOLS / 'fault_replay.py'
    spec = importlib.util.spec_from_file_location('archived_replay_generator', generator)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    regenerated = module.assembly(32, indexed=True, lmul='mf2', fields=7)
    assert regenerated.encode() == asm.read_bytes(), 'Target assembly has drifted'
    report = dict(
        status='GEOMETRY_VERIFIED_NOT_RTL_EXECUTED',
        source_identity={str(p): sha(p) for p in
                         (elf, asm, generator, TOOLS / 'fault_replay_oracle.c',
                          archive / 'evidence.json')},
        limitation='Current C oracle is pinned but not proven identical to the '
                   'original compiled C. Archived aggregate does not identify '
                   'the failing trial or phase. No original Linux acceptance.',
        shape=dict(sew=32, lmul='mf2', fields=7, vl=8, index_sew=32,
                   data_registers=list(range(24, 31)), index_register=16),
        cases=cases())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('96 geometries, 72 expected faults; archived ELF/assembly verified')


if __name__ == '__main__':
    main()
