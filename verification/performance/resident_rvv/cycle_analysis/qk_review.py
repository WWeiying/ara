#!/usr/bin/env python3
"""Recompute accepted QK work, including unequal lane tails, without RTL runs."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('qk_accepted_cycles',HERE/'analyze.py')
accepted=importlib.util.module_from_spec(spec)
spec.loader.exec_module(accepted)
require,sha=accepted.require,accepted.sha


def geometry(tokens,dimension=128,heads=2,lanes=4):
    require(tokens and all(1<=t<=64 for t in tokens),'Invalid tile lengths')
    require(dimension in (64,96,128) and heads in (1,2) and lanes==4,'Unreviewed geometry')
    tiles=[]
    total_beats=[0]*lanes
    total_elements=[0]*lanes
    for t in tokens:
        local=[t//lanes+int(l<t%lanes) for l in range(lanes)]
        elements=[n*dimension*heads for n in local]
        beats=[((n+1)//2)*dimension*heads for n in local]
        tiles.append(dict(tokens=t,local_elements=local,fma_elements=elements,
                          fma_beats=beats,current_mapping_issue_floor=max(beats)))
        total_beats=[a+b for a,b in zip(total_beats,beats)]
        total_elements=[a+b for a,b in zip(total_elements,elements)]
    return dict(tiles=tiles,lane_fma_beats=total_beats,lane_fma_elements=total_elements,
        mean_lane_fma_beats=sum(total_beats)/lanes,
        busiest_lane_fma_beats=max(total_beats),
        current_mapping_issue_floor=sum(t['current_mapping_issue_floor'] for t in tiles),
        useful_fma_elements=sum(total_elements),
        masked_simd_slots=sum(total_beats)*2-sum(total_elements))


def review(result):
    require(result['state']=='ACCEPTED_PROBES_ANALYZED' and not result['hardware_optimization_measured'],
            'Unreviewed profile result')
    g=geometry((64,64,9))
    phase=result['phases']['qk']
    per_lane=[]
    for lane in range(4):
        row=result['lanes'][str(lane)]['qk']
        require(row['fma_input_handshakes']==g['lane_fma_beats'][lane] and
                row['fma_destination_byte_enable_elements']==g['lane_fma_elements'][lane] and
                row['fp_input_handshakes']==row['fma_input_handshakes'] and
                row['cycles']==phase['cycles'],'QK lane work/geometry mismatch')
        per_lane.append(dict(lane=lane,**row))
    require(phase['lane_totals']['fma_input_handshakes']==sum(g['lane_fma_beats']) and
            phase['lane_totals']['fma_destination_byte_enable_elements']==g['useful_fma_elements'],
            'QK aggregate work mismatch')
    akv=phase['akv']
    require(akv['command_fires']==96 and akv['terminals']==96 and
            akv['axi_ar_handshakes']==akv['context_conflict_cycles']==akv['replay_request_denied_cycles']==0,
            'Accepted workload no longer matches the reviewed QK transport')
    return dict(schema='resident-qk-lane-work-review-v1',state='ACCEPTED_QK_WORK_RECOMPUTED',
        hardware_optimization_measured=False,scope=result['scope'],geometry=g,
        measured_qk_helper_cycles=phase['cycles'],lane_work=per_lane,akv_work=akv,
        nonadditive_diagnostics=True,
        floor_scope='Existing element-to-lane mapping, two FP32 SIMD elements per lane per cycle; '
                    'no conversion, initialization, ownership, input or commit costs',
        next_action='Retain dimension-ordered FP32 accumulation and count real source/transport/flags costs; '
                    'do not infer a complete-call speedup from the arithmetic floor')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('profile','evidence','build','output'): p.add_argument('--'+key,required=True,type=Path)
    args=p.parse_args()
    raw=accepted.analyze(args.profile,args.evidence,args.build)
    result=review(raw)
    result['source_artifacts']=dict(raw['source_artifacts'])
    for path in (Path(__file__),HERE/'analyze.py',HERE.parent/'analyze.py',
                 args.evidence/'result.json',args.build/'build.json'):
        result['source_artifacts'][str(path.resolve())]=sha(path)
    with args.output.open('x') as out: json.dump(result,out,indent=2); out.write('\n')
    print(json.dumps(dict(state=result['state'],output=str(args.output),
        mean_lane_beats=result['geometry']['mean_lane_fma_beats'],
        busiest_lane_beats=result['geometry']['busiest_lane_fma_beats'])))


if __name__=='__main__': main()
