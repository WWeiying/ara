#!/usr/bin/env python3
"""Frozen paired SoC test of the optional FMA, six concurrent simulations max."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import run_shared_alu_soc as api

HERE=Path(__file__).resolve().parent
CHANGED=['hardware/include/ara_pkg.sv','hardware/src/lane/vmfpu.sv',
         'hardware/src/lane/simd_fpnew.sv','hardware/src/lane/simd_fma_shared.sv']
ISA='''vfadd vfmul vfmacc vfmadd vfmsac vfmsub vfnmacc vfnmadd vfnmsac vfnmsub
vfwadd vfwmul vfwmacc vfwmsac vfwnmacc vfwnmsac
vfredusum vfredosum vfwredusum vfwredosum vfdiv vfsqrt vfcvt vfncvt_int8
vfsgnj vfredmin vfredmax vadd vmul'''.split()
ROW=re.compile(r'^FMA_SOC_SUMMARY (\S+) shared=(\d+) cycles=(\d+) issued=(\d+) retired=(\d+) '
               r'blocked=(\d+) latency_wait=(\d+) fma=(\d+),(\d+),(\d+),(\d+)$',re.M)


def read(path): return json.loads(path.read_text())


def parse(text,name,shared):
    if 'Core Test *** SUCCESS ***' not in text or re.search(r'Fatal:|Error:|Error-|\bFAILED\b',text):
        raise ValueError('Missing EOC or test/assertion failure')
    if name.startswith('rv64uv-ara-'):
        stem=name.removeprefix('rv64uv-ara-')
        if not re.search(r'^PASSED: .*[/\\]'+re.escape(stem)+r'\.c!$',text,re.M):
            raise ValueError('Missing numerical ISA verdict')
    elif name=='fma_edges':
        timer=re.findall(r'\[hw-cycles\]:\s*(\d+)',text)
        if len(timer)!=1 or int(timer[0])<=0: raise ValueError('Missing directed-program timer')
    elif name=='llama_q4km_micro':
        names={'quantize_f32_to_q8_k_k1536','quantize_f32_to_q8_k_k8960',
               'q4_k_x_q8_k_dot_n1536_nrc1','q4_k_x_q8_k_dot_n8960_nrc1',
               'q6_k_x_q8_k_dot_n1536_nrc1','q6_k_x_q8_k_dot_n8960_nrc1'}
        found=re.findall(r'^MICRO (\S+) PASS cycles=(\d+)(.*)$',text,re.M)
        if len(found)!=6 or {x[0] for x in found}!=names or 'Q4_K_M micro verification: PASS (0/6 failed)' not in text:
            raise ValueError('Incomplete real-model microkernel checks')
    else: raise ValueError('Unspecified checker')
    rows=ROW.findall(text)
    if len(rows)!=4 or len({r[0] for r in rows})!=4 or any(int(r[1])!=shared for r in rows):
        raise ValueError('Missing four-lane configuration/probe evidence')
    if any(int(r[3])!=int(r[4]) for r in rows): raise ValueError('Unretired FPU transaction')
    if name not in ('rv64uv-ara-vadd','rv64uv-ara-vmul') and not sum(int(r[3]) for r in rows):
        raise ValueError('No floating-point requests')
    finish=re.findall(r'\$finish at simulation time\s+(\d+)',text)
    if len(finish)!=1: raise ValueError('Missing unique completion')
    return dict(lanes=rows,finish_time=int(finish[0]),
                hw_cycles=re.findall(r'\[hw-cycles\]:\s*(\d+)',text),
                micro=re.findall(r'^MICRO (\S+) PASS cycles=(\d+)(.*)$',text,re.M))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    p.add_argument('--accepted',type=Path,required=True)
    p.add_argument('--component',type=Path,required=True)
    p.add_argument('--tag-check',type=Path,required=True)
    p.add_argument('--edges',type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve(); old=a.accepted.resolve(); comp=a.component.resolve()
    out.mkdir(parents=True,exist_ok=False)
    status={'state':'PREPARING','completed_runs':0}
    def state(**kw):
        status.update(kw); api.save(out/'status.json',status); print(json.dumps(status),flush=True)
    pins={}
    def verify():
        for f,h in pins.items():
            if api.sha(Path(f))!=h: raise ValueError('Input drift: '+f)
    try:
        state()
        if read(old/'report.json')['state']!='PASS' or read(comp/'status.json')['state']!='PASS':
            raise ValueError('Acceptance prerequisite missing')
        tag_check=a.tag_check.resolve(); edges=a.edges.resolve()
        if read(tag_check/'report.json')['state']!='PASS': raise ValueError('Tag checker qualification missing')
        if read(edges/'manifest.json')['phases']!=144: raise ValueError('Directed matrix incomplete')
        for directory in (old,comp,tag_check,edges):
            for f,h in read(directory/'source-pins.json').items():
                if api.sha(Path(f))!=h: raise ValueError('Inherited input drift: '+f)
                pins[f]=h
            pins[str(directory/'source-pins.json')]=api.sha(directory/'source-pins.json')
            report=directory/('report.json' if directory in (old,tag_check) else
                              'manifest.json' if directory==edges else 'status.json')
            pins[str(report)]=api.sha(report)
        if api.sha(api.ROOT/CHANGED[-1])!=api.sha(comp/'src/simd_fma_shared.sv'):
            raise ValueError('Candidate differs from independent arithmetic check')
        if api.sha(api.ROOT/CHANGED[-1])!=api.sha(tag_check/'src/simd_fma_shared.sv'):
            raise ValueError('Candidate differs from qualified tag checker')
        for name in ('fpnew_pkg.sv','fpnew_classifier.sv','fpnew_rounding.sv',
                     'fpnew_fma.sv','fpnew_fma_multi.sv'):
            if api.sha(comp/'src'/name)!=api.sha(old/'source/hardware/deps/fpnew/src'/name):
                raise ValueError('SoC and independent reference use different fpnew: '+name)
        # Confirm the starting snapshot really has the accepted production FPU.
        for rel in CHANGED[:2]:
            prior=subprocess.check_output(['git','-C',str(api.ROOT),'show','b3228cfa7:'+rel])
            if (old/'source'/rel).read_bytes()!=prior: raise ValueError('Unmatched FPU baseline: '+rel)
        helpers=out/'helpers'; helpers.mkdir()
        for f in ('run_shared_fma_soc.py','run_shared_alu_soc.py','shared_fma_soc_monitor.sv'):
            shutil.copy2(HERE/f,helpers/f)
        inputs=out/'inputs'; inputs.mkdir()
        names=['rv64uv-ara-vfadd','fma_edges']+['rv64uv-ara-'+n for n in ISA if n!='vfadd']+['llama_q4km_micro']
        for name in names:
            elf=(old/'inputs'/name if name=='llama_q4km_micro' else edges/'fma_edges.elf' if name=='fma_edges'
                 else api.ROOT/'apps/bin'/name)
            if elf.read_bytes()[:4]!=b'\x7fELF': raise ValueError('Not ELF: '+str(elf))
            shutil.copy2(elf,inputs/name)
        shutil.copy2(old/'elfloader.o',out/'elfloader.o')
        builds={}
        for variant in ('baseline','shared'):
            d=out/variant; d.mkdir(); (d/'sim').mkdir()
            source=d/'source'; shutil.copytree(old/'source',source,symlinks=True)
            for rel in CHANGED: shutil.copy2(api.ROOT/rel,source/rel)
            pkg=source/CHANGED[0]
            if variant=='shared':
                text=pkg.read_text()
                if text.count("localparam bit EnableSharedFma = 1'b0;")!=1: raise ValueError('Configuration selector drift')
                pkg.write_text(text.replace("localparam bit EnableSharedFma = 1'b0;",
                                            "localparam bit EnableSharedFma = 1'b1;"))
            raw=(old/'candidate/sources.f').read_text().replace(str(old/'source')+'/',str(source)+'/')
            anchor=str(source/'hardware/src/lane/vmfpu.sv')
            if raw.count(anchor)!=1: raise ValueError('VMFPU source boundary missing')
            raw=raw.replace(anchor,'\n'.join(str(source/rel) for rel in CHANGED[2:])+ '\n'+anchor)
            (d/'sources.f').write_text(raw)
            for line in raw.splitlines():
                if line.startswith('/') and (not line.startswith(str(source)+'/') or not Path(line).is_file()):
                    raise ValueError('Unsealed source: '+line)
            command=[]
            for arg in read(old/'candidate/command.json')['command']:
                if arg.endswith('.sv'): continue  # Old optimization-specific monitors are not this checker.
                arg=arg.replace(str(old/'candidate/sources.f'),str(d/'sources.f'))
                arg=arg.replace(str(old/'elfloader.o'),str(out/'elfloader.o'))
                command.append(arg)
            command.append(str(helpers/'shared_fma_soc_monitor.sv'))
            api.save(d/'command.json',{'command':command})
            builds[variant]=command
        api.save(out/'plan.json',dict(cases=names,workers=6,accepted=str(old),component=str(comp),
                 tag_check=str(tag_check),directed_edges=str(edges),
                 scope='Paired optional ADDMUL integration; unchanged DIVSQRT/CONV/NONCOMP'))
        for f in out.rglob('*'):
            if f.is_file() and f.name!='status.json': pins[str(f)]=api.sha(f)
        api.save(out/'source-pins.json',pins); verify(); state(state='BUILDING',total_runs=2*len(names))
        def build(v):
            d=out/v
            rc=api.execute(builds[v],d/'sim',d/'build.log',7200)
            if rc or not (d/'sim/simv').is_file() or re.search(r'(?m)^(Error-|Error:|Fatal:)',(d/'build.log').read_text(errors='replace')):
                raise ValueError('VCS build failed: '+v)
        with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(build,builds))
        for v in builds:
            image=out/v/'sim/simv'; pins[str(image)]=api.sha(image)
            for f in image.with_name('simv.daidir').rglob('*'):
                if f.is_file(): pins[str(f)]=api.sha(f)
        api.save(out/'source-pins.json',pins)
        def run(task):
            variant,name=task; d=out/variant/'cases'/name; d.mkdir(parents=True)
            cmd=[str(out/variant/'sim/simv'),'-no_save','-l','run.vcs.log',
                 f'+PRELOAD={inputs/name}',f'+TESTCASE={name}','+NO_FSDB','+ntb_random_seed=1']
            api.save(d/'command.json',dict(command=cmd,elf_sha256=api.sha(inputs/name)))
            start=time.monotonic(); rc=api.execute(cmd,d,d/'console.log',10800 if name=='llama_q4km_micro' else 3600)
            row=dict(variant=variant,case=name,returncode=rc,wall_seconds=time.monotonic()-start)
            try:
                if rc: raise ValueError('Simulation exit '+str(rc))
                row.update(status='PASS',metrics=parse((d/'console.log').read_text(errors='replace'),name,int(variant=='shared')))
            except ValueError as exc: row.update(status='FAIL',reason=str(exc))
            api.save(d/'result.json',row); return row
        rows=[]
        for offset in range(0,len(names),3):
            tasks=[(v,n) for n in names[offset:offset+3] for v in builds]
            verify(); state(state='RUNNING',active=tasks)
            with ThreadPoolExecutor(max_workers=6) as pool: rows.extend(pool.map(run,tasks))
            api.save(out/'results.json',rows); state(completed_runs=len(rows))
            if any(r['status']!='PASS' for r in rows): state(state='STOPPED_ON_FAILURE'); return 1
        verify()
        pairs=[]
        for name in names:
            b,c=[next(r for r in rows if r['case']==name and r['variant']==v) for v in builds]
            pairs.append(dict(case=name,baseline_finish=b['metrics']['finish_time'],
                              shared_finish=c['metrics']['finish_time'],
                              completion_ratio=c['metrics']['finish_time']/b['metrics']['finish_time'],
                              baseline_hw_cycles=b['metrics']['hw_cycles'],shared_hw_cycles=c['metrics']['hw_cycles'],
                              baseline_micro=b['metrics']['micro'],shared_micro=c['metrics']['micro']))
        api.save(out/'report.json',dict(state='PASS',paired_cases=len(names),pairs=pairs,
                 scope='Functional integration PASS; measured performance is not automatic adoption'))
        state(state='PASS',active=[])
        return 0
    except Exception as exc: state(state='ERROR',reason=str(exc)); raise


if __name__=='__main__': raise SystemExit(main())
