#!/usr/bin/env python3
"""Real GGML tensor/C-entry replay, QBS numerical reference, no timing claim."""
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
    parser.add_argument('output',type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    audit=ROOT/'verification/out/quant-prefill-capture-audit-20261028-01'
    pins=json.loads((audit/'manifest.json').read_text())
    assert json.loads((audit/'result.json').read_text())['state']=='PASS'
    # Verify sealed libraries independently of the source/header dependency list.
    capture=ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'
    receipt=json.loads((capture/'result.json').read_text())
    assert digest(capture/'build-artifacts.json')==receipt['build_artifacts_sha256']
    pins.update(json.loads((capture/'build-artifacts.json').read_text()))
    pins[str(Path(__file__))]=digest(__file__)
    pins[str(HERE/'run_replay.py')]=digest(HERE/'run_replay.py')
    for p,h in pins.items():assert digest(p)==h,p
    commands=[]
    def run(argv,label):
        argv=list(map(str,argv));commands.append(dict(label=label,argv=argv))
        (out/'commands.json').write_text(json.dumps(commands,indent=2))
        with (out/(label+'.log')).open('w') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        return (out/(label+'.log')).read_text()
    ggml=Path('/home/wangwy/llama/llama-q4km-extract/ggml')
    libs=capture/'build/bin'
    sources=[HERE/'replay_ggml.cpp',HERE/'ggml_entry.c',HERE/'host_bindings.cpp',
             ROOT/'software/akv/experimental/quantized_kv/runtime.c',
             ROOT/'software/qbs/src/qbs_runtime.c',ROOT/'verification/qbs/qbs_ref.c']
    objects=[]
    for i,source in enumerate(sources):
        cpp=source.suffix=='.cpp';cc='/usr/bin/g++' if cpp else '/usr/bin/gcc'
        pins[cc]=digest(cc)
        frontend=subprocess.check_output([cc,'-print-prog-name='+('cc1plus' if cpp else 'cc1')],text=True).strip()
        pins[frontend]=digest(frontend)
        flags=[cc,'-std=c++17' if cpp else '-std=gnu11','-O2','-Wall','-Wextra','-Werror',
               '-fno-fast-math','-frounding-math','-ffp-contract=off' if source.name=='qbs_ref.c' else '-ffp-contract=fast',
               '-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include'),'-I'+str(ggml/'include'),'-I'+str(ggml/'src')]
        if cpp:flags.append('-march=native')
        deps=run([*flags,source,'-M','-MT','object'],'deps-'+str(i))
        for p in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):
            p=str(Path(p).resolve());h=digest(p)
            assert p not in pins or pins[p]==h,p
            pins[p]=h
        obj=out/f'{i}.o';objects.append(obj)
        run([*flags,'-c',source,'-o',obj],'compile-'+str(i))
    binary=out/'replay'
    run(['/usr/bin/g++',*objects,'-L'+str(libs),'-Wl,-rpath,'+str(libs),
         '-lggml-cpu','-lggml','-lggml-base','-pthread','-lm','-o',binary],'link')
    results={}
    for kind in ('q4_0','q8_0'):
        data=ROOT/'verification/out/quant-prefill-capture-20261028-01'/kind/'prefill/block'
        text=run([binary,data,kind],kind)
        assert text.startswith('REAL_GGML_PREFILL_PASS key='+kind+' ') and len(text.splitlines())==1,text
        results[kind]=text.strip()
    for p,h in pins.items():assert digest(p)==h,p
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='PASS',results=results,binary_sha256=digest(binary),
                source_pins_sha256=digest(out/'source-pins.json'),
                performance_measured=False,production_integrated=False,
                scope='Real Qwen3 tensors allocated by GGML and executed through C entry; QBS reference')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
