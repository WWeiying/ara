"""Host-only RVFI04 union readiness; no launch or population admission override."""
import argparse
import copy
import json
from pathlib import Path
import re

import report_native_batch764 as retained
import capture_system_rvfi788_v4 as native
import capture_cva6_parent_rvfi457 as cva6

life,require,merge=retained.life,retained.require,retained.merge
HERE=Path(__file__).resolve().parent
BASE=life.OUT/'native-batch-full765-agent-20261007-02'
BASE_CONFIG_SHA='7788edc2ea227e403c9fecc03abbc3085712e2a35a967028a317f6ee33b78c72'
CAPTURE=life.OUT/'system-rvfi788-native-agent-20261007-04'
CAPTURE_SHA='ff9ceb495a70de8d602788128c030a1b5e3698378dccc0cbdce7884fb6f3108d'
CVA6=life.OUT/'cva6-parent-rvfi457-native-agent-20261007-01'
CVA6_SHA='e5ae15157446f1848413fda855cea69b6910c08e590b1f5e44a8027ecfd2e5cf'


def qualification_gate(q,c):
    require(q['status']=='SYSTEM_RVFI788_NATIVE_ROUNDTRIP_QUALIFIED_NOT_POPULATION_APPLICATION' and
        q['objects']==788 and q['bits']==22126 and q['protected_objects']==418 and
        q['all_arrays_ports_control_protected'] and q['semantic_reload'] and q['finalreset'] and
        q['non_target_exclusions']==0 and q['population_application'] is False and
        q['complete1206_metadata_matches_sealed02'] and q['before_any_exclude_bijection_verified'] and
        q['binding_sha256']==native.BINDING_SHA and q['explicit_target_aliases']==11 and
        q['explicit_protected_aliases']==30,'RVFI04 whole target/complement boundary differs')
    native.previous.contract(c)


def records(text,c,rvfi,cva=None):
    wanted={p['signal'] for p in rvfi['targets']}
    cva_wanted={p['name'] for p in cva['bindings'] if p['role']=='target'} if cva else set()
    old_parts,new_parts,cva_parts=[],[],[]
    for scope,block in retained.old.blocks(text):
        header=[];bodies=[[],[],[]];annotation=None
        for line in block.splitlines():
            if not line or line.startswith('//'):continue
            if line.startswith(('CHECKSUM:','INSTANCE:')):header.append(line);continue
            if line.startswith('ANNOTATION:'):annotation=line;continue
            match=re.match(r'^Toggle\s+(?:(?:0to1|1to0)\s+)?(\S+)',line)
            which=int(scope==native.core.review.SCOPE and match is not None and match[1] in wanted)
            if cva and scope==cva['scope'] and match is not None and match[1] in cva_wanted:which=2
            if annotation is not None:bodies[which].append(annotation)
            bodies[which].append(line)
        for body,parts in zip(bodies,(old_parts,new_parts,cva_parts)):
            if body:parts.append('\n'.join(header+body)+'\n')
        if not any(bodies):
            old_parts.append(block)
    result=dict(retained=retained.records(''.join(old_parts),c),
                rvfi788=retained.old.normalized(native.records(''.join(new_parts),rvfi)))
    if cva:result['cva6rvfi457']=retained.old.normalized(cva6.records(''.join(cva_parts),cva))
    return result


def cva6_gate(q,c):
    require(q['status']=='CVA6_PARENT_RVFI457_NATIVE_QUALIFIED_NOT_POPULATION_APPLICATION' and
        q['targets']==457 and q['logical_bits']==2599 and q['protected']==1315 and q['protected_arrays']==31 and
        q['five_stages']==list(cva6.STAGES) and q['non_target_new_exclusions']==0 and
        q['observation_output_exception_only'] is True and q['child_and_functional_hardware_exclusions']==0 and
        q['population_application'] is False,'CVA6 exact output-only boundary differs')
    cva6.contract(c)


def prepare_review(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh review output only')
    # Config is immutable; do not inspect any active765 output or process.
    c=life.read_bound(BASE/'config.json',BASE_CONFIG_SHA)
    q=life.read_bound(CAPTURE/'capture-result.json',CAPTURE_SHA)
    rvfi=life.read_bound(CAPTURE/'config.json',q['config_seal']);qualification_gate(q,rvfi)
    first=native.records((CAPTURE/'first.el').read_text(),rvfi)
    require(first==native.records((CAPTURE/'second.el').read_text(),rvfi) and len(first)==788,
            'Exact RVFI04 semantic reload differs')
    refs=[native.inventory(CAPTURE,rvfi,s) for s in ('before','selected','reset','reloaded','final')]
    require(all(ref==refs[0] and len(ref)==1206 for ref in refs),'Complete1206 native five-stage binding differs')
    cq=life.read_bound(CVA6/'capture-result.json',CVA6_SHA)
    cc=life.read_bound(CVA6/'config.json',cq['config_seal']);cva6_gate(cq,cc)
    cfirst=cva6.records((CVA6/'first.el').read_text(),cc)
    require(cfirst==cva6.records((CVA6/'second.el').read_text(),cc) and len(cfirst)==457,'Exact CVA6 semantic reload differs')
    crefs=[cva6.inventory(CVA6,cc,s)[0] for s in cva6.STAGES]
    require(all(ref==crefs[0] and len(ref)==1772 for ref in crefs),'Complete1772 CVA6 five-stage identity differs')
    combined=(BASE/'combined.el').read_text()+(CAPTURE/'first.el').read_text()+(CVA6/'first.el').read_text()
    union=records(combined,c,rvfi,cc)
    require(union['retained']==c['expected_union'] and union['rvfi788']==retained.old.normalized(first) and
            union['cva6rvfi457']==retained.old.normalized(cfirst),
            'Retained765 policy or exact788 canonical union changed')
    pins=merge(c['pins'],q['input_pins'],q['output_pins'],cq['input_pins'],cq['output_pins'],
        {str(BASE/'config.json'):BASE_CONFIG_SHA,str(CAPTURE/'capture-result.json'):CAPTURE_SHA,
         str(CAPTURE/'config.json'):q['config_seal'],str(CVA6/'capture-result.json'):CVA6_SHA,
         str(CVA6/'config.json'):cq['config_seal']})
    for path in [Path(__file__).resolve(),HERE/'test_prepare_rvfi788_union_successor.py',
                 Path(native.__file__).resolve(),Path(native.parser.__file__).resolve(),Path(cva6.__file__).resolve()]:
        pins[str(path)]=life.digest(path)
    life.check(pins);out.mkdir()
    with (out/'candidate-union.el').open('x') as stream:stream.write(combined)
    pins[str(out/'candidate-union.el')]=life.digest(out/'candidate-union.el')
    data=dict(status='RVFI04_CANONICAL_UNION_HOST_READY_NOT_RUNTIME_APPLICATION',
        predecessor=str(BASE),predecessor_config_seal=BASE_CONFIG_SHA,capture_seal=CAPTURE_SHA,
        objects=788,bits=22126,protected=418,native_binding_rows=1206,expected_union=union,
        full_native_reference=refs[0],cva6_capture_seal=CVA6_SHA,cva6_objects=457,cva6_bits=2599,
        cva6_protected=1315,cva6_protected_arrays=31,cva6_full_native_reference=crefs[0],pins=pins,EDA_launched=False,
        population_policy='765 unchanged, or formal766 only after independent matrix4 qualification/admission and exact765 prefix/full6162 OR.',
        launch_gate='Actual765 sealed full five-stage qualification required; this review does not launch.',
        other_unqualified_scopes_included=False,runtime_ready=False)
    life.save(out/'review.json',data)
    print(json.dumps(dict(status=data['status'],output=str(out),seal=life.digest(out/'review.json'))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare_review(a.output.resolve())
