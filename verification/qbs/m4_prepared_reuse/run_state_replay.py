#!/usr/bin/env python3
"""Real Prefill M4 data: prove prepared-byte exception replay, not a cache."""
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
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    runtime=ROOT/'verification/out/q8k-installed-runtime-build-20261026-01'
    pins=json.loads((runtime/'manifest.json').read_text())
    r=json.loads((runtime/'result.json').read_text())
    if r['state']!='PASS' or hashes(map(Path,pins))!=pins:raise ValueError('Normal library drift')
    data=ROOT/'verification/qbs/combined_zvfh_m4/projection/build-03'
    prior=json.loads((data/'manifest.json').read_text())
    files=[data/'activation_f32.bin',data/'activation_q8k_m4.bin']
    if any(prior.get(str(x))!=digest(x) for x in files):raise ValueError('Reference capture drift')
    if [x.stat().st_size for x in files]!=[24576,7008]:raise ValueError('M4 capture geometry')
    helper=ROOT/'software/qbs/ggml'
    live=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv')
    for name in ('q8_K-m4.h','q8_K-signed-max.h'):
        if (helper/name).read_bytes()!=(live/name).read_bytes():raise ValueError('Producer differs from installed helper')
    base=ROOT/'verification/out/q8k-signed-max-model-20261026-01'
    compile_template=json.loads((base/'compile.command.json').read_text())
    platform=Path('/home/wangwy/llama/platforms/cva6-qemu')
    qemu=ROOT/'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
    init=ROOT/'verification/out/q8k-decode-layout-full-20261026-01/init'
    cpio=platform/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    pins.update(hashes([*files,HERE/'producer.cpp',HERE/'state_replay.cpp',Path(__file__),qemu,init,cpio,
                       platform/'images/Image',platform/'images/fw_dynamic.bin',helper/'q8_K-m4.h',helper/'q8_K-signed-max.h']))
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
            for name,path in zip(('real_input','golden_packed'),files)))
        objects=[]
        for name,source in (('producer',HERE/'producer.cpp'),('test',HERE/'state_replay.cpp'),('data',assembly)):
            cmd=list(compile_template);cmd[cmd.index('-c')+1]=str(source)
            obj=out/(name+'.o');cmd[cmd.index('-o')+1]=str(obj)
            cmd+=['-Wno-unused-function','-DGGML_USE_RISCV_QBS','-I'+str(helper),
                  '-I/home/wangwy/llama/llama.cpp/ggml/src','-I/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu']
            run(cmd,'compile-'+name,180);objects.append(obj)
        run([compile_template[0],'-static',*objects,*r['libraries'],'-ldl','-lm','-pthread','-o',out/'test'],'link',180)
        listing=out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
                           f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as f:
            subprocess.run([str(cpio),str(listing)],stdout=f,check=True,timeout=60)
        pins.update(hashes([assembly,listing,out/'initramfs.cpio',out/'test',*objects]))
        atomic_json(out/'manifest.json',pins)
        run([qemu,'-M','virt','-cpu','rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=false',
             '-smp','1','-m','512M','-display','none','-monitor','none','-serial','stdio',
             '-bios',platform/'images/fw_dynamic.bin','-kernel',platform/'images/Image',
             '-initrd',out/'initramfs.cpio','-append','console=ttyS0 rdinit=/init'],'qemu',600)
        lines=(out/'qemu.log').read_text().splitlines()
        if lines.count('M4_STATE_REPLAY_PASS checks=262 bytes=7008 raised_flags=1')!=1 or lines.count('GUEST_TEST_EXIT=0')!=1:
            raise ValueError('Missing complete state-replay acceptance')
        if hashes(map(Path,pins))!=pins:raise ValueError('Execution drift')
        state.update(state='PASS',checks=262,bytes=7008,
                     scope='Real-input byte/CSR replay only; no graph cache or performance claim',
                     log_sha256=digest(out/'qemu.log'))
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc));raise
    finally:
        state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
