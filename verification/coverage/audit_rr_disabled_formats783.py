"""Static783 typed residual ranking and direct disabled-format input proof. No EDA."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re

import rank_toggle781_compact as rank
import mfpu_constants272_sourcefirst770 as m

t, OUT = rank.t, rank.OUT
POLICY = OUT/'current-population783-fpnew90-prepared-agent-20261008-02'
ADMISSION = OUT/'qbs-k2-pending-offline-admitted783-agent-20261008-01/admission-manifest.json'
ADMISSION_SHA = '8d0d58bf873e0b0f4c601d1e9fb88fca74babb572f822a0580967eef9e5d23f0'
CONFIG_SHA = 'cd90ea43f021b88ae42eab1ab60c8112c7e92bc1201b5a11f1a8bd3d1cf9edae'
BOOK = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'


def disabled(mask, units, index):
    t.require(0 <= index < 6 and 0 <= mask < 64 and 0 <= units < 4096, 'Format parameter bounds')
    unit = (units >> (2*(5-index))) & 3
    t.require(unit in (0, 1, 2), 'Unknown unit type')
    return not ((mask >> (5-index)) & 1) or unit == 0


def source_guard(texts):
    proof = m.semantic_proof(texts)
    pkg, block, arb = (texts[n] for n in ('fpnew_pkg.sv', 'fpnew_opgroup_block.sv', 'rr_arb_tree.sv'))
    t.require('typedef logic [0:NUM_FP_FORMATS-1]       fmt_logic_t;' in pkg and
              re.search(r'unit_type_t\s*\[0:NUM_FP_FORMATS-1\]\s*fmt_unit_types_t', pkg),
              'Ascending format mask/unit packing')
    t.require(re.search(r'DISABLED,\s*//.*?\n\s*PARALLEL,.*?\n\s*MERGED', pkg, re.S),
              'Exact enum ordering')
    start = block.index('else if (!FpFmtMask[fmt] || (FmtUnitTypes[fmt] == fpnew_pkg::DISABLED))')
    body = block[start:block.index('\n    end\n', start)]
    for token in ("assign fmt_outputs[fmt].result  = '{default: fpnew_pkg::DONT_CARE};",
                  "assign fmt_outputs[fmt].tag     = TagType'(fpnew_pkg::DONT_CARE);"):
        t.require(token in body, 'Disabled branch literal changed')
    t.require(re.search(r'DataType\s*\[NumIn-1:0\]\s*data_i', arb) and
              'output_t [NUM_FORMATS-1:0] fmt_outputs;' in block and
              '.NumIn     ( NUM_FORMATS )' in block, 'Direct input array geometry')
    return proof


def parameters(text):
    values = {k: int(v) for k, v in re.findall(r'\b(Width|FpFmtMask|FmtUnitTypes|NUM_FORMATS|NumIn)=(\d+)', text)}
    return values


def collect():
    pins = {}
    def read(path, sha):
        path = Path(path).resolve()
        t.require(t.digest(path) == sha, 'Bound input drift: '+str(path))
        pins[str(path)] = sha
        return path.read_bytes()
    a = json.loads(read(ADMISSION, ADMISSION_SHA))
    c = json.loads(read(POLICY/'config.json', CONFIG_SHA))
    qp = POLICY/'qualification.json'
    q = json.loads(read(qp, t.digest(qp)))
    t.require(q['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED' and
              q['population'] == c['population'] == 783 and q['config_seal'] == CONFIG_SHA and
              q['admission_seal'] == ADMISSION_SHA and q['all_other_bits_protected'] is True and
              q['raw_reset_final_equal'] is True and q['applied_reloaded_equal'] is True,
              'Actual qualified783 required')
    lp = ADMISSION.parent/'combined-inputs.txt'
    ledger = read(lp, a['output_pins'][str(lp)]).decode().splitlines()
    t.require(a['coverage_admitted'] is True and ledger == c['input_ledger'] and
              len(ledger) == len(set(ledger)) == 784, 'Exact783 admitted ledger')
    cache = json.loads(read(rank.old.CACHE, rank.old.CACHE_SHA))
    prefix = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    t.require(ledger[:742] == read(prefix, cache['input_pins'][str(prefix)]).decode().splitlines(), 'Exact741 prefix')
    union = {s: {k: r[k] for k in ('width', 'checksum', 'bits')} for s, r in cache['instances'].items()}
    for vdb in ledger[742:]:
        files = list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        t.require(len(files) == 1, 'Unique suffix native data')
        read(files[0], a['input_pins'][str(files[0])])
        rows, _ = t.rows(files[0], set(union))
        union = t.union(union, rows)
    ep = POLICY/'combined.el'
    entries, whole = rank.old.el_fields(read(ep, c['pins'][str(ep)]).decode())
    owners = defaultdict(set)
    for scope, name in entries: owners[scope].add(name)
    db = Path(ledger[0])/'snps/coverage/db'
    paths = [db/'design/verilog.design.xml', db/'shape/tgl.verilog.info.xml', db/'shape/tgl.verilog.shape.xml']
    for p in paths: read(p, a['input_pins'][str(p)])
    design, info, shape = (t.xml(p) for p in paths)
    nodes = {n.get('id'): (n, d) for d in design.findall('srcdef') for n in d.findall('srcinst')}
    def scope_path(key):
        n, _ = nodes[key]
        return (scope_path(n.get('pid'))+'.' if n.get('pid') in nodes else '')+n.get('name')
    modules = {scope_path(k): d for k, (_, d) in nodes.items()}
    checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data')}
    definitions = defaultdict(list)
    for d in shape.findall('tgldef'): definitions[d.get('name').split(' (')[0], d.get('chksum')].append(d)
    def definition(scope):
        ds = definitions[modules[scope].get('name').split(' (')[0], checks[scope]]
        exact = [d for d in ds if d.get('name') == modules[scope].get('name')]
        ds = exact or ds
        t.require(len(ds) == 1, 'Unique specialized definition: '+scope)
        return ds[0]
    book = json.loads(read(BOOK, BOOK_SHA)); texts = {}
    for rel in m.SOURCE:
        p = m.ROOT/rel
        texts[p.name] = read(p, book[str(p)]).decode()
    proof = source_guard(texts)
    groups = {}; scope_rows = []; holds = []; callers = []; candidates = []
    for scope, row in union.items():
        if not (scope == 'ara_tb.dut.i_ara_soc.i_system' or scope.startswith('ara_tb.dut.i_ara_soc.i_system.')): continue
        if any(scope == w or scope.startswith(w+'.') for w in whole): continue
        d = definition(scope); family = modules[scope].get('name').split(' (')[0]
        t.require(checks[scope] == row['checksum'], 'Native shape checksum')
        rr = family == 'rr_arb_tree'
        parent = scope.rsplit('.', 1)[0]
        direct = rr and parent in modules and modules[parent].get('name') == 'fpnew_opgroup_block'
        p = parameters(definition(parent).get('name')) if direct else {}
        if direct:
            t.require(parameters(d.get('name')).get('NumIn') == p.get('NUM_FORMATS') == 6 and
                      p.get('Width') in (32, 64) and p.get('FmtUnitTypes') in (0,1365,2730),
                      'Direct compiled caller geometry/uniform unit domain')
            caller = dict(scope=scope, parameters=p, definition=definition(parent).get('name'),
                          disabled_formats=[i for i in range(6) if disabled(p['FpFmtMask'],p['FmtUnitTypes'],i)],
                          candidates=[], protected_objects=[])
            callers.append(caller)
        binary = format(int(row['bits'], 16), '0%db' % row['width'])
        offset = 0; scope_missing = 0
        for n in d.find('tglshape'):
            name = n.get('name')
            if n.tag == 'arrays':
                holds.append(dict(scope=scope, field=name, reason='MDA_CAPACITY_UNBOUND'))
                if direct: caller['protected_objects'].append(dict(kind=n.tag,attributes=dict(n.attrib)))
                continue
            t.require(n.tag in ('node','vectornode'), 'Known typed serialization')
            left, right = int(n.get('left','0')), int(n.get('right','0'))
            width = 1 if n.tag == 'node' else abs(left-right)+1
            start = offset; offset += 2*width
            missing = [start+i for i,b in enumerate(binary[start:offset]) if b == '0']
            legal = set(range(min(left,right),max(left,right)+1))
            field_entries = entries.get((scope,name),[])
            mda_owner = any(bits == 'MDA_HOLD' for _,bits,_ in field_entries)
            removed, ambiguous = (set(),True) if mda_owner else rank.old.excluded_bits(field_entries,legal)
            ancestor = any(name.startswith(owner+'.') for owner in owners[scope])
            clean = not removed and not ambiguous and not ancestor
            match = re.fullmatch(r'data_i\[([0-5])\]\.(result|tag\.operand_a)', name or '')
            target = False
            if direct and match and int(match[1]) in caller['disabled_formats']:
                operand = match[2] != 'result'
                tag_ok = re.search(r'TagType=vfpu_tag_t(?=[, )])', definition(parent).get('name'))
                if not operand or tag_ok:
                    expected_width = 64 if operand else p['Width']
                    t.require(n.tag == 'vectornode' and (left,right)==(expected_width-1,0) and
                              n.get('portnode') == '2' and n.get('type') == '1' and
                              n.get('aux_file') == '210' and n.get('aux_line_num') == '103',
                              'Exact direct input port identity')
                    if clean:
                        target = True
                        record = dict(scope=scope, field=name, checksum=row['checksum'],
                            module_checksum=modules[scope].get('chksum'), attributes=dict(n.attrib),
                            kind=n.tag, logical_bits=list(range(width)), raw_range=[start,offset],
                            raw_missing=len(missing), missing_coordinates=missing,
                            constant_hex=hex(0 if operand else (1<<width)-1), format_index=int(match[1]),
                            reason='DISABLED_FORMAT_DIRECT_INPUT_LITERAL', native_qualified=False,
                            serialized_pair_direction_order_inferred=False)
                        candidates.append(record); caller['candidates'].append(name)
                    elif removed != legal:
                        holds.append(dict(scope=scope,field=name,reason='PARTIAL_OR_STRUCT_EL_OWNERSHIP'))
            if direct and not target:
                caller['protected_objects'].append(dict(kind=n.tag,attributes=dict(n.attrib),raw_range=[start,offset]))
            if not missing or removed == legal: continue
            if not clean:
                holds.append(dict(scope=scope,field=name,reason='PARTIAL_OR_STRUCT_EL_NATIVE_MAPPING_REQUIRED',
                                  raw_missing_upper_bound=len(missing))); continue
            key = family, name
            group = groups.setdefault(key,dict(module_family=family,field=name,missing=0,members=[]))
            group['missing'] += len(missing)
            group['members'].append(dict(scope=scope,checksum=row['checksum'],kind=n.tag,
                                        attributes=dict(n.attrib),raw_missing=len(missing),coordinates=missing))
            scope_missing += len(missing)
        t.require(offset == row['width'], 'Complete non-MDA serialized native width')
        scope_rows.append(dict(scope=scope,module=family,unwaived_exact_field_missing=scope_missing))
    t.require(len(callers) == 30, 'Exact compiled direct format callers')
    for helper in (Path(__file__), Path(rank.__file__), Path(rank.old.__file__), Path(m.__file__),
                   Path(__file__).with_name('test_audit_rr_disabled_formats783.py')):
        pins[str(helper.resolve())] = t.digest(helper)
    for path,sha in pins.items(): t.require(t.digest(path)==sha,'Read-end drift')
    return dict(schema='FORMAL783_RR_DISABLED_INPUT_PROOF_AND_RESIDUAL_CAPACITY_V1',population=783,
        qualification_sha=pins[str(qp)], policy_EL_sha=pins[str(ep)], admission_sha=ADMISSION_SHA,
        source_proof=proof,callers=callers,candidates=candidates,candidate_count=len(candidates),
        candidate_directions=sum(2*len(r['logical_bits']) for r in candidates),
        candidate_raw_missing=sum(r['raw_missing'] for r in candidates),
        top10=sorted(groups.values(),key=lambda g:(-g['missing'],g['module_family'],g['field']))[:10],
        scope_top10=sorted(scope_rows,key=lambda r:-r['unwaived_exact_field_missing'])[:10],
        residual_groups=sorted(groups.values(),key=lambda g:(-g['missing'],g['module_family'],g['field'])),
        hold=holds,pins=pins, official_denominator=None,predicted_percentage_gain=None,
        scope='Disabled direct input result and reviewed vfpu tag operand only; active formats/top arbitration/control/status preserved',
        initialization_X_not_waived=True,arrays_capacity=None,EDA_started=False,waivers_applied=False,
        status='STATIC_SOURCE_PROVEN_NOT_NATIVE_QUALIFIED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    output = parser.parse_args().output.resolve()
    t.require(output.parent == OUT and not output.exists(),'Fresh independent evidence')
    result = collect()
    with output.open('x') as stream: json.dump(result,stream,separators=(',',':')); stream.write('\n')
    print(json.dumps(dict(output=str(output),sha256=t.digest(output),candidates=result['candidate_count'],
                         directions=result['candidate_directions'],missing=result['candidate_raw_missing'],
                         top10=[(r['module_family'],r['field'],r['missing']) for r in result['top10']])))
