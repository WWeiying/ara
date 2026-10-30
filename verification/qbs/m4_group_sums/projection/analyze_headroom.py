#!/usr/bin/env python3
"""Reconcile latest accepted projection counters without another RTL simulation."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'verification/qbs/m4_prepared_reuse'))
from analyze_pipeline import analyze,digest,RTL


def normalized(text,rows):
    converted=[]
    trials=[]
    for row in rows:
        trial=dict(row)
        candidate=trial.pop('candidate')
        trial['reuse']=candidate
        trials.append(trial)
    for line in text.splitlines():
        if line.startswith('M4_SUMS_QKV_TRIAL '):
            line=line.replace('M4_SUMS_QKV_TRIAL ','M4_QKV_TRIAL ',1).replace(' candidate=',' reuse=',1)
        elif line.startswith('M4_SUMS_QKV_RESULT '):
            line=line.replace('M4_SUMS_QKV_RESULT ','M4_QKV_RESULT ',1)
        converted.append(line)
    # The legacy analyzer uses reuse only to identify ABBA slots. Both actual
    # paths retain cache reuse; its activity counts are not cache statistics.
    return analyze('\n'.join(converted),trials)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run=args.run.resolve(strict=True);out=args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Fresh output required')
    receipt=json.loads((run/'result.json').read_text())
    pins_path=run/'source-pins.json';pins=json.loads(pins_path.read_text())
    log=run/'work/run.vcs.log';uvm=json.loads((run/'work/uvm_result.json').read_text())
    if (receipt.get('state')!='PASS' or receipt.get('post_pins_match') is not True or
        receipt.get('performance_measured') is not True or
        digest(pins_path)!=receipt['source_pins_sha256'] or
        uvm.get('status')!='PASS' or uvm.get('issues') or
        uvm['elf_sha256']!=receipt['elf_sha256'] or uvm['log_sha256']!=digest(log)):
        raise ValueError('Original evidence identity/status')
    build=Path(receipt['build']);b=json.loads((build/'build.json').read_text())
    if (b.get('group_sums_projection') is not True or b.get('reuse_both') is not True or
        digest(build/'qbs_current_projection_soc')!=receipt['elf_sha256']):
        raise ValueError('Wrong projection scope/image')
    for path in RTL:
        if pins.get(str(path))!=digest(path):raise ValueError('Measured RTL changed: '+str(path))
    spec=importlib.util.spec_from_file_location('latest_projection_check',HERE/'check.py')
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    measured=checker.check_output(log.read_text())
    measured['traffic']=checker.check_trace(run/'work/vector_trace.csv')
    if measured!=receipt['measured']:raise ValueError('Original checker replay disagrees')
    result=normalized(log.read_text(),measured['trials'])
    result.update(state='ANALYSIS_COMPLETE',new_simulations=0,current_counter_rtl_matches=True,
        measured_run=str(run),both_paths_reuse=True,
        current_all_software_pins_revalidated=False,
        software_identity_note='Original worker sealed inputs; later reviewed llama.cpp integration changed software. This analysis rechecks raw evidence, ELF and counter RTL, not current software equivalence.',
        source_pins={str(p):digest(p) for p in (Path(__file__),HERE/'check.py',
            ROOT/'verification/qbs/m4_prepared_reuse/analyze_pipeline.py',
            run/'result.json',pins_path,log,run/'work/uvm_result.json',*RTL)})
    out.mkdir(parents=True)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['optimized_pair'],indent=2))


if __name__=='__main__':main()
