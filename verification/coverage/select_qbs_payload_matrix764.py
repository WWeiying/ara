"""Eight-command greedy union from source-bound typed764 DIRECT hypotheses."""
import argparse
import json
from pathlib import Path

import rank_qbs_payload_hits764 as model

life,require=model.life,model.require
REPORT=life.OUT/'qbs-payload-current764-hit-matrix-agent-20261007-02.json'
REPORT_SHA='0b79f0a8def4c3633b496c9d889c2d506d834abb75928827005bc92c00f0e68a'


def pairs(item,side_only=False):
    return {(scope,c) for scope,matches in item['matches'].items()
            for kind,coords in matches.items() if not side_only or kind=='SIDE_DIRECT_METADATA' for c in coords}


def select(rows,count=8):
    seen=set();side=set();commands=[]
    for index in range(count):
        best=None
        for weight in rows:
            if weight['kind']!='WEIGHT':continue
            activation_profile='Q8_K' if weight['profile'] in ('Q4_K','Q5_K','Q6_K','Q3_K','Q2_K') else 'Q8_0'
            for activation in rows:
                if activation['kind']!='ACTIVATION' or activation['contexts']!=8 or activation['profile']!=activation_profile:continue
                candidate=pairs(weight)|pairs(activation)
                fresh=candidate-seen
                if best is None or len(fresh)>len(best[0]):best=fresh,weight,activation,candidate
        require(best is not None and best[0],'No positive next unique command')
        fresh,weight,activation,candidate=best
        metadata=pairs(weight,True)|pairs(activation,True)
        commands.append(dict(index=index,weight_profile=weight['profile'],weight_profile_enum=weight['profile_enum'],
            weight_layout=weight['layout'],weight_phase=weight['phase'],activation_profile=activation['profile'],
            activation_layout='M8_INTERLEAVED',activation_phase=activation['phase'],m=8,n=8,k_blocks=1,
            incremental_mapping_directions=len(fresh),incremental_side_metadata_directions=len(metadata-side),
            fresh_typed_coordinates=[dict(scope=s,raw_coordinate=c,category='SIDE_DIRECT_METADATA' if (s,c) in metadata
                else 'MAIN_CONDITIONAL_ON_PENDING_AND_SELECTED_WORD') for s,c in sorted(fresh)]))
        seen|=candidate;side|=metadata
    return commands,seen,side


def build():
    report=life.read_bound(REPORT,REPORT_SHA)
    require(report['baseline']==764 and report['baseline_seal']==model.BASE_SHA and
        report['remaining_mapping_HOLD_directions']==16439,'Latest typed764 required')
    pins=dict(report['pins']);pins[str(REPORT)]=REPORT_SHA
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_select_qbs_payload_matrix764.py'),
        life.ROOT/'verification/qbs/qbs_ref.c',life.ROOT/'verification/qbs/qbs_ref.h',
        life.ROOT/'apps/common/qbs_abi.h'):
        pins[str(path)]=life.digest(path)
    life.check(pins)
    commands,all_coords,side=select(report['ranking'])
    require(len(all_coords)==2820 and len(side)==1100,'Pinned exact greedy outcome')
    typed={}
    for scope,data in report['scopes'].items():
        for record in data['records']:
            if record['classification'].startswith('HOLD'):
                for c in record['missing_serialized_coordinates']:
                    require((scope,c) not in typed,'Duplicate physical coordinate')
                    typed[scope,c]=dict(scope=scope,checksum=data['checksum'],raw_width=data['raw_width'],
                        signal=record['signal'],declaration_line=record['declaration_line'],bit=record['bit'],
                        left=record['left'],right=record['right'],raw_coordinate=c,
                        serialized_pair_slot=(c-record['raw_offset'])%2)
    targets=[dict(typed[key],category='SIDE_DIRECT_METADATA' if key in side else
        'MAIN_CONDITIONAL_ON_PENDING_AND_SELECTED_WORD') for key in sorted(all_coords)]
    require(len(targets)==len(all_coords),'Only current missing HOLD bits can be targeted')
    return dict(schema='QBS_PAYLOAD764_GREEDY8_SOURCE_PROPOSAL_V1',baseline=764,baseline_seal=model.BASE_SHA,
        pins=pins,commands=commands,targets=targets,mapping_union_raw_directions=2820,
        side_metadata_raw_directions=1100,conditional_main_raw_directions=1720,
        no_EDA=True,coverage_admitted=False,exclusions_approved=False,official_percentage=False,
        proposed_budget_s=600,runtime_fit_verified=False,
        runtime_basis='Original2 full8 commands CPU220.880s. Copying8 old software bodies is rejected (approximately884s). Proposed compact8 needs static seed/gold images, no repeated dataset copying, one complete post-command VRF snapshot and six pre/post CSRs per command; complete independent offline guard/native checks remain mandatory.',
        oracle='Reuse unchanged verification/qbs/qbs_ref.c all-format decoder plus independent exact integer fixture recipes. Unit power-of-two scales and bounded integer operations permit bit-exact FP32 and zero new flags. No custom Spike or whole scalar ISA differential claim.',
        source_edges=['read_engine compact prefix strb preserves original writer index',
            'bank1 weight range starts at global row4: address shift4*blockbytes is mandatory',
            'adapter stored target/location and pending.strb are not repacked',
            'main selected_word is first valid candidate unless older write_req selects another word',
            'side hit is valid target/location match and has no SRAM selected-word arbitration'],
        blocked_until='Actual Host positive/negative oracle/ELF fit and bounded scalar-overhead proof; exact full VRF/CSR/source guards and command lifecycle qualifier ready. Main gains remain hypotheses until one measured run.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(not a.output.exists(),'Fresh artifact');record=build();life.save(a.output,record)
    print(json.dumps(dict(path=str(a.output),seal=life.digest(a.output),union=record['mapping_union_raw_directions'],
        side=record['side_metadata_raw_directions'],main_conditional=record['conditional_main_raw_directions'],
        commands=[{k:v for k,v in c.items() if k!='fresh_typed_coordinates'} for c in record['commands']])),flush=True)
