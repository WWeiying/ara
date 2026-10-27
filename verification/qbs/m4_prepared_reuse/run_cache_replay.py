#!/usr/bin/env python3
"""Test the experimental byte cache with the real M4 producer under RVV QEMU."""
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
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Independent output required')
    previous=ROOT/'verification/out/m4-state-replay-20261027-01'
    pins=json.loads((previous/'manifest.json').read_text())
    if json.loads((previous/'result.json').read_text())['state']!='PASS':
        raise ValueError('Original replay proof missing')
    if hashes(map(Path,pins))!=pins:raise ValueError('Original replay input drift')
    sources=[HERE/'producer.cpp',HERE/'cache_replay.cpp',HERE/'value_cache.hpp',Path(__file__)]
    pins.update(hashes(sources))
    out.mkdir(parents=True,exist_ok=False)
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,label,limit):
        cmd=list(map(str,cmd));state.update(state=label.upper(),child_pid=None);save()
        atomic_json(out/(label+'.command.json'),cmd)
        if run_command(cmd,out/(label+'.log'),limit,os.environ.copy(),started):
            raise RuntimeError(label+' failed')
    try:
        assembly=out/'data.S';assembly.write_bytes((previous/'data.S').read_bytes())
        objects=[]
        for name,source in (('producer',HERE/'producer.cpp'),('test',HERE/'cache_replay.cpp'),('data',assembly)):
            cmd=json.loads((previous/('compile-'+name+'.command.json')).read_text())
            cmd[cmd.index('-c')+1]=str(source)
            obj=out/(name+'.o');cmd[cmd.index('-o')+1]=str(obj)
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
        pins.update(hashes([assembly,listing,out/'initramfs.cpio',out/'test',*objects]))
        atomic_json(out/'manifest.json',pins)
        cmd=json.loads((previous/'qemu.command.json').read_text())
        cmd[cmd.index('-initrd')+1]=str(out/'initramfs.cpio')
        run(cmd,'qemu',600)
        lines=(out/'qemu.log').read_text().splitlines()
        marker='M4_CACHE_REPLAY_PASS checks=269 computations=4 hits=260 misses=4'
        if lines.count(marker)!=1 or lines.count('GUEST_TEST_EXIT=0')!=1:
            raise ValueError('Missing complete cache replay acceptance')
        if hashes(map(Path,pins))!=pins:raise ValueError('Execution drift')
        state.update(state='PASS',checks=269,computations=4,hits=260,misses=4,
                     scope='Real-input cache/CSR functionality only; no RTL timing or production integration',
                     log_sha256=digest(out/'qemu.log'))
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc));raise
    finally:
        state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
