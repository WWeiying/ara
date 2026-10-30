#!/usr/bin/env python3
"""Fresh bare-metal canonical runtime ELF with unchanged accepted test/data sources."""
import argparse
import importlib.util
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
import attention_run as s

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASES = {
    'decode':ROOT/'verification/out/akv-native-pair-runtime-build-20261024-03',
    'prefill':ROOT/'verification/out/akv-prefill-pv-slice-build-20261024-01',
}
BACKUP = ROOT/'verification/out/akv-runtime-promotion-20261024-01'
CANONICAL = ROOT/'software/akv/src/akv_v2_native_riscv.c'
ASSEMBLY = ROOT/'software/akv/src/akv_v2_attention_rvv.S'


def historical_pins(base,report):
    s.require(report['state'] == 'BUILT_NOT_EXECUTED' and report['post_pins_match'] is True and
        s.digest(base/'source-pins.json') == report['source_pins_sha256'],'Original build receipt drift')
    original = s.read_json(base/'source-pins.json')
    s.merge_pins(original,report['artifact_sha256'])
    aliases = {str(CANONICAL):BACKUP/'native-before.c',str(ASSEMBLY):BACKUP/'attention-before.S'}
    resolved = {}
    for path,sha in original.items():
        actual = aliases.get(path,Path(path))
        s.require(s.digest(actual) == sha,'Historical input/artifact drift: '+path)
        s.merge_pins(resolved,{str(actual):sha})
    s.merge_pins(resolved,s.hashes([base/'build.json',base/'source-pins.json']))
    return resolved,{path:dict(snapshot=str(actual),sha256=original[path]) for path,actual in aliases.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind',choices=BASES,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    base,out = BASES[a.kind],a.output.resolve()
    s.require(not out.is_relative_to(base),'Use a separate fresh build')
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
        old = s.read_json(base/'build.json')
        pins,aliases = historical_pins(base,old)
        s.require(s.digest(CANONICAL) == 'aff613518b3495df363209beacf0940ef6d8b6c734f4851f63a7aa820d4f692c',
                  'Canonical implementation differs from reviewed promotion')
        image,accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',Path(old['simv']))
        s.require(image == old['accepted_image_pins'],'Original/current accepted image mismatch')
        s.merge_pins(pins,accepted)
        old_commands = s.read_json(base/'commands.json')
        compiles = [r['argv'] for r in old_commands if '-c' in r['argv']]
        links = [r['argv'] for r in old_commands if '-nostdlib' in r['argv']]
        s.require(len(compiles) == (14 if a.kind == 'decode' else 15) and len(links) == 1,
                  'Unexpected original build structure')
        leaf_sources = {str(ROOT/'software/akv/experimental/paired_heads/attention_rvv.S'),
                        str(ROOT/'software/akv/experimental/paired_heads/f32_pv/attention_rvv.S')}
        objects,replacements = [],{}
        replaced = skipped = 0
        for index,original in enumerate(compiles):
            argv = list(original)
            si,oi = argv.index('-c')+1,argv.index('-o')+1
            old_object = argv[oi]
            if argv[si] in leaf_sources:
                replacements[old_object] = None
                skipped += 1
                continue
            if Path(argv[si]).name in ('akv_v2_native_candidate.c','akv_prefill_pv_candidate.c'):
                argv[si] = str(CANONICAL)
                replaced += 1
            s.require(all(flag in argv for flag in ('-fno-fast-math','-ffp-contract=off')),
                      'Native compiler FP contract differs')
            obj = out/f'{index}.o'
            argv[oi] = str(obj)
            dep = [x for i,x in enumerate(argv) if i not in (si-1,oi-1,oi)]+['-M','-MT','object']
            text = invoke(dep,f'deps-{index}')
            s.merge_pins(pins,s.hashes([Path(x).resolve(strict=True) for x in
                shlex.split(text.replace('\\\n',' ').split(':',1)[1])]))
            invoke(argv,f'compile-{index}')
            replacements[old_object] = str(obj)
            objects.append(obj)
        s.require(replaced == skipped == 1,'Runtime replacement or duplicate-leaf removal incomplete')
        elf = out/('akv_live_'+a.kind+'.elf')
        link = [replacements.get(x,x) for x in links[0] if replacements.get(x,x) is not None]
        link[link.index('-o')+1] = str(elf)
        link = ['-Wl,-Map='+str(out/'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
        s.require(all(str(obj) in link for obj in objects) and not any(str(base) in x and x.endswith('.o')
                  for x in link),'Original runtime object leaked into fresh ELF')
        invoke(link,'link')
        cc = Path(compiles[0][0])
        text = invoke([cc.with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        for name in ('akv_experimental_pv_f16_pair','akv_experimental_pv_f32_pair',
                     'akv_experimental_qk_f16_pair_panel4'):
            s.require('<'+name+'>:' in text,'Canonical leaf not linked: '+name)
        s.require('bench_pair_enabled' not in text and 'bench_active' not in text,'Mutable benchmark dispatch leaked')
        helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
        spec = importlib.util.spec_from_file_location('live_regression_elf',helper)
        elf_tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(elf_tools)
        sections = elf_tools.alloc_sections(elf)
        s.require(min(x['address'] for x in sections) >= 0x80000000 and
                  max(x['address']+x['bytes'] for x in sections) < 0x81000000-65536,'ELF bounds')
        s.merge_pins(pins,s.hashes([Path(__file__),HERE/'test_live_regression.py',helper]))
        s.verify_pins(pins)
        s.atomic_json(out/'source-pins.json',pins)
        s.atomic_json(out/'build.json',dict(state='BUILT_NOT_EXECUTED',execution='NOT_RUN',kind=a.kind,
            elf=str(elf),elf_sha256=s.digest(elf),simv=old['simv'],accepted_image_pins=image,
            source_pins_sha256=s.digest(out/'source-pins.json'),post_pins_match=True,
            artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()),sections=sections,
            original_build=str(base),historical_source_resolution=aliases,old_runtime_objects_reused=False,
            expected_commands=3680 if a.kind == 'decode' else 13380,
            expected_calls=12 if a.kind == 'decode' else 4,
            scope='Unchanged accepted stimulus/data with freshly compiled canonical runtime and both shared leaves'))
        print('BUILT_NOT_EXECUTED kind='+a.kind)
    except BaseException as exc:
        s.atomic_json(out/'build.json',dict(state='FAIL',execution='NOT_RUN',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
