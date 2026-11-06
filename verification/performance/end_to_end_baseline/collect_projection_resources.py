#!/usr/bin/env python3
"""Recompute the completed resource campaign and save a compact audit receipt."""
import argparse
import json
from pathlib import Path

from audit import digest, require, verify_pins
from projection_resources import check


def collect(run):
    report = json.loads((run/'result.json').read_text())
    require(report['state'] == 'RTL_PORT_AUDIT_PASS', 'Resource worker incomplete')
    pins = run/'source-pins.json'
    require(digest(pins) == report['source_pins_sha256'], 'Worker pin map drift')
    checked = verify_pins(json.loads(pins.read_text()))
    for name, sha in report['artifacts'].items():
        path = Path(name).resolve(strict=True)
        require(path.is_relative_to(run) and digest(path) == sha, 'Artifact drift: '+name)
    summaries = []
    count = 0
    for record in report['results']:
        vector = Path(record['vector']).resolve(strict=True)
        require(vector.is_relative_to(run), 'External vector')
        log = run/('run-'+vector.stem+'.log')
        cases = check(log.read_text(),vector.read_text())
        require(cases == record['cases'], 'Recomputed resource result differs')
        count += len(cases)
        summaries.append(dict(vector=vector.name,cases=len(cases),
                              observations=cases if len(cases) == 1 else
                              [row for row in cases if row['geometry']['m'] == 4]))
    require([x['vector'] for x in summaries] == ['matrix.txt','real-m1.txt','real-m4.txt']
            and [x['cases'] for x in summaries] == [36,1,1], 'Expected matrix and real cases missing')
    return dict(state='RTL_PORT_COUNTS_REAUDITED',cases=count,checked_inputs=checked,
                run=str(run),run_result_sha256=digest(run/'result.json'),
                source_pins_sha256=digest(pins),
                collector_sha256=digest(__file__),observations=summaries,
                hardware_changed=False,model_performance_measured=False,
                limitations=report['limitations'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    result = collect(a.run.resolve(strict=True))
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('state','cases','checked_inputs')},indent=2))


if __name__ == '__main__':
    main()
