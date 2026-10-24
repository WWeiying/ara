#!/usr/bin/env python3
"""Reuse immutable accepted primitive/data objects; compile only new multioutput main."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/akv/paired_heads'))
import attention_run as s


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous-build',type=Path,default=ROOT/'verification/out/akv-quantkv-rvv-qbs-build-20261024-01')
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    old,out = a.previous_build.resolve(strict=True),a.output.resolve()
    s.require(not out.is_relative_to(old),'Use an independent build directory')
    out.mkdir(parents=True,exist_ok=False)
    commands = []
    def invoke(argv,label):
        argv = list(map(str,argv))
        commands.append(dict(argv=argv,cwd=str(out)))
        s.atomic_json(out/'commands.json',commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(label+'.log')).read_text()
    try:
        report = s.read_json(old/'build.json')
        s.require(report['state'] == 'BUILT_NOT_EXECUTED' and report['expected_commands'] == 16 and
                  report['profiles'] == ['q8_0','q4_0'],'Wrong primitive/data build')
        pins = s.read_json(old/'source-pins.json')
        s.require(s.digest(old/'source-pins.json') == report['source_pins_sha256'],'Build receipt drift')
        s.merge_pins(pins,report['artifact_sha256'])
        s.verify_pins(pins)
        prior_commands = s.read_json(old/'commands.json')
        mains = [row['argv'] for row in prior_commands if '-c' in row['argv'] and
                 str(HERE/'rvv_qbs_main.c') in row['argv']]
        links = [row['argv'] for row in prior_commands if '-nostdlib' in row['argv']]
        s.require(len(mains) == len(links) == 1,'Ambiguous original compile/link')
        main = HERE/'batch_qk_main.c'
        obj = out/'batch_main.o'
        compile_command = [str(main) if x == str(HERE/'rvv_qbs_main.c') else x for x in mains[0]]
        compile_command[compile_command.index('-o')+1] = str(obj)
        invoke(compile_command,'compile-main')
        elf = out/'quantized_kv_batch_qk.elf'
        link = [str(obj) if x == str(old/'0.o') else
                '-Wl,-Map='+str(out/'link.map') if x == '-Wl,-Map='+str(old/'link.map') else x
                for x in links[0] if x != str(old/'3.o')]
        s.require(str(obj) in link and str(old/'0.o') not in link and str(old/'3.o') not in link,
                  'Failed to replace main/remove unused on-target reference')
        link[link.index('-o')+1] = str(elf)
        invoke(link,'link')
        cc = Path(compile_command[0])
        text = invoke([cc.with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        for symbol in ('quantize_row_q8_0','qbs_native_execute_command'):
            s.require('<'+symbol+'>:' in text,'Missing actual target primitive '+symbol)
        s.require('<qbs_ref_execute>:' not in text,'On-target scalar reference unexpectedly retained')
        helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
        spec = importlib.util.spec_from_file_location('quant_batch_elf_tools',helper)
        elf_tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(elf_tools)
        sections = elf_tools.alloc_sections(elf)
        s.require(min(x['address'] for x in sections) >= 0x80000000 and
            max(x['address']+x['bytes'] for x in sections) < 0x81000000-65536,'ELF bounds')
        s.merge_pins(pins,s.hashes([Path(__file__),main,helper,old/'build.json',old/'source-pins.json']))
        s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json',pins)
        s.atomic_json(out/'build.json',dict(state='BUILT_NOT_EXECUTED',execution='NOT_RUN',
            elf=str(elf),elf_sha256=s.digest(elf),simv=report['simv'],
            accepted_image_pins=report['accepted_image_pins'],source_pins_sha256=s.digest(out/'source-pins.json'),
            post_pins_match=True,artifact_sha256=s.hashes(x for x in out.iterdir() if x.is_file()),
            profiles=['q8_0','q4_0'],query_heads=list(range(12)),kv_heads=2,visible=128,capacity=256,
            expected_commands=40,expected_outputs=3336,query_exports=24,sections=sections,
            scope='Complete real QK score matrices plus N31/N1 tails; not complete Attention, timing or GGML deployment'))
        print('BUILT_NOT_EXECUTED commands=40 outputs=3336 queries=24')
    except BaseException as exc:
        s.atomic_json(out/'build.json',dict(state='FAIL',execution='NOT_RUN',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
