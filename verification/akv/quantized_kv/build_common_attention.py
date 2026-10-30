#!/usr/bin/env python3
"""Build a public-entry Attention inquiry; never launch or promote a benchmark."""
import argparse
import importlib.util
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
GGML=Path('/home/wangwy/llama/llama.cpp/ggml/include')
sys.path.insert(0,str(ROOT/'verification/akv/paired_heads'))
import attention_run as s


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind',choices=('q8_0','q4_0'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    tag='q8' if args.kind=='q8_0' else 'q4'
    base=ROOT/f'verification/out/akv-quantkv-attention-{tag}-build-20261024-03'
    report=s.read_json(base/'build.json')
    s.require(report['state']=='BUILT_NOT_EXECUTED' and report['kind']==args.kind and
        report['expected_commands']==16 and report['trials']==4 and
        s.digest(base/'source-pins.json')==report['source_pins_sha256'],'Wrong original inquiry')
    pins=s.read_json(base/'source-pins.json'); s.merge_pins(pins,report['artifact_sha256']); s.verify_pins(pins)
    old=s.read_json(base/'commands.json'); commands=[]
    def execute(argv,label):
        argv=list(map(str,argv)); commands.append(dict(argv=argv,cwd=str(out)))
        s.atomic_json(out/'commands.json',commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(label+'.log')).read_text()
    template=list(next(r['argv'] for r in old if '-c' in r['argv'] and
        str(HERE/'attention_initialized_main.c') in r['argv']))
    s.require('-ffp-contract=fast' in template and '-fno-fast-math' in template,'FP policy differs')
    template.insert(1,'-I'+str(GGML))
    for source,name in ((HERE/'attention_common_main.c','main'),
                        (ROOT/'software/akv/experimental/quantized_kv/runtime.c','runtime')):
        command=list(template)
        command[command.index(str(HERE/'attention_initialized_main.c'))]=str(source)
        command[command.index('-o')+1]=str(out/(name+'.o'))
        dep=[x for i,x in enumerate(command) if i not in
            (command.index('-c'),command.index('-o'),command.index('-o')+1)]+['-M','-MT','object']
        dependencies=execute(dep,'deps-'+name)
        s.merge_pins(pins,s.hashes(Path(x).resolve(strict=True) for x in
            shlex.split(dependencies.replace('\\\n',' ').split(':',1)[1])))
        execute(command,'compile-'+name)
    mask=ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'/(
        'capture-k-'+args.kind+'-v-q8_0')/'decode/block/attn_mask_input-0.bin'
    s.require(mask.stat().st_size==512 and pins.get(str(mask))==s.digest(mask),'Original mask not pinned')
    assembly=out/'mask.S'
    assembly.write_text('.section .rodata,"a",@progbits\n.balign 64\n.global attention_mask\n'
        'attention_mask:\n.incbin "'+str(mask)+'"\n')
    command=[str(assembly) if x==str(HERE/'attention_initialized_main.c') else x for x in template]
    command[command.index('-o')+1]=str(out/'mask.o'); execute(command,'compile-mask')
    elf=out/'common_attention.elf'
    link=[str(out/'main.o') if x==str(base/'attention-main.o') else
          '-Wl,-Map='+str(out/'link.map') if x=='-Wl,-Map='+str(base/'link.map') else x
          for x in next(r['argv'] for r in old if '-nostdlib' in r['argv'])]
    link[link.index('-o')+1]=str(elf)
    link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')]=[str(out/'runtime.o'),str(out/'mask.o')]
    execute(link,'link')
    disassembly=execute([Path(template[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
    for symbol in ('akv_quant_native_execute','quantize_row_q8_0','dequantize_row_q8_0',
        'quant_kv_ggml_mad_f32','quant_kv_ggml_scale_f32','qbs_native_execute_command'):
        s.require('<'+symbol+'>:' in disassembly,'Public entry or original primitive absent '+symbol)
    s.require('<qbs_ref_execute>:' not in disassembly and '<archived_attention_main>:' not in disassembly,
              'Reference or archived test body retained')
    helper=ROOT/'verification/akv/refill_overlap_probe/build.py'
    spec=importlib.util.spec_from_file_location('common_attention_elf',helper)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    sections=module.alloc_sections(elf)
    s.require(min(x['address'] for x in sections)>=0x80000000 and
        max(x['address']+x['bytes'] for x in sections)<0x81000000-65536,'ELF bounds')
    s.merge_pins(pins,s.hashes([Path(__file__),base/'build.json',base/'source-pins.json']))
    s.verify_pins(pins); s.atomic_json(out/'source-pins.json',pins)
    updated=dict(report)
    updated.update(state='COMMON_ENTRY_BUILT_NOT_EXECUTED',execution='NOT_RUN',
        elf=str(elf),elf_sha256=s.digest(elf),original_build=str(base),sections=sections,
        common_entry=True,mapping_timed=True,admission_timed=True,
        runtime_fp_contract='fast, matching both original schedule and production primitives',
        source_pins_sha256=s.digest(out/'source-pins.json'),post_pins_match=True,
        artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()),
        scope='Original six-head KV-head-0 group; public GGML mapping/runtime candidate, not model execution')
    s.atomic_json(out/'build.json',updated)
    print('COMMON_ENTRY_BUILT_NOT_EXECUTED',args.kind)


if __name__=='__main__':
    main()
