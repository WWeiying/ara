#!/usr/bin/env python3
"""Run the real Linux libm on extracted inputs; no EDA or timing claims."""
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
spec=importlib.util.spec_from_file_location('linux_exp_replay_check',HERE/'check.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();pairs_path=a.pairs.resolve(strict=True);out=a.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out') or out.exists():raise ValueError('Fresh independent output required')
    previous=json.loads((pairs_path.parent/'result.json').read_text())
    pins=json.loads((pairs_path.parent/'source-pins.json').read_text())
    if previous['state']!='REAL_EXP_ARGUMENTS_EXTRACTED' or previous['pairs_sha256']!=digest(pairs_path) or hashes(map(Path,pins))!=pins:
        raise ValueError('Extracted input identity drift')
    data=json.loads(pairs_path.read_text())
    if data['schema']!='actual_attention_expf_pairs_v1' or len(data['calls'])!=768:raise ValueError('Wrong real input dataset')
    calls=data['calls'];out.mkdir(parents=True)
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None,performance_measured=False)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,name,limit=180):
        cmd=list(map(str,cmd));atomic_json(out/(name+'.command.json'),cmd);state['state']=name.upper();save()
        if run_command(cmd,out/(name+'.log'),limit,os.environ.copy(),started):raise RuntimeError(name+' failed')
    try:
        assembly=out/'data.S'
        assembly.write_text('.section .rodata\n'+''.join(
            '.balign 8\n.global '+symbol+'\n'+symbol+':\n'+''.join('.word 0x'+row[key]+'\n' for row in calls)
            for symbol,key in (('exp_inputs','input_bits'),('newlib_outputs','output_bits')))+
            '.section .note.GNU-stack,"",@progbits\n')
        compiler=Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-gcc')
        archives=[Path(subprocess.check_output([str(compiler),'-print-file-name='+name],text=True).strip()).resolve(strict=True)
                  for name in ('libm.a','libc.a','libgcc.a','libgcc_eh.a')]
        run([compiler,'-std=c11','-O3','-march=rv64gc','-mabi=lp64d','-static','-fno-builtin',
             '-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror',HERE/'replay.c',assembly,
             '-Wl,-Map='+str(out/'link.map'),'-lm','-o',out/'test'],'compile')
        if 'libm.a(e_expf.o)' not in (out/'link.map').read_text():raise ValueError('Actual Linux expf object not linked')
        qemu=json.loads((ROOT/'verification/out/m4-state-replay-20261027-01/qemu.command.json').read_text())
        init=ROOT/'verification/out/q8k-decode-layout-full-20261026-01/init'
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        recipe=out/'initramfs.list'
        recipe.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
                          f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as stream:subprocess.run([str(cpio),str(recipe)],stdout=stream,check=True,timeout=60)
        pins.update(hashes([pairs_path,pairs_path.parent/'result.json',Path(__file__),HERE/'replay.c',HERE/'check.py',
                            assembly,out/'test',recipe,out/'initramfs.cpio',compiler,*archives,init,cpio,
                            Path(qemu[0]),Path(qemu[qemu.index('-bios')+1]),Path(qemu[qemu.index('-kernel')+1])]))
        atomic_json(out/'source-pins.json',pins)
        qemu[qemu.index('-initrd')+1]=str(out/'initramfs.cpio')
        run(qemu,'qemu',600)
        measured=checker.check((out/'qemu.log').read_text(),calls)
        if hashes(map(Path,pins))!=pins:raise ValueError('Input drift')
        atomic_json(out/'comparison.json',measured)
        state.update(state='PASS',summary={k:v for k,v in measured.items() if k!='rows'},
                     log_sha256=digest(out/'qemu.log'),comparison_sha256=digest(out/'comparison.json'))
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
