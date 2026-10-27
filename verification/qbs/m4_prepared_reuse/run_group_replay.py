#!/usr/bin/env python3
"""Real full 15-token activation groups and unchanged single-row tails."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,hashes,digest
from run_tile_context_engine import run_command


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    previous=ROOT/'verification/out/m4-state-replay-20261027-01'
    pins=json.loads((previous/'manifest.json').read_text())
    if json.loads((previous/'result.json').read_text())['state']!='PASS' or hashes(map(Path,pins))!=pins:
        raise ValueError('Original producer input drift')
    captures=Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators')
    data=[]
    for name in ('attn_q','attn_v','attn_k','ffn_gate','ffn_up'):
        folder=captures/('blk_0_'+name+'_weight');meta=folder/'activation_f32.json';binary=folder/'activation_f32.bin'
        m=json.loads(meta.read_text())
        if m['type']!='f32' or m['shape']!=[1536,15,1,1] or m['strides']!=[4,6144,92160,92160] or \
                m['nbytes']!=92160 or binary.stat().st_size!=92160:raise ValueError('Capture geometry')
        pins.update(hashes([meta,binary,folder/'operator.json']));data.append(binary)
    pins.update(hashes([HERE/'producer.cpp',HERE/'group_replay.cpp',HERE/'value_cache.hpp',Path(__file__)]))
    out.mkdir(parents=True,exist_ok=False)
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,label,limit):
        cmd=list(map(str,cmd));state.update(state=label.upper(),child_pid=None);save()
        atomic_json(out/(label+'.command.json'),cmd)
        if run_command(cmd,out/(label+'.log'),limit,os.environ.copy(),started):raise RuntimeError(label+' failed')
    try:
        assembly=out/'data.S'
        assembly.write_text('.section .rodata\n'+''.join(
            f'.balign 64\n.global {name}\n{name}:\n.incbin "{path}"\n'
            for name,path in zip(('q_input','v_input','k_input','gate_input','up_input'),data)))
        objects=[]
        for name,source in (('producer',HERE/'producer.cpp'),('test',HERE/'group_replay.cpp'),('data',assembly)):
            cmd=json.loads((previous/('compile-'+name+'.command.json')).read_text())
            cmd[cmd.index('-c')+1]=str(source);obj=out/(name+'.o');cmd[cmd.index('-o')+1]=str(obj)
            cmd+=['-I'+str(ROOT/'software/qbs/include')]
            run(cmd,'compile-'+name,180);objects.append(obj)
        template=json.loads((previous/'link.command.json').read_text())
        libs=json.loads((ROOT/'verification/out/q8k-installed-runtime-build-20261026-01/result.json').read_text())['libraries']
        run([template[0],'-static',*objects,*libs,'-ldl','-lm','-pthread','-o',out/'test'],'link',180)
        init=ROOT/'verification/out/q8k-decode-layout-full-20261026-01/init'
        listing=out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
                           f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out/'initramfs.cpio').open('xb') as f:
            subprocess.run([str(cpio),str(listing)],stdout=f,check=True,timeout=60)
        pins.update(hashes([assembly,listing,out/'initramfs.cpio',out/'test',*objects]));atomic_json(out/'manifest.json',pins)
        cmd=json.loads((previous/'qemu.command.json').read_text());cmd[cmd.index('-initrd')+1]=str(out/'initramfs.cpio')
        run(cmd,'qemu',600)
        lines=(out/'qemu.log').read_text().splitlines()
        marker='M4_GROUP_REPLAY_PASS checks=36 computations=6 hits=12 misses=6 tails=18'
        if lines.count(marker)!=1 or lines.count('GUEST_TEST_EXIT=0')!=1:raise ValueError('Missing acceptance')
        if hashes(map(Path,pins))!=pins:raise ValueError('Execution drift')
        state.update(state='PASS',checks=36,computations=6,hits=12,misses=6,tails=18,
                     scope='Real 15-token grouped preparation and tail functionality; no graph integration or timing',
                     log_sha256=digest(out/'qemu.log'))
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc));raise
    finally:
        state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
