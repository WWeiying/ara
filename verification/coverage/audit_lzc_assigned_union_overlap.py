"""Exact instance/field overlap audit, without population application or EDA."""
import argparse
import json
import re
from pathlib import Path
import fma_lzc_assigned_native as native

life,require=native.life,native.require
BASE=life.OUT/'native-batch-full768-v3-prepared-agent-20261007-02'
BASE_SHA='5b6a373a2937cf15809143c813ce250d4af49af011e2564a5f68fda8542071fc'
NEW=life.OUT/'fma-lzc-assigned23132-native-agent-20261007-01'


def ownership(text):
    scopes=set();fields=set();scope=None
    for raw in text.splitlines():
        line=raw.strip()
        if line.startswith('INSTANCE:'):
            scope=line.split(':',1)[1].strip();require(scope,'Empty instance');scopes.add(scope)
        elif line.startswith('Toggle'):
            m=re.match(r'^Toggle\s+(?:(?:0to1|1to0)\s+)?([^\s\[]+(?:\[\d+\]\.[^\s\[]+)*)',line)
            require(scope is not None and m is not None,'Unbound Toggle field')
            fields.add((scope,m[1]))
    return scopes,fields


def audit():
    old=life.read_bound(BASE/'config.json',BASE_SHA)
    combined=BASE/'combined.el';require(life.digest(combined)==old['pins'][str(combined)],'Sealed existing EL drift')
    qpath=NEW/'capture-result.json';qsha=life.digest(qpath);q=life.read_bound(qpath,qsha)
    require(q['status']=='LZC_ASSIGNED23132_NATIVE_PARTIAL_ARRAY_ROUNDTRIP_NOT_APPLIED'
            and q['population_application'] is False,'Not an application receipt')
    c=life.read_bound(NEW/'config.json',q['config_seal']);life.check(c['pins'])
    pins={str(BASE/'config.json'):BASE_SHA,str(combined):old['pins'][str(combined)],
          str(qpath):qsha,str(NEW/'config.json'):q['config_seal']}
    values=[]
    for name in ('first.el','second.el'):
        path=NEW/name;require(life.digest(path)==q['pins'][str(path)],'Actual saved native EL drift')
        pins[str(path)]=q['pins'][str(path)];values.append(native.parse_el(path.read_text(),c))
    require(values[0]==values[1] and len(values[0])==46264,'Actual paired coordinate reload differs')
    old_scopes,old_fields=ownership(combined.read_text())
    new_fields={(i['scope'],s['name']) for i in c['instances'] for s in i['signals']}
    new_scopes={i['scope'] for i in c['instances']}
    shared_scopes=old_scopes&new_scopes;shared_fields=old_fields&new_fields
    # The zero-intersection conclusion is deliberately closed to disjoint instances.
    # Shared fields need dimension-aware canonical union; do not silently re-own them.
    require(not shared_scopes and not shared_fields,'Overlap requires explicit coordinate-aware union review')
    path=Path(__file__).resolve();pins[str(path)]=life.digest(path)
    return dict(status='EXACT_LZC_INSTANCE_FIELD_INTERSECTION_ZERO_NOT_APPLICATION',
                reference_population=768,reference_report_native_qualification_claimed=False,
                new_local_result_sha256=qsha,parent_approval_not_inferred=True,
                new_instances=len(new_scopes),new_fields=len(new_fields),new_bits=23132,
                new_physical_directions=len(values[0]),retained_spare_bits=212,protected_ports=96,
                shared_instance_scopes=sorted(shared_scopes),shared_instance_fields=sorted(shared_fields),
                duplicate_physical_directions=0,same_field_names_different_instances=sorted(
                    {n for _,n in old_fields}&{n for _,n in new_fields}),
                ownership_policy='Exact full instance required; no field-name-only partition reassignment',
                EDA_launched=False,population_application=False,pins=pins)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=audit();life.save(a.output.resolve(),result)
    print(json.dumps(result,indent=2))
