#!/usr/bin/env python3
"""Run real GGML with a private repack object; do not modify production libraries."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes
from run_tile_context_engine import run_command


def check(text):
    lines=text.splitlines();begins=[];passes=[];active=None;events=Counter()
    for line in lines:
        if line.startswith('M4_RUNTIME_GRAPH_BEGIN '):
            if active is not None:raise ValueError('Unclosed graph')
            f=dict(re.findall(r'(\w+)=(\d+)',line));active=tuple(int(f[k]) for k in ('mode','scenario','epoch'));begins.append(active)
        elif line.startswith('GGML_RISCV_QBS_M4_CACHE '):
            if active is None or active[0]!=1 or active[1] not in (0,1):raise ValueError('Unexpected cache use')
            f=dict(re.findall(r'(\w+)=(\S+)',line))
            if f['event'] not in ('hit','compute_rvv') or int(f['group']) not in range(3):raise ValueError('Invalid event')
            events[(active,f['event'],int(f['group']))]+=1
        elif line.startswith('M4_RUNTIME_GRAPH_PASS '):
            f=dict(re.findall(r'(\w+)=(\d+)',line));key=tuple(int(f[k]) for k in ('mode','scenario','epoch'))
            if active!=key:raise ValueError('Graph completion order')
            passes.append(key);active=None
    expected=[(m,s,e) for m in range(2) for s in range(6) for e in range(2)]
    if begins!=expected or passes!=expected or active is not None:raise ValueError('Incomplete graph suite')
    wanted=Counter({((1,s,e),event,g):1 for s in (0,1) for e in range(2)
                    for event in ('hit','compute_rvv') for g in range(3)})
    if events!=wanted:raise ValueError('Cache work did not match selected consumer chains')
    if lines.count('M4_RUNTIME_GRAPH_SUITE_PASS graphs=24 paired_bytes=46272 performance=not_measured')!=1 or \
       lines.count('GUEST_TEST_EXIT=0')!=1 or 'M4_RUNTIME_GRAPH_FAIL' in text:raise ValueError('Missing paired acceptance')
    return dict(graphs=24,paired_bytes=46272,cache_hits=12,cache_vector_computations=12,
                scope='Actual private GGML repack path, function/CSR/work-selection only, not RTL performance')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    candidate=ROOT/'verification/out/m4-runtime-candidate-compile-20261027-01'
    pins=json.loads((candidate/'manifest.json').read_text())
    if json.loads((candidate/'result.json').read_text())['state']!='COMPILE_ONLY_PASS' or hashes(map(Path,pins))!=pins:
        raise ValueError('Candidate drift')
    runtime=ROOT/'verification/out/q8k-installed-runtime-build-20261026-01'
    rpins=json.loads((runtime/'manifest.json').read_text())
    if json.loads((runtime/'result.json').read_text())['state']!='PASS' or hashes(map(Path,rpins))!=rpins:
        raise ValueError('Normal library drift')
    pins.update(rpins)
    base=ROOT/'verification/out/m4-state-replay-20261027-01'
    pins.update(json.loads((base/'manifest.json').read_text()))
    data=Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators/blk_0_attn_q_weight/activation_f32.bin')
    if data.stat().st_size!=92160:raise ValueError('Capture geometry')
    pins.update(hashes([data,HERE/'runtime_graph.cpp',Path(__file__)]))
    if hashes(map(Path,pins))!=pins:raise ValueError('Inherited input drift')
    out.mkdir(parents=True,exist_ok=False)
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,label,limit):
        cmd=list(map(str,cmd));state.update(state=label.upper(),child_pid=None);save()
        atomic_json(out/(label+'.command.json'),cmd)
        if run_command(cmd,out/(label+'.log'),limit,os.environ.copy(),started):raise RuntimeError(label+' failed')
    try:
        assembly=out/'data.S';assembly.write_text(f'.section .rodata\n.balign 64\n.global real_activation\nreal_activation:\n.incbin "{data}"\n')
        objects=[]
        for name,source in (('test',HERE/'runtime_graph.cpp'),('data',assembly)):
            cmd=json.loads((base/('compile-'+name+'.command.json')).read_text())
            cmd[cmd.index('-c')+1]=str(source);obj=out/(name+'.o');cmd[cmd.index('-o')+1]=str(obj)
            run(cmd,'compile-'+name,180);objects.append(obj)
        template=json.loads((base/'link.command.json').read_text())
        libs=json.loads((runtime/'result.json').read_text())['libraries']
        run([template[0],'-static',*objects,candidate/'candidate.o',*libs,'-ldl','-lm','-pthread',
             '-Wl,-Map='+str(out/'link.map'),'-o',out/'test'],'link',180)
        init=ROOT/'verification/out/q8k-decode-layout-full-20261026-01/init'
        listing=out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /tmp 1777 0 0\n'+
                           f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out/'initramfs.cpio').open('xb') as f:
            subprocess.run([str(cpio),str(listing)],stdout=f,check=True,timeout=60)
        pins.update(hashes([assembly,listing,out/'initramfs.cpio',out/'test',*objects]));atomic_json(out/'manifest.json',pins)
        cmd=json.loads((base/'qemu.command.json').read_text());cmd[cmd.index('-initrd')+1]=str(out/'initramfs.cpio')
        cmd[cmd.index('-cpu')+1]=cmd[cmd.index('-cpu')+1].replace('xaraqbs=false','xaraqbs=true')
        run(cmd,'qemu',600)
        measured=check((out/'qemu.log').read_text())
        if hashes(map(Path,pins))!=pins:raise ValueError('Execution drift')
        state.update(state='PASS',measured=measured,log_sha256=digest(out/'qemu.log'))
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc));raise
    finally:
        state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
