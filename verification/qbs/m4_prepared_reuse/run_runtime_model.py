#!/usr/bin/env python3
"""Full Qwen model cache OFF/ON, actual private repack object, no runtime edits."""
import argparse
from collections import Counter
import importlib.util
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


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    graph=ROOT/'verification/out/m4-runtime-graph-20261027-01'
    pins=json.loads((graph/'manifest.json').read_text())
    if json.loads((graph/'result.json').read_text())['state']!='PASS' or hashes(map(Path,pins))!=pins:
        raise ValueError('Actual graph gate missing/drifted')
    candidate=ROOT/'verification/out/m4-runtime-candidate-compile-20261027-01'
    runtime=ROOT/'verification/out/q8k-installed-runtime-build-20261026-01'
    base=ROOT/'verification/out/q8k-normal-runtime-model-20261026-01'
    archived=json.loads((base/'manifest.json').read_text())
    source=base/'test.cpp'
    if archived.get(str(source))!=digest(source):raise ValueError('Reviewed model test drift')
    cmd=json.loads((base/'qemu.command.json').read_text())
    drive=Path(cmd[cmd.index('-drive')+1].split(',')[0].removeprefix('file='))
    init=ROOT/'verification/out/q8k-signed-max-model-20261026-01/init'
    cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
    audit=ROOT/'verification/qbs/combined_zvfh_m4/model/native_audit.py'
    audit_checker=audit.with_name('check.py')
    pins.update(hashes([source,base/'test-compile.command.json',base/'qemu.command.json',
                       Path(__file__),drive,init,cpio,audit,audit_checker]))
    for item in (Path(cmd[0]),Path(cmd[cmd.index('-bios')+1]),Path(cmd[cmd.index('-kernel')+1])):
        if archived.get(str(item))!=digest(item):raise ValueError('Model machine drift')
        pins.update(hashes([item]))
    out.mkdir(parents=True,exist_ok=False)
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(argv,label,limit):
        argv=list(map(str,argv));state.update(state=label.upper(),child_pid=None);save()
        atomic_json(out/(label+'.command.json'),argv)
        if run_command(argv,out/(label+'.log'),limit,os.environ.copy(),started):raise RuntimeError(label+' failed')
    try:
        text=source.read_text()
        for before,after in (
            ('env("GGML_RISCV_QBS_CROSS_OP_CONTEXT", mode ? "1" : "0");','env("GGML_RISCV_QBS_CROSS_OP_CONTEXT", "1");'),
            ('env("GGML_QBS_COMBINED_TEST", mode ? "1" : "0");','env("GGML_RISCV_QBS_M4_CACHE", mode ? "1" : "0");')):
            if text.count(before)!=1:raise ValueError('Model mode selector drift')
            text=text.replace(before,after,1)
        target=out/'test.cpp';target.write_text(text)
        command=json.loads((base/'test-compile.command.json').read_text())
        command[command.index('-c')+1]=str(target);command[command.index('-o')+1]=str(out/'test.o')
        run(command,'compile',180)
        libs=json.loads((runtime/'result.json').read_text())['libraries']
        run([command[0],'-static',out/'test.o',candidate/'candidate.o',*libs,'-ldl','-lm','-pthread',
             '-Wl,-Map='+str(out/'link.map'),'-o',out/'test'],'link',180)
        listing=out/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /model 755 0 0\ndir /tmp 1777 0 0\n'+
                           f'file /init {init} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as f:
            subprocess.run([str(cpio),str(listing)],stdout=f,check=True,timeout=60)
        pins.update(hashes([target,out/'test.o',out/'test',listing,out/'initramfs.cpio']));atomic_json(out/'manifest.json',pins)
        cmd[cmd.index('-initrd')+1]=str(out/'initramfs.cpio');run(cmd,'qemu',7200)
        text=(out/'qemu.log').read_text();lines=text.splitlines()
        expected=[f'Q8K_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
                  for k in range(2) for s in range(3)]
        if [l for l in lines if l.startswith('Q8K_MODEL_COMPARE ')]!=expected or \
           lines.count('Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured')!=1 or \
           lines.count('GUEST_TEST_EXIT=0')!=1 or 'Q8K_MODEL_FAIL' in text:raise ValueError('Model comparison failed')
        # Load the native checker with its own sibling imports, not this folder's SoC checker.
        sys.path.insert(0,str(audit.parent))
        spec=importlib.util.spec_from_file_location('m4_model_native_audit',audit)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        work=module.native_accounting(text)
        mode=None;events=Counter()
        for line in lines:
            if line.startswith('Q8K_MODEL_BEGIN '):mode=int(line.split('enabled=')[1])
            elif line.startswith('GGML_RISCV_QBS_M4_CACHE '):
                if mode!=1:raise ValueError('Cache used in baseline')
                f=dict(re.findall(r'(\w+)=(\S+)',line))
                if f['event'] not in ('hit','compute_rvv','compute_generic') or int(f['epoch'])<=0:
                    raise ValueError('Invalid cache event')
                events[f['event']]+=1
        if events['hit']<=0 or events['compute_rvv']<=0 or events['compute_generic']:
            raise ValueError('Missing admitted real-model cache activity')
        if hashes(map(Path,pins))!=pins:raise ValueError('Execution drift')
        state.update(state='PASS',comparisons=6,logits_compared=911616,native_work=work,
                     cache_events=dict(events),performance_measured=False,runtime_modified=False,
                     log_sha256=digest(out/'qemu.log'))
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc));raise
    finally:
        state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
