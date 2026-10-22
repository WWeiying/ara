"""Read-only binary residual ranking; MDA and native scoring remain separate."""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import targeted_toggle_evidence_v2 as t
import rank_cva6_scalar_data767 as typed
import report_global777_compact as native

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'verification/out'
BASE = OUT/'valu-restart-offline-admitted785-agent-20261008-01'
BASE_SHA = '10273c45e4a4eb21929e0599a2bfc27bfb76afb2b36fe547de0198b5ee918cf5'
REPORT = OUT/'current-population785-rr190-prepared-agent-20261008-01'
CACHE = OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_SHA = '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'


def main():
    pins = {}
    def read(p, h):
        t.require(t.digest(p) == h, 'Input drift: '+str(p)); pins[str(p)] = h
        return json.loads(p.read_bytes())
    m = read(BASE/'admission-manifest.json',BASE_SHA)
    authority = dict(m['input_pins'],**m['output_pins'])
    c = read(CACHE,CACHE_SHA)
    ledger_path = BASE/'combined-inputs.txt'
    t.require(t.digest(ledger_path) == authority[str(ledger_path)], 'Ledger pin')
    ledger = ledger_path.read_text().splitlines()
    t.require(len(ledger) == len(set(ledger)) == 786, 'Exact785')
    cached_files = {p for p in c['input_pins'] if p.endswith('/tgl.verilog.data.xml')}
    first = []
    for v in ledger[1:742]:
        paths = list((Path(v)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        t.require(len(paths) == 1, 'Cached sample identity');first.append(str(paths[0]))
    t.require(set(first) == cached_files and len(cached_files) == 741 and
              all(authority.get(p) == h for p,h in c['input_pins'].items()), 'Sealed741 prefix authority')
    scopes = sorted(s for s in c['instances'] if s.startswith('ara_tb.dut.i_ara_soc.i_system.'))
    union = {s:{k:c['instances'][s][k] for k in ('width','checksum','bits')} for s in scopes}
    for i,v in enumerate(ledger[742:],742):
        files = list((Path(v)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        t.require(len(files) == 1, 'Suffix identity')
        rows,h = t.rows(files[0],scopes)
        t.require(authority.get(str(files[0])) == h, 'Suffix authority')
        pins[str(files[0])] = h;union = t.union(union,rows)
        if i % 10 == 0: print('READONLY_SUFFIX',i,flush=True)
    q = json.loads((REPORT/'qualification.json').read_bytes())
    t.require(q['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
              q['population'] == 785 and q['admission_seal'] == BASE_SHA, 'Qualified785 report')
    for name in ('applied.el','modules_applied.csv'):
        p = REPORT/name;t.require(t.digest(p) == q['output_pins'][str(p)], 'Native report output pin')
        pins[str(p)] = q['output_pins'][str(p)]
    others,masks = native.semantic((REPORT/'applied.el').read_text())
    whole = {s for s,checks,machine,line in others if line == 'WHOLE_SCOPE'}
    excluded = {}
    for (scope,checks,name,kind,decl,prefix,direction),mask in masks.items():
        if not prefix: excluded[(scope,name,direction)] = excluded.get((scope,name,direction),0) | mask
    shape_path = Path(ledger[0])/'snps/coverage/db/shape/tgl.verilog.shape.xml'
    t.require(t.digest(shape_path) == authority[str(shape_path)], 'Compiled shape pin')
    pins[str(shape_path)] = authority[str(shape_path)]
    definitions = {}
    for d in t.xml(shape_path).findall('tgldef'): definitions.setdefault(d.get('chksum'),[]).append(d)
    ranked, held = [], []
    for scope,row in union.items():
        if any(scope == s or scope.startswith(s+'.') for s in whole): continue
        defs = definitions.get(row['checksum'],[])
        if len(defs) != 1:
            held.append(dict(scope=scope,reason='Ambiguous/missing compiled checksum definition'));continue
        try: nodes,arrays = typed.typed_nodes(ET.tostring(defs[0],encoding='unicode'),row)
        except ValueError as e:
            held.append(dict(scope=scope,reason=str(e)));continue
        objects = []
        for n in nodes:
            if not n['missing_slots']:continue
            left,right = int(n.get('left','0')),int(n.get('right','0'))
            lo,hi = min(left,right),max(left,right); full = ((1 << (hi-lo+1))-1) << lo
            coverage = [excluded.get((scope,n['name'],d),0) for d in ('0to1','1to0')]
            if all(mask & full == full for mask in coverage):continue
            partial = any(mask & full for mask in coverage)
            objects.append(dict(name=n['name'],missing_binary_positions=n['missing_slots'],
                width=n['logical_width'],line=n.get('line_num'),file=n.get('file'),
                partial_EL_direction_binding_HOLD=partial,
                source_classification_required=True,coordinates=n['missing_coordinates']))
        ranked.append(dict(scope=scope,checksum=row['checksum'],
            remaining_binary_positions=sum(n['missing_binary_positions'] for n in objects),
            objects=sorted(objects,key=lambda n:-n['missing_binary_positions']),
            arrays_not_ranked_as_binary_directions=arrays))
    ranked.sort(key=lambda r:-r['remaining_binary_positions'])
    for p,h in pins.items():t.require(t.digest(Path(p)) == h, 'End drift')
    result=dict(status='STATIC_BINARY_785_RESIDUAL_NOT_OFFICIAL_DIRECTION_DENOMINATOR',population=785,
        cache_prefix=741,suffix=44,waived_report=str(REPORT),input_pins=pins,ranking=ranked,holds=held,
        unknown_MDA_codes_not_ORed=True,whole_approved_observers_removed=True,
        fully_approved_binary_objects_removed=True,partial_EL_masks_upper_bound_only=True,
        official_percentage_claimed=False,EDA_launched=False,RTL_changed=False)
    out = OUT/'dynamic-toggle785-static-ranking-agent-20261008-01.json'
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print('STATIC_RESULT',str(out),t.digest(out),flush=True)


if __name__ == '__main__':main()
