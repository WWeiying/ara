#!/usr/bin/env python3
"""Independent QEMU functional gate, then same-ELF VCS complete projection timing."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes,image_files,script_files
from run_tile_context_engine import run_command
from check_context_qkv import check


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); build=a.build.resolve(strict=True); out=a.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'): raise ValueError('Use verification/out')
    pins=json.loads((build/'manifest.json').read_text())
    report=json.loads((build/'build.json').read_text())
    if report['state']!='BUILT_NOT_EXECUTED' or digest(build/'manifest.json')!=report['manifest_sha256'] or hashes(map(Path,pins))!=pins:
        raise ValueError('Build drift')
    simv=ROOT/'verification/out/canonical-shared-resources-build-20261025-02/sim/simv'
    qemu=ROOT/'verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
    platform=Path('/home/wangwy/llama/platforms/cva6-qemu')
    init=ROOT/'verification/out/q8k-decode-layout-soc-golden-20261026-01/init'
    cpio=platform/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
    pins.update(hashes([Path(__file__),HERE/'check_context_qkv.py',build/'build.json',
                       init,cpio,qemu,platform/'images/Image',platform/'images/fw_dynamic.bin',
                       *image_files(simv),*script_files()]))
    out.mkdir(parents=True,exist_ok=False)
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None)
    def save(): atomic_json(out/'status.json',state)
    def started(pid):
        state['child_pid']=pid; save()
    def run(cmd,label,bound,env=None):
        cmd=list(map(str,cmd)); atomic_json(out/(label+'.command.json'),cmd)
        state.update(state=label.upper(),child_pid=None); save()
        if run_command(cmd,out/(label+'.log'),bound,env or os.environ.copy(),started):
            raise RuntimeError(label+' failed')
        state['child_pid']=None
    try:
        listing=out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
            f'file /init {init} 755 0 0\nfile /test {build/"context-qkv-linux"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as f:
            subprocess.run([str(cpio),str(listing)],stdout=f,check=True,timeout=60)
        pins.update(hashes([listing,out/'initramfs.cpio']))
        atomic_json(out/'manifest.json',pins)
        run([qemu,'-M','virt','-cpu','rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
             '-smp','1','-m','512M','-display','none','-monitor','none','-serial','stdio',
             '-bios',platform/'images/fw_dynamic.bin','-kernel',platform/'images/Image',
             '-initrd',out/'initramfs.cpio','-append','console=ttyS0 rdinit=/init'],'golden',600)
        text=(out/'golden.log').read_text()
        golden=check(text)
        if text.splitlines().count('GUEST_TEST_EXIT=0')!=1: raise ValueError('Guest exit missing')
        atomic_json(out/'golden.json',dict(state='PASS',trials=golden,performance_measured=False))
        if hashes(map(Path,pins))!=pins: raise ValueError('Pre-VCS drift')
        env=dict(os.environ,ARA_VCS_TIMEOUT_SECONDS='7200')
        run(['bash',ROOT/'verification/uvm/run_real_dut_case.sh',simv,build/'context-qkv.elf',
             'q8k_context_qkv_pair',out/'soc'],'vcs',7320,env)
        log=out/'soc/work/run.vcs.log'
        trials=check(log.read_text(),golden)
        if hashes(map(Path,pins))!=pins: raise ValueError('Execution drift')
        totals={name:sum(r['total'] for r in trials if r['reuse']==flag)
                for name,flag in (('original',0),('candidate',1))}
        atomic_json(out/'result.json',dict(state='PASS',trials=trials,totals=totals,
            speedup=totals['original']/totals['candidate'],log_sha256=digest(log),
            scope='Captured Q/V/K context reuse, excludes intervening graph operators; not full model performance'))
        state['state']='PASS'
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc)); atomic_json(out/'result.json',state); raise
    finally:
        state['child_pid']=None; save()


if __name__=='__main__': main()
