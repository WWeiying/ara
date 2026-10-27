#!/usr/bin/env python3
"""Functional byte-helper probe, with runtime-selected VLEN; no performance claim."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes
from run_tile_context_engine import run_command


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--vlen',type=int,choices=(128,256,512,1024),required=True);a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    base=ROOT/'verification/out/m4-state-replay-20261027-01'
    pins=json.loads((base/'manifest.json').read_text())
    if hashes(map(Path,pins))!=pins:raise ValueError('Inherited machine/library drift')
    pins.update(hashes([HERE/'byte_ops_test.cpp',ROOT/'software/qbs/ggml/rvv-byte-ops.h',Path(__file__)]))
    out.mkdir(parents=True,exist_ok=False);state=dict(state='PREPARING',pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,label,limit):
        cmd=list(map(str,cmd));state.update(state=label.upper(),child_pid=None);save();atomic_json(out/(label+'.command.json'),cmd)
        if run_command(cmd,out/(label+'.log'),limit,os.environ.copy(),started):raise RuntimeError(label+' failed')
    try:
        cmd=json.loads((base/'compile-test.command.json').read_text())
        cmd[cmd.index('-c')+1]=str(HERE/'byte_ops_test.cpp');cmd[cmd.index('-o')+1]=str(out/'test.o')
        run(cmd,'compile',180)
        link=json.loads((base/'link.command.json').read_text())
        libs=json.loads((ROOT/'verification/out/q8k-installed-runtime-build-20261026-01/result.json').read_text())['libraries']
        run([link[0],'-static',out/'test.o',*libs,'-ldl','-lm','-pthread','-o',out/'test'],'link',180)
        init=ROOT/'verification/out/q8k-decode-layout-full-20261026-01/init'
        listing=out/'initramfs.list';listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
            f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out/'initramfs.cpio').open('xb') as f:subprocess.run([str(cpio),str(listing)],stdout=f,check=True,timeout=60)
        pins.update(hashes([out/'test.o',out/'test',listing,out/'initramfs.cpio']));atomic_json(out/'manifest.json',pins)
        cmd=json.loads((base/'qemu.command.json').read_text());cmd[cmd.index('-initrd')+1]=str(out/'initramfs.cpio')
        cmd[cmd.index('-cpu')+1]=cmd[cmd.index('-cpu')+1].replace('vlen=1024',f'vlen={a.vlen}')
        run(cmd,'qemu',600)
        lines=(out/'qemu.log').read_text().splitlines()
        if lines.count('RVV_BYTE_OPS_PASS cases=52 states=256')!=1 or lines.count('GUEST_TEST_EXIT=0')!=1:
            raise ValueError('Missing acceptance')
        if hashes(map(Path,pins))!=pins:raise ValueError('Execution drift')
        state.update(state='PASS',vlen=a.vlen,cases=52,states=256,log_sha256=digest(out/'qemu.log'),performance_measured=False)
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
