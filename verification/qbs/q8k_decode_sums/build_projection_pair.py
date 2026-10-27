#!/usr/bin/env python3
"""Build paired complete Decode Q projection from captured model tensors."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'): raise ValueError('Use verification/out')
    base=ROOT/'verification/out/q8k-decode-layout-soc-build-20261026-01'
    gate=ROOT/'verification/out/q8k-decode-layout-soc-vcs-20261026-01'
    pins=json.loads((base/'manifest.json').read_text())
    if json.loads((gate/'result.json').read_text())['state']!='PASS' or hashes(map(Path,pins))!=pins:
        raise ValueError('Preparation acceptance/input drift')
    capture=Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/decode/operators/blk_0_attn_q_weight')
    shapes={'activation_f32':('f32',[1536,1,1,1],6144),
            'output_f32':('f32',[1536,1,1,1],6144),
            'weight_q4_K':('q4_K',[1536,1536,1,1],1536*6*144)}
    for name,(kind,shape,size) in shapes.items():
        meta=json.loads((capture/(name+'.json')).read_text())
        if meta['type']!=kind or meta['shape']!=shape or meta['nbytes']!=size or (capture/(name+'.bin')).stat().st_size!=size:
            raise ValueError('Captured tensor geometry mismatch')
    native=ROOT/'software/qbs/src/qbs_native_riscv.c'
    commands=json.loads((base/'commands.json').read_text())
    pins.update(hashes([Path(__file__),HERE/'projection_pair.c',native,*capture.iterdir(),
                       * (ROOT/'software/qbs/include').rglob('*.h'),gate/'result.json']))
    out.mkdir(parents=True,exist_ok=False)
    weights=(capture/'weight_q4_K.bin').read_bytes()
    packed=b''.join(weights[((first+r)*6+b)*144:((first+r)*6+b+1)*144]
                    for first in range(0,1536,4) for b in range(6) for r in range(4))
    (out/'weight_r4.bin').write_bytes(packed)
    data=out/'data.S'
    data.write_text('.section .rodata\n'+''.join(
        f'.balign 64\n.global {name}\n{name}:\n.incbin "{path}"\n'
        for name,path in (('projection_input',capture/'activation_f32.bin'),
                          ('projection_expected',capture/'output_f32.bin'),
                          ('projection_weights',out/'weight_r4.bin'))))
    golden=ROOT/'verification/out/q8k-decode-layout-soc-golden-20261026-01'
    quantizers=out/'quantizers.c'
    quantizer_text=(golden/'quantizers.h').read_text()
    if quantizer_text.count('static __attribute__((noinline)) void decode_')!=2:
        raise ValueError('Quantizer source structure drift')
    quantizers.write_text(quantizer_text.replace('static __attribute__((noinline)) void decode_', 'void decode_'))
    records=[]
    def run(cmd,name):
        records.append(cmd); atomic_json(out/'commands.json',records)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    template=commands[0]
    objects=[]
    for i,source in enumerate((HERE/'projection_pair.c',native,data,quantizers)):
        cmd=list(template)
        cmd[cmd.index('-c')+1]=str(source)
        obj=out/f'projection-{i}.o'
        cmd[cmd.index('-o')+1]=str(obj)
        cmd+=['-I'+str(ROOT/'software/qbs/include'),'-I/home/wangwy/llama/llama.cpp/ggml/src']
        run(cmd,f'compile-{i}'); objects.append(obj)
    link=list(next(cmd for cmd in commands if '-nostdlib' in cmd))
    link[link.index(str(base/'0.o'))]=str(objects[0])
    link[link.index('-o')+1]=str(out/'projection.elf')
    link=[('-Wl,-Map='+str(out/'link.map')) if x.startswith('-Wl,-Map=') else x for x in link]
    link[link.index('-lm'):link.index('-lm')]=list(map(str,objects[1:]))
    run(link,'link')
    linux='/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-gcc'
    flags=template[1:template.index('-c')]
    flags=[x for x in flags if not x.startswith('-I'+str(ROOT/'apps/'))]
    flags+=['-I'+str(ROOT/'software/qbs/include'),'-I/home/wangwy/llama/llama.cpp/ggml/src','-DDECODE_LINUX','-static']
    run([linux,*flags,str(HERE/'projection_pair.c'),str(native),str(data),str(quantizers),'-lm','-o',str(out/'projection-linux')],'linux')
    objdump=Path(template[0]).with_name('riscv64-unknown-elf-objdump')
    run([str(objdump),'-d',str(out/'projection.elf')],'disassembly')
    if hashes(map(Path,pins))!=pins: raise ValueError('Source drift')
    pins.update(hashes([Path(linux).resolve(),quantizers,data,out/'weight_r4.bin',out/'projection.elf',out/'projection-linux',*objects]))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'build.json',dict(state='BUILT_NOT_EXECUTED',manifest_sha256=digest(out/'manifest.json'),
        elf_sha256=digest(out/'projection.elf'),m=1,n=1536,k=1536,
        scope='Complete real Decode Q projection, original/layout ABBA, context fill/reuse/release'))


if __name__=='__main__': main()
