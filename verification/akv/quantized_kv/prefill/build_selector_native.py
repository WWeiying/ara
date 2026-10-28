#!/usr/bin/env python3
"""Fresh Decode pair using an archived recipe, never its old object/source identity."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
from run_replay import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe-build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prior=args.recipe_build.resolve(strict=True);out=args.output.resolve()
    report=json.loads((prior/'build.json').read_text())
    assert report['state']=='BUILT_NOT_EXECUTED' and report.get('token_major') is True
    records_path=prior/'commands.json'
    assert digest(records_path)==report['artifacts'][str(records_path)]
    old_pins_path=prior/'source-pins.json'
    assert digest(old_pins_path)==report['source_pins_sha256']
    old_pins=json.loads(old_pins_path.read_text());old_pins.update(report['artifacts'])
    records=json.loads(records_path.read_text())
    compiles=[list(r['argv']) for r in records if r['label'].startswith('compile-')]
    assert len(compiles)==16 and report['kind'] in ('q4_0','q8_0')
    out.mkdir(parents=True,exist_ok=False);pins={};commands=[]
    def pin(p):
        p=Path(p).resolve(strict=True);h=digest(p)
        assert str(p) not in pins or pins[str(p)]==h,str(p)
        pins[str(p)]=h
    for p in (Path(__file__),HERE/'run_replay.py',prior/'build.json',records_path,old_pins_path):pin(p)
    # Historical assembly and its binary payloads are immutable recipe inputs.
    # C/header sources are freshly dependency-scanned and independently pinned below.
    for cmd in compiles:
        source=Path(cmd[cmd.index('-c')+1])
        if source.suffix=='.S':
            if str(source) in old_pins:assert digest(source)==old_pins[str(source)],source
            pin(source)
            for payload in re.findall(r'\.incbin\s+"([^"]+)"',source.read_text()):
                assert digest(payload)==old_pins[payload],payload
                pin(payload)
    compiles[1][compiles[1].index('-c')+1]=str(HERE/'native_selector_main.c')
    candidate=list(compiles[15]);candidate[candidate.index('-c')+1]=str(HERE/'selector_runtime.c')
    compiles.append(candidate)
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);commands.append(dict(label=label,argv=argv))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        with (out/(label+'.log')).open('w') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(label+'.log')).read_text()
    objects=[]
    for i,cmd in enumerate(compiles):
        obj=out/f'{i}.o';objects.append(str(obj));cmd[cmd.index('-o')+1]=str(obj)
        deps=[v for j,v in enumerate(cmd) if j not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
        text=run([*deps,'-M','-MT','object'],'deps-'+str(i))
        for p in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):pin(p)
        run(cmd,'compile-'+str(i))
    link=list(next(r['argv'] for r in records if r['label']=='link'))
    link=[v for v in link if not v.endswith('.o')]
    link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')]=objects
    elf=out/'selector.elf';link[link.index('-o')+1]=str(elf)
    link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
    run(link,'link')
    dis=run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
    for symbol in ('qbs_native_execute_command','akv_quant_strided_execute','akv_quant_selector_execute','main'):
        assert '<'+symbol+'>:' in dis,symbol
    assert '<qbs_ref_execute>:' not in dis
    for p,h in pins.items():assert digest(p)==h,p
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='BUILT_NOT_EXECUTED',kind=report['kind'],elf=str(elf),elf_sha256=digest(elf),
      source_pins_sha256=digest(out/'source-pins.json'),commands_per_trial=1,outputs_per_trial=256,
      value_decodes=[20]*4,reused_objects=0,rebuilt_objects=17,whole_call=True,aligned_selector=True,
      recipe_only=str(prior),historical_source_identity_reused=False,
      scope='Qwen3 query19 GQA2 D128 token-major Decode original versus aligned selector',
      performance_measured=False,artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file()})
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    print('SELECTOR_BUILT_NOT_EXECUTED '+str(elf))


if __name__=='__main__':main()
