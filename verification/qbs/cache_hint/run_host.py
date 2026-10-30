#!/usr/bin/env python3
"""Host differential tests and real activation-key replay, not performance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'m4_prepared_reuse'))
from analyze_capture_residency import load, ORDER


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--captures',type=Path,required=True)
    p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cxx',default='g++')
    args=p.parse_args();out=args.output.resolve()
    operations,pins=load(args.captures)
    subprocess.run([sys.executable,str(HERE/'prepare.py'),'--source',
                    str(args.runtime/'q8_K-prepared-cache.h'),'--output',str(out)],check=True)
    pins.update(json.loads((out/'source-pins.json').read_text()))
    sources=[Path(__file__),HERE/'test.cpp',HERE/'replay.cpp',
             HERE.parent/'m4_prepared_reuse/analyze_capture_residency.py',
             args.runtime/'rvv-byte-ops.h',HERE.parents[2]/'software/qbs/include/qbs/qbs_abi.h']
    pins.update({str(f.resolve()):digest(f) for f in sources})
    commands=[]
    def run(command,label):
        commands.append(command)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    for name in ('test','replay'):
        run([args.cxx,'-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
             '-fsanitize=address,undefined','-fno-omit-frame-pointer',
             '-I'+str(out),'-I'+str(args.runtime),
             '-I'+str(HERE.parents[2]/'software/qbs/include'),str(HERE/(name+'.cpp')),
             '-o',str(out/name)],'build-'+name)
    run([str(out/'test')],'test')
    arguments=[]
    for name,k,m,_ in operations:
        arguments += [str(k),str(m),str(args.captures/('blk_0_'+name+'_weight')/'activation_f32.bin')]
    run([str(out/'replay'),*arguments],'replay')
    assert 'CACHE_HINT_HOST_PASS' in (out/'test.log').read_text()
    assert 'CACHE_HINT_CAPTURE_PASS' in (out/'replay.log').read_text()
    for path,value in pins.items():
        if digest(path)!=value:raise ValueError('Input drift: '+path)
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    result=dict(state='PASS',scope='host cache semantics with opaque payloads; not quantization or timing',
                operations=list(ORDER),sanitizers=['address','undefined'],production_modified=False,
                artifacts={str(f):digest(f) for f in out.iterdir() if f.is_file()})
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print((out/'test.log').read_text()+(out/'replay.log').read_text())


if __name__=='__main__':main()
