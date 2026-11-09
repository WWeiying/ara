#!/usr/bin/env python3
"""Reconcile a returned board archive and derive bounded projection budgets."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

from audit import read, require, sha
from check_probe import check


def command_budget(rows, width):
    require(width in (32,64), 'Unsupported screening geometry')
    selected=[r for r in rows if r['op_name']=='MUL_MAT']
    require(selected and all(r['ne'][1:]==[1,1,1] for r in selected),
            'Budget applies only to single-row decode projections')
    return sum((r['ne'][0]+width-1)//width for r in selected)


def grouping(row):
    if row['op_name']!='MUL_MAT':
        return row['op_name']
    name=row['name']
    if name.startswith(('ffn_gate-','ffn_up-','ffn_out-')):
        return 'FFN_projection'
    if name=='result_output':
        return 'vocabulary_projection'
    return 'other_projection'


def review(root):
    receipt=read(root/'evidence_01/receipt.json')
    require(sha(root/'evidence_01/evidence.zip')==receipt['sha256'], 'Archive differs from receipt')
    previous=read(root/'analysis_01/summary.json')
    for p,digest in previous['pinned_checker']['evidence'].items():
        require(sha(p)==digest, 'Returned input changed: '+p)
    trials=root/'evidence_01/board/campaign_04/trials'
    checked=check([trials/name for name in ('plain_a','metadata','timed','plain_b')])
    phases=defaultdict(lambda:dict(probe_ns=0,unit_ns=0,unattributed_ns=0,groups=defaultdict(int)))
    budgets=[]
    for i in range(5):
        node=read(trials/'timed'/f'nodes_{i}.jsonl')
        phase=phases['prefill' if not i else 'decode']
        phase['probe_ns']+=node['phase_ns']
        phase['unit_ns']+=node['unit_ns']
        phase['unattributed_ns']+=node['unattributed_ns']
        member_map={(r['graph'],r['member']):r for r in node['records']}
        for r in node['records']:
            if r['elapsed_ns'] is not None:
                key=grouping(r)
                if r['op_name']!='MUL_MAT':
                    key='+'.join(member_map[r['graph'],j]['op_name']
                                 for j in range(r['first'],r['last']+1))
                phase['groups'][key]+=r['elapsed_ns']
        if i:
            budgets.append({str(w):command_budget(node['records'],w) for w in (32,64)})
    require(len(budgets)==4 and all(b==budgets[0] for b in budgets), 'Decode geometry changed')
    for phase in phases.values():
        require(sum(phase['groups'].values())==phase['unit_ns'], 'Grouping lost or double-counted time')
        phase['observed_fractions']={k:v/phase['probe_ns'] for k,v in phase['groups'].items()}
    # Mathematical count evidence, not a new ISA or measured candidate timing.
    candidate=budgets[0]
    baseline=checked['overhead']['decode_compute_ns']['plain_mean_ns']
    hz=previous['identity']['frequency_hz']
    required_cycles=.05*(baseline/1e9)*hz/(candidate['32']*4)
    require(math.isfinite(required_cycles) and required_cycles>0, 'Invalid cycle budget')
    return dict(state='BOARD_RETURN_RECONCILED_NOT_TIMING_ACCEPTED',
                measurement_accepted=False,checks=checked,observed_phases=dict(phases),
                model_identity=previous['identity'],
                decode_command_geometry=candidate,
                decode_five_percent_target_cycles_saved_per_original_command=required_cycles,
                scope='Observed short-context software-node intervals, not engine busy or long-context shares',
                no_new_hardware_or_board_run=True,
                evidence_pins={str(p):sha(p) for p in (
                    root/'evidence_01/receipt.json',root/'evidence_01/evidence.zip',
                    root/'analysis_01/summary.json')})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    sources={name:(Path(__file__).parent/name).read_bytes() for name in
             ('review_board_return.py','audit.py','check_probe.py')}
    result=review(args.campaign.resolve(strict=True))
    require(all((Path(__file__).parent/name).read_bytes()==raw for name,raw in sources.items()),
            'Analysis source changed during execution')
    args.output.mkdir(parents=True,exist_ok=False)
    for name,raw in sources.items():
        target=args.output/name
        target.write_bytes(raw)
        result['evidence_pins'][str(target.resolve())]=sha(target)
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('state','decode_command_geometry',
         'decode_five_percent_target_cycles_saved_per_original_command')},indent=2))


if __name__=='__main__':
    main()
