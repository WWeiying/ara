"""Residual typed hit map on formal766; static predictions are never measured gain."""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import rank_qbs_payload_hits764 as old
import select_qbs_payload_matrix764 as greedy

life,require=old.life,old.require
BASE=life.OUT/'qbs-payload-matrix4-offline-admitted-766-agent-20261007-01'
BASE_SHA='bbad20298653af04606493c1e6c6433cf22bb9f532b4cc16f52922fe9b7bfb3b'
REPORT=greedy.REPORT
REPORT_SHA=greedy.REPORT_SHA
PRIOR=life.OUT/'qbs-payload-matrix4-uart-qualified765-agent-20261007-01/toggle-gain.json'


def residual(scopes,rows):
    result={}
    for scope,definition in scopes.items():
        row=rows[scope]
        require((row['width'],row['checksum'])==(definition['raw_width'],definition['checksum']), 'Compiled shape differs')
        bits=int(row['bits'],16);records=[];counts=Counter()
        for record in definition['records']:
            coords=[c for c in record['missing_serialized_coordinates'] if not bits>>(row['width']-1-c)&1]
            if coords:
                if not record['classification'].startswith('HOLD'):require(len(coords)==2,'Structural counterexample')
                records.append(dict(record,missing_serialized_coordinates=coords));counts[record['classification']]+=len(coords)
        result[scope]=dict(checksum=row['checksum'],raw_width=row['width'],records=records,remaining_directions_by_class=dict(counts))
    return result


def signature(weight,activation):
    return weight['profile_enum'],weight['layout'],weight['phase'],activation['profile'],activation['phase']


def select(rows,count,forbidden):
    seen=set();side=set();commands=[]
    for index in range(count):
        best=None
        for w in rows:
            if w['kind']!='WEIGHT':continue
            act='Q8_K' if w['profile'] in ('Q4_K','Q5_K','Q6_K','Q3_K','Q2_K') else 'Q8_0'
            for a in rows:
                if a['kind']!='ACTIVATION' or a['contexts']!=8 or a['profile']!=act or signature(w,a) in forbidden:continue
                candidate=greedy.pairs(w)|greedy.pairs(a);fresh=candidate-seen
                if best is None or len(fresh)>len(best[0]):best=fresh,w,a,candidate
        if best is None or not best[0]:break
        fresh,w,a,candidate=best;metadata=greedy.pairs(w,True)|greedy.pairs(a,True)
        commands.append(dict(index=index,weight_profile=w['profile'],weight_profile_enum=w['profile_enum'],
            weight_layout=w['layout'],weight_phase=w['phase'],activation_profile=a['profile'],activation_phase=a['phase'],
            activation_layout='M8_INTERLEAVED',m=8,n=8,k_blocks=1,incremental_mapping_directions=len(fresh),
            incremental_side_metadata_directions=len(metadata-side),
            fresh_coordinates=[dict(scope=s,raw_coordinate=c) for s,c in sorted(fresh)]))
        seen|=candidate;side|=metadata;forbidden=set(forbidden)|{signature(w,a)}
    return commands,seen,side


def build():
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    status=life.read_bound(BASE/'status.json',manifest['output_pins'][str(BASE/'status.json')])
    require(status['aggregate_passed']==766 and status['coverage_admitted'] is True,'Formal766 required')
    gain_path=BASE/'scoped-toggle-gain.json'
    gain=life.read_bound(gain_path,manifest['output_pins'][str(gain_path)])
    require(gain['total_new_raw_directions']==2561 and gain['population']==766,'Actual matrix4 gain')
    report=life.read_bound(REPORT,REPORT_SHA);pins=dict(report['pins'])
    pins.update({str(REPORT):REPORT_SHA,str(BASE/'admission-manifest.json'):BASE_SHA,
        str(gain_path):manifest['output_pins'][str(gain_path)],str(BASE/'status.json'):manifest['output_pins'][str(BASE/'status.json')]})
    require(str(PRIOR) in manifest['input_pins'],'Qualified prior predicted misses unbound')
    prior=life.read_bound(PRIOR,manifest['input_pins'][str(PRIOR)]);pins[str(PRIOR)]=manifest['input_pins'][str(PRIOR)]
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_rank_qbs_payload_hits766.py')):
        pins[str(path)]=life.digest(path)
    life.check(pins)
    scopes=residual(report['scopes'],gain['combined_rows'])
    typed={(s,c):dict(record,scope=s,raw_coordinate=c,raw_width=d['raw_width'],checksum=d['checksum'])
        for s,d in scopes.items() for record in d['records'] if record['classification'].startswith('HOLD')
        for c in record['missing_serialized_coordinates']}
    ranking=copy.deepcopy(report['ranking'])
    for item in ranking:
        for scope,matches in item['matches'].items():
            for kind,coords in matches.items():matches[kind]=[c for c in coords if (scope,c) in typed]
        item['side_metadata_missing_directions']=len(greedy.pairs(item,True))
        item['conditional_main_missing_directions']=len(greedy.pairs(item))-item['side_metadata_missing_directions']
    ranking.sort(key=lambda item:-(item['side_metadata_missing_directions']+item['conditional_main_missing_directions']))
    forbidden={(2,'R4_BLOCK_MAJOR',14,'Q8_K',8),(2,'R4_BLOCK_MAJOR',6,'Q8_K',12),
        (2,'ROW_MAJOR',10,'Q8_K',8),(2,'ROW_MAJOR',2,'Q8_K',8),
        (5,'R4_BLOCK_MAJOR',0,'Q8_K',12),(5,'R4_BLOCK_MAJOR',12,'Q8_K',0)}
    commands,coords,side=select(ranking,8,forbidden)
    misses=[]
    for record in prior['predicted_targets']:
        if record['measured_new']:continue
        key,slot,is_side=old.proof.mapping.identity(record['signal'],record['bit'])
        require(slot==0 and not is_side,'Unexpected conditional miss ownership')
        require((record['scope'],record['raw_coordinate']) in typed,'Missing coordinate was covered in766')
        misses.append(dict(record,decoded_identity=list(key),slot=slot,
            static_reason='Old predictor assigns non-first-word incoming bytes to pending slot0 under isolated ingress. Real slot1 selected_word may use existing older write_addr, granting that word immediately; pending is created only for remaining unconsumed strobes. Mapping alone does not prove this writer entered pending.',
            measured_cause_unique=False,waiver_allowed=False,
            distinguishing_signals=['write_req[0][plane][row]','write_addr[0][plane][row]',
                'first_word[1]','selected_word','word_match','source_valid',
                'weight_remaining/activation_remaining','pending_q_valid','pending_q.strb','pending_target.valid']))
    require(len(misses)==14,'Exact14 conditional residuals')
    targets=[dict(typed[k],prediction_category='SIDE_DIRECT_METADATA' if k in side else 'MAIN_CONDITIONAL') for k in sorted(coords)]
    life.check(pins)
    return dict(schema='QBS_PAYLOAD_FORMAL766_RESIDUAL_GREEDY_STATIC_V1',baseline=766,baseline_seal=BASE_SHA,
        pins=pins,scopes=scopes,ranking=ranking,remaining_mapping_HOLD_directions=len(typed),
        commands=commands,targets=targets,mapping_union_raw_directions=len(coords),side_metadata_raw_directions=len(side),
        conditional_main_raw_directions=len(coords)-len(side),prior14conditional_misses=misses,
        measured_previous_matrix_gain=2561,measured_next_gain=None,official_percentage=False,
        no_EDA=True,coverage_admitted=False,forbidden_completed_signatures=[list(s) for s in sorted(forbidden)],
        budget_basis='Measured previous compact4 CPU148.680s; same complete oracle4 estimated149s/8 estimated297s, hard600s only after Host and ELF proof. Different format latency remains a hypothesis.',
        scope_limits='Only finite DIRECT M8 K1 mappings; no claim of full layout enumeration, unique runtime arbitration root cause, or unreachable residual. No control exclusion. Raw missing data bits require separate named compiled object audit, not sign-pattern speculation.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(not a.output.exists(),'Preserve prior artifacts');record=build();life.save(a.output,record)
    print(json.dumps(dict(path=str(a.output),seal=life.digest(a.output),remaining=record['remaining_mapping_HOLD_directions'],
        union=record['mapping_union_raw_directions'],side=record['side_metadata_raw_directions'],
        commands=[{k:v for k,v in c.items() if k!='fresh_coordinates'} for c in record['commands']])),flush=True)
