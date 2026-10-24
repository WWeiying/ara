#!/usr/bin/env python3
"""GNU assembly/link and bounded host checks only; no native execution."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from check import check, QK, PV

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', type=Path, default=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc'))
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cc = args.cc.resolve(strict=True)
    objdump = cc.with_name(cc.name.removesuffix('gcc')+'objdump')
    nm = cc.with_name(cc.name.removesuffix('gcc')+'nm')
    source = ROOT/'software/akv/experimental/paired_heads/attention_rvv.S'
    inputs = [source, source.with_name('README.md'), Path(__file__).resolve(), HERE/'check.py',
              cc, objdump, nm, Path(sys.executable).resolve()]
    pins = {str(p): digest(p) for p in inputs}
    commands = []
    def save(name, value):
        (out/name).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    def run(argv, name):
        argv = list(map(str, argv))
        commands.append(argv)
        save('commands.json', commands)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        return (out/(name+'.log')).read_text()
    # Pin the underlying assembler/linker too, not just the GCC driver.
    for tool in ('as', 'ld'):
        p = Path(run([cc, '-print-prog-name='+tool], tool+'-path').strip()).resolve(strict=True)
        pins[str(p)] = digest(p)
    save('sources-before.json', pins)
    run([cc, '--version'], 'gcc-version')
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax']
    obj, elf = out/'attention.o', out/'attention.elf'
    run([cc, *flags, '-c', source, '-o', obj], 'assemble')
    run([cc, *flags, '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,-Ttext=0x80000000',
         '-Wl,-e,'+QK, obj, '-o', elf], 'link')
    symbols = run([nm, '-g', '--defined-only', obj], 'symbols')
    if {line.split()[-1] for line in symbols.splitlines()} != {QK, PV}:
        raise ValueError('Unexpected exported symbols')
    disassembly = run([objdump, '-d', elf], 'disassembly')
    result = check(disassembly)
    after = {p: digest(p) for p in pins}
    save('sources-after.json', after)
    if after != pins:
        raise ValueError('Source/tool drift')
    result.update(state='HOST_OBJECT_CHECK_PASS', sources=pins,
                  artifacts={str(p): digest(p) for p in out.iterdir() if p.is_file()},
                  execution='NO_NATIVE_EXECUTION_NO_SIMULATION')
    save('result.json', result)
    print(json.dumps({k: result[k] for k in ('state', 'mapped_matrix_cases', 'rejected_mutations', 'execution')}))


if __name__ == '__main__':
    main()
