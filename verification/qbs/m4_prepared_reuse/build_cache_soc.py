#!/usr/bin/env python3
"""Build full byte-cache cold/miss/hit costs against the accepted M4 producer."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    base=ROOT/'verification/qbs/combined_zvfh_m4/projection/build-03'
    commands=json.loads((base/'commands.json').read_text())
    oldpins=json.loads((base/'manifest.json').read_text())
    data=[base/'activation_f32.bin',base/'activation_q8k_m4.bin']
    if any(digest(x)!=oldpins[str(x)] for x in data):raise ValueError('Real capture drift')
    replay=ROOT/'verification/out/m4-cache-replay-20261027-01'
    rpins=json.loads((replay/'manifest.json').read_text())
    if json.loads((replay/'result.json').read_text())['state']!='PASS' or hashes(map(Path,rpins))!=rpins:
        raise ValueError('Missing real producer/cache functional acceptance')
    out.mkdir(parents=True,exist_ok=False)
    assembly=out/'data.S'
    assembly.write_text('.section .rodata\n'+''.join(
        f'.balign 64\n.global {name}\n{name}:\n.incbin "{path}"\n'
        for name,path in zip(('projection_input','projection_golden'),data)))
    link=out/'link.ld';link.write_bytes((base/'link.ld').read_bytes())
    sources=[HERE/'cache_soc.cpp',HERE/'producer.cpp',base/'generic.cpp',assembly,
             *(ROOT/'apps/common'/name for name in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c'))]
    compiler=Path(commands[0][0]);gcc=compiler.with_name('riscv64-unknown-elf-gcc')
    pins=dict(rpins)
    pins.update(hashes([Path(__file__),HERE/'cache_soc.cpp',link,base/'commands.json',
                       replay/'result.json',replay/'manifest.json',compiler.resolve(),gcc.resolve(),*sources]))
    pins.update(hashes((ROOT/'apps/common').glob('*.h')))
    for directory in (ROOT/'software/qbs/include',ROOT/'software/qbs/ggml',ROOT/'apps/include'):
        pins.update(hashes(directory.rglob('*.h')))
    # Pin current external headers too; no historical quants.c source is substituted.
    pins.update(hashes(Path('/home/wangwy/llama/llama.cpp/ggml').rglob('*.h')))
    executed=[];objects=[]
    for i,source in enumerate(sources):
        original=commands[0] if source.suffix=='.cpp' else commands[2]
        cmd=list(original);cmd[cmd.index('-c')+1]=str(source)
        obj=out/f'{i}.o';cmd[cmd.index('-o')+1]=str(obj)
        cmd+=['-I'+str(HERE),'-I'+str(ROOT/'software/qbs/ggml')]
        if source.name=='string.c':cmd+=['-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns']
        executed.append(cmd)
        with (out/f'compile-{i}.log').open('x') as stream:
            subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=180)
        objects.append(obj)
    elf=out/'qbs_current_projection_soc'
    cmd=[str(compiler),'-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax',
         '-static','-nostartfiles','-nostdlib',*map(str,objects),'-Wl,--gc-sections',
         '-Wl,-Map='+str(out/'link.map'),'-T',str(link),'-Wl,--start-group',
         '-lstdc++','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',str(elf)]
    executed.append(cmd)
    with (out/'link.log').open('x') as stream:
        subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=180)
    atomic_json(out/'commands.json',executed)
    listing=subprocess.check_output([str(compiler.with_name('riscv64-unknown-elf-objdump')),'-d',str(elf)],text=True)
    if not all(x in listing for x in ('m4_produce','vredmaxu.vs','_sbrk')):
        raise ValueError('Missing real producer/allocator path')
    (out/'disassembly.log').write_text(listing)
    if hashes(map(Path,pins))!=pins:raise ValueError('Build drift')
    pins.update(hashes(p for p in out.iterdir() if p.is_file()))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'build.json',dict(state='READY',execution='NOT_RUN',
        manifest_sha256=digest(out/'manifest.json'),elf_sha256=digest(elf),
        scope='M4/K1536 three preparation calls, baseline/cache ABBA; excludes QBS matrix execution',
        production_modified=False,performance_validation=False))
    print(json.dumps(dict(state='READY',output=str(out))))


if __name__=='__main__':main()
