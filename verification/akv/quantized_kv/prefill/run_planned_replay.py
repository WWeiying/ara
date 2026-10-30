#!/usr/bin/env python3
"""Audited real-data whole-call Prefill host replay; never measures RTL timing."""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from run_replay import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    audit=ROOT/'verification/out/quant-prefill-capture-audit-20261028-01'
    pins=json.loads((audit/'manifest.json').read_text())
    assert json.loads((audit/'result.json').read_text())['state']=='PASS'
    for p,h in pins.items():assert digest(p)==h,p
    commands=[]
    def pin(p):
        p=Path(p).resolve(strict=True);h=digest(p)
        assert str(p) not in pins or pins[str(p)]==h,str(p)
        pins[str(p)]=h
    def run(argv,label):
        argv=list(map(str,argv));commands.append(dict(label=label,argv=argv))
        (out/'commands.json').write_text(json.dumps(commands,indent=2))
        with (out/(label+'.log')).open('w') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        return (out/(label+'.log')).read_text()
    cc,cxx=shutil.which('gcc'),shutil.which('g++')
    for compiler,frontend in ((cc,'cc1'),(cxx,'cc1plus')):
        pin(compiler);pin(subprocess.check_output([compiler,'-print-prog-name='+frontend],text=True).strip())
    for p in (Path(__file__),HERE/'run_replay.py',audit/'manifest.json',audit/'result.json'):pin(p)
    ggml=Path('/home/wangwy/llama/llama-q4km-extract/ggml')
    libraries=ROOT/'verification/out/akv-quantkv-host-capture-20261024-01/build/bin'
    sources=[HERE/'replay_planned.c',ROOT/'software/qbs/src/qbs_runtime.c',
             ROOT/'verification/qbs/qbs_ref.c',HERE/'host_bindings.cpp',
             ROOT/'software/akv/experimental/quantized_kv/runtime.c']
    objects=[]
    for i,source in enumerate(sources):
        cpp=source.suffix=='.cpp'
        flags=[cxx if cpp else cc,'-std=c++17' if cpp else '-std=gnu11','-O2','-Wall','-Wextra','-Werror',
               '-fno-fast-math','-ffp-contract=off' if i==2 else '-ffp-contract=fast','-frounding-math',
               '-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include'),
               '-I'+str(ggml/'include'),'-I'+str(ggml/'src')]
        if cpp:flags.append('-march=native')
        deps=run([*flags,source,'-M','-MT','object'],'deps-'+str(i))
        for p in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):pin(p)
        obj=out/f'{i}.o';objects.append(obj)
        run([*flags,'-c',source,'-o',obj],'compile-'+str(i))
    binary=out/'replay'
    run([cxx,*objects,'-L'+str(libraries),'-Wl,-rpath,'+str(libraries),
         '-lggml-cpu','-lggml-base','-lm','-o',binary],'link')
    results={}
    for kind in ('q4_0','q8_0'):
        data=ROOT/'verification/out/quant-prefill-capture-20261028-01'/kind/'prefill/block'
        text=run([binary,data,kind],kind)
        assert text.count('REAL_PREFILL_PLANNED_PASS ')==2,text
        results[kind]=text.splitlines()
    for p,h in pins.items():assert digest(p)==h,p
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='PASS',results=results,binary_sha256=digest(binary),
                source_pins_sha256=digest(out/'source-pins.json'),
                scope='Independent planned five-query composition with actual GGML primitives and QBS numerical reference',
                performance_measured=False,production_integrated=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
