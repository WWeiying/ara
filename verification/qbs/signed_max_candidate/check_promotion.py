#!/usr/bin/env python3
"""Compile installed production TU and verify tested text plus fallback builds."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json, digest, hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'): raise ValueError('Private output required')
    old=ROOT/'verification/out/q8k-combined-zvfh-integration-20261026-01/command.json'
    command=json.loads(old.read_text())
    installed=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv')
    for name in ('q8_K-m4.h','q8_K-signed-max.h'):
        if (installed/name).read_bytes() != (ROOT/'software/qbs/ggml'/name).read_bytes():
            raise ValueError('Installed copy mismatch')
    candidate=ROOT/'verification/out/q8k-signed-max-compile-20261026-01/candidate.o'
    paths=[old,Path(__file__),candidate,Path(command[0]).resolve(),Path(command[command.index('-c')+1])]
    for directory in {Path(flag[2:]).resolve() for flag in command if flag.startswith('-I')}:
        paths.extend(p for p in directory.rglob('*') if p.is_file() and p.suffix in ('.h','.hpp','.inc','.inl'))
    pins=hashes(paths)
    out.mkdir(parents=True,exist_ok=False)
    atomic_json(out/'inputs.json',pins)
    results={}
    for mode in ('combined','no_vector','fast_math'):
        cmd=[flag for flag in command if not flag.startswith('-march=')]
        cmd += ['-march=rv64gc' if mode=='no_vector' else '-march=rv64gcv_zfh_zvfh']
        if mode=='fast_math': cmd += ['-ffast-math']
        obj=out/(mode+'.o')
        cmd[cmd.index('-o')+1]=str(obj)
        atomic_json(out/(mode+'.command.json'),cmd)
        with (out/(mode+'.log')).open('x') as stream:
            process=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,timeout=300)
        results[mode]=dict(exit_code=process.returncode,object_sha256=digest(obj) if process.returncode==0 else None)
        if process.returncode: raise RuntimeError(mode+' compile failed')
    objcopy=Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-objcopy')
    for name,obj in [('tested',candidate),('installed',out/'combined.o')]:
        subprocess.run([objcopy,'-O','binary','--only-section=.text',obj,out/(name+'.text')],check=True)
    equal=(out/'tested.text').read_bytes()==(out/'installed.text').read_bytes()
    if not equal: raise ValueError('Installed .text differs from tested TU')
    if hashes(map(Path,pins)) != pins: raise ValueError('Source drift')
    atomic_json(out/'result.json',dict(state='PASS',compile=results,text_equal=True,
        text_sha256=digest(out/'installed.text'),text_bytes=(out/'installed.text').stat().st_size,
        inputs_sha256=digest(out/'inputs.json'),whole_object_identity=False))
    print((out/'result.json').read_text())


if __name__=='__main__': main()
