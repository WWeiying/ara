#!/usr/bin/env python3
"""Verify and compile the actual quantizer integration, not a private wrapper."""
import argparse
import json
from pathlib import Path
import subprocess
from compile_shared_decode import HERE,ROOT,opcodes
from run_half_scale_soc import atomic_json,hashes,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--before',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();before=a.before.resolve(strict=True)
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    base=ROOT/'verification/out/q8k-decode-layout-compile-20261026-01'
    source=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/quants.c')
    canonical=ROOT/'software/qbs/ggml/q8_K-decode-sums.h'
    installed=source.with_name('q8_K-decode-sums.h')
    if digest(before)!=json.loads((base/'inputs.json').read_text())[str(source)]:
        raise ValueError('Pre-integration source differs from measured original')
    if canonical.read_bytes()!=installed.read_bytes():raise ValueError('Installed helper drift')
    expected=(base/'candidate.c').read_text().replace(
        '#include "'+str(HERE/'sums_layout.h')+'"','#include "q8_K-decode-sums.h"').replace(
        'qbs_decode_sums_layout_candidate(','ggml_riscv_q8_K_bsums(')
    if source.read_text()!=expected:raise ValueError('Unexpected production source delta')
    reference=base/'candidate.o'
    if digest(reference)!=json.loads((base/'result.json').read_text())['objects']['candidate']:
        raise ValueError('Measured object drift')
    cmd=json.loads((base/'candidate.command.json').read_text())
    pins=hashes([before,source,canonical,installed,reference,base/'candidate.c',Path(__file__),HERE/'compile_shared_decode.py'])
    for directory in {Path(x[2:]).resolve() for x in cmd if x.startswith('-I')}:
        pins.update(hashes([p for p in directory.rglob('*') if p.is_file() and p.suffix in ('.h','.hpp','.inc','.inl')]))
    out.mkdir(parents=True,exist_ok=False)
    cmd[cmd.index('-c')+1]=str(source);cmd[cmd.index('-o')+1]=str(out/'quants.c.o')
    atomic_json(out/'command.json',cmd)
    with (out/'compile.log').open('x') as f:
        subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
    objdump=Path(cmd[0]).with_name('riscv64-linux-objdump')
    instructions=[]
    for name,obj in (('measured',reference),('installed',out/'quants.c.o')):
        text=subprocess.run([str(objdump),'-d','--disassemble=quantize_row_q8_K',str(obj)],
                            capture_output=True,text=True,check=True,timeout=30).stdout
        (out/(name+'.asm')).write_text(text);instructions.append(opcodes(text))
    if instructions[0]!=instructions[1]:raise ValueError('Installed quantizer opcodes differ from measured candidate')
    if hashes(map(Path,pins))!=pins:raise ValueError('Input drift')
    pins.update(hashes([out/'quants.c.o',objdump.resolve()]))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'result.json',dict(state='INSTALLED_DECODE_COMPILE_EQUIVALENT',instructions=len(instructions[0]),
        source_sha256=digest(source),helper_sha256=digest(installed),object_sha256=digest(out/'quants.c.o'),
        scope='Actual installed production TU; complete quantize_row_q8_K opcodes match measured candidate'))


if __name__=='__main__':main()
