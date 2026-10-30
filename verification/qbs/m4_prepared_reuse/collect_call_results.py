#!/usr/bin/env python3
"""Summarize completed checked call receipts without extrapolating model speed."""
import argparse
import json
from pathlib import Path


def paired(trials,index,mode,cycles):
    if len(trials)!=4:raise ValueError('Need all four ABBA trials')
    for i,row in enumerate(trials):
        if row[index]!=i or row[mode]!=(0,1,1,0)[i]:raise ValueError('Invalid ABBA order')
        if type(row[cycles]) is not int or row[cycles]<=0:raise ValueError('Invalid cycle count')
    baseline=trials[0][cycles]+trials[3][cycles]
    candidate=trials[1][cycles]+trials[2][cycles]
    return dict(baseline_cycles=baseline,candidate_cycles=candidate,
                speedup=baseline/candidate,cycle_reduction=1-candidate/baseline,
                improved=candidate<baseline)


def summarize(report,kind):
    if report.get('state')!='PASS' or report.get('performance_measured') is not True or \
       report.get('post_pins_match') is not True or report.get('simulations_launched')!=1:
        raise ValueError('Not a completed checked RTL measurement')
    measured=report['measured']
    trials=measured['trials']
    if kind=='projection':
        if measured.get('performance_measured') is not True or measured.get('state')!='PASS' or \
           measured.get('traffic')!=dict(commands=256,result_bytes=131072):
            raise ValueError('Wrong/incomplete full projection work')
        if any(t.get('errors')!=0 for t in trials):raise ValueError('Projection numerical failure')
        result=paired(trials,'id','reuse','total')
        scope='Complete Q/V/K projection slice, excludes GGML scheduling/intervening operators'
    elif kind=='attention':
        if report.get('independent_protocol_checked') is not True or \
           measured.get('state')!='COMPACT_ABBA_AND_WORK_CHECKED' or \
           measured.get('on_target_full_numerical_checks') is not True or \
           measured.get('same_elf') is not True or len(measured.get('hardware_records',[]))!=32 or \
           any(t.get('commands')!=8 or t.get('values')!=128 for t in trials):
            raise ValueError('Wrong/incomplete Attention work')
        result=paired(trials,'trial','enabled','cycles')
        scope='Complete quantized-KV Decode Attention call for one H6/D128/T128 group'
    else:raise ValueError('Unknown measurement scope')
    result.update(kind=kind,scope=scope,whole_model=False)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--projection',type=Path,required=True,help='Completed run result.json')
    parser.add_argument('--attention',type=Path,required=True,help='Completed run result.json')
    args=parser.parse_args();rows=[]
    for kind in ('projection','attention'):
        path=getattr(args,kind).resolve(strict=True)
        report=json.loads(path.read_text());row=summarize(report,kind)
        row['receipt']=str(path);rows.append(row)
    print(json.dumps(dict(state='COMPLETED_RECEIPTS_SUMMARIZED',measurements=rows,
                          whole_model_speedup=None,combined_speedup=None,
                          verification='Consumes checked worker receipts; does not independently replay raw traces'),indent=2))


if __name__=='__main__':main()
