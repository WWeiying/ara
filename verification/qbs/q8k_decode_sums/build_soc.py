#!/usr/bin/env python3
"""Build the same captured-input ABBA harness for bare-metal VCS."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes
from check_soc import check


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--golden',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    golden=args.golden.resolve(strict=True)
    out=args.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'): raise ValueError('Use verification/out')
    report=json.loads((golden/'result.json').read_text())
    pins=json.loads((golden/'source-pins.json').read_text())
    if report['state']!='PASS' or hashes(map(Path,pins))!=pins or report['trials']!=check((golden/'qemu-1024.log').read_text()):
        raise ValueError('Golden evidence mismatch')
    out.mkdir(parents=True,exist_ok=False)
    common=ROOT/'apps/common'
    gcc=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
    objdump=gcc.with_name('riscv64-unknown-elf-objdump')
    helper=ROOT/'apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/script/build_pair.py'
    spec=importlib.util.spec_from_file_location('decode_link_check',helper)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    startup=[common/n for n in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    pins.update(hashes([Path(__file__),HERE/'check_soc.py',golden/'result.json',golden/'source-pins.json',
                       golden/'qemu-1024.log',gcc.resolve(),objdump.resolve(),helper,*startup,
                       *common.glob('*.h'),common/'arch.link.ld']))
    link=out/'link.ld'
    link.write_text((common/'arch.link.ld').read_text().replace('ALIGNMENT','16').replace('LENGTH = 0x00100000','LENGTH = 0x01000000'))
    flags=['-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-mno-relax','-O3','-DNDEBUG',
           '-fno-fast-math','-ffp-contract=off','-frounding-math','-fno-tree-vectorize',
           '-ffunction-sections','-fdata-sections','-DNR_LANES=4','-DVLEN=1024',
           *['-I'+str(d) for d in (common,ROOT/'apps/include',golden,HERE)]]
    commands=[]; objects=[]
    def run(argv,name):
        argv=list(map(str,argv)); commands.append(argv)
        atomic_json(out/'commands.json',commands)
        with (out/(name+'.log')).open('x') as stream:
            subprocess.run(argv,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=180)
    for i,path in enumerate([HERE/'soc_test.c',*startup]):
        extra=['-std=gnu11']
        if path==common/'string.c': extra+=['-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns']
        obj=out/(str(i)+'.o')
        run([gcc,*flags,*extra,'-c',path,'-o',obj],'compile-'+str(i))
        if path==common/'string.c': module.check_libc_calls(subprocess.check_output([objdump,'-dr',obj],text=True))
        objects.append(obj)
    elf=out/'q8k_decode_sums_soc'
    run([gcc,*flags,'-static','-nostartfiles','-nostdlib',*objects,'-Wl,--gc-sections',
         '-Wl,-Map='+str(out/'link.map'),'-T',link,'-lm','-lgcc','-o',elf],'link')
    sections=module.allocated_sections(elf)
    if min(s['address'] for s in sections)<0x80000000 or max(s['address']+s['bytes'] for s in sections)>0x81000000-65536:
        raise ValueError('ELF outside memory')
    run([objdump,'-d',elf],'disassembly')
    if hashes(map(Path,pins))!=pins: raise ValueError('Source drift')
    pins.update(hashes([link,*objects,elf]))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'build.json',dict(state='BUILT_NOT_EXECUTED',elf_sha256=digest(elf),
        manifest_sha256=digest(out/'manifest.json'),golden_trials=report['trials'],sections=sections,
        scope='Captured Decode Q and FFN-down complete activation preparation; not projection or model'))


if __name__=='__main__': main()
