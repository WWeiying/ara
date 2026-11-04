#!/usr/bin/env python3
"""Read-only final audit, including the actual DOTP output format."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import finish_shared_alu_soc as completion


def main():
    p=argparse.ArgumentParser(); p.add_argument('campaign',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args(); c=a.campaign.resolve(); o=a.output.resolve();o.mkdir(exist_ok=False)
    read=lambda p:json.loads(p.read_text())
    old=Path(read(c/'status.json')['previous'])
    spec=importlib.util.spec_from_file_location('sealed',old/'run_shared_alu_soc.py')
    api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
    try:
        for f,h in read(c/'source-pins.json').items():
            if api.sha(Path(f))!=h:raise ValueError('Input drift: '+f)
        rows=read(c/'results.json');names=read(old/'plan.json')['cases']
        if len(rows)!=2*len(names):raise ValueError('Incomplete simulation set')
        pins={}; pairs=[];applications={}
        for name in names:
            group=[r for r in rows if r['case']==name]
            if len(group)!=2 or {r['variant'] for r in group}!={'baseline','shared'}:
                raise ValueError('Incomplete pair: '+name)
            parsed=[]
            for r in sorted(group,key=lambda r:r['variant']):
                d=Path(r['evidence']);log=d/'console.log';cmd=d/'command.json'
                pins[str(log)]=api.sha(log);pins[str(cmd)]=api.sha(cmd)
                command=read(cmd);elf=Path(next(x.split('=',1)[1] for x in command['command'] if x.startswith('+PRELOAD=')))
                if command['elf_sha256']!=api.sha(elf):raise ValueError('ELF drift')
                rc=r.get('returncode',read(d/'result.json').get('returncode'))
                if rc!=0:raise ValueError('Nonzero exit: '+name)
                text=log.read_text(errors='replace')
                if name=='dotproduct':
                    result=api.parse(text,'dotproduct_format_audit')
                    regions=re.findall(r'Calulating (\d+)b dotp with vectors with length = (\d+)\s+Vector runtime: (\d+)\s+Scalar runtime: (\d+)',text)
                    expected={(str(s),str(n)) for s in (8,16,32,64) for n in (8,64)}|{('8','512')}
                    if len(regions)!=9 or {(s,n) for s,n,_,_ in regions}!=expected or 'SUCCESS.' not in text or any(int(v)<=0 or int(sc)<=0 for _,_,v,sc in regions):
                        raise ValueError('Incomplete checked DOTP regions')
                    result['dotproduct_regions']=regions
                else:result=completion.classify(api,text,name)
                parsed.append(result)
            if parsed[0]!=parsed[1]:raise ValueError('Result/cycle/activity difference: '+name)
            pairs.append(dict(case=name,status='PASS',role='collateral_non_ALU' if name in completion.COLLATERAL else 'ALU_active'))
            if name in ('mixed','vvaddint32','dotproduct','llama_q4km_micro'):applications[name]=parsed[0]
        api.save(o/'source-pins.json',pins)
        api.save(o/'pairs.json',pairs)
        api.save(o/'application_results.json',applications)
        api.save(o/'report.json',dict(state='PASS',functional_status='PASS',performance_status='PASS',
            paired_cases=len(pairs),alu_active_pairs=len(pairs)-len(completion.COLLATERAL),
            collateral_pairs=len(completion.COLLATERAL),exact_result_cycle_activity_equivalence=True,
            substitution=read(c/'substitution.json'),evidence=str(c),
            correction='DOTP requires its nine labeled Vector runtime / Scalar runtime regions, not The execution took.',
            scope='Bounded full-SoC shared ALU acceptance, not physical or FPGA signoff'))
        print((o/'report.json').read_text())
    except Exception as exc:
        api.save(o/'failure.json',dict(reason=str(exc)));raise


if __name__=='__main__':main()
