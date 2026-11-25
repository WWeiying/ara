#!/usr/bin/env python3
"""Successor adapter: require activity02 private-FPU semantic handshake evidence."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import check as base
from contract import require, save

FIELDS = set('cycles native_requests native_fma_requests native_fma_elements qk_requests qk_elements pv_requests pv_elements native_blocked resident_blocked'.split())


def unit_activity(text, fixture):
    records = []
    for line in text.splitlines():
        if 'OPERATOR_UNIT' not in line: continue
        m = re.fullmatch(r'OPERATOR_UNIT (\S+) (.+)',line)
        require(m is not None, 'Malformed unit activity prefix')
        path, fields = m.groups()
        lane = re.search(r'gen_lanes\[([0-3])\]',path)
        require(lane is not None and path.endswith('i_operator_unit_activity'), 'Unknown unit activity owner')
        pairs = [part.split('=') for part in fields.split()]
        require(all(len(p) == 2 and re.fullmatch('[0-9]+',p[1]) for p in pairs) and
                len({p[0] for p in pairs}) == len(pairs) and {p[0] for p in pairs} == FIELDS,
                'Unit activity field schema')
        records.append((int(lane[1]),path,{k:int(v) for k,v in pairs}))
    require(len(records) == 4*len(fixture['order']), 'Require four private-FPU records per complete-call ROI')
    c, results, owners = fixture['case'], [], None
    for trial,mode in enumerate(fixture['order']):
        block = records[trial*4:(trial+1)*4]
        require({lane for lane,_,_ in block} == set(range(4)), 'Duplicate/missing ROI lane')
        paths = {path for _,path,_ in block}
        if owners is None: owners = paths
        require(paths == owners and len({r['cycles'] for _,_,r in block}) == 1, 'ROI owners/cycle interval drift')
        for lane,_,r in block:
            require(r['cycles'] > 0 and r['native_requests'] >= r['native_fma_requests'] and
                    r['native_fma_elements'] <= 4*r['native_fma_requests'] and
                    r['native_blocked'] <= r['cycles'] and r['resident_blocked'] <= r['cycles'],
                    'Unit handshake counter bounds')
            qk = c['dimension']*c['heads']*sum(max(0,(min(64,c['tokens']-start)+3-lane)//4)
                                             for start in range(0,c['tokens'],64)) if mode == 2 else 0
            pv = c['dimension']//4*c['heads']*c['tokens'] if mode == 2 else 0
            require(r['qk_elements'] == qk and r['pv_elements'] == pv, 'Private FPU accepted semantic FMA count')
            require((r['qk_requests'] == 0) == (qk == 0) and (r['pv_requests'] == 0) == (pv == 0) and
                    r['qk_elements'] <= 2*r['qk_requests'] and r['pv_elements'] <= 4*r['pv_requests'],
                    'Private request/semantic-mask inconsistency')
        sums = {k:sum(r[k] for _,_,r in block) for k in FIELDS if k != 'cycles'}
        work = c['heads']*c['tokens']*c['dimension'] if mode == 2 else 0
        require(sums['qk_elements'] == sums['pv_elements'] == work, 'Whole-call private FMA work mismatch')
        results.append(dict(trial=trial,mode=mode,monitor_cycles=block[0][2]['cycles'],
                            sums=sums,lanes={str(lane):r for lane,_,r in block}))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for name in ('build','log','vector','commit','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    try:
        result = base.check(args.build,args.log,args.vector,args.commit)
        m = base.receipt(args.build)
        result['metrics']['unit_activity'] = unit_activity(args.log.read_text(),m['fixture'])
        result['metrics']['private_fpu_semantic_work_checked'] = True
    except Exception as exc:
        result = dict(state='FAIL',error=str(exc),performance_acceptance=False)
    save(args.output,result)
    print(json.dumps({k:v for k,v in result.items() if k != 'metrics'}))
    return result['state'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
