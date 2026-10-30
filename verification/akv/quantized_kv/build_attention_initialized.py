#!/usr/bin/env python3
"""Replace only the measurement entry; preserve sealed Attention workload and FP policy."""
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
    parser.add_argument('--kind',choices=('q8_0','q4_0'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--startup-probe',action='store_true')
    args=parser.parse_args()
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    tag='q8' if args.kind=='q8_0' else 'q4'
    base=ROOT/f'verification/out/akv-quantkv-attention-{tag}-build-20261024-02'
    report=s.read_json(base/'build.json')
    s.require(report['state']=='BUILT_NOT_EXECUTED' and report['kind']==args.kind and
        report['heads']==6 and report['visible_tokens']==128 and report['trials']==4 and
        s.digest(base/'source-pins.json')==report['source_pins_sha256'],'Wrong full workload')
    pins=s.read_json(base/'source-pins.json'); s.merge_pins(pins,report['artifact_sha256']); s.verify_pins(pins)
    source=HERE/('attention_startup_probe.c' if args.startup_probe else 'attention_initialized_main.c')
    old=s.read_json(base/'commands.json'); commands=[]
    def execute(argv,label):
        argv=list(map(str,argv)); commands.append(dict(argv=argv,cwd=str(out)))
        s.atomic_json(out/'commands.json',commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(label+'.log')).read_text()
    compile_command=list(next(r['argv'] for r in old if '-c' in r['argv'] and str(HERE/'attention_main.c') in r['argv']))
    compile_command[compile_command.index(str(HERE/'attention_main.c'))]=str(source)
    compile_command[compile_command.index('-o')+1]=str(out/'attention-main.o')
    dep=[x for i,x in enumerate(compile_command) if i not in
        (compile_command.index('-c'),compile_command.index('-o'),compile_command.index('-o')+1)]+['-M','-MT','object']
    dependencies=execute(dep,'deps-main')
    s.merge_pins(pins,s.hashes(Path(x).resolve(strict=True) for x in
        shlex.split(dependencies.replace('\\\n',' ').split(':',1)[1])))
    execute(compile_command,'compile-main')
    elf=out/'quantized_attention.elf'
    link=[str(out/'attention-main.o') if x==str(base/'attention-main.o') else
          '-Wl,-Map='+str(out/'link.map') if x=='-Wl,-Map='+str(base/'link.map') else x
          for x in next(r['argv'] for r in old if '-nostdlib' in r['argv'])]
    link[link.index('-o')+1]=str(elf); execute(link,'link')
    disassembly=execute([Path(compile_command[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
    s.require('vsetivli' in disassembly and 'vmv.x.s\tzero,v8' in disassembly,'Initialization/drain absent')
    if not args.startup_probe:
        for symbol in ('quantize_row_q8_0','dequantize_row_q8_0','quant_kv_ggml_mad_f32',
                       'quant_kv_ggml_scale_f32','qbs_native_execute_command'):
            s.require('<'+symbol+'>:' in disassembly,'Missing original primitive '+symbol)
    helper=ROOT/'verification/akv/refill_overlap_probe/build.py'
    spec=importlib.util.spec_from_file_location('attention_initialized_elf',helper)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    sections=module.alloc_sections(elf)
    s.require(min(x['address'] for x in sections)>=0x80000000 and
        max(x['address']+x['bytes'] for x in sections)<0x81000000-65536,'ELF bounds')
    s.merge_pins(pins,s.hashes([Path(__file__),base/'build.json',base/'source-pins.json']))
    s.verify_pins(pins); s.atomic_json(out/'source-pins.json',pins)
    updated=dict(report)
    updated.update(state='PROBE_BUILT_NOT_EXECUTED' if args.startup_probe else 'BUILT_NOT_EXECUTED',
        elf=str(elf),elf_sha256=s.digest(elf),original_build=str(base),
        entry_initialization='vsetivli zero,1,e32,m1,ta,ma before measurement-only drain',
        source_pins_sha256=s.digest(out/'source-pins.json'),
        artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()),
        sections=sections,post_pins_match=True)
    s.atomic_json(out/'build.json',updated)
    print(updated['state'],args.kind)


if __name__=='__main__':
    main()
