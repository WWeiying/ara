#!/usr/bin/env python3
"""Fresh GNU assembly plus independent host oracle; no native run or simulation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from check import check, SYMBOL

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', type=Path, default=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc'))
    parser.add_argument('--host-cc', type=Path, default=Path('/usr/bin/gcc'))
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cc, host = args.cc.resolve(strict=True), args.host_cc.resolve(strict=True)
    objdump = cc.with_name(cc.name.removesuffix('gcc')+'objdump')
    nm = cc.with_name(cc.name.removesuffix('gcc')+'nm')
    source = ROOT/'software/akv/experimental/paired_heads/f32_pv/attention_rvv.S'
    baseline = ROOT/'software/akv/src/akv_v2_attention_rvv.S'
    inputs = [source, source.with_name('README.md'), baseline,
        ROOT/'software/akv/include/akv/akv_abi.h', HERE/'check.py', HERE/'oracle.c',
        Path(__file__).resolve(), cc, host, objdump, nm, Path(sys.executable).resolve()]
    pins = {str(p): digest(p) for p in inputs}
    commands = []
    def save(name, value):
        (out/name).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    def run(argv, name):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        save('commands.json', commands)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        return (out/(name+'.log')).read_text()
    try:
        for compiler, prefix in ((cc, 'riscv'), (host, 'host')):
            run([compiler, '--version'], prefix+'-gcc-version')
            for tool in ('cc1', 'as', 'ld'):
                name = run([compiler, '-print-prog-name='+tool], prefix+'-'+tool).strip()
                p = Path(name if '/' in name else shutil.which(name)).resolve(strict=True)
                pins[str(p)] = digest(p)
        libm = Path(run([host, '-print-file-name=libm.so.6'], 'libm-path').strip()).resolve(strict=True)
        pins[str(libm)] = digest(libm)
        save('sources-before.json', pins)
        flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax']
        obj, elf = out/'f32_pv.o', out/'f32_pv.elf'
        run([cc, *flags, '-c', source, '-o', obj], 'assemble')
        run([cc, *flags, '-nostdlib', '-nostartfiles', '-Wl,--no-relax', '-Wl,-Ttext=0x80000000',
             '-Wl,-e,'+SYMBOL, obj, '-o', elf], 'link')
        symbols = run([nm, '-g', '--defined-only', obj], 'symbols')
        if {line.split()[-1] for line in symbols.splitlines()} != {SYMBOL}:
            raise ValueError('Unexpected exported symbol')
        run([objdump, '-d', '-M', 'no-aliases', elf], 'disassembly')
        oracle = out/'oracle.so'
        run([host, '-std=c11', '-O2', '-shared', '-fPIC', '-fno-fast-math', '-frounding-math',
             '-ffp-contract=off', '-fno-builtin-fmaf', '-Wall', '-Wextra', '-Werror',
             '-Wno-unknown-pragmas', HERE/'oracle.c', '-lm', '-o', oracle], 'host-oracle')
        result = check(elf, oracle)
        after = {p: digest(p) for p in pins}
        save('sources-after.json', after)
        if after != pins:
            raise ValueError('Source/tool drift')
        result.update(source_pins=pins, artifacts={str(p): digest(p) for p in out.iterdir() if p.is_file()},
                      execution='NO_NATIVE_EXECUTION_NO_SIMULATION')
        save('result.json', result)
        print(json.dumps({k: result[k] for k in ('state', 'mapped_cases', 'exhaustive_shapes', 'rejected_mutations', 'execution')}))
    except BaseException as exc:
        save('result.json', dict(state='FAIL', error=repr(exc), execution='NO_NATIVE_EXECUTION_NO_SIMULATION'))
        raise


if __name__ == '__main__':
    main()
