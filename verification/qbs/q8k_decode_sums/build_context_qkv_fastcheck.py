#!/usr/bin/env python3
"""Build real captured Q/V/K context reuse pair without changing live inputs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import hashes,atomic_json,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'): raise ValueError('Independent output required')
    base=ROOT/'verification/out/q8k-decode-projection-build-20261026-02'
    pins=json.loads((base/'manifest.json').read_text())
    if hashes(map(Path,pins))!=pins: raise ValueError('Prerequisite build drift')
    commands=json.loads((base/'commands.json').read_text())
    capture=Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/decode/operators')
    items=[]
    activation=None
    for name,kind,n,block in (('q','q4_K',1536,144),('v','q6_K',256,210),('k','q4_K',256,144)):
        directory=capture/f'blk_0_attn_{name}_weight'
        for stem,typ,shape,size in (('activation_f32','f32',[1536,1,1,1],6144),
                ('output_f32','f32',[n,1,1,1],n*4),
                ('weight_'+kind,kind,[1536,n,1,1],n*6*block)):
            meta=json.loads((directory/(stem+'.json')).read_text())
            if meta['type']!=typ or meta['shape']!=shape or meta['nbytes']!=size:
                raise ValueError('Capture geometry drift')
            if (directory/(stem+'.bin')).stat().st_size!=size: raise ValueError('Capture length')
        value=(directory/'activation_f32.bin').read_bytes()
        if activation is not None and activation!=value: raise ValueError('Inputs not identical: reuse invalid')
        activation=value
        items.append((name,directory,kind,n,block))
        pins.update(hashes(list(directory.iterdir())))
    pins.update(hashes([Path(__file__),HERE/'context_qkv_pair_fastcheck.c']))
    pins.update(hashes([HERE/'integrity_words.h']))
    out.mkdir(parents=True,exist_ok=False)
    assets=[('qkv_input',items[0][1]/'activation_f32.bin')]
    for name,directory,kind,n,block in items:
        w=(directory/('weight_'+kind+'.bin')).read_bytes()
        target=out/(name+'_r4.bin')
        target.write_bytes(b''.join(w[((row+r)*6+b)*block:((row+r)*6+b+1)*block]
                                   for row in range(0,n,4) for b in range(6) for r in range(4)))
        assets.extend([(name+'_weights',target),(name+'_expected',directory/'output_f32.bin')])
    data=out/'data.S'
    data.write_text('.section .rodata\n'+''.join(
        f'.balign 64\n.global {n}\n{n}:\n.incbin "{f}"\n' for n,f in assets))
    records=[]
    def run(cmd,name):
        records.append(cmd);atomic_json(out/'commands.json',records)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    for index,source in ((0,HERE/'context_qkv_pair_fastcheck.c'),(2,data)):
        cmd=list(commands[index]);cmd[cmd.index('-c')+1]=str(source)
        cmd[cmd.index('-o')+1]=str(out/f'projection-{index}.o')
        run(cmd,f'compile-{index}')
    link=list(next(c for c in commands if '-nostdlib' in c))
    for index in (0,2):
        link[link.index(str(base/f'projection-{index}.o'))]=str(out/f'projection-{index}.o')
    link[link.index('-o')+1]=str(out/'context-qkv.elf')
    link=[('-Wl,-Map='+str(out/'link.map')) if x.startswith('-Wl,-Map=') else x for x in link]
    run(link,'link')
    linux=list(next(c for c in commands if c[0].endswith('riscv64-linux-gcc')))
    linux[linux.index(str(HERE/'projection_pair.c'))]=str(HERE/'context_qkv_pair_fastcheck.c')
    linux[linux.index(str(base/'data.S'))]=str(data)
    linux[linux.index('-o')+1]=str(out/'context-qkv-linux')
    run(linux,'linux')
    if hashes(map(Path,pins))!=pins: raise ValueError('Build drift')
    pins.update(hashes([data,out/'projection-0.o',out/'projection-2.o',out/'context-qkv.elf',
                       out/'context-qkv-linux',*[out/(n+'_r4.bin') for n in ('q','v','k')]]))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'build.json',dict(state='BUILT_NOT_EXECUTED',manifest_sha256=digest(out/'manifest.json'),
        scope='Real Q/V/K projections; isolated context reuse, excludes intermediate graph operations',
        k=1536,outputs=[1536,256,256],profiles=['Q4_K','Q6_K','Q4_K'],commands_per_trial=64))


if __name__=='__main__':main()
