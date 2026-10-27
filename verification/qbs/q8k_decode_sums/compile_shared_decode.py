#!/usr/bin/env python3
"""Compile canonical Decode helper and require measured quantizer opcodes."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def opcodes(text):
    if '<quantize_row_q8_K>:' not in text:raise ValueError('Quantizer symbol missing')
    values=re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{4,8})\s',text,re.M)
    if not values:raise ValueError('No quantizer opcodes')
    return values


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    base=ROOT/'verification/out/q8k-decode-layout-compile-20261026-01'
    helper=ROOT/'software/qbs/ggml/q8_K-decode-sums.h'
    cmd=json.loads((base/'candidate.command.json').read_text())
    reference=base/'candidate.o'
    if digest(reference)!=json.loads((base/'result.json').read_text())['objects']['candidate']:
        raise ValueError('Measured candidate object drift')
    text=(base/'candidate.c').read_text()
    old='#include "'+str(HERE/'sums_layout.h')+'"'
    if text.count(old)!=1 or text.count('qbs_decode_sums_layout_candidate(')!=1:
        raise ValueError('Measured source structure drift')
    text=text.replace(old,'#include "'+str(helper)+'"').replace(
        'qbs_decode_sums_layout_candidate(','ggml_riscv_q8_K_bsums(')
    pins=hashes([reference,base/'candidate.c',base/'candidate.command.json',helper,Path(__file__)])
    for directory in {Path(x[2:]).resolve() for x in cmd if x.startswith('-I')}:
        pins.update(hashes([p for p in directory.rglob('*') if p.is_file() and p.suffix in ('.h','.hpp','.inc','.inl')]))
    out.mkdir(parents=True,exist_ok=False)
    source=out/'quants.shared.c';source.write_text(text)
    cmd[cmd.index('-c')+1]=str(source);cmd[cmd.index('-o')+1]=str(out/'quants.o')
    atomic_json(out/'command.json',cmd)
    with (out/'compile.log').open('x') as f:
        subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
    objdump=Path(cmd[0]).with_name('riscv64-linux-objdump')
    listings=[]
    for name,obj in (('measured',reference),('shared',out/'quants.o')):
        listing=subprocess.run([str(objdump),'-d','--disassemble=quantize_row_q8_K',str(obj)],
                               capture_output=True,text=True,check=True,timeout=30).stdout
        (out/(name+'.asm')).write_text(listing);listings.append(opcodes(listing))
    if listings[0]!=listings[1]:raise ValueError('Shared helper changed generated quantizer opcodes')
    if hashes(map(Path,pins))!=pins:raise ValueError('Compile input drift')
    pins.update(hashes([source,out/'quants.o',objdump.resolve()]))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'result.json',dict(state='SHARED_HELPER_COMPILE_EQUIVALENT',
        instructions=len(listings[0]),helper_sha256=digest(helper),object_sha256=digest(out/'quants.o'),
        scope='Complete production-flags TU; quantize_row_q8_K opcodes match measured candidate'))


if __name__=='__main__':main()
