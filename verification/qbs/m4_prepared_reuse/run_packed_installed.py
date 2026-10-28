#!/usr/bin/env python3
"""Packed/cache acceptance using normal libraries, without object overrides."""
import argparse
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
from run_candidate_runtime import check_model


def select_packed(text):
    lines = text.splitlines(True)
    selected = [i for i, line in enumerate(lines) if 'env("GGML_RISCV_QBS_M4_CACHE",' in line]
    if len(selected) != 1 or 'GGML_RISCV_QBS_M4_PACKED' in text:
        raise ValueError('Packed driver selector drift')
    i = selected[0]
    lines.insert(i + 1, lines[i].replace('GGML_RISCV_QBS_M4_CACHE', 'GGML_RISCV_QBS_M4_PACKED'))
    return ''.join(lines)


def check_selected(text, stage):
    prefix = 'M4_RUNTIME_GRAPH_MODE mode=' if stage == 'graph' else 'Q8K_MODEL_BEGIN enabled='
    mode = None
    counts = {0: 0, 1: 0}
    for line in text.splitlines():
        if line.startswith(prefix):
            mode = int(line[len(prefix):])
        elif line.startswith('GGML_RISCV_QBS_M4_SELECTED '):
            fields = dict(item.split('=', 1) for item in line.split()[1:])
            if mode not in counts or int(fields['tag']) != mode + 1:
                raise ValueError('Unexpected packed producer identity')
            if fields.get('path') == 'rvv' or fields.get('event') == 'compute_rvv':
                counts[mode] += 1
    if not all(counts.values()):
        raise ValueError('Both producers must actually execute; cache hits alone do not qualify')
    return counts


def check_schema(text,stage):
    active=None;summaries={};records={0:0,1:0}
    prefix='M4_RUNTIME_GRAPH_MODE mode=' if stage=='graph' else 'Q8K_MODEL_BEGIN enabled='
    for line in text.splitlines():
        if line.startswith(prefix):active=int(line[len(prefix):])
        elif line.startswith('GGML_RISCV_QBS_LIFETIME_SUMMARY'):
            if active not in records or active in summaries:raise ValueError('Summary scope/count')
            fields=dict(word.split('=',1) for word in line.split()[1:])
            expected='prepared_buffer_invocations' if active else 'quantizations'
            other='quantizations' if active else 'prepared_buffer_invocations'
            if expected not in fields or other in fields or int(fields[expected])<=0:raise ValueError('Ambiguous preparation counter')
            if line.split()[0]!=('GGML_RISCV_QBS_LIFETIME_SUMMARY_V2' if active else 'GGML_RISCV_QBS_LIFETIME_SUMMARY'):
                raise ValueError('Schema version')
            summaries[active]=fields
        elif line.startswith('GGML_RISCV_QBS_LIFETIME '):
            if active not in records:raise ValueError('Record scope')
            fields=dict(word.split('=',1) for word in line.split()[1:])
            expected='preparation_time_valid' if active else 'quantize_time_valid'
            other='quantize_time_valid' if active else 'preparation_time_valid'
            if expected not in fields or other in fields:raise ValueError('Ambiguous timing field')
            records[active]+=1
    if set(summaries)!={0,1} or not all(records.values()):raise ValueError('Missing summary/records')
    for mode,summary in summaries.items():
        name='prepared_buffer_invocations' if mode else 'quantizations'
        if int(summary[name])!=records[mode]:raise ValueError('Logical count does not reconcile')
    return dict(summary_schema_off=1,summary_schema_on=2,logical_records=records)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime-build',type=Path,required=True)
    p.add_argument('--stage',choices=('graph','model'),required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();runtime=a.runtime_build.resolve(strict=True)
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    report=json.loads((runtime/'result.json').read_text());pins=json.loads((runtime/'manifest.json').read_text())
    if report['state']!='PASS' or hashes(map(Path,pins))!=pins:raise ValueError('Normal build drift')
    libs=report['libraries']
    if len(libs)!=4 or set(Path(x).name for x in libs)!={'libllama.a','libggml.a','libggml-cpu.a','libggml-base.a'}:
        raise ValueError('Expected only four normal libraries')
    reference=ROOT/('verification/out/m4-vector-runtime-'+a.stage+'-20261027-01')
    oldpins=json.loads((reference/'manifest.json').read_text())
    if json.loads((reference/'result.json').read_text())['state']!='PASS':raise ValueError('Missing private reference')
    source=reference/'test.cpp'
    if oldpins.get(str(source))!=digest(source):raise ValueError('Frozen driver drift')
    argv=json.loads((reference/'qemu.command.json').read_text())
    used=[source,Path(argv[0]),Path(argv[argv.index('-bios')+1]),Path(argv[argv.index('-kernel')+1])]
    recipe=reference/'initramfs.list';entries=[shlex.split(l) for l in recipe.read_text().splitlines() if l.strip()]
    if oldpins.get(str(recipe))!=digest(recipe):raise ValueError('Init recipe drift')
    used.extend(Path(row[2]) for row in entries if row[:2]==['file','/init'])
    if a.stage=='model':used.append(Path(argv[argv.index('-drive')+1].split(',')[0].removeprefix('file=')))
    for path in used:
        if oldpins.get(str(path))!=digest(path):raise ValueError('Actual reference input drift: '+str(path))
    # Old source/object pins are not carried forward: none of those objects are linked.
    pins.update(hashes([*used,recipe,Path(__file__),HERE/'run_runtime_graph.py',
                       HERE/'run_candidate_runtime.py',HERE/'audit_model_preparations.py',runtime/'result.json']))
    if a.stage=='model':pins.update(hashes(ROOT/'verification/qbs/combined_zvfh_m4/model'/n for n in ('native_audit.py','check.py')))
    out.mkdir(parents=True,exist_ok=False);state=dict(state='PREPARING',stage=a.stage,pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,label,limit):
        cmd=list(map(str,cmd));state.update(state=label.upper(),child_pid=None);save();atomic_json(out/(label+'.command.json'),cmd)
        if run_command(cmd,out/(label+'.log'),limit,os.environ.copy(),started):raise RuntimeError(label+' failed')
    try:
        objects=[];compiler=None
        sources=[('test',source)]
        if a.stage=='graph':sources.append(('data',reference/'data.S'))
        for name,path in sources:
            if oldpins.get(str(path))!=digest(path):raise ValueError('Driver/data drift')
            target=out/('test.cpp' if name=='test' else 'data.S');text=path.read_text()
            if name == 'test':
                text = select_packed(text)
            if a.stage=='graph' and name=='test':
                marker='    env("GGML_RISCV_QBS_TRACE_M4_PREPARE","1");'
                if text.count(marker)!=1:raise ValueError('Graph trace selector drift')
                text=text.replace(marker,marker+'\n    env("GGML_RISCV_QBS_TRACE_LIFETIME","1");',1)
            target.write_text(text)
            cmd=json.loads((reference/('compile-'+name+'.command.json')).read_text());compiler=cmd[0]
            obj=out/(name+'.o');cmd[cmd.index('-c')+1]=str(target);cmd[cmd.index('-o')+1]=str(obj)
            run(cmd,'compile-'+name,180);objects.append(obj);pins.update(hashes([target]))
        # Deliberately no candidate.o, wrappers or old quantizer overrides.
        run([compiler,'-static',*objects,*libs,'-ldl','-lm','-pthread','-Wl,-Map='+str(out/'link.map'),'-o',out/'test'],'link',180)
        for row in entries:
            if row[:2]==['file','/test']:row[2]=str(out/'test')
        listing=out/'initramfs.list';listing.write_text(''.join(' '.join(row)+'\n' for row in entries))
        cpio=Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        with (out/'initramfs.cpio').open('xb') as f:subprocess.run([str(cpio),str(listing)],stdout=f,check=True,timeout=60)
        pins.update(hashes([*objects,out/'test',listing,out/'initramfs.cpio',cpio]));atomic_json(out/'manifest.json',pins)
        argv[argv.index('-initrd')+1]=str(out/'initramfs.cpio');run(argv,'qemu',600 if a.stage=='graph' else 7200)
        text=(out/'qemu.log').read_text();measured=check_graph(text) if a.stage=='graph' else check_model(text)
        measured['scope']='Normal installed libraries: output/state/activity acceptance, no object overrides or hardware timing'
        measured['preparation_schema']=check_schema(text,a.stage)
        measured['executed_producers']=check_selected(text,a.stage)
        if hashes(map(Path,pins))!=pins:raise ValueError('Execution drift')
        state.update(state='PASS',measured=measured,normal_libraries=libs,object_overrides=False,
                     performance_measured=False,log_sha256=digest(out/'qemu.log'))
    except BaseException as exc:state.update(state='FAIL',error=repr(exc));raise
    finally:state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
