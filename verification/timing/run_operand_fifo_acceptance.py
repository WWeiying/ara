#!/usr/bin/env python3
"""Run local PPA first; only a useful candidate proceeds to 62-case SoC acceptance."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import run_shared_alu_soc as api
from run_shared_alu_shift_soc import parse

HERE=Path(__file__).resolve().parent
RTL=Path('hardware/src/lane/operand_queue.sv')


def read(p):
    return json.loads(p.read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    p.add_argument('--component',type=Path,required=True)
    p.add_argument('--accepted',type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve(); comp=a.component.resolve(); old=a.accepted.resolve()
    out.mkdir(parents=True,exist_ok=False)
    status={'state':'PREPARING','completed_cases':0}
    pins={}; inventories=set()
    def state(**kw):
        status.update(kw); api.save(out/'status.json',status); print(json.dumps(status),flush=True)
    def inherit(inv):
        inv=inv.resolve()
        if inv in inventories: return
        inventories.add(inv); pins[str(inv)]=api.sha(inv)
        for name,digest in read(inv).items():
            if api.sha(Path(name))!=digest: raise ValueError('Inherited input drift: '+name)
            if name in pins and pins[name]!=digest: raise ValueError('Conflicting pin: '+name)
            pins[name]=digest
            if Path(name).name=='source-pins.json': inherit(Path(name))
    def verify():
        for name,digest in pins.items():
            if api.sha(Path(name))!=digest: raise ValueError('Input drift: '+name)
    try:
        inherit(comp/'source-pins.json'); inherit(old/'source-pins.json')
        if read(comp/'test.status.json')['state']!='PASS' or read(old/'report.json')['state']!='PASS':
            raise ValueError('Functional prerequisite missing')
        if api.sha(comp/'baseline.sv')!=api.sha(old/'source'/RTL): raise ValueError('Different queue baseline')
        # Freeze acceptance helpers before lengthy DC; never read mutable helpers afterwards.
        helpers=out/'helpers'; helpers.mkdir()
        for name in ('run_operand_fifo_acceptance.py','run_operand_ext.py','operand_ext_soc_monitor.sv','run_shared_alu_soc.py',
                     'run_shared_alu_shift_soc.py','run_shared_alu.py','finish_shared_alu_soc.py'):
            shutil.copy2(HERE/name,helpers/name)
        for f in helpers.iterdir(): pins[str(f)]=api.sha(f)
        api.save(out/'source-pins.json',pins)
        state(state='LOCAL_PPA')
        with (out/'ppa-worker.log').open('w') as log:
            rc=subprocess.run([sys.executable,str(helpers/'run_operand_ext.py'),str(comp),'--worker','ppa'],
                stdout=log,stderr=subprocess.STDOUT).returncode
        if rc: raise ValueError('Local PPA worker failed')
        report=read(comp/'ppa/report.json'); b=report['metrics']['baseline']; c=report['metrics']['candidate']
        api.save(out/'ppa-measurement.json',report)
        inherit(comp/'ppa/source-pins.json')
        for name,digest in read(comp/'ppa/library-pins.json').items(): pins[name]=digest
        verify()
        if c['area_um2']>=b['area_um2'] or c['clk_i_slack_ns']<0 or c['clk_i_arrival_ns']>b['clk_i_arrival_ns']:
            state(state='STOPPED_PPA_REVIEW',reason='Require smaller area, nonnegative setup slack, no longer clk_i path arrival (including clock-gating checks)')
            return 0
        names=read(old/'plan.json')['cases']
        if len(names)!=read(old/'report.json')['cases']: raise ValueError('Case inventory mismatch')
        source=out/'source'; shutil.copytree(old/'source',source,symlinks=True)
        shutil.copy2(comp/'src/operand_queue.sv',source/RTL)
        shutil.copytree(old/'inputs',out/'inputs')
        baseline={}
        for name in names:
            path=old/'candidate/cases'/name
            log=path/'console.log'; row=read(path/'result.json'); command=read(path/'command.json')
            metrics=json.loads(json.dumps(parse(log.read_text(errors='replace'),name,observation_aware=True)))
            if row['status']!='PASS' or row['metrics']!=metrics: raise ValueError('Reference mismatch: '+name)
            if api.sha(out/'inputs'/name)!=command['elf_sha256']: raise ValueError('ELF mismatch: '+name)
            baseline[name]=metrics
            for f in (log,path/'result.json',path/'command.json'): pins[str(f)]=api.sha(f)
        for f in ('elfloader.o','reference.sv','shared_alu_shift_soc_monitor.sv','shared_alu_observation.sv','vrf_return_soc_monitor.sv'):
            shutil.copy2(old/f,out/f)
        shutil.copy2(comp/'src/reference.sv',out/'operand_queue_reference.sv')
        shutil.copy2(helpers/'operand_ext_soc_monitor.sv',out/'operand_ext_soc_monitor.sv')
        d=out/'candidate'; d.mkdir(); (d/'sim').mkdir()
        frozen=(old/'candidate/sources.f').read_text().replace(str(old/'source')+'/',str(source)+'/')
        for line in frozen.splitlines():
            if line.startswith('/') and (not line.startswith(str(source)+'/') or not Path(line).is_file()):
                raise ValueError('Unsealed source: '+line)
            if line.startswith('+incdir+'):
                for inc in line[8:].split('+'):
                    if not inc.startswith(str(source)+'/') or not Path(inc).is_dir(): raise ValueError('Unsealed include: '+inc)
        (d/'sources.f').write_text(frozen)
        cmd=[x.replace(str(old)+'/',str(out)+'/') for x in read(old/'candidate/command.json')['command']]
        cmd += [str(out/'operand_queue_reference.sv'),str(out/'operand_ext_soc_monitor.sv')]
        api.save(d/'command.json',{'command':cmd})
        api.save(out/'plan.json',dict(cases=names,workers=6,accepted=str(old),component=str(comp),
            scope='Only input FIFO payload reset removed; original conversion retained; reference monitors all live queues',
            baseline='62 previous checked runs reused with exact ELF/source/image pins'))
        for f in out.rglob('*'):
            if f.is_file() and f.name not in ('status.json','source-pins.json','ppa-worker.log'): pins[str(f)]=api.sha(f)
        api.save(out/'source-pins.json',pins); verify()
        state(state='BUILDING',total_cases=len(names))
        rc=api.execute(cmd,d/'sim',d/'build.log',7200); image=d/'sim/simv'
        if rc or not image.is_file() or re.search(r'(?m)^(Error-|Error:|Fatal:)',(d/'build.log').read_text(errors='replace')):
            raise ValueError('SoC build failed')
        pins[str(image)]=api.sha(image)
        for f in (image.parent/'simv.daidir').rglob('*'):
            if f.is_file(): pins[str(f)]=api.sha(f)
        api.save(out/'source-pins.json',pins)
        def run(name):
            case=d/'cases'/name; case.mkdir(parents=True)
            cmd=[str(image),'-no_save','-l','run.vcs.log',f'+PRELOAD={out/"inputs"/name}',f'+TESTCASE={name}',
                 '+NO_FSDB','+ntb_random_seed=1']
            api.save(case/'command.json',dict(command=cmd,elf_sha256=api.sha(out/'inputs'/name)))
            start=time.monotonic()
            rc=api.execute(cmd,case,case/'console.log',10800 if name in ('dotproduct','llama_q4km_micro') else 3600)
            row=dict(case=name,returncode=rc,wall_seconds=time.monotonic()-start)
            try:
                text=(case/'console.log').read_text(errors='replace')
                if rc or re.search(r'Fatal:|Error:|EXT_SOC_.*MISMATCH|VRF_SOC_.*MISMATCH',text): raise ValueError('Simulation failure')
                metrics=json.loads(json.dumps(parse(text,name,observation_aware=True)))
                checks=re.findall(r'^EXT_SOC_CHECKED (\S+) cycles=(\d+)',text,re.M)
                if len(checks)!=36 or len({x[0] for x in checks})!=36 or not sum(int(x[1]) for x in checks):
                    raise ValueError('Missing live queue monitor evidence')
                if metrics!=baseline[name]: raise ValueError('Result/cycle/activity mismatch')
                row.update(status='PASS',metrics=metrics,queue_checks=checks)
            except ValueError as exc: row.update(status='FAIL',reason=str(exc))
            api.save(case/'result.json',row); return row
        rows=[]
        for i in range(0,len(names),6):
            batch=names[i:i+6]; verify(); state(state='RUNNING',active_cases=batch)
            with ThreadPoolExecutor(max_workers=6) as pool: results=list(pool.map(run,batch))
            rows.extend(results); api.save(out/'results.json',rows); state(completed_cases=len(rows))
            if any(x['status']!='PASS' for x in results): state(state='STOPPED_ON_FAILURE'); return 1
        verify(); api.save(out/'report.json',dict(state='PASS',cases=len(rows),baseline_reused=True,
            exact_result_cycle_activity_equivalence=True,scope='Bounded SoC regression, not physical/FPGA signoff'))
        state(state='PASS',active_cases=[]); return 0
    except Exception as exc:
        state(state='ERROR',reason=str(exc)); raise


if __name__=='__main__':
    raise SystemExit(main())
