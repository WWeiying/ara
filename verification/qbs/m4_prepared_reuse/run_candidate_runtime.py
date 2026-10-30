#!/usr/bin/env python3
"""Reusable graph/model acceptance for a pinned private repack candidate."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,digest,hashes
from run_tile_context_engine import run_command
from run_runtime_graph import check as check_graph
from audit_model_preparations import analyze as check_activity


def check_model(text):
    lines=text.splitlines()
    expected=[f'Q8K_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
              for k in range(2) for s in range(3)]
    if [l for l in lines if l.startswith('Q8K_MODEL_COMPARE ')]!=expected or \
       lines.count('Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured')!=1 or \
       lines.count('GUEST_TEST_EXIT=0')!=1 or 'Q8K_MODEL_FAIL' in text:raise ValueError('Model pairing incomplete')
    folder=ROOT/'verification/qbs/combined_zvfh_m4/model';sys.path.insert(0,str(folder))
    spec=importlib.util.spec_from_file_location('m4_candidate_native_audit',folder/'native_audit.py')
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    if Path(sys.modules['check'].__file__).resolve()!=folder/'check.py':raise ValueError('Wrong native checker import')
    work=native.native_accounting(text);activity=check_activity(text)
    old,new=activity['modes']['0'],activity['modes']['1']
    if old['executed_m4_computations']!=386 or new['executed_m4_computations']!=220 or new['cache_hits']!=166:
        raise ValueError('Changed preparation workload/selection in byte-only successor')
    return dict(comparisons=6,logits_compared=911616,native_work=work,preparation_activity=activity,
                scope='Private model byte/state/work equivalence, not hardware/model timing')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--stage',choices=('graph','model'),required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();candidate=a.candidate.resolve(strict=True)
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    previous=ROOT/('verification/out/m4-runtime-'+a.stage+'-20261027-01')
    pins={}
    for folder in (candidate,previous):
        data=json.loads((folder/'manifest.json').read_text())
        if hashes(map(Path,data))!=data:raise ValueError('Pinned gate drift: '+str(folder))
        pins.update(data);pins.update(hashes([folder/'manifest.json',folder/'result.json']))
    if json.loads((candidate/'result.json').read_text())['state']!='COMPILE_ONLY_PASS' or \
       json.loads((previous/'result.json').read_text())['state']!='PASS':raise ValueError('Missing acceptance prerequisites')
    runtime=ROOT/'verification/out/q8k-installed-runtime-build-20261026-01'
    libs=json.loads((runtime/'result.json').read_text())['libraries']
    if set(Path(x).name for x in libs)!={'libllama.a','libggml.a','libggml-cpu.a','libggml-base.a'}:
        raise ValueError('Unexpected library set')
    cpp=HERE/'runtime_graph.cpp' if a.stage=='graph' else previous/'test.cpp'
    helpers=[Path(__file__),HERE/'run_runtime_graph.py',HERE/'audit_model_preparations.py']
    if a.stage=='model':helpers.extend(ROOT/'verification/qbs/combined_zvfh_m4/model'/x for x in ('native_audit.py','check.py'))
    pins.update(hashes([cpp,*helpers]));out.mkdir(parents=True,exist_ok=False)
    state=dict(state='PREPARING',stage=a.stage,pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,label,limit):
        cmd=list(map(str,cmd));state.update(state=label.upper(),child_pid=None);save();atomic_json(out/(label+'.command.json'),cmd)
        if run_command(cmd,out/(label+'.log'),limit,os.environ.copy(),started):raise RuntimeError(label+' failed')
    try:
        sources=[('test',cpp)]
        if a.stage=='graph':sources.append(('data',previous/'data.S'))
        objects=[];compiler=None
        for name,source in sources:
            command_file=previous/(('compile-'+name if a.stage=='graph' else 'compile')+'.command.json')
            cmd=json.loads(command_file.read_text());compiler=cmd[0]
            target=out/('test.cpp' if name=='test' else 'data.S');target.write_bytes(source.read_bytes())
            obj=out/(name+'.o');cmd[cmd.index('-c')+1]=str(target);cmd[cmd.index('-o')+1]=str(obj)
            run(cmd,'compile-'+name,180);objects.append(obj);pins.update(hashes([target,command_file]))
        run([compiler,'-static',*objects,candidate/'candidate.o',*libs,'-ldl','-lm','-pthread',
             '-Wl,-Map='+str(out/'link.map'),'-o',out/'test'],'link',180)
        records=[shlex.split(l) for l in (previous/'initramfs.list').read_text().splitlines() if l.strip()]
        found=0
        for row in records:
            if row[:2]==['file','/test']:row[2]=str(out/'test');found+=1
        if found!=1 or any(any(c.isspace() for c in field) for row in records for field in row):
            raise ValueError('Initramfs recipe')
        listing=out/'initramfs.list';listing.write_text(''.join(' '.join(row)+'\n' for row in records))
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out/'initramfs.cpio').open('xb') as f:subprocess.run([str(cpio),str(listing)],stdout=f,check=True,timeout=60)
        pins.update(hashes([*objects,out/'test',listing,out/'initramfs.cpio',previous/'qemu.command.json',cpio]))
        atomic_json(out/'manifest.json',pins)
        cmd=json.loads((previous/'qemu.command.json').read_text());cmd[cmd.index('-initrd')+1]=str(out/'initramfs.cpio')
        run(cmd,'qemu',600 if a.stage=='graph' else 7200)
        text=(out/'qemu.log').read_text();measured=check_graph(text) if a.stage=='graph' else check_model(text)
        if hashes(map(Path,pins))!=pins:raise ValueError('Execution drift')
        state.update(state='PASS',measured=measured,performance_measured=False,runtime_modified=False,
                     log_sha256=digest(out/'qemu.log'))
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
