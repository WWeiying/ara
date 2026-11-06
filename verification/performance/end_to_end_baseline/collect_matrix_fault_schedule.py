#!/usr/bin/env python3
"""Audit original passing scopes and the explicit fault-stimulus successor."""
import argparse
import json
from pathlib import Path

from audit import digest,require,verify_pins
from matrix_engine_pair import check_mode,pair
from matrix_fault_schedule import late_fault_proof


def collect(run):
    report=json.loads((run/'result.json').read_text())
    require(report['state']=='FULL_ENGINE_PAIR_WITH_FAULT_SCHEDULE_PASS','Successor incomplete')
    require(digest(run/'source-pins.json')==report['source_pins_sha256'],'Pin-map drift')
    checked=verify_pins(json.loads((run/'source-pins.json').read_text()))
    for name,sha in report['artifacts'].items():
        p=Path(name).resolve(strict=True)
        require(p.is_relative_to(run) and digest(p)==sha,'Artifact drift')
    proof=json.loads(json.dumps(late_fault_proof((run/'passive-prefix.log').read_text())))
    require(proof==report['rootcause']==json.loads((run/'rootcause.json').read_text()),'Root-cause replay differs')
    check_mode((run/'fast-prefix.log').read_text(),(run/'prefix.txt').read_text(),0,3,2,False)
    wanted=[(name,gap) for name in ('matrix','real-m1','real-m4','contexts') for gap in (0,3)]
    found={};results=[]
    for record in report['results']:
        name=record['vector'];gap=record['measured']['response_gap'];key=(name,gap)
        require(key in wanted and key not in found,'Unexpected/duplicate scope')
        source=Path(record['source']).resolve(strict=True)
        if source==run:
            require(key==('contexts',3),'Unexpected successor substitution')
            logs=[(run/f'contexts-{mode}.log').read_text() for mode in (0,1)]
            require(all(t.splitlines().count('MATRIX_FAULT_SCHEDULE fast=1')==1 for t in logs),'Wrong fault schedule')
            old=json.loads((source/'commands.json').read_text())
            vector_root=Path(next(r['argv'][1].split('=',1)[1] for r in old if r['label']=='contexts-0')).parent
        else:
            require(json.loads((source/'result.json').read_text())['state']=='FAIL','Original failure must remain FAIL')
            logs=[(source/f'run-{name}-gap{gap}-{mode}.log').read_text() for mode in (0,1)]
            vector_root=source
        measured=pair(*logs,*[(vector_root/f'{name}-{mode}.txt').read_text() for mode in ('base','wide')],
                      gap,12 if name=='contexts' else 1 if name=='matrix' else 0,name.startswith('real-'))
        require(measured==record['measured'],'Measured scope differs')
        found[key]=record;results.append(record)
    require(set(found)==set(wanted),'Missing paired scopes')
    require(sum(len(r['measured']['direct']) for r in results)==100 and
            sum(len(r['measured']['contexts']) for r in results)==26,'Incomplete direct/context coverage')
    return dict(state='MATRIX_FULL_ENGINE_COMPOSITE_REAUDITED',run=str(run),checked_inputs=checked,
                result_sha256=digest(run/'result.json'),source_pins_sha256=digest(run/'source-pins.json'),
                collector_sha256=digest(__file__),direct_cases_per_configuration=100,
                context_checks_per_configuration=26,rootcause=proof,results=results,
                original_failed_run_preserved=True,default_enabled=False,full_soc_tested=False,
                model_performance_measured=False,area_measured=False,limitations=report['limitations'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=collect(a.run.resolve(strict=True));a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('state','checked_inputs','direct_cases_per_configuration',
                                          'context_checks_per_configuration')},indent=2))


if __name__=='__main__':main()
