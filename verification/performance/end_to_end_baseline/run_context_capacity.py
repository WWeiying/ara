#!/usr/bin/env python3
"""Pinned host planner study; deliberately not a hardware performance test."""
import argparse
import csv
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess

from audit import digest,require,verify_pins

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[HERE/'context_capacity_study.c',ROOT/'software/qbs/src/qbs_runtime.c',
             ROOT/'software/qbs/src/qbs_format.c']
    base=['/usr/bin/cc','-O2','-std=c11','-Wall','-Wextra','-Werror',
          '-I'+str(ROOT/'software/qbs/include')]
    pins={str(Path(__file__).resolve()):digest(__file__),str(HERE/'audit.py'):digest(HERE/'audit.py')}
    commands=[]
    def pin(path):
        path=Path(path).resolve(strict=True);sha=digest(path)
        require(str(path) not in pins or pins[str(path)]==sha,'Input drift')
        pins[str(path)]=sha
    def run(argv,name):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(name=name,argv=argv))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        r=subprocess.run(argv,capture_output=True,timeout=120,cwd=out)
        (out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
        require(r.returncode==0,name+' failed');return r.stdout.decode()
    for name in ('cc1','as','ld'):
        program=run([base[0],'-print-prog-name='+name],'locate-'+name).strip()
        resolved=program if Path(program).is_absolute() else shutil.which(program)
        require(resolved is not None,'Tool unavailable: '+program);pin(resolved)
    for i,source in enumerate(sources):
        deps=run([*base,'-M','-MT','object',source],f'deps-{i}')
        for dep in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):pin(dep)
    run([*base,*sources,'-o',out/'study'],'compile');pin(out/'study')
    text=run([out/'study'],'study')
    rows=list(csv.DictReader(io.StringIO(text)))
    require(len(rows)==864,'Matrix incomplete')
    keys=[(r['profile'],r['m'],r['n'],r['k'],r['capacity_bytes'],r['max_context_blocks']) for r in rows]
    require(len(set(keys))==len(rows),'Duplicate scenario')
    def row(profile,m,n,k,capacity,blocks):
        key=(profile,str(m),str(n),str(k),str(capacity),str(blocks))
        return rows[keys.index(key)]
    for capacity,eligible,traffic in ((4672,0,598016),(9344,1,9344)):
        r=row('Q4_K',4,2048,2048,capacity,32)
        require(int(r['context_eligible'])==eligible and int(r['context_activation_bytes'])==traffic,
                'Hand-derived Q4_K anchor differs')
    for blocks,eligible in ((32,0),(255,1)):
        require(int(row('Q8_0_WEIGHT',4,2048,2048,9344,blocks)['context_eligible'])==eligible,
                'Block-tag/capacity separation differs')
    verify_pins(pins)
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    summary=dict(state='PLANNER_WHAT_IF_PASS_NOT_RTL',scenarios=len(rows),
        hardware_changed=False,performance_measured=False,area_measured=False,
        current_eligibility=sum(int(r['context_eligible']) for r in rows if r['capacity_bytes']=='4672' and r['max_context_blocks']=='32'),
        hypothetical_eligibility={str(cap):sum(int(r['context_eligible']) for r in rows
            if r['capacity_bytes']==str(cap) and r['max_context_blocks']=='32') for cap in (4672,9344,18688,37376)},
        artifacts={str(out/name):digest(out/name) for name in ('study.stdout','commands.json','source-pins.json','study')},
        limitations=['255-block variants require new capability encoding and RTL changes',
                     'Logical payload is not DDR traffic, cycle saving or model coverage'])
    (out/'result.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
