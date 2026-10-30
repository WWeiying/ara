#!/usr/bin/env python3
"""Same full decoder workload; only reduce proven off-timer verification cost."""
import argparse
import importlib.util
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/akv/paired_heads'))
import attention_run as s


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    base=ROOT/'verification/out/akv-quantkv-value-decode-build-20261024-02'
    report=s.read_json(base/'build.json')
    s.require(report['state']=='BUILT_NOT_EXECUTED' and report['trials']==8 and
        report['elements_per_trial']==32768 and report['boundary_elements']==3584 and
        s.digest(base/'source-pins.json')==report['source_pins_sha256'],'Wrong original workload/build')
    pins=s.read_json(base/'source-pins.json'); s.merge_pins(pins,report['artifact_sha256']); s.verify_pins(pins)
    commands=[]
    def execute(argv,label):
        argv=list(map(str,argv)); commands.append(dict(argv=argv,cwd=str(out)))
        s.atomic_json(out/'commands.json',commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(label+'.log')).read_text()
    old=s.read_json(base/'commands.json')
    compile_command=list(next(r['argv'] for r in old if '-c' in r['argv'] and str(HERE/'value_decode_main.c') in r['argv']))
    compile_command[compile_command.index(str(HERE/'value_decode_main.c'))]=str(HERE/'value_decode_fast_main.c')
    compile_command[compile_command.index('-o')+1]=str(out/'main.o')
    dep=[x for i,x in enumerate(compile_command) if i not in
        (compile_command.index('-c'),compile_command.index('-o'),compile_command.index('-o')+1)]+['-M','-MT','object']
    dependencies=execute(dep,'deps-main')
    s.merge_pins(pins,s.hashes(Path(x).resolve(strict=True) for x in
        shlex.split(dependencies.replace('\\\n',' ').split(':',1)[1])))
    execute(compile_command,'compile-main')
    elf=out/'quant_value_decode_fast.elf'
    link=[str(out/'main.o') if x==str(base/'main.o') else
          '-Wl,-Map='+str(out/'link.map') if x=='-Wl,-Map='+str(base/'link.map') else x
          for x in next(r['argv'] for r in old if '-nostdlib' in r['argv'])]
    link[link.index('-o')+1]=str(elf); execute(link,'link')
    disassembly=execute([Path(compile_command[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
    for name in ('vsext.vf4','vfcvt.f.x.v','vfmul.vf','<dequantize_row_q8_0>:'):
        s.require(name in disassembly,'Original or candidate decoder missing')
    s.require('<archived_byte_hash_main>:' not in disassembly and '<qbs_native_execute_command>:' not in disassembly,
              'Unused old harness or custom arithmetic retained')
    helper=ROOT/'verification/akv/refill_overlap_probe/build.py'
    spec=importlib.util.spec_from_file_location('value_fast_elf',helper)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    sections=module.alloc_sections(elf)
    s.require(min(x['address'] for x in sections)>=0x80000000 and
        max(x['address']+x['bytes'] for x in sections)<0x81000000-65536,'ELF bounds')
    s.merge_pins(pins,s.hashes([Path(__file__),helper,base/'build.json',base/'source-pins.json']))
    s.verify_pins(pins); s.atomic_json(out/'source-pins.json',pins)
    updated=dict(report)
    updated.update(elf=str(elf),elf_sha256=s.digest(elf),original_build=str(base),
        harness='scalar_integer_compare_word_hash_once_per_capture',hash_algorithm='word_fnv64',
        elements_per_trial=32768,trials=8,boundary_elements=3584,
        source_pins_sha256=s.digest(out/'source-pins.json'),sections=sections,
        artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()),post_pins_match=True,
        scope='Same original/candidate decoder, both real V tensors and full eight-trial workload; checking is outside timing')
    s.atomic_json(out/'build.json',updated)
    print('BUILT_NOT_EXECUTED same_workload=1 trials=8 elements_per_trial=32768')


if __name__=='__main__':
    main()
