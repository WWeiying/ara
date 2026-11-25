#!/usr/bin/env python3
"""Snapshot finished checked cases without pretending the running batch is done."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from monitor_metrics import parse


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def verify(pins):
    for name,h in pins.items():
        if sha(name)!=h:
            raise ValueError('Snapshot identity drift: '+name)


def leaves(value,prefix=''):
    if isinstance(value,dict):
        for k,v in value.items():
            yield from leaves(v,prefix+'.'+k if prefix else k)
    elif isinstance(value,list):
        for k,v in enumerate(value):
            yield from leaves(v,prefix+'['+str(k)+']')
    else:
        yield prefix,value


def write_csv(path,fields,rows):
    with path.open('x') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        raise ValueError('Fresh snapshot directory required')
    pins=json.loads((a.campaign/'source-pins.json').read_text()); verify(pins)
    cases,rows,attention=[],[],[]
    for file in sorted((a.campaign/'runs').glob('*/result.json')):
        result=json.loads(file.read_text())
        if result['state']!='PASS':
            continue
        work=file.parent
        verify(result['checked_artifact_hashes'])
        measured=json.loads((work/'numerical.json').read_text())
        protocol=json.loads((work/'protocol.json').read_text())
        if measured!=result['measured'] or measured['state']!='PASS' or \
                not result['independent_protocol_checked'] or protocol['status']!='PASS' or protocol['issues'] or \
                protocol['log_sha256']!=sha(work/'run.vcs.log') or \
                protocol['vector_trace_sha256']!=sha(work/'vector.csv') or \
                any(protocol['contract_counts'][k] for k in ('exceptions','protocol_errors','outstanding')):
            raise ValueError('Incomplete or inconsistent accepted case '+result['id'])
        pins.update(result['checked_artifact_hashes']); pins[str(file)]=sha(file)
        metrics=measured['metrics']
        observations=parse(work)
        for log in work.glob('llm_perf_report_*.log'):
            pins[str(log)]=sha(log)
        for metric,value in leaves(dict(measured=metrics,monitor=observations)):
            rows.append(dict(case=result['id'],metric=metric,value=value))
        for trial in metrics.get('trials',[]):
            if 'rdcycle_total' in trial:
                attention.append(dict(case=result['id'],trial=trial['trial'],mode=trial['mode'],
                    cycles=trial['rdcycle_total'],final_drain_cycles=trial['final_drain_cycles']))
        cases.append(dict(id=result['id'],state='PASS',result_sha256=sha(file),
            evidence=str(work),wall_seconds=result['wall_seconds']))
    pins[str(Path(__file__).resolve())]=sha(__file__)
    pins[str(Path(__file__).with_name('monitor_metrics.py'))]=sha(Path(__file__).with_name('monitor_metrics.py'))
    verify(pins)
    a.output.mkdir()
    write_csv(a.output/'metrics_long.csv',('case','metric','value'),rows)
    write_csv(a.output/'attention_calls.csv',('case','trial','mode','cycles','final_drain_cycles'),attention)
    (a.output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result=dict(state='CHECKED_CASE_SNAPSHOT_NOT_FINAL_BATCH',campaign=str(a.campaign),
        checked_cases=cases,pass_count=len(cases),source_image_pins_match_at_snapshot=True,
        full_batch_completed=(a.campaign/'result.json').exists(),whole_model=False)
    (a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(state=result['state'],pass_count=len(cases))))


if __name__=='__main__':
    main()
