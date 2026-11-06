#!/usr/bin/env python3
"""Re-audit raw paired compute logs before changing the next integration stage."""
import argparse
import json
from pathlib import Path

from audit import digest,require,verify_pins
from matrix_dot_pair import pair


def collect(run):
    report=json.loads((run/'result.json').read_text())
    require(report['state']=='MATRIX_DOT_COMPONENT_PAIR_PASS','Incomplete pair')
    require(digest(run/'source-pins.json')==report['source_pins_sha256'],'Pin-map drift')
    checked=verify_pins(json.loads((run/'source-pins.json').read_text()))
    for path,sha in report['artifacts'].items():
        p=Path(path).resolve(strict=True)
        require(p.is_relative_to(run) and digest(p)==sha,'Artifact drift')
    results=[]
    require([r['vector'] for r in report['results']]==['matrix','real-m1','real-m4'],'Wrong vector set')
    for r in report['results']:
        name=r['vector']
        rows=pair(*[(run/f'run-{name}-{mode}.log').read_text() for mode in (0,1)],
                  *[(run/f'{name}-{mode}.txt').read_text() for mode in ('base','wide')])
        require(rows==r['cases'],'Recomputed pair differs')
        results.append(dict(vector=name,cases=[dict(
            geometry={k:v for k,v in row['shape'].items() if k!='counters'},
            baseline_busy=row['baseline']['busy'],candidate_busy=row['candidate']['busy'],
            baseline_dot=row['baseline']['dot'],candidate_dot=row['candidate']['dot'],
            candidate_result_blocked=row['candidate']['request_blocked'],
            ratio=row['compute_bench_ratio']) for row in rows]))
    require([len(x['cases']) for x in results]==[36,1,1],'Wrong case counts')
    return dict(state='MATRIX_DOT_COMPONENT_PAIR_REAUDITED',checked_inputs=checked,
                run=str(run),result_sha256=digest(run/'result.json'),
                pins_sha256=digest(run/'source-pins.json'),collector_sha256=digest(__file__),
                numerical_cases_per_configuration=38,results=results,
                default_enabled=False,full_soc_tested=False,model_performance_measured=False,
                area_measured=False,limitations=report['limitations'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=collect(a.run.resolve(strict=True));a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('state','checked_inputs','numerical_cases_per_configuration')},indent=2))


if __name__=='__main__':main()
