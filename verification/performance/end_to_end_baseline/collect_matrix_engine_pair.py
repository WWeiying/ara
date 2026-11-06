#!/usr/bin/env python3
"""Re-audit completed full-engine pairs, including context and memory schedules."""
import argparse
import json
from pathlib import Path

from audit import digest,require,verify_pins
from matrix_engine_pair import pair


def collect(run):
    report=json.loads((run/'result.json').read_text())
    require(report['state']=='MATRIX_DOT_FULL_ENGINE_PAIR_PASS','Full-engine worker incomplete')
    require(digest(run/'source-pins.json')==report['source_pins_sha256'],'Pin-map drift')
    checked=verify_pins(json.loads((run/'source-pins.json').read_text()))
    for name,sha in report['artifacts'].items():
        p=Path(name).resolve(strict=True)
        require(p.is_relative_to(run) and digest(p)==sha,'Artifact drift')
    results=[]
    wanted=[(name,gap) for name in ('matrix','real-m1','real-m4','contexts') for gap in (0,3)]
    require([(r['vector'],r['measured']['response_gap']) for r in report['results']]==wanted,
            'Incomplete vector/memory schedule matrix')
    for record,(name,gap) in zip(report['results'],wanted):
        contexts=12 if name=='contexts' else 1 if name=='matrix' else 0
        functional=name.startswith('real-')
        measured=pair(*[(run/f'run-{name}-gap{gap}-{mode}.log').read_text() for mode in (0,1)],
                      *[(run/f'{name}-{mode}.txt').read_text() for mode in ('base','wide')],
                      gap,contexts,functional)
        require(measured==record['measured'],'Raw result replay differs')
        results.append(record)
    direct=sum(len(r['measured']['direct']) for r in results)
    lifecycle=sum(len(r['measured']['contexts']) for r in results)
    require(direct==100 and lifecycle==26,'Wrong direct/lifecycle case counts')
    return dict(state='MATRIX_DOT_FULL_ENGINE_PAIR_REAUDITED',checked_inputs=checked,
                direct_cases_per_configuration=direct,context_checks_per_configuration=lifecycle,
                run=str(run),result_sha256=digest(run/'result.json'),
                pins_sha256=digest(run/'source-pins.json'),collector_sha256=digest(__file__),
                results=results,default_enabled=False,full_soc_tested=False,
                model_performance_measured=False,area_measured=False,limitations=report['limitations'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=collect(a.run.resolve(strict=True));a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('state','checked_inputs','direct_cases_per_configuration',
                                          'context_checks_per_configuration')},indent=2))


if __name__=='__main__':main()
