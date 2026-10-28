#!/usr/bin/env python3
"""Link graph fixtures against normal OFF/ON libraries; do not run QEMU."""
import argparse
import json
from pathlib import Path
import subprocess
from run_replay import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--library-build',type=Path,default=ROOT/'verification/out/prefill-ggml-build-20261028-01')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    build=args.library_build.resolve(strict=True)
    receipt=json.loads((build/'result.json').read_text());assert receipt['state']=='PASS'
    pins=json.loads((build/'source-pins.json').read_text())
    assert digest(build/'source-pins.json')==receipt['source_pins_sha256']
    for config in receipt['configurations'].values():pins.update(config['libraries'])
    pins[str(HERE/'graph_test.cpp')]=digest(HERE/'graph_test.cpp')
    pins[str(Path(__file__))]=digest(__file__)
    prior=ROOT/'verification/out/m4-packed-normal-model-20261028-01'
    commands=[]
    def verify():
        for p,h in pins.items():assert digest(p)==h,p
    def run(argv,label):
        verify();commands.append(dict(label=label,argv=argv))
        (out/'commands.json').write_text(json.dumps(commands,indent=2))
        with (out/(label+'.log')).open('w') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        verify()
    cc=json.loads((prior/'compile-test.command.json').read_text())
    cc[cc.index('-c')+1]=str(HERE/'graph_test.cpp');cc[cc.index('-o')+1]=str(out/'test.o')
    pins[cc[0]]=digest(cc[0]);run(cc,'compile')
    executables={}
    for mode in ('off','on'):
        link=json.loads((prior/'link.command.json').read_text())
        link=[str(out/'test.o') if x.endswith('/test.o') else x for x in link]
        old=str(ROOT/'verification/out/m4-packed-normal-build-20261028-01/build')
        link=[x.replace(old,str(build/mode)) for x in link]
        link=[('-Wl,-Map='+str(out/(mode+'.map'))) if x.startswith('-Wl,-Map=') else x for x in link]
        elf=out/('graph-'+mode);link[link.index('-o')+1]=str(elf);run(link,'link-'+mode)
        executables[mode]=dict(path=str(elf),sha256=digest(elf))
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='BUILT_NOT_EXECUTED',executables=executables,
                source_pins_sha256=digest(out/'source-pins.json'),performance_measured=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
