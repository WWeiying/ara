#!/usr/bin/env python3
"""Independent same-ELF preparation comparison, only after the QEMU gate."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out') or out.exists():raise ValueError('Fresh independent output required')
    gate=ROOT/'verification/out/m4-tiled-reference-20261027-02'
    pins=json.loads((gate/'manifest.json').read_text());report=json.loads((gate/'result.json').read_text())
    if report['state']!='PASS' or len(report['configurations'])!=4 or hashes(map(Path,pins))!=pins:
        raise ValueError('Missing exact functional comparison')
    base=ROOT/'verification/qbs/combined_zvfh_m4/projection/build-03'
    old=json.loads((base/'manifest.json').read_text());data=[base/'activation_f32.bin',base/'activation_q8k_m4.bin']
    if any(old.get(str(p))!=digest(p) for p in data):raise ValueError('Accepted input/golden drift')
    templates=json.loads((base/'commands.json').read_text())
    out.mkdir(parents=True)
    assembly=out/'data.S';assembly.write_text('.section .rodata\n'+''.join(
        f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{path}"\n'
        for symbol,path in (('projection_input',data[0]),('projection_input_copy',data[0]),('projection_golden',data[1]))))
    link=out/'link.ld';link.write_bytes((base/'link.ld').read_bytes())
    sources=[HERE/'main.cpp',HERE.parent/'producer.cpp',HERE.parent/'tiled_producer.cpp',base/'generic.cpp',assembly,
        *(ROOT/'apps/common'/name for name in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c'))]
    pins.update(hashes([Path(__file__),gate/'result.json',gate/'manifest.json',*data,*sources,link,base/'commands.json']))
    pins.update(hashes((ROOT/'apps/common').glob('*.h')))
    commands=[];objects=[]
    def run(cmd,name):
        cmd=list(map(str,cmd));commands.append(cmd);atomic_json(out/'commands.json',commands)
        with (out/(name+'.log')).open('x') as stream:subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=180)
    for i,source in enumerate(sources):
        cmd=list(templates[0] if source.suffix=='.cpp' else templates[2])
        obj=out/f'{i}.o';cmd[cmd.index('-c')+1]=str(source);cmd[cmd.index('-o')+1]=str(obj)
        cmd+=['-I'+str(ROOT/'software/qbs/ggml')]
        if source.name=='string.c':cmd+=['-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns']
        run(cmd,'compile-'+str(i));objects.append(obj)
    compiler=Path(templates[0][0])
    for name in ('libstdc++.a','libm.a','libc.a','libgcc.a','libnosys.a'):
        path=Path(subprocess.check_output([str(compiler),'-print-file-name='+name],text=True).strip()).resolve(strict=True)
        pins.update(hashes([path]))
    elf=out/'qbs_current_projection_soc'
    run([compiler,'-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax','-static','-nostartfiles','-nostdlib',
         *objects,'-Wl,--gc-sections','-Wl,-Map='+str(out/'link.map'),'-T',link,'-Wl,--start-group',
         '-lstdc++','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf],'link')
    listing=subprocess.check_output([str(compiler.with_name('riscv64-unknown-elf-objdump')),'-d',str(elf)],text=True)
    if not all(value in listing for value in ('m4_produce','m4_tiled_produce','vsseg4e8.v','vsse8.v')):
        raise ValueError('Missing original/tiled producer or segment/stride stores')
    (out/'disassembly.log').write_text(listing)
    if hashes(map(Path,pins))!=pins:raise ValueError('Source drift')
    pins.update(hashes(p for p in out.iterdir() if p.is_file()));atomic_json(out/'manifest.json',pins)
    atomic_json(out/'build.json',dict(state='READY',elf_sha256=digest(elf),manifest_sha256=digest(out/'manifest.json'),
        performance_measured=False,scope='Three original/tiled preparations, no cache or QBS matrix computation'))
    print('READY')


if __name__=='__main__':main()
