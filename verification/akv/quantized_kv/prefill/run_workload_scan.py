#!/usr/bin/env python3
"""Count actual C scheduler callbacks across shapes; no timing estimate."""
import argparse
import csv
import io
import json
from pathlib import Path
import subprocess
from run_replay import digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),HERE/'workload_scan.c',HERE/'prefix_schedule.h',
             ROOT/'software/akv/experimental/quantized_kv/online.h']
    pins={str(p):digest(p) for p in sources};outputs=[]
    for label,cc,flags in [('gcc','/usr/bin/gcc',[]),('ubsan','/usr/bin/clang',
                                          ['-fsanitize=undefined','-fno-sanitize-recover=undefined'])]:
        binary=out/label
        cmd=[cc,'-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math',*flags,
             '-I'+str(ROOT),'-I'+str(ROOT/'software/qbs/include'),HERE/'workload_scan.c','-lm','-o',binary]
        with (out/(label+'-compile.log')).open('w') as log:
            subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        run=subprocess.run([binary],capture_output=True,text=True,check=True,timeout=60)
        (out/(label+'.csv')).write_text(run.stdout);outputs.append(run.stdout)
    assert outputs[0]==outputs[1]
    rows=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(io.StringIO(outputs[0]))]
    assert len(rows)==160
    for r in rows:
        q,g,past=r['queries'],r['gqa'],r['past']
        assert r['base_v']==q*past+q*(q+1)//2
        expected=sum(past+min(q,(first+7)//g+1) for first in range(0,q*g,8))
        assert r['new_v']==expected
        assert r['base_key_rows']==r['base_v'] and r['new_key_rows']==r['new_v']
        if g==8:assert r['new_v']==r['base_v'] and r['new_commands']==r['base_commands']
    for p,h in pins.items():assert digest(Path(p))==h,p
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='PASS',cases=160,command_increase_cases=sum(r['new_commands']>r['base_commands'] for r in rows),
                no_value_reuse_cases=sum(r['new_v']==r['base_v'] for r in rows),
                performance_measured=False,scope='Actual scheduler callback counts with synthetic constant arithmetic')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
