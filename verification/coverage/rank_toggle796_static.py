"""Complete published796 binary union minus sealed approved EL; no EDA."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import report_population796_alua_ptw as policy
import targeted_toggle_evidence_v2 as native
import rank_cva6_scalar_data767 as typed

OUT = policy.life.OUT
REPORT = OUT/'current-population796-alua137-ptw156-agent-20261008-01'
CONFIG_SHA = '062daf585d00ef170942b36f5a631dee7f4676af32fcbb4e5d8af86a8159badf'


def collect():
    pins = {}
    def read(path, expected):
        value = policy.life.read_bound(path,expected)
        pins[str(path)] = expected
        return value
    manifest = read(policy.BASE,policy.BASE_SHA)
    config = read(REPORT/'config.json',CONFIG_SHA)
    policy.need(config['population'] == 796 and config['admission'] == dict(path=str(policy.BASE),sha256=policy.BASE_SHA),
                'Exact published796 report configuration')
    base = policy.BASE.parent
    ledger = base/'combined-inputs.txt'
    policy.need(native.digest(ledger) == manifest['output_pins'][str(ledger)],'Published ledger')
    pins[str(ledger)] = manifest['output_pins'][str(ledger)]
    names = ledger.read_text().splitlines()
    policy.need(len(names) == len(set(names)) == 797 and names == config['input_ledger'],'Exact796 membership')
    bitmap = base/'combined-toggle-bits.json'
    rows = read(bitmap,manifest['output_pins'][str(bitmap)])
    policy.need(len(rows) == 2989,'Complete Toggle scope union')
    el = REPORT/'combined.el'
    policy.need(native.digest(el) == config['pins'][str(el)],'Approved immutable complete796 EL')
    pins[str(el)] = config['pins'][str(el)]
    other,masks = policy.stable.semantic(el.read_text())
    whole = {r[0] for r in other if r[3] == 'WHOLE_SCOPE'}
    fields = {}
    for (scope,checks,name,kind,decl,prefix,direction),mask in masks.items():
        policy.need(scope in rows and checks.split()[-1] == rows[scope]['checksum'],'EL checksum identity')
        if not prefix:
            entry = fields.setdefault((scope,name),dict({'0to1':0,'1to0':0}))
            entry[direction] |= mask
    db = Path(names[0])/'snps/coverage/db'
    shape = db/'shape/tgl.verilog.shape.xml'
    sourceinfo = db/'auxiliary/verilog.sourceinfo.xml'
    for path in (shape,sourceinfo):
        policy.need(native.digest(path) == manifest['input_pins'][str(path)],'Frozen compiled identity')
        pins[str(path)] = manifest['input_pins'][str(path)]
    files = {n.get('id'):n.get('name') for n in native.xml(sourceinfo).findall('fileinfo')}
    definitions = {}
    for d in native.xml(shape).findall('tgldef'):
        definitions.setdefault(d.get('chksum'),[]).append(d)
    book_path = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book = read(book_path,manifest['input_pins'][str(book_path)])
    ranked,holds = [],[]
    scopes = []
    for scope,row in rows.items():
        if not scope.startswith('ara_tb.dut.i_ara_soc.i_system.') or scope in whole:
            continue
        defs = definitions.get(row['checksum'],[])
        if len(defs) != 1:
            holds.append(dict(scope=scope,reason='Nonunique compiled definition'));continue
        try:
            nodes,arrays = typed.typed_nodes(ET.tostring(defs[0],encoding='unicode'),row)
        except ValueError as error:
            holds.append(dict(scope=scope,reason=str(error)));continue
        if arrays:holds.append(dict(scope=scope,reason='MDA not flattened or counted',arrays=arrays))
        total,held = 0,0
        for node in nodes:
            if not node['missing_slots']:continue
            lo = min(int(node.get('left',0)),int(node.get('right',0)))
            masks2 = fields.get((scope,node['name']),{'0to1':0,'1to0':0})
            both = masks2['0to1'] & masks2['1to0']
            single = masks2['0to1'] ^ masks2['1to0']
            remaining,ambiguous = [],[]
            for pos in node['missing_coordinates']:
                bit = lo + (pos-node['serialized_offset'])//2
                if both >> bit & 1:continue
                if single >> bit & 1:ambiguous.append(pos)
                else:remaining.append(pos)
            held += len(ambiguous)
            if not remaining:continue
            total += len(remaining)
            path = files.get(node.get('file'))
            obj = dict(scope=scope,checksum=row['checksum'],definition=defs[0].get('name'),
                attributes=dict(node),source_file=path,expected_frozen_source_sha256=book.get(path),
                net_missing_serialized_positions=len(remaining),raw_missing=node['missing_slots'],
                both_direction_EL_removed=node['missing_slots']-len(remaining)-len(ambiguous),
                single_direction_EL_HOLD=len(ambiguous),coordinates=remaining)
            # Compact per-object mask, not a named native-direction assignment.
            obj['attributes'].pop('missing_coordinates',None)
            ranked.append(obj)
        scopes.append(dict(scope=scope,checksum=row['checksum'],net_binary_missing=total,
                           single_direction_EL_HOLD_positions=held))
    ranked.sort(key=lambda r:(-r['net_missing_serialized_positions'],r['scope'],r['attributes']['name']))
    scopes.sort(key=lambda r:(-r['net_binary_missing'],r['scope']))
    pins[str(Path(__file__).resolve())] = native.digest(Path(__file__).resolve())
    policy.life.check(pins)
    return dict(status='FULL796_STATIC_BINARY_RESIDUAL_MINUS_APPROVED_EL_NOT_REACHABLE_GAIN',
        population=796,manifest_sha256=policy.BASE_SHA,report_config_sha256=CONFIG_SHA,
        EL_sha256=pins[str(el)],EL_additions=config['EL_additions'],pins=pins,
        objects=ranked,scopes=scopes,holds=holds,whole_scope_removed_exact_only=sorted(whole),
        serialized_rule='Existing low logical bit first with unnamed pair slots. Only both-direction EL masks remove pairs; single-direction ownership stays HOLD.',
        EDA_started=False,RTL_changed=False,new_exclusions=False,measured_gain=None,official_denominator=None,
        limitations=['Source reachability not implied by raw capacity','MDA is separate, not binary directions',
                     'Source-proven constants not yet in approved EL still require filtering','No native GUI direction-ID order inferred'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();policy.need(not args.output.exists(),'Fresh evidence only')
    result=collect();args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(native.digest(args.output))
    for row in result['scopes'][:25]:print(row['net_binary_missing'],row['scope'])
    for row in result['objects'][:35]:print(row['net_missing_serialized_positions'],row['scope'],row['attributes']['name'])
