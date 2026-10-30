#!/usr/bin/env python3
"""Functional QEMU admission for the complete slice; never report QEMU cycles."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes
from run_tile_context_engine import run_command
spec=importlib.util.spec_from_file_location('m4_qkv_check',HERE/'check.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();build=a.build.resolve(strict=True)
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    report=json.loads((build/'build.json').read_text());pins=json.loads((build/'manifest.json').read_text())
    if report['state']!='READY' or report['linux_elf_sha256']!=digest(build/'qkv-linux') or hashes(map(Path,pins))!=pins:
        raise ValueError('Build drift')
    base=ROOT/'verification/out/m4-state-replay-20261027-01'
    qemu=json.loads((base/'qemu.command.json').read_text())
    init=ROOT/'verification/out/q8k-decode-layout-full-20261026-01/init'
    cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
    pins.update(hashes([Path(__file__),HERE/'check.py',init,cpio,Path(qemu[0]),
        Path(qemu[qemu.index('-bios')+1]),Path(qemu[qemu.index('-kernel')+1])]))
    out.mkdir(parents=True,exist_ok=False);state=dict(state='PREPARING',pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    try:
        recipe=out/'initramfs.list';recipe.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
            f'file /init {init} 755 0 0\nfile /test {build/"qkv-linux"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as f:subprocess.run([str(cpio),str(recipe)],stdout=f,check=True,timeout=60)
        pins.update(hashes([recipe,out/'initramfs.cpio']));atomic_json(out/'manifest.json',pins)
        qemu[qemu.index('-cpu')+1]=qemu[qemu.index('-cpu')+1].replace('xaraqbs=false','xaraqbs=true')
        qemu[qemu.index('-initrd')+1]=str(out/'initramfs.cpio');atomic_json(out/'qemu.command.json',qemu)
        state['state']='QEMU';save()
        if run_command(qemu,out/'qemu.log',600,os.environ.copy(),started):raise RuntimeError('QEMU failed')
        text=(out/'qemu.log').read_text();measured=checker.check_output(text,timed=False)
        if text.splitlines().count('GUEST_TEST_EXIT=0')!=1:raise ValueError('Guest exit')
        if hashes(map(Path,pins))!=pins:raise ValueError('Execution drift')
        state.update(state='PASS',measured=measured,performance_measured=False,log_sha256=digest(out/'qemu.log'))
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
