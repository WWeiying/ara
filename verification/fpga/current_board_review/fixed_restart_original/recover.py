#!/usr/bin/env python3
"""Prove binary identity of one archived fixed-point restart source configuration."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
CAMP = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
ARCH = CAMP / 'rvv_fixed_restart01'
NAME = 'rvv_fixed_restart_e8_m4'
EXPECTED = 'ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc'
OLD_C = 'b50d3298db2c10f35a5a286f4db01d8b32603afdfc0a0ad1a5b0d3df087e56bc'
CC = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def main():
    out = HERE / 'recovery01'
    out.mkdir(exist_ok=False)
    manifest = json.loads((ARCH / 'manifest.json').read_text())
    entry = next(c for c in manifest['cases'] if c['name'] == NAME)
    assert entry['sha256'] == EXPECTED and manifest['source_sha256']['oracle.c'] == OLD_C
    original = ARCH / 'overlay/opt/ara-tests' / NAME
    assert sha(original) == EXPECTED
    for source, name in ((SOURCE / 'oracle.c', 'successor_oracle.c'),
                         (ARCH / 'operations.h', 'operations.h'), (ARCH / (NAME + '.S'), 'scenario.S')):
        shutil.copyfile(source, out / name)
    # Original fixed.py flags, no semantic/optimizer search and no source edits.
    flags = ['-Os', '-march=rv64gcv', '-mabi=lp64d', '-nostdlib', '-static',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize',
             '-fno-tree-slp-vectorize', '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
             '-Wall', '-Wextra', '-Werror', '-DSEW=8', '-DFRACTIONAL_SUITE=1']
    command = [str(CC), *flags, '-I' + str(out), str(out / 'successor_oracle.c'),
               str(out / 'scenario.S'), '-lgcc', '-o', str(out / NAME)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (out / 'build.log').write_text(result.stdout + result.stderr)
    result.check_returncode()
    for elf, name in ((original, 'original'), (out / NAME, 'rebuilt')):
        dis = subprocess.check_output([str(CC.with_name('riscv64-buildroot-linux-gnu-objdump')), '-d', str(elf)], text=True)
        (out / (name + '.dis')).write_text(dis)
    triage = json.loads((CAMP / 'stall_family_triage02/triage.json').read_text())
    # Locate the genuine record without assuming the outer ledger schema.
    def records(value):
        if isinstance(value, dict):
            if value.get('name') == NAME and 'last_trial' in value:
                yield value
            for child in value.values():
                yield from records(child)
        elif isinstance(value, list):
            for child in value:
                yield from records(child)
    record, = records(triage)
    assert sha(record['report']) == record['report_sha256'] and sha(record['binary']) == EXPECTED
    inputs = [SOURCE / 'oracle.c', SOURCE / 'fixed.py', SOURCE / 'build.py', ARCH / 'manifest.json',
              ARCH / 'operations.h', ARCH / (NAME + '.S'), original, CC,
              CAMP / 'stall_family_triage02/triage.json', Path(record['report']), Path(record['binary']), Path(__file__)]
    report = dict(status='EXACT_ELF_REBUILT' if sha(out / NAME) == EXPECTED else 'PROVENANCE_BLOCKED',
        original_c_bytes_recovered=sha(out / 'successor_oracle.c') == OLD_C,
        expected_original_c_sha256=OLD_C, successor_c_sha256=sha(out / 'successor_oracle.c'),
        original_elf_sha256=EXPECTED, rebuilt_elf_sha256=sha(out / NAME),
        byte_identical=(out / NAME).read_bytes() == original.read_bytes(), command=command,
        historical_record=record, pins={str(p): sha(p) for p in inputs}, DUT_started=False)
    save(out / 'report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('pins', 'command', 'historical_record')}, indent=2))
    assert report['byte_identical'], 'Stop: original binary equivalence not proved'


if __name__ == '__main__':
    main()
