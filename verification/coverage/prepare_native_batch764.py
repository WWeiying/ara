"""Preparation-only successor contract. No EDA/run mode; qualified763 required."""
import argparse
import copy
import json
from pathlib import Path

import report_native_batch763 as predecessor
import capture_vmfpu_ten762 as vmfpu
import capture_sldu_two763 as sldu
import capture_scalar_dwc3 as scalar_dwc
import c910_prepare_pack_native as c910

life, require, merge = predecessor.life, predecessor.require, predecessor.merge
HERE = Path(__file__).resolve().parent
PREDECESSOR = life.OUT/'native-batch-full763-agent-20261007-01'
PREDECESSOR_CONFIG_SHA = '54a49eefe913cadfe588cdf4f5f2e7cd1927af802e8b49f4fc646e3d74ebd084'
VMFPU_SHA = 'd26981360b37062bd0c0c84d81709f1c3eeb9eba8c5c627821ab49c800db3ce1'
SLDU_SHA = '9bfdf3fd1b7ce9810071499e017f731d0053dddbb6b2f98c76e053b2359b0ab0'
MANIFEST = life.OUT/'qbs-payload-phase-offline-admitted-764-agent-20261007-01/admission-manifest.json'
MANIFEST_SHA = '167f82e2a614e34e7dd8606bdb9211370cb573ebc0ad414baa99f7da355398f1'
PROFILES = {
    'vmfpu10': ('EXACT_VMFPU4_STATES_6_HANDOFFS_NATIVE_QUALIFIED_NOT_APPLIED', vmfpu),
    'sldu2': ('EXACT_SLDU2_NATIVE_QUALIFIED_NOT_APPLIED', sldu),
    'scalarDWC3': ('SCALAR_DWC3_NATIVE_SEMANTIC_ROUNDTRIP_QUALIFIED', scalar_dwc),
    'c910240': ('EXACT_C910_PREPARE192_PACK48_NATIVE_ROUNDTRIP_PASS', c910),
}


def predecessor_gate(q,c):
    require(q['status'] == 'SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED' and
            q['population'] == c['population'] == 763 and q['config_seal'] == PREDECESSOR_CONFIG_SHA and
            c['qualified_fsm_union'] == q['qualified_fsm_union'] == 161 and
            c['schema'] == predecessor.SCHEMA and c['output'] == str(PREDECESSOR), 'Full763 predecessor not qualified')
    reports=q['system']
    require(set(reports)=={'raw','applied','reset','reloaded','final'} and
            reports['raw']==reports['reset']==reports['final'] and
            reports['applied']==reports['reloaded'],'Predecessor five-stage mismatch')
    require(q['batch_capture_seals']=={k:v[1] for k,v in predecessor.CAPTURES.items()},'Prior seven qualifications changed')


def population_gate(book,bits,before,single,status):
    require(book['schema']=='QBS_PHASE_HISTORICAL764_NATIVE_ADMISSION_V1' and
            book['explicit_parent_authorized'] is True and book['baseline_seal']==predecessor.MANIFEST_SHA and
            book['baseline']==str(predecessor.MANIFEST.parent),'Only reviewed QBS phase formal764 successor')
    require(status['aggregate_passed']==764 and status['coverage_admitted'] is True,'Formal764 not admitted')
    require(len(before['tests'])==763 and bits['tests'][:-1]==before['tests'] and
            len(bits['tests'])==len(set(bits['tests']))==764 and single['tests']==bits['tests'][-1:] and
            bits['design']==before['design']==single['design'],'Exact763 prefix/singleton/design mismatch')
    total=0
    require(set(bits['metrics'])==set(before['metrics'])==set(single['metrics']),'Metric families differ')
    for metric,rows in before['metrics'].items():
        require(set(rows)==set(bits['metrics'][metric])==set(single['metrics'][metric]),'Hierarchy differs')
        total+=len(rows)
        for scope,p in rows.items():
            now,one=bits['metrics'][metric][scope],single['metrics'][metric][scope]
            require((p['checksum'],p['width'])==(now['checksum'],now['width'])==(one['checksum'],one['width']),
                    'Compiled shape differs')
            require(int(now['bits'],16)==int(p['bits'],16)|int(one['bits'],16) and
                    int(now['bits'],16).bit_length()<=now['width'],'Full OR/overflow mismatch')
    require(total==6162,'Not full6162')


def native_gate(key,q):
    require(key in PROFILES and q['status']==PROFILES[key][0] and q['population_application'] is False,
            'Unknown/unqualified native profile')
    if key=='vmfpu10':
        require(q['targets']==10 and q['protected']==138 and q['protected_reachable_reset_arcs']==20 and
                q['five_stages'] and q['semantic_reload'] and q['global_empty'] and q['state_expansion_rejected'],
                'VMFPU exact source/native boundary')
    elif key=='sldu2':
        require(q['targets']==2 and q['protected']==34 and q['five_stages'] and q['semantic_reload'] and
                q['global_empty'] and q['states_explicitly_excluded'] is False,'SLDU exact two-only boundary')
    elif key=='scalarDWC3':
        require(q['semantic_points']==3 and q['protected_points']==28 and q['native_extra_records']==0 and
                q['all_other_machines_and_descendants_protected'],'Scalar DWC protected boundary')
    else:
        require(q['objects']==240 and q['logical_bits']==10896 and len(q['stages'])==5 and q['both_directions'] and
                q['non_target_exclusions']==0 and q['semantic_reload'] and q['reset_global_empty'] and
                q['all16_vector_cores_source_and_architecture_bound'] and q['scalar_and_children_retained'] and
                q['exhaustive_IEEE_validation'] is False,'C910 complete arithmetic/control boundary')


def merge_fsm(plan,addition):
    result=copy.deepcopy(plan);added=[]
    for g in addition['groups']:
        matches=[(index,j) for index,j in enumerate(result['groups']) if
                 (j['scope'],j['checksum'],j['machine'],j['mode'])==(g['scope'],g['checksum'],g['machine'],g['mode'])]
        require(len(matches)<=1,'Ambiguous FSM group')
        if matches:
            index,j=matches[0]
            require([dict(r,target=False) for r in j['rows']]==[dict(r,target=False) for r in g['rows']],
                    'Native full complement differs')
            for row,candidate in zip(j['rows'],g['rows']):
                if candidate['target']:
                    require(not row['target'],'Duplicate prior FSM target')
                    row['target']=True;added.append((index,row['raw_index']))
                    result['targets']+=1;result['protected']-=1
        else:
            require(not any(j['scope']==g['scope'] and j['machine']['name']==g['machine']['name'] and
                            j['mode']==g['mode'] for j in result['groups']),'Machine checksum/definition mismatch')
            index=len(result['groups']);result['groups'].append(copy.deepcopy(g))
            result['targets']+=sum(r['target'] for r in g['rows'])
            result['protected']+=sum(not r['target'] for r in g['rows'])
            added.extend((index,r['raw_index']) for r in g['rows'] if r['target'])
    require(len(added)==addition['targets'],'Exact additional target count mismatch')
    return result,added


def load_native(key,out,seal):
    require(key in PROFILES,'Unknown native family')
    if key=='vmfpu10':require(seal==VMFPU_SHA,'Parent-approved VMFPU seal differs')
    if key=='sldu2':require(seal==SLDU_SHA,'Parent-approved SLDU seal differs')
    q=life.read_bound(out/'capture-result.json',seal);native_gate(key,q)
    pins=q.get('pins') or merge(q['input_pins'],q['output_pins']);life.check(pins)
    cseal=q['config_seal'];c=life.read_bound(out/'config.json',cseal)
    module=PROFILES[key][1]
    first,second=(out/'first.el').read_text(),(out/'second.el').read_text()
    if key=='c910240':
        actual=module.parse_el(first,c);require(actual==module.parse_el(second,c),'C910 exact typed reload differs')
        for stage in module.STAGES:module.check_stage(out,c,stage)
    elif key=='scalarDWC3':
        actual=module.semantics(first,c);require(actual==module.semantics(second,c),'DWC exact semantic closure differs')
    else:
        actual=vmfpu.native.native_records(first)
        require(actual==vmfpu.native.native_records(second)==[tuple(r) for r in c['expected_records']],
                'FSM exact direct native reload differs')
    return dict(profile=key,output=str(out),seal=seal,config=c,qualification=q,
                canonical_records=predecessor.old.normalized(actual)),merge(pins,
                    {str(out/'capture-result.json'):seal,str(out/'config.json'):cseal})


def prepare(out,pred_seal,manifest,manifest_seal,selections):
    require(out.parent==life.OUT and not out.exists(),'Fresh independent output only')
    require(manifest==MANIFEST and manifest_seal==MANIFEST_SHA,'Parent-approved formal764 seal differs')
    # Fail closed before scanning population or creating output while763 is live.
    q=life.read_bound(PREDECESSOR/'qualification.json',pred_seal)
    c=life.read_bound(PREDECESSOR/'config.json',PREDECESSOR_CONFIG_SHA);predecessor_gate(q,c)
    predecessor.namespace()['verify'](PREDECESSOR,PREDECESSOR_CONFIG_SHA)
    pins=merge(c['pins'],q['output_pins'],{str(PREDECESSOR/'qualification.json'):pred_seal,
                                       str(PREDECESSOR/'config.json'):PREDECESSOR_CONFIG_SHA})
    book=life.read_bound(manifest,manifest_seal)
    require(book['output']==str(manifest.parent),'Admission output mismatch')
    pins=merge(pins,book['input_pins'],book['output_pins'],{str(manifest):manifest_seal})
    def read(name):
        p=manifest.parent/name;require(str(p) in book['output_pins'],'Unsealed formal output')
        return life.read_bound(p,book['output_pins'][str(p)])
    bits,single,status=read('combined-bits.json'),read('single-bits.json'),read('status.json')
    beforepath=predecessor.MANIFEST.parent/'combined-bits.json'
    require(str(beforepath) in pins,'Unsealed predecessor bitmap')
    before=life.read_bound(beforepath,pins[str(beforepath)]);population_gate(book,bits,before,single,status)
    ledger=(manifest.parent/'combined-inputs.txt').read_text().splitlines()
    require(ledger==[c['input_ledger'][0],*bits['tests']],'Formal ledger mismatch')
    require(selections and set(selections)<=set(PROFILES),'Explicit closed native profile selection required')
    captures={};combined=(PREDECESSOR/'applied.el').read_text();plan=copy.deepcopy(c['plan'])
    for key,(path,seal) in selections.items():
        item,npins=load_native(key,path,seal);pins=merge(pins,npins);captures[key]=item
        combined+=(path/'first.el').read_text()
        if key in ('vmfpu10','sldu2'):plan,_=merge_fsm(plan,item['config']['plan'])
    deps=[Path(__file__).resolve(),HERE/'test_prepare_native_batch764.py',Path(predecessor.__file__).resolve(),
          *[Path(PROFILES[key][1].__file__).resolve() for key in selections]]
    pins=merge(pins,{str(p):life.digest(p) for p in deps});life.check(pins)
    out.mkdir()
    with (out/'candidate-union.el').open('x') as stream:stream.write(combined)
    pins[str(out/'candidate-union.el')]=life.digest(out/'candidate-union.el')
    data=dict(status='QUALIFIED763_TO_FORMAL764_NATIVE_SUCCESSOR_INPUTS_PREPARED_NOT_RUNTIME_REPORT',
              predecessor=str(PREDECESSOR),predecessor_qualification_seal=pred_seal,
              population=764,admission=str(manifest),admission_seal=manifest_seal,input_ledger=ledger,
              exact763prefix=True,full6162_OR=True,retained763_expected_union=c['expected_union'],
              selected_new_captures=captures,fsm_plan=plan,pins=pins,EDA_launched=False,
              runtime_apply_authorized=False,full_report_generated=False,
              pending_runtime_checks=['Full canonical union routing, scalar DWC state semantic closure.',
                  'All inherited and added complete native complements in five same-session stages.',
                  'Generated Tcl actual source/eval and raw/applied/reset/reload/final metrics.'])
    life.save(out/'prepared-inputs.json',data)
    print(json.dumps(dict(status=data['status'],output=str(out),seal=life.digest(out/'prepared-inputs.json'))),flush=True)


def pairs(values):
    result={}
    for value in values:
        key,sep,rest=value.partition('=')
        require(sep and rest and key in PROFILES and key not in result,'Unknown/duplicate explicit profile')
        result[key]=rest
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--predecessor-qualification-seal',required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--manifest-seal',required=True)
    p.add_argument('--native',action='append',default=[]);p.add_argument('--native-seal',action='append',default=[])
    a=p.parse_args();paths,seals=pairs(a.native),pairs(a.native_seal)
    require(set(paths)==set(seals),'Native path/seal families differ')
    prepare(a.output.resolve(),a.predecessor_qualification_seal,a.manifest.resolve(),a.manifest_seal,
            {key:(Path(path).resolve(),seals[key]) for key,path in paths.items()})
