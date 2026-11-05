#!/usr/bin/env python3
"""Old/new shared-FMA SoC pairs; only scoped tag compaction may differ."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil
import subprocess
import time
import run_operand_ext as api
import run_shared_alu_soc as runner
from run_shared_fma_soc import parse

CHANGED=('hardware/src/lane/simd_fma_shared.sv','hardware/src/lane/simd_fpnew.sv',
         'hardware/src/lane/vmfpu.sv')
EXTRA=('vfrec7','vfrsqrt7','vmfeq','vmfne','vmflt','vmfle','vmfgt','vmfge')


def compare(b,c):
    for key in ('finish_time','hw_cycles','micro','lanes'):
        # Hierarchy is identical; each lane probe must match, not merely aggregate cycles.
        if b[key]!=c[key]: raise ValueError('Performance/activity/output drift: '+key)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    p.add_argument('--prior-soc',type=Path,required=True)
    p.add_argument('--component',type=Path,required=True)
    p.add_argument('--softfloat',type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve(); prior=a.prior_soc.resolve(); comp=a.component.resolve()
    out.mkdir(parents=True,exist_ok=False)
    status={'state':'PREPARING','completed_runs':0}
    def state(**kw):
        status.update(kw); api.save(out/'status.json',status); print(status,flush=True)
    try:
        state(); pins={}
        for d in (prior,comp,a.softfloat.resolve()):
            api.verify(d)
            verdict='report.json' if d==prior else 'status.json'
            if api.read(d/verdict)['state']!='PASS': raise ValueError('Prerequisite missing: '+str(d))
            pins.update(api.read(d/'source-pins.json'))
            pins[str(d/verdict)]=api.sha(d/verdict)
        for rel in CHANGED:
            f=comp/'src'/('vmfpu_integration.sv' if rel.endswith('vmfpu.sv') else Path(rel).name)
            if api.sha(api.ROOT/rel)!=api.sha(f): raise ValueError('Candidate identity differs: '+rel)
        if api.sha(a.softfloat/'src/simd_fma_shared.sv')!=api.sha(api.ROOT/CHANGED[0]):
            raise ValueError('Independent arithmetic identity differs')
        names=api.read(prior/'plan.json')['cases']+['rv64uv-ara-'+n for n in EXTRA]
        if len(names)!=len(set(names)): raise ValueError('Duplicate case')
        (out/'inputs').mkdir(); (out/'helpers').mkdir()
        for name in names:
            src=prior/'inputs'/name if (prior/'inputs'/name).exists() else api.ROOT/'apps/bin'/name
            if src.read_bytes()[:4]!=b'\x7fELF': raise ValueError('Not ELF: '+str(src))
            shutil.copy2(src,out/'inputs'/name)
        for f in ('run_shared_fma_tagpack_soc.py','run_shared_fma_soc.py',
                  'run_shared_alu_soc.py','run_operand_ext.py','shared_fma_soc_monitor.sv',
                  'shared_fma_tagpack_soc_monitor.sv'):
            shutil.copy2(api.HERE/f,out/'helpers'/f)
        shared=out/'shared'; (shared/'sim').mkdir(parents=True)
        source=shared/'source'
        shutil.copytree(prior/'shared/source',source,symlinks=True)
        for rel in CHANGED: shutil.copy2(api.ROOT/rel,source/rel)
        if "localparam bit EnableSharedFma = 1'b1;" not in (source/'hardware/include/ara_pkg.sv').read_text():
            raise ValueError('Shared FPU not selected')
        shutil.copy2(prior/'elfloader.o',out/'elfloader.o')
        raw=(prior/'shared/sources.f').read_text().replace(str(prior/'shared/source'),str(source))
        (shared/'sources.f').write_text(raw)
        command=[]
        for arg in api.read(prior/'shared/command.json')['command']:
            arg=arg.replace(str(prior/'shared/sources.f'),str(shared/'sources.f'))
            arg=arg.replace(str(prior/'elfloader.o'),str(out/'elfloader.o'))
            arg=arg.replace(str(prior/'helpers/shared_fma_soc_monitor.sv'),str(out/'helpers/shared_fma_soc_monitor.sv'))
            command.append(arg)
        command.append(str(out/'helpers/shared_fma_tagpack_soc_monitor.sv'))
        api.save(shared/'command.json',dict(command=command))
        api.save(out/'plan.json',dict(cases=names,workers=6,compact_tag=True,prior_soc=str(prior),
                 component=str(comp),softfloat=str(a.softfloat.resolve()),
                 baseline_image=str(prior/'shared/sim/simv'),scope='Shared full-tag vs shared compact-tag'))
        for f in out.rglob('*'):
            if f.is_file() and f.name!='status.json': pins[str(f)]=api.sha(f)
        api.save(out/'source-pins.json',pins); api.verify(out)
        state(state='BUILDING',total_runs=len(names)*2)
        rc=runner.execute(command,shared/'sim',shared/'build.log',7200)
        if rc or re.search(r'(?m)^(Error-|Error:|Fatal:)',(shared/'build.log').read_text(errors='replace')):
            raise ValueError('VCS build failed')
        image=shared/'sim/simv'; pins[str(image)]=api.sha(image)
        for f in (shared/'sim/simv.daidir').rglob('*'):
            if f.is_file(): pins[str(f)]=api.sha(f)
        api.save(out/'source-pins.json',pins)
        def run(task):
            variant,name=task; d=out/variant/'cases'/name; d.mkdir(parents=True)
            exe=prior/'shared/sim/simv' if variant=='baseline' else image
            cmd=[str(exe),'-no_save','-l','run.vcs.log',f'+PRELOAD={out}/inputs/{name}',
                 f'+TESTCASE={name}','+NO_FSDB','+ntb_random_seed=1']
            api.save(d/'command.json',dict(command=cmd,elf_sha256=api.sha(out/'inputs'/name)))
            start=time.monotonic(); rc=runner.execute(cmd,d,d/'console.log',10800 if name=='llama_q4km_micro' else 3600)
            row=dict(variant=variant,case=name,returncode=rc,wall_seconds=time.monotonic()-start)
            try:
                if rc: raise ValueError('Simulation exit '+str(rc))
                text=(d/'console.log').read_text(errors='replace')
                if variant=='shared':
                    tags=re.findall(r'^FMA_TAGPACK_CONFIG (\S+) external=(\d+) stored=(\d+)$',text,re.M)
                    if len(tags)!=4 or len({t[0] for t in tags})!=4 or any(int(x)-int(y)!=64 for _,x,y in tags):
                        raise ValueError('Missing four-lane tag compaction evidence')
                row.update(status='PASS',metrics=parse(text,name,1))
            except ValueError as exc: row.update(status='FAIL',reason=str(exc))
            api.save(d/'result.json',row); return row
        rows=[]; pairs=[]
        # Added consumers run first, so a broken NONCOMP tag cannot hide behind a long sweep.
        order=names[-len(EXTRA):]+names[:-len(EXTRA)]
        for offset in range(0,len(order),3):
            tasks=[(v,n) for n in order[offset:offset+3] for v in ('baseline','shared')]
            api.verify(out); state(state='RUNNING',active=tasks)
            with ThreadPoolExecutor(max_workers=6) as pool: batch=list(pool.map(run,tasks))
            rows+=batch; api.save(out/'results.json',rows); state(completed_runs=len(rows))
            if any(r['status']!='PASS' for r in batch): raise ValueError('Simulation failed; stop next batch')
            for name in order[offset:offset+3]:
                b,c=[next(r['metrics'] for r in batch if r['variant']==v and r['case']==name) for v in ('baseline','shared')]
                compare(b,c)
                pairs.append(dict(case=name,baseline_finish=b['finish_time'],shared_finish=c['finish_time'],
                    baseline_hw_cycles=b['hw_cycles'],shared_hw_cycles=c['hw_cycles'],
                    baseline_micro=b['micro'],shared_micro=c['micro']))
        api.verify(out)
        api.save(out/'report.json',dict(state='PASS',paired_cases=len(pairs),pairs=pairs,
                 performance='Exact cycle, lane activity and microkernel output comparison'))
        state(state='PASS',active=[])
    except Exception as exc:
        state(state='STOPPED',reason=str(exc)); raise


if __name__=='__main__': main()
