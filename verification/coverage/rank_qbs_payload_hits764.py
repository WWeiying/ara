"""Typed current764 missing-hit map and finite DIRECT stream hypotheses; no EDA."""
import argparse
from collections import Counter
import itertools
import json
from pathlib import Path

import admit_qbs_payload_phase764 as admitted
import prove_qbs_even_start_hits762 as proof

life,require=admitted.life,admitted.require
BASE=admitted.OUT
BASE_SHA='167f82e2a614e34e7dd8606bdb9211370cb573ebc0ad414baa99f7da355398f1'
FORMATS=('Q4_K','Q5_K','Q6_K','Q3_K','Q8_0','Q4_0','Q2_K','Q5_0','IQ4_NL')
ENUMS=(1,4,2,5,6,3,7,8,9)


def weight_beats(profile,phase,grouped,bank=0):
    size=proof.mapping.SIZES[profile-1]
    ranges=[(0,4*size,None)] if grouped else [(r*size,size,r) for r in range(4)]
    for base,length,row in ranges:
        for offset,first,take in proof.compact_range(0x80000040+phase+4*bank*size+base,length):
            targets=[]
            for writer in range(take):
                r,o=divmod(offset+writer,size) if grouped else (row,offset+writer)
                p,d=proof.mapping.weight_location(profile,o)
                targets.append(('weight',r,p,d,writer))
            yield targets


def activation_beats(scale,quants,contexts,phase):
    size=scale+quants+(32 if quants==256 else 0)
    ranges=[(0,contexts*size,None)] if contexts!=1 else [(r*size,size,r) for r in range(4)]
    for base,length,row in ranges:
        for offset,first,take in proof.compact_range(0x80000040+phase+base,length):
            targets=[]
            for writer in range(take):
                ctx,o=proof.mapping.activation_target(offset+writer,contexts,scale,quants)
                if row is not None:ctx=row
                p,d=proof.mapping.activation_location(o,scale,quants)
                targets.append(('activation',ctx,p,d,writer))
            yield targets


def trace_keys(beats,bank):
    """Metadata plus isolated ingress hypothesis. Never claim arbitrary pending scheduling."""
    side,newer,pending=set(),set(),set()
    for beat in beats:
        main={}
        for kind,row,plane,d,writer in beat:
            if kind=='activation':
                if not 4*bank<=row<4*bank+4:continue
                row-=4*bank
            key=(kind,row,plane,d if plane==2 else d%(32 if kind=='activation' else 16),writer)
            if plane==2:
                side.add(key);continue
            shift=5 if kind=='activation' else 4
            main.setdefault((kind,row,plane),[]).append((d>>shift,key))
        for group,items in main.items():
            first=items[0][0]
            for word,key in items:
                (newer if word==first else pending).add(key)
    return side,newer,pending


def match_missing(records,keys):
    side,newer,pending=keys
    result={'SIDE_DIRECT_METADATA':[],'NEWER_MAIN_ISOLATED_INGRESS_HYPOTHESIS':[],
            'OLDER_MAIN_PENDING_DRAIN_HYPOTHESIS':[]}
    for record in records:
        key,slot,is_side=proof.mapping.identity(record['signal'],record['bit'])
        if is_side:
            if slot==1 and key in side:result['SIDE_DIRECT_METADATA'].extend(record['missing_serialized_coordinates'])
        elif slot==1 and key in newer:
            result['NEWER_MAIN_ISOLATED_INGRESS_HYPOTHESIS'].extend(record['missing_serialized_coordinates'])
        elif slot==0 and key in pending:
            result['OLDER_MAIN_PENDING_DRAIN_HYPOTHESIS'].extend(record['missing_serialized_coordinates'])
    return {kind:sorted(set(coords)) for kind,coords in result.items()}


def build():
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(manifest['schema']==admitted.SCHEMA and manifest['baseline_seal']==admitted.BASE_SHA,
        'Exact formal764 successor')
    status=life.read_bound(BASE/'status.json',manifest['output_pins'][str(BASE/'status.json')])
    require(status['aggregate_passed']==764 and status['coverage_admitted'] is True,'Formal764 PASS')
    gains_path=BASE/'scoped-toggle-gain.json'
    gains=life.read_bound(gains_path,manifest['output_pins'][str(gains_path)])
    static=life.read_bound(admitted.q.recipe.STATIC,admitted.q.recipe.STATIC_SHA)
    pins=dict(static['pins'])
    pins.update({str(BASE/'admission-manifest.json'):BASE_SHA,str(gains_path):manifest['output_pins'][str(gains_path)],
        str(BASE/'status.json'):manifest['output_pins'][str(BASE/'status.json')],
        str(admitted.q.recipe.STATIC):admitted.q.recipe.STATIC_SHA})
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_rank_qbs_payload_hits764.py')):
        pins[str(p)]=life.digest(p)
    life.check(pins)
    scopes={};ranking=[]
    for scope,original in static['scopes'].items():
        row=gains['combined_rows'][scope]
        require((row['checksum'],row['width'])==(original['checksum'],original['raw_width']),
            'Typed native shape')
        bits=int(row['bits'],16);records=[];counts=Counter()
        for record in original['records']:
            missing=[c for c in record['missing_serialized_coordinates'] if not bits>>(row['width']-1-c)&1]
            if not missing:continue
            if not record['classification'].startswith('HOLD'):
                require(len(missing)==2,'Observed counterexample to a structural candidate')
            entry=dict(record,missing_serialized_coordinates=missing);records.append(entry)
            counts[record['classification']]+=len(missing)
        scopes[scope]=dict(checksum=row['checksum'],raw_width=row['width'],records=records,
            remaining_directions_by_class=dict(counts))
    for profile,phase,grouped in itertools.product(range(1,10),range(0,16,2),(False,True)):
        matches={s:match_missing(d['records'],trace_keys(weight_beats(profile,phase,grouped,bank),bank))
                 for bank,(s,d) in enumerate(sorted(scopes.items()))}
        ranking.append(dict(kind='WEIGHT',profile=FORMATS[profile-1],profile_enum=ENUMS[profile-1],
            phase=phase,layout='R4_BLOCK_MAJOR' if grouped else 'ROW_MAJOR',matches=matches))
    for (scale,quants),contexts,phase in itertools.product(((4,256),(2,32)),(1,4,8),(0,4,8,12)):
        matches={s:match_missing(d['records'],trace_keys(activation_beats(scale,quants,contexts,phase),bank))
                 for bank,(s,d) in enumerate(sorted(scopes.items()))}
        ranking.append(dict(kind='ACTIVATION',profile='Q8_K' if scale==4 else 'Q8_0',
            contexts=contexts,phase=phase,layout={1:'ROW_MAJOR',4:'M4',8:'M8'}[contexts],matches=matches))
    for item in ranking:
        item['side_metadata_missing_directions']=sum(len(v['SIDE_DIRECT_METADATA']) for v in item['matches'].values())
        item['conditional_main_missing_directions']=sum(len(v['NEWER_MAIN_ISOLATED_INGRESS_HYPOTHESIS'])+
            len(v['OLDER_MAIN_PENDING_DRAIN_HYPOTHESIS']) for v in item['matches'].values())
    ranking.sort(key=lambda item:-(item['side_metadata_missing_directions']+item['conditional_main_missing_directions']))
    counts={s:d['remaining_directions_by_class'] for s,d in scopes.items()}
    remaining=sum(sum(v for k,v in c.items() if k.startswith('HOLD')) for c in counts.values())
    require(remaining==16439,'Exact16983 minus measured544 HOLD directions')
    life.check(pins)
    return dict(schema='QBS_PAYLOAD_CURRENT764_TYPED_HIT_MATRIX_V1',baseline=764,baseline_seal=BASE_SHA,pins=pins,
        scopes=scopes,remaining_mapping_HOLD_directions=remaining,ranking=ranking,
        no_EDA=True,exclusions_approved=False,
        limitations='Finite DIRECT mapping only. Main predictions require empty/drained older slot and exact selected-word arbitration; not guaranteed gain or impossibility proof. Context-cache replay, stale invalid metadata, simultaneous pending/ingress require separate induction. No missing-control exclusion.',
        enum_note='Finite mapper uses logical FORMAT order, not package enum numeric order; profile_enum explicitly maps actual package values.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(not a.output.exists(),'Fresh artifact');record=build();life.save(a.output,record)
    print(json.dumps(dict(path=str(a.output),seal=life.digest(a.output),remaining=record['remaining_mapping_HOLD_directions'],
        best=[{k:v for k,v in r.items() if k!='matches'} for r in record['ranking'][:8]])),flush=True)
