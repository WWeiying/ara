#!/usr/bin/env python3
"""Independent full-output SDK replay, with no extrapolation to whole-model time."""
import argparse
import json
from pathlib import Path

from audit import digest, require, verify_pins
from full_projection import check, N
from check_projection_native import fields
from collect_projection_native import PHASES, COUNTERS


def collect(root, wide):
    from collect_matrix_soc import audit_build
    from run_output_native import s, accepted
    root=root.resolve(strict=True); report=json.loads((root/'result.json').read_text())
    require(report['state']=='PASS' and report['wide']==wide and report['full_n'] and
            report['performance_measured'] and report['independent_protocol_checked'] and report['post_pins_match'],
            'Incomplete full-output run')
    require(digest(root/'source-pins.json')==report['source_pins_sha256'],'Pin-map drift')
    pins=json.loads((root/'source-pins.json').read_text()); checked=verify_pins(pins)
    build=Path(report['build']); program=json.loads((build/'build.json').read_text())
    require(program['state']=='FULL_QWEN3_SDK_BUILT_NOT_EXECUTED' and
            pins.get(str(build/'build.json'))==digest(build/'build.json') and
            report['elf_sha256']==program['elf_sha256']==digest(program['elf']), 'Full program binding')
    status=json.loads((root/'status.json').read_text()); simv=Path(status['simv'])
    soc=audit_build(simv.parent.parent)
    require(soc['wide']==wide and soc['image_pins']==report['image_pins'] and
            s.hashes(s.image_files(simv))==report['image_pins'], 'Actual image identity')
    names=('attn_q','attn_k','attn_v')
    for name in names:
        path=build/(name+'_expected.bin'); require(pins.get(str(path))==digest(path),'Golden identity')
    text=(root/'work/run.vcs.log').read_text()
    measured=check(text,wide,[(build/(name+'_expected.bin')).read_bytes() for name in names])
    require(measured==report['measured'],'Raw full-output replay differs')
    accepted.protocol(root/'work',report['elf_sha256'],report['image_pins'])
    rows=[fields(line,'[QBS_PERF]') for line in text.splitlines() if line.startswith('[QBS_PERF] ')]
    activity=[]; start=0
    for part,n in enumerate(N):
        count=n//32; commands=rows[start:start+count]; start+=count
        for command in commands:
            require(all(k in command for k in COUNTERS),'Missing diagnostic field')
            require(sum(command.get('phase_'+phase+'_cycles',-1000000) for phase in PHASES)==
                    command['busy_cycles'],'Phase accounting')
        activity.append(dict(part=part,n=n,commands=count,
            counters={k:sum(c[k] for c in commands) for k in COUNTERS},
            phases={phase:sum(c['phase_'+phase+'_cycles'] for c in commands) for phase in PHASES}))
    verify_pins(pins)
    return dict(wide=wide,run=str(root),build=str(build),elf_sha256=report['elf_sha256'],
                measured=measured,activity=activity,checked_inputs=checked,
                result_sha256=digest(root/'result.json'),source_pins_sha256=report['source_pins_sha256'],
                log_sha256=digest(root/'work/run.vcs.log'),protocol_sha256=digest(root/'work/uvm_result.json'))


def compare(base,wide):
    require(base['wide']==0 and wide['wide']==1 and base['build']==wide['build'] and
            base['elf_sha256']==wide['elf_sha256'],'Unpaired full workloads')
    a,b=base['measured'],wide['measured']
    require(a['qbs_commands']==b['qbs_commands']==128 and a['useful_pairs']==b['useful_pairs']==33554432 and
            a['dot_issue_count']==2*b['dot_issue_count'],'Useful work/width mismatch')
    require([(p['checksum'],p['fcsr'],p['vcsr']) for p in a['parts']]==
            [(p['checksum'],p['fcsr'],p['vcsr']) for p in b['parts']], 'Output/state mismatch')
    require(a['preparation_cycles']==b['preparation_cycles'],'Unexpected preparation change')
    for key in ('payload_bytes','weight_bytes','activation_bytes','useful_pairs','fp_uop_issue','accumulator_updates'):
        require(sum(p['counters'][key] for p in base['activity'])==
                sum(p['counters'][key] for p in wide['activity']), 'Different command work: '+key)
    return dict(region_ratio=a['region_cycles']/b['region_cycles'],
                execution_ratio=a['execution_cycles']/b['execution_cycles'],
                candidate_preparation_fraction=b['preparation_cycles']/b['region_cycles'],
                parts=[dict(part=i,n=N[i],baseline_execution=a['parts'][i]['execution'],
                            candidate_execution=b['parts'][i]['execution'],
                            ratio=a['parts'][i]['execution']/b['parts'][i]['execution']) for i in range(3)])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True); parser.add_argument('--wide',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    out=args.output.absolute(); require(out==out.resolve(),'Nonaliased output'); out.mkdir(parents=True,exist_ok=False)
    state=dict(state='CHECKING',whole_model=False,area_measured=False)
    try:
        reports=[collect(args.base,0),collect(args.wide,1)]
        state.update(state='FULL_QWEN3_QKV_SDK_PAIR_REAUDITED',reports=reports,comparison=compare(*reports),
            collector_sha256=digest(__file__),m=4,n=list(N),k=2048,full_ggml=False,
            scope='One reset-start full-output QKV group for four genuine prompt rows, not all prompt tokens',
            cold_weight_repack_included=False,preparation_included=True)
    except BaseException as exc: state.update(state='FAIL',error=repr(exc)); raise
    finally: (out/'result.json').write_text(json.dumps(state,indent=2)+'\n')


if __name__=='__main__': main()
