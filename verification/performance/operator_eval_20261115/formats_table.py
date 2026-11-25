#!/usr/bin/env python3
"""Produce matched format tables from an independently checked collection."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ASSETS=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_formats_prepare_20261115_release_02/cases')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,fields,rows):
    with path.open('x') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collection',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        raise ValueError('Fresh table output required')
    summary=json.loads((a.collection/'summary.json').read_text())
    allowed=('CHECKED_CASE_SNAPSHOT_NOT_FINAL_BATCH','CHECKED_CASES_COLLECTED')
    if summary['state'] not in allowed:
        raise ValueError('Checked collection required')
    pins=json.loads((a.collection/'source-pins.json').read_text()); used={}
    def checked(path):
        path=Path(path); value=sha(path)
        if pins.get(str(path))!=value:
            raise ValueError('Collection-bound artifact changed/missing: '+str(path))
        used[str(path)]=value
        return value
    records=summary.get('checked_cases',summary.get('cases',[]))
    rows=[]; keys=set()
    for record in records:
        if record.get('state')!='PASS':
            continue
        run=Path(record['evidence']) if 'evidence' in record else Path(record['campaign'])/'runs'/record['id']
        checked(run/'result.json')
        result=json.loads((run/'result.json').read_text())
        if result['state']!='PASS' or not result['independent_protocol_checked']:
            raise ValueError('Unchecked result in collection')
        m=result['measured']['metrics']; build=ASSETS/record['id']
        checked(build/'build.json')
        identity=tuple(checked(build/f) for f in ('input_f32.bin','weights_row.bin','expected.bin'))
        for t in m['trials']:
            key=(m['format'],m['m'],m['n'],m['k'],m['backend'],t['trial'])
            if key in keys:
                raise ValueError('Duplicate format call')
            keys.add(key)
            rows.append(dict(format=m['format'],m=m['m'],n=m['n'],k=m['k'],backend=m['backend'],
                trial=t['trial'],label=t['label'],cycles=t['total_cycles'],
                **{k+'_cycles':v for k,v in t['software_cycles'].items()},
                baseline_kind=m['baseline_kind'],primary_eligible=m['primary_eligible'],
                input_sha256=identity[0],weights_sha256=identity[1],gold_sha256=identity[2]))
    pairs=[]
    for q in rows:
        if q['backend']!='native':
            continue
        matches=[v for v in rows if v['backend']=='rvv_x32' and
            all(v[k]==q[k] for k in ('format','m','n','k','trial','input_sha256','weights_sha256','gold_sha256'))]
        if len(matches)>1:
            raise ValueError('Ambiguous baseline')
        if matches:
            v=matches[0]
            pairs.append(dict(format=q['format'],m=q['m'],n=q['n'],k=q['k'],trial=q['trial'],
                rvv_cycles=v['cycles'],qbs_cycles=q['cycles'],full_call_speedup=v['cycles']/q['cycles'],
                rvv_execute_cycles=v['execute_cycles'],qbs_execute_cycles=q['execute_cycles'],
                execute_speedup=v['execute_cycles']/q['execute_cycles'],
                baseline_kind=v['baseline_kind'],primary_eligible=v['primary_eligible']))
    a.output.mkdir()
    write(a.output/'calls.csv',tuple(rows[0]) if rows else ('format',),rows)
    write(a.output/'paired.csv',tuple(pairs[0]) if pairs else ('format',),pairs)
    used[str(a.collection/'summary.json')]=sha(a.collection/'summary.json')
    used[str(a.collection/'source-pins.json')]=sha(a.collection/'source-pins.json')
    used[str(Path(__file__).resolve())]=sha(__file__)
    (a.output/'source-pins.json').write_text(json.dumps(used,indent=2)+'\n')
    (a.output/'summary.json').write_text(json.dumps(dict(state='MATCHED_FORMAT_TABLES',
        source_collection=str(a.collection),source_collection_state=summary['state'],
        checked_calls=len(rows),paired_calls=len(pairs),whole_model=False,
        provenance='Controlled two-stage requantization, not nine native models',
        averaging='None: first/repeat calls remain separate; unpaired cases have no speedup',
        baseline_policy='New x32 candidates remain separately identified and not primary eligible'),indent=2)+'\n')
    print(dict(calls=len(rows),paired=len(pairs)))


if __name__=='__main__':
    main()
