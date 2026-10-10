#!/usr/bin/env python3
"""Prepare exact 688+1 membership only; do not merge or authorize reports."""
import argparse
from pathlib import Path
import verify_gap82_offline as offline


def prepare(baseline, sidecar, output):
    require,target = offline.require,offline.target
    baseline,sidecar = baseline.resolve(strict=True),sidecar.resolve(strict=True)
    require(baseline.parent == sidecar.parent == offline.ROOT/'verification/out' and
            output.absolute().parent.resolve() == baseline.parent and not output.exists(),
            'Independent local evidence/output required')
    pins = target.read(sidecar/'evidence-pins.json')
    for p,h in pins.items():require(target.sha(p) == h,'Sidecar evidence drift: '+p)
    status=target.read(sidecar/'status.json')
    require(status['status']=='OFFLINE_SINGLE_CASE_VERIFIED' and status['both_targets_hit'],
            'Verified GAP82 single case required')
    measured=target.read(sidecar/'target-measurement.json')
    raw=Path(measured['raw_file'])
    vdb=raw.parents[5]
    require(raw.relative_to(vdb).parts == ('snps','coverage','db','testdata',
            offline.frozen.NAME,'cond.verilog.data.xml') and vdb.name == 'code.vdb',
            'Unexpected raw condition path structure')
    run=vdb.parent
    require(run.parent == baseline.parent,'Unexpected raw VDB path')
    bits=target.read(baseline/'combined-bits.json')
    members=(baseline/'combined-inputs.txt').read_text().splitlines()
    static=target.read(run/'static-plan.json')
    require(len(bits['tests']) == 688 and len(members) == 689 and
            members == [static['design_vdb'],*bits['tests']], 'Exact baseline list/bitmap membership differs')
    resolved=[str(Path(p).resolve(strict=True)) for p in members]
    require(len(set(resolved)) == len(resolved) and str(vdb.resolve(strict=True)) not in resolved,
            'Duplicate/aliased VDB population')
    prior=bits['metrics']['cond'][measured['scope']]
    require(str(prior['checksum']) == str(measured['checksum']) and prior['width']==measured['width'] and
            all(target.bit(prior,x['raw_index']) == '0' for x in measured['targets']),
            'Targets already hit or baseline shape differs')
    require(target.read(baseline/'runtime-audit.json')['status'] == 'PASS', 'GAP81 runtime audit absent')
    for path in [baseline/'combined-bits.json',baseline/'combined-inputs.txt',baseline/'status.json',
                 baseline/'runtime-audit.json',sidecar/'status.json',sidecar/'evidence-pins.json',
                 sidecar/'runtime-audit.json',sidecar/'target-measurement.json',Path(__file__).resolve()]:
        pins[str(path)]=target.sha(path)
    for p,h in pins.items():require(target.sha(p)==h,'Preparation evidence drift: '+p)
    output.mkdir()
    with (output/'proposed-inputs.txt').open('x') as stream:
        stream.write('\n'.join([*members,str(vdb)])+'\n')
    offline.frozen.save(output/'single-case-description.json',dict(
        status='PREPARED_NOT_AGGREGATE_ADMISSION',name=offline.frozen.NAME,
        case_vdb=str(vdb),custom_commands=2,new_cases=1,baseline_cases=688,proposed_cases=689,
        baseline=str(baseline),baseline_terminal=target.read(baseline/'status.json'),
        gap82_sidecar=str(sidecar),original_gap82_terminal_preserved='FAIL',
        targets=measured['targets'],baseline_targets_zero=True,
        baseline_membership_exact=True,aggregate_combined=False,dve_run=False,
        receipt_issued=False,waivers_applied=False))
    pins[str(output/'proposed-inputs.txt')]=target.sha(output/'proposed-inputs.txt')
    offline.frozen.save(output/'preparation-pins.json',pins)
    return str(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('baseline','sidecar','output'):p.add_argument('--'+arg,type=Path,required=True)
    a=p.parse_args();print(prepare(a.baseline,a.sidecar,a.output))
