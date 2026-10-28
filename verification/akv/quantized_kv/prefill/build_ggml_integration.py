#!/usr/bin/env python3
"""Build standard llama libraries with experimental Prefill OFF and ON."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
LLAMA=Path('/home/wangwy/llama/llama.cpp')


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        p=out/name;tmp=p.with_suffix(p.suffix+'.tmp')
        tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(p)
    prior=ROOT/'verification/out/m4-packed-normal-build-20261028-01/configure.command.json'
    suffixes={'.c','.cpp','.h','.hpp','.S','.cmake','.txt'}
    files={Path(__file__).resolve(),prior,Path('/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake')}
    for directory in (LLAMA/'ggml',LLAMA/'src',LLAMA/'cmake',ROOT/'software/qbs',ROOT/'software/akv',HERE):
        files.update(p.resolve() for p in directory.rglob('*') if p.is_file() and p.suffix in suffixes)
    files.add(LLAMA/'CMakeLists.txt')
    pins={str(p):digest(p) for p in sorted(files)};save('source-pins.json',pins)
    def verify():
        for p,h in pins.items():
            if digest(Path(p))!=h:raise RuntimeError('Source drift: '+p)
    def run(argv,label):
        verify();save('status.json',dict(state=label))
        save(label+'.command.json',argv)
        with (out/(label+'.log')).open('w') as log:
            subprocess.run(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=3600)
        verify()
    result=dict(state='FAIL',runtime_tested=False)
    try:
        configurations={}
        for mode in ('OFF','ON'):
            build=out/mode.lower();argv=json.loads(prior.read_text())
            argv[argv.index('-B')+1]=str(build)
            argv.extend(['-DGGML_RISCV_AKV_QUANT_PREFILL='+mode,
                         '-DGGML_RISCV_AKV_PREFILL_DIR='+str(HERE)])
            run(argv,'configure-'+mode.lower())
            run(['cmake','--build',str(build),'--target','llama','-j','8'],'build-'+mode.lower())
            records=json.loads((build/'compile_commands.json').read_text())
            entries=[r for r in records if Path(r['file']).resolve()==HERE/'ggml_entry.c']
            assert len(entries)==int(mode=='ON')
            frontend=next(r for r in records if r['file'].endswith('/arch/riscv/quant-kv.cpp'))
            assert ('-DGGML_USE_RISCV_QUANT_PREFILL' in frontend['command'])==(mode=='ON')
            libraries={str(p):digest(p) for p in build.rglob('*.a')}
            assert any(p.endswith('/libllama.a') for p in libraries)
            configurations[mode]=dict(libraries=libraries,prefill_source_count=len(entries))
        result.update(state='PASS',configurations=configurations,post_pins_match=True,
                      source_pins_sha256=digest(out/'source-pins.json'))
    except BaseException as exc:
        result['error']=repr(exc);raise
    finally:
        save('result.json',result);save('status.json',dict(state=result['state']))


if __name__=='__main__':main()
