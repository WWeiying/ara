#!/usr/bin/env python3
"""Bit/CSR compare the independent tiled producer at four VLENs under QEMU."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes
from run_tile_context_engine import run_command


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();out=a.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out') or out.exists():raise ValueError('Fresh independent output required')
    runtime=ROOT/'verification/out/m4-prepared-installed-build-20261027-01'
    pins=json.loads((runtime/'manifest.json').read_text());receipt=json.loads((runtime/'result.json').read_text())
    if receipt['state']!='PASS' or hashes(map(Path,pins))!=pins:raise ValueError('Installed runtime drift')
    capture=Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators/blk_0_attn_q_weight/activation_f32.bin')
    meta=json.loads(capture.with_suffix('.json').read_text())
    if meta['shape']!=[1536,15,1,1] or capture.stat().st_size!=92160:raise ValueError('Real capture extent')
    accepted_capture=ROOT/'verification/out/m4-prepared-qkv-build-20261027-02/manifest.json'
    accepted_pins=json.loads(accepted_capture.read_text())
    if accepted_pins.get(str(capture))!=digest(capture):raise ValueError('Capture differs from accepted projection input')
    previous=ROOT/'verification/out/m4-state-replay-20261027-01'
    template=json.loads((previous/'compile-producer.command.json').read_text())
    qemu=json.loads((previous/'qemu.command.json').read_text())
    init=ROOT/'verification/out/q8k-decode-layout-full-20261026-01/init'
    cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
    sources=[HERE/name for name in ('producer.cpp','tiled_producer.cpp','tiled_candidate.h','tiled_test.cpp')]
    pins.update(hashes([Path(__file__),*sources,capture,capture.with_suffix('.json'),accepted_capture,
        previous/'compile-producer.command.json',Path(template[0]),init,cpio,Path(qemu[0]),
        Path(qemu[qemu.index('-bios')+1]),Path(qemu[qemu.index('-kernel')+1])]))
    out.mkdir(parents=True);state=dict(state='PREPARING',pid=os.getpid(),child_pid=None,performance_measured=False)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,name,limit=180):
        cmd=list(map(str,cmd));atomic_json(out/(name+'.command.json'),cmd);state['state']=name.upper();save()
        if run_command(cmd,out/(name+'.log'),limit,os.environ.copy(),started):raise RuntimeError(name+' failed')
    try:
        assembly=out/'data.S';assembly.write_text('.section .rodata\n.balign 64\n.global real_input\nreal_input:\n'+
                                                f'.incbin "{capture}"\n')
        objects=[]
        for i,source in enumerate([HERE/'producer.cpp',HERE/'tiled_producer.cpp',HERE/'tiled_test.cpp',assembly]):
            cmd=list(template);cmd[cmd.index('-c')+1]=str(source);obj=out/f'{i}.o';cmd[cmd.index('-o')+1]=str(obj)
            cmd+=['-I'+str(ROOT/'software/qbs/include')]
            run(cmd,'compile-'+str(i));objects.append(obj)
        run([template[0],'-static',*objects,*receipt['libraries'],'-ldl','-lm','-pthread','-o',out/'test'],'link')
        recipe=out/'initramfs.list';recipe.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
            f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as stream:subprocess.run([str(cpio),str(recipe)],stdout=stream,check=True,timeout=60)
        pins.update(hashes([assembly,recipe,out/'test',out/'initramfs.cpio',*objects]));atomic_json(out/'manifest.json',pins)
        qemu[qemu.index('-initrd')+1]=str(out/'initramfs.cpio');results=[]
        for vlen in (128,256,512,1024):
            cmd=list(qemu);cmd[cmd.index('-cpu')+1]=f'rv64,v=true,vlen={vlen},elen=64,zfh=true,zvfh=true,xaraqbs=false'
            run(cmd,'qemu-'+str(vlen),600);text=(out/f'qemu-{vlen}.log').read_text()
            if text.splitlines().count('TILED_M4_PASS checks=808 real_groups=3 generated_cases=4 bytes=7008')!=1 or \
               text.splitlines().count('GUEST_TEST_EXIT=0')!=1:raise ValueError('Missing full tiled comparison: '+str(vlen))
            results.append(dict(vlen=vlen,checks=808,log_sha256=digest(out/f'qemu-{vlen}.log')))
        if hashes(map(Path,pins))!=pins:raise ValueError('Source drift')
        state.update(state='PASS',configurations=results,
                     scope='Exact prepared-byte/fallback/CSR comparison, not graph integration or hardware performance')
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
