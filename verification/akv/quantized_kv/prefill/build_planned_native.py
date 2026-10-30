#!/usr/bin/env python3
"""Rebuild whole-call ABBA including admission/scatter; do not launch VCS."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
from run_replay import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prior=args.previous_build.resolve(strict=True);out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    report=json.loads((prior/'build.json').read_text())
    assert report['state']=='BUILT_NOT_EXECUTED' and digest(prior/'source-pins.json')==report['source_pins_sha256']
    pins=json.loads((prior/'source-pins.json').read_text());pins.update(report['artifacts'])
    for p,h in pins.items():assert digest(p)==h,p
    commands=[]
    def pin(p):
        p=Path(p).resolve(strict=True);h=digest(p)
        assert str(p) not in pins or pins[str(p)]==h,str(p)
        pins[str(p)]=h
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);commands.append(dict(label=label,argv=argv))
        (out/'commands.json').write_text(json.dumps(commands,indent=2))
        with (out/(label+'.log')).open('w') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(label+'.log')).read_text()
    pin(__file__);pin(prior/'build.json');pin(HERE/'run_replay.py')
    records=json.loads((prior/'commands.json').read_text())
    compiles=[r['argv'] for r in records if r['label'].startswith('compile-')]
    assert len(compiles)==15
    compiles[1]=list(compiles[1])
    compiles[1][compiles[1].index('-c')+1]=str(HERE/'native_planned_main.c')
    objects=[]
    for i,cmd in enumerate(compiles):
        cmd=list(cmd);obj=out/f'{i}.o';objects.append(str(obj));cmd[cmd.index('-o')+1]=str(obj)
        deps=[v for j,v in enumerate(cmd) if j not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
        text=run([*deps,'-M','-MT','object'],'deps-'+str(i))
        for p in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):pin(p)
        run(cmd,'compile-'+str(i))
    link=list(next(r['argv'] for r in records if r['label']=='link'))
    link=[v for v in link if not v.endswith('.o')]
    at=link.index('-Wl,--gc-sections');link[at:at]=objects
    elf=out/'prefill-full.elf';link[link.index('-o')+1]=str(elf)
    link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
    run(link,'link')
    dis=run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
    for symbol in ('qbs_native_execute_command','main'):
        assert '<'+symbol+'>:' in dis,symbol
    assert '<qbs_ref_execute>:' not in dis
    for p,h in pins.items():assert digest(p)==h,p
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='BUILT_NOT_EXECUTED',kind=report['kind'],elf=str(elf),elf_sha256=digest(elf),
      source_pins_sha256=digest(out/'source-pins.json'),commands_per_trial=5,outputs_per_trial=1280,
      value_decodes=[9,6,6,9],reused_objects=0,rebuilt_objects=15,whole_call=True,planned_boundaries=True,
      scope='Real Qwen3 fixed versus planned boundaries, planning included in full call',
      performance_measured=False,artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file()})
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    print('FULL_CALL_BUILT_NOT_EXECUTED '+str(elf))


if __name__=='__main__':main()
