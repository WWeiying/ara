#!/usr/bin/env python3
"""Reuse validated objects and add an independent exact weight-image copy."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
from exact_projection_source import generate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,hashes,digest


def load_ranges(path):
    data=path.read_bytes()
    if data[:6]!=b'\x7fELF\x02\x01': raise ValueError('Expected ELF64 little endian')
    offset=struct.unpack_from('<Q',data,32)[0]
    size,count=struct.unpack_from('<HH',data,54)
    if size!=56: raise ValueError('Unexpected program header layout')
    ranges=[]
    for i in range(count):
        typ,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',data,offset+i*size)
        if typ==1:
            if filesz>memsz or off+filesz>len(data) or pa<0x80000000 or pa+memsz>0x81000000:
                raise ValueError('ELF load segment exceeds simulation L2')
            ranges.append(dict(address=pa,bytes=memsz))
    if not ranges: raise ValueError('No load segments')
    return ranges


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind',choices=('projection','qkv'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--combined-prepare',action='store_true')
    parser.add_argument('--archived-quantizer-source',type=Path)
    args=parser.parse_args();out=args.output.resolve()
    if args.combined_prepare and args.kind!='qkv':raise ValueError('Combined preparation requires Q/V/K')
    if not out.is_relative_to(ROOT/'verification/out'): raise ValueError('Independent output required')
    stem='q8k-decode-projection' if args.kind=='projection' else 'q8k-context-qkv'
    base=ROOT/f'verification/out/{stem}-groupcheck-build-20261026-01'
    pins=json.loads((base/'manifest.json').read_text())
    rebindings=[]
    if args.archived_quantizer_source:
        original_source=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/quants.c')
        archived=args.archived_quantizer_source.resolve(strict=True)
        expected=pins[str(original_source)]
        if archived==original_source or digest(archived)!=expected:
            raise ValueError('Archived quantizer must exactly match the inherited original source')
        # The reused quantizer objects and generated source remain unchanged.
        # Preserve their original input identity using its saved byte-exact copy.
        del pins[str(original_source)]
        pins[str(archived)]=expected
        pins.update(hashes([original_source]))
        rebindings.append(dict(original_path=str(original_source),archived_path=str(archived),
                               inherited_sha256=expected,current_sha256=digest(original_source)))
    if hashes(map(Path,pins))!=pins: raise ValueError('Prerequisite input drift')
    commands=json.loads((base/'commands.json').read_text())
    compile_cmd=list(commands[0])
    original=Path(compile_cmd[compile_cmd.index('-c')+1])
    generated=generate(original.read_text(),args.kind)
    if args.combined_prepare:
        declaration='extern void decode_original(const float *, void *, int64_t);'
        call='            if(!reuse || part==0) decode_original(qkv_input,packed+1,1536);'
        if generated.count(declaration)!=1 or generated.count(call)!=1:
            raise ValueError('Reviewed combined preparation structure drift')
        generated=generated.replace(declaration,declaration+'\nextern void decode_candidate(const float *, void *, int64_t);')
        generated=generated.replace(call,
            '            if(!reuse || part==0) {\n'
            '                if(reuse) decode_candidate(qkv_input,packed+1,1536);\n'
            '                else decode_original(qkv_input,packed+1,1536);\n'
            '            }')
    pins.update(hashes([Path(__file__),HERE/'exact_projection_source.py',HERE/'integrity_equal.h']))
    out.mkdir(parents=True,exist_ok=False)
    atomic_json(out/'source-rebindings.json',rebindings)
    source=out/'experiment.c';source.write_text(generated)
    weights=[('projection_weights',base/'weight_r4.bin')] if args.kind=='projection' else [
        (n+'_weights',base/(n+'_r4.bin')) for n in ('q','v','k')]
    # Append a separate image, not an alias of the executed weights.
    expected=out/'expected.S'
    expected.write_text('.section .rodata\n'+''.join(
        f'.balign 64\n.global {name}_expected\n{name}_expected:\n.incbin "{path}"\n'
        for name,path in weights))
    records=[]
    def run(cmd,name):
        records.append(cmd);atomic_json(out/'commands.json',records)
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    for name,src in (('experiment',source),('expected',expected)):
        cmd=list(compile_cmd)
        cmd[cmd.index('-c')+1]=str(src);cmd[cmd.index('-o')+1]=str(out/(name+'.o'))
        cmd+=['-iquote',str(HERE)]
        run(cmd,name)
    link=list(next(c for c in commands if '-nostdlib' in c))
    link[link.index(str(base/'projection-0.o'))]=str(out/'experiment.o')
    link.insert(link.index('-lm'),str(out/'expected.o'))
    link[link.index('-o')+1]=str(out/'projection.elf')
    link=[('-Wl,-Map='+str(out/'link.map')) if x.startswith('-Wl,-Map=') else x for x in link]
    run(link,'link')
    linux=list(next(c for c in commands if c[0].endswith('riscv64-linux-gcc')))
    linux[linux.index(str(original))]=str(source)
    linux.insert(linux.index('-lm'),str(expected))
    linux+=['-iquote',str(HERE)]
    linux[linux.index('-o')+1]=str(out/'projection-linux')
    run(linux,'linux')
    ranges=load_ranges(out/'projection.elf')
    if hashes(map(Path,pins))!=pins: raise ValueError('Build input drift')
    pins.update(hashes([source,expected,out/'experiment.o',out/'expected.o',out/'projection.elf',out/'projection-linux']))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'build.json',dict(state='BUILT_NOT_EXECUTED',kind=args.kind,combined_prepare=args.combined_prepare,
        source_rebindings=rebindings,
        manifest_sha256=digest(out/'manifest.json'),load_ranges=ranges,
        scope='Original complete shapes and ABBA; independent exact weight comparison outside timing'))


if __name__=='__main__':main()
