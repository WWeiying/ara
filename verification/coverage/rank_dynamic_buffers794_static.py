"""Formal794 binary buffer gaps minus sealed policy; no native direction guesses."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import targeted_toggle_evidence_v2 as t
import rank_cva6_scalar_data767 as typed
import report_population794_soc61 as report

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'verification/out'
POLICY = OUT/'current-population794-soc61-parent-20261008-01'
POLICY_SHA = '81526ba2020842417df95403931ca06441716ecf7b98ebf88ba0a67daca9434f'


def collect():
    pins = {}
    def read(path,sha):
        t.require(t.digest(path) == sha,'Authority drift: '+str(path)); pins[str(path)] = sha
        return path.read_bytes()
    manifest = json.loads(read(report.BASE,report.BASE_SHA))
    t.require(manifest['coverage_admitted'] is True,'Published794 required')
    authority = dict(manifest['input_pins'],**manifest['output_pins'])
    base = report.BASE.parent
    union = json.loads(read(base/'combined-toggle-bits.json',authority[str(base/'combined-toggle-bits.json')]))
    ledger = read(base/'combined-inputs.txt',authority[str(base/'combined-inputs.txt')]).decode().splitlines()
    config = json.loads(read(POLICY/'config.json',POLICY_SHA))
    t.require(len(ledger) == len(set(ledger)) == 795 and config['input_ledger'] == ledger,'Exact794 population')
    text = read(POLICY/'combined.el',config['pins'][str(POLICY/'combined.el')]).decode('ascii')
    semantic = report.stable.semantic(text)
    t.require(report.stable.semantic_seal(semantic) == config['expected_EL_semantic_sha256'],'Frozen prospective EL union')
    whole = {r[0] for r in semantic[0] if r[3] == 'WHOLE_SCOPE'}
    physical = report.physical(semantic)
    ownership = {}
    for k,v in physical.items(): ownership.setdefault((k[0],k[2]),[]).append((k,v))
    constant_path = OUT/'qbs-accumulator-config-constants-source-review767-agent-20261007-01.json'
    constants = json.loads(read(constant_path,config['pins'][str(constant_path)]))
    constant_targets = {(r['scope'],r['attributes']['name']) for r in constants['candidates']}
    t.require(len(constant_targets) == 66,'Exact static66 candidate registry, not native exclusion')
    shape_path = Path(ledger[0])/'snps/coverage/db/shape/tgl.verilog.shape.xml'
    read(shape_path,authority[str(shape_path)])
    definitions = {}
    for node in t.xml(shape_path).findall('tgldef'): definitions.setdefault(node.get('chksum'),[]).append(node)
    ranked, held, groups = [],[],[]
    removed = 0
    for scope,row in union.items():
        if not ('.i_vlsu' in scope or '.i_operand_queues.' in scope or scope.endswith('.i_operand_requester')): continue
        if any(scope == s or scope.startswith(s+'.') for s in whole): continue
        ds = definitions.get(row['checksum'],[])
        if len(ds) != 1:
            held.append(dict(scope=scope,reason='No unique compiled checksum shape',capacity_not_inferred=True)); continue
        instance_names = {i.get('name') for i in ds[0].iter('tglinst')}
        if instance_names and scope not in instance_names:
            held.append(dict(scope=scope,reason='Explicit compiled instance list conflict',capacity_not_inferred=True)); continue
        try: nodes,arrays = typed.typed_nodes(ET.tostring(ds[0],encoding='unicode'),row)
        except ValueError as error:
            held.append(dict(scope=scope,reason=str(error),capacity_not_inferred=True)); continue
        missing = 0; objects = 0
        if arrays: held.append(dict(scope=scope,reason='MDA separate serializer, not ranked as binary directions',arrays=arrays))
        for n in nodes:
            if not n['missing_slots']: continue
            left,right = int(n.get('left','0')),int(n.get('right','0'))
            lo,hi = min(left,right),max(left,right); full = ((1 << (hi-lo+1))-1) << lo
            owners = ownership.get((scope,n['name']),[])
            t.require(all(k[1].split()[-1] == row['checksum'] for k,v in owners),'EL scope checksum binding')
            covered = {d:0 for d in ('0to1','1to0')}
            for k,v in owners:
                if not k[3]: covered[k[4]] |= v
            if all(v & full == full for v in covered.values()): removed += 1; continue
            if owners:
                held.append(dict(scope=scope,name=n['name'],reason='Partial EL: raw direction order not inferred',
                                 raw_missing_upper_bound=n['missing_slots'],not_added_to_rank=True)); continue
            if (scope,n['name']) in constant_targets:
                held.append(dict(scope=scope,name=n['name'],reason='Proven source constant candidate, not dynamic stimulus',
                                 raw_missing_upper_bound=n['missing_slots'],not_added_to_rank=True)); continue
            if '.i_fp_accumulator.' in scope: continue
            if any(token in n['name'].lower() for token in ('cause','tval','group_hit','hit','cnt','count','addr','index',
                        'idx','state','cycles','bytes','base','offset','hazard','lifetime','vstart','eew','conv','target','valid','ready','len')): continue
            if not any(token in n['name'].lower() for token in ('data','payload','operand','weight','activation','scale','result','strb')): continue
            item = dict(scope=scope,checksum=row['checksum'],definition_name=ds[0].get('name'),
                        name=n['name'],logical_width=n['logical_width'],compiled_attributes=n,
                        missing_binary_positions=n['missing_slots'],coordinates=n['missing_coordinates'],
                        source_dynamic_classification_pending=True,EL_overlap=False,
                        native_bit_direction_labels_not_guessed=True)
            ranked.append(item); missing += n['missing_slots']; objects += 1
        if objects: groups.append(dict(scope=scope,objects=objects,unowned_missing_binary_positions=missing))
    ranked.sort(key=lambda r:(-r['missing_binary_positions'],r['scope'],r['name']))
    groups.sort(key=lambda r:-r['unowned_missing_binary_positions'])
    pins[str(Path(__file__).resolve())] = t.digest(Path(__file__).resolve())
    for path,sha in pins.items(): t.require(t.digest(Path(path)) == sha,'Read-end drift')
    return dict(status='FORMAL794_UNOWNED_BUFFER_DIAGNOSTIC_NOT_REACHABILITY_APPROVAL',population=794,
                prospective_EL_config_sha256=POLICY_SHA,prospective_EL_not_claimed_native_qualified=True,
                input_pins=pins,top50=ranked[:50],groups=groups,holds=held,
                unowned_binary_objects=len(ranked),fully_EL_owned_objects_removed=removed,
                all_ranked_unowned_missing_binary_positions=sum(r['missing_binary_positions'] for r in ranked),
                partial_EL_fields_not_counted=True,MDA_not_counted=True,
                official_denominator=None,expected_actual_gain=None,EDA_started=False,RTL_changed=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True)
    a = p.parse_args(); t.require(a.output.parent.resolve() == OUT and not a.output.exists(),'Fresh independent output')
    result = collect()
    with a.output.open('x') as stream: json.dump(result,stream,indent=2,sort_keys=True); stream.write('\n')
    print(json.dumps(dict(output=str(a.output),sha256=t.digest(a.output),top10=[
        (r['scope'],r['name'],r['missing_binary_positions']) for r in result['top50'][:10]])))
