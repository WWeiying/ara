#!/usr/bin/env python3
"""One bounded source reconstruction and whole-ELF identity check, no execution."""
import difflib
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
CAMP = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix')
ARCH = CAMP / 'rvv_macc_restart_disjoint01'
NAME = 'rvv_integer_macc_accumulators_restart_e8_m4'
EXPECTED = '608e941760443563f055058d60f18ce466a06d016fb277989fc332ed9cdb347d'
CC = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main(unchanged_successor=False):
    out = HERE / ('identity02' if unchanged_successor else 'identity01')
    out.mkdir(exist_ok=False)
    manifest = json.loads((ARCH / 'manifest.json').read_text())
    entry = next(r for r in manifest['cases'] if r['name'] == NAME)
    original = CAMP / 'rvv_additions42/binaries' / NAME
    assert sha(original) == entry['sha256'] == EXPECTED
    source = (SOURCE / 'oracle.c').read_text()
    old = '''                        /* TCSBRK with nonzero argument drains the tty output. */
                        if(syscall3(29,1,0x5409,1)) {
                            text("RVV_TRACE_TTY_DRAIN_FAILED\\n");finish(2);
                        }'''
    assert source.count(old) == 1
    recovered = source if unchanged_successor else source.replace(old, '                        syscall3(29,1,0x5409,1);')
    (out / 'successor_oracle.c').write_text(source)
    (out / 'reconstructed_oracle.c').write_text(recovered)
    (out / 'reconstruction.diff').write_text(''.join(difflib.unified_diff(
        source.splitlines(True), recovered.splitlines(True), fromfile='current', tofile='reconstructed')))
    shutil.copyfile(ARCH / (NAME + '.S'), out / 'scenario.S')
    shutil.copyfile(ARCH / 'operations.h', out / 'operations.h')
    cmd = [str(CC), '-Os', '-march=rv64gcv', '-mabi=lp64d', '-nostdlib', '-static',
           '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize',
           '-fno-tree-slp-vectorize', '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
           '-Wall', '-Wextra', '-Werror', '-DSEW=8', '-I' + str(out),
           str(out / 'reconstructed_oracle.c'), str(out / 'scenario.S'), '-lgcc', '-o', str(out / NAME)]
    save(out / 'compile.command.json', cmd)
    with (out / 'compile.log').open('x') as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    for label, elf in [('original', original), ('reconstructed', out / NAME)]:
        with (out / (label + '.dis')).open('x') as log:
            subprocess.run([str(CC.with_name('riscv64-buildroot-linux-gnu-objdump')), '-d', str(elf)],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    same = sha(out / NAME) == EXPECTED
    inputs = [SOURCE / 'oracle.c', SOURCE / 'integer_forms.py', SOURCE / 'build.py',
              ARCH / 'manifest.json', ARCH / 'operations.h', ARCH / (NAME + '.S'), original, CC]
    report = dict(status='EXACT_ORIGINAL_ELF_RECONSTRUCTED' if same else 'IDENTITY_MISMATCH',
                  original_sha256=EXPECTED, rebuilt_sha256=sha(out / NAME),
                  original_c_sha256=manifest['source_sha256']['oracle.c'],
                  reconstructed_c_sha256=sha(out / 'reconstructed_oracle.c'),
                  source_text_recovered=sha(out / 'reconstructed_oracle.c') == manifest['source_sha256']['oracle.c'],
                  whole_elf_byte_equal=same, full_program_executed=False,
                  hypothesis=('Original disassembly checks tty return at 0x106be; retain current C unchanged; '
                              'successor chain/alias features may preprocess away under archived header'
                              if unchanged_successor else
                              'Only observable successor change is checked tty-drain return; remove that branch'),
                  input_pins={str(p): sha(p) for p in inputs})
    save(out / 'report.json', report)
    print(json.dumps(report, indent=2))
    return 0 if same else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unchanged-successor', action='store_true')
    raise SystemExit(main(parser.parse_args().unchanged_successor))
