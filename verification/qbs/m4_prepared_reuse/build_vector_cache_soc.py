#!/usr/bin/env python3
"""Controlled successor: replace only cache byte operations with tested VLA RVV."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes


def vector_header(text):
    replacements=[('#include <array>','#include "rvv-byte-ops.h"\n#include <array>',1),
        ('std::memcmp(e.data.get(),input,in)==0','ggml_riscv_byte_ops::equal(e.data.get(),input,in)',1),
        ('std::memcmp(e.data.get()+in,output,out)!=0','!ggml_riscv_byte_ops::equal(e.data.get()+in,output,out)',1),
        ('std::memcpy(','ggml_riscv_byte_ops::copy(',3)]
    for before,after,count in replacements:
        if text.count(before)!=count:raise ValueError('Reviewed cache structure drift')
        text=text.replace(before,after)
    return text


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    base=ROOT/'verification/out/m4-cache-soc-build-20261027-03'
    pins=json.loads((base/'manifest.json').read_text())
    if hashes(map(Path,pins))!=pins:raise ValueError('Accepted scalar-byte experiment drift')
    helper=ROOT/'software/qbs/ggml/rvv-byte-ops.h'
    for v in (128,256,512,1024):
        probe=ROOT/(f'verification/out/m4-byte-ops-v{v}-20261027-'+('02' if v==1024 else '01'))
        r=json.loads((probe/'result.json').read_text());pinned=json.loads((probe/'manifest.json').read_text())
        if r['state']!='PASS' or r['cases']!=52 or r['states']!=256 or hashes(map(Path,pinned))!=pinned:
            raise ValueError('Byte-helper functional gate drift')
        pins.update(pinned);pins.update(hashes([probe/'result.json']))
    pins.update(hashes([Path(__file__),helper,base/'commands.json',base/'manifest.json']))
    out.mkdir(parents=True,exist_ok=False)
    header=out/'value_cache.hpp';header.write_text(vector_header((HERE/'value_cache.hpp').read_text()))
    source=out/'cache_soc.cpp';source.write_bytes((HERE/'cache_soc.cpp').read_bytes())
    commands=json.loads((base/'commands.json').read_text());executed=[];rebindings={}
    for i,original in enumerate(commands):
        cmd=list(original)
        if '-c' in cmd:
            original_source=Path(cmd[cmd.index('-c')+1])
            if original_source==HERE/'cache_soc.cpp':cmd[cmd.index('-c')+1]=str(source)
            old_object=cmd[cmd.index('-o')+1];obj=str(out/f'{i}.o');rebindings[old_object]=obj
            cmd[cmd.index('-o')+1]=obj
        else:
            cmd=[rebindings.get(s,s) for s in cmd]
            cmd[cmd.index('-o')+1]=str(out/'qbs_current_projection_soc')
            cmd=[('-Wl,-Map='+str(out/'link.map')) if s.startswith('-Wl,-Map=') else s for s in cmd]
        executed.append(cmd)
        with (out/f'command-{i}.log').open('x') as f:
            subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
    atomic_json(out/'commands.json',executed)
    compiler=Path(commands[0][0]);elf=out/'qbs_current_projection_soc'
    listing=subprocess.check_output([str(compiler.with_name('riscv64-unknown-elf-objdump')),'-d',str(elf)],text=True)
    if not all(op in listing for op in ('vle8.v','vse8.v','vfirst.m','m4_produce')):
        raise ValueError('Missing producer/vector byte operations')
    (out/'disassembly.log').write_text(listing)
    if hashes(map(Path,pins))!=pins:raise ValueError('Build drift')
    pins.update(hashes(p for p in out.iterdir() if p.is_file()))
    atomic_json(out/'manifest.json',pins)
    atomic_json(out/'build.json',dict(state='READY',execution='NOT_RUN',elf_sha256=digest(elf),
        manifest_sha256=digest(out/'manifest.json'),runtime_modified=False,rtl_modified=False,
        delta='Only exact byte comparison/copy inside the existing cache use VLA RVV',
        scope='Preparation-only ABBA, cold fill included; not full projection/model speedup'))
    print(json.dumps(dict(state='READY',output=str(out))))


if __name__=='__main__':main()
