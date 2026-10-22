"""Static full-field constant candidates; no native qualification or application."""
import argparse
import json
import re
from pathlib import Path
import mfpu_constants272_sourcefirst770 as m
import rank_toggle781_compact as rank

RANK = m.OUT/'toggle781-compact-residual-ranking-agent-20261008-01.json'
RANK_SHA = 'ff14752d5c2085a1992d6de6d8f663656e0259b3f4ef2436ebf1c8ab0c731731'
BOOK = m.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
EXTRA = ['hardware/deps/fpnew/src/fpnew_fma.sv',
         'hardware/deps/fpnew/src/fpnew_cast_multi.sv',
         'hardware/deps/fpnew/src/fpnew_rounding.sv']


def rounding_guard(text, declaration):
    m.need(re.search(r'input\s+logic\s*\[33:0\]\s+id_i', declaration), 'ID width changed')
    calls = re.findall(r'fpnew_rounding\s*#\s*\(.*?\)\s*i_fpnew_rounding\s*\((.*?)\);', text, re.S)
    m.need(len(calls) == 1 and [v.strip() for v in re.findall(r'\.id_i\s*\((.*?)\)', calls[0])] == ["'0"],
           'Exact rounding caller must tie ID zero')


def disabled_guard(definition, fmt):
    text = definition.get('name')
    values = {k: int(v) for k, v in re.findall(r'\b(FpFmtMask|NUM_FORMATS|Width|OpGroup)=(\d+)', text)}
    m.need(values.get('NUM_FORMATS') == 6 and values.get('Width') == 64, 'Compiled format geometry')
    m.need(fmt in (3, 4) and not (values['FpFmtMask'] & (1 << (5-fmt))), 'Enabled format cannot be constant')
    m.need(re.search(r'TagType=vfpu_tag_t(?=[, )])', text), 'Compiled reviewed packed tag required')
    return values


def typed_guard(node, field):
    width = 34 if field == 'id_i' else 64
    m.need(node.tag == 'vectornode' and node.get('left') == str(width-1) and node.get('right') == '0'
           and node.get('portnode') == ('2' if field == 'id_i' else '0'), 'Exact typed field/role/bounds')
    return width


def collect():
    m.need(m.digest(RANK) == RANK_SHA and m.digest(BOOK) == BOOK_SHA, 'Sealed ranking/book drift')
    inventory = json.loads(RANK.read_bytes())
    pins = dict(inventory['pins']); pins[str(RANK)] = RANK_SHA; pins[str(BOOK)] = BOOK_SHA
    m.check_pins(pins)
    book = json.loads(BOOK.read_bytes()); texts = {}
    for rel in m.SOURCE + EXTRA:
        path = m.ROOT/rel
        m.need(m.digest(path) == book[str(path)], 'Frozen source mismatch: '+rel)
        pins[str(path)] = book[str(path)]; texts[path.name] = path.read_text()
    proof = m.semantic_proof(texts)
    pkg = texts['fpnew_pkg.sv']; block = texts['fpnew_opgroup_block.sv']
    m.need('typedef logic [0:NUM_FP_FORMATS-1]       fmt_logic_t;' in pkg and
           "FP8     = 'd3" in pkg and "FP16ALT = 'd4" in pkg, 'Ascending format identity')
    m.need('else if (!FpFmtMask[fmt] || (FmtUnitTypes[fmt] == fpnew_pkg::DISABLED))' in block,
           'Disabled driver guard changed')
    for family in ('fpnew_fma', 'fpnew_cast_multi'):
        rounding_guard(texts[family+'.sv'], texts['fpnew_rounding.sv'])
    db = m.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    design, shape = (m.xml(db/p) for p in ('design/verilog.design.xml', 'shape/tgl.verilog.shape.xml'))
    nodes = {n.get('id'): (n, d) for d in design.findall('srcdef') for n in d.findall('srcinst')}
    def path(k):
        n, _ = nodes[k]
        return (path(n.get('pid'))+'.' if n.get('pid') in nodes else '')+n.get('name')
    modules = {path(k): d for k, (_, d) in nodes.items()}
    definitions = {}
    for d in shape.findall('tgldef'):
        definitions.setdefault((d.get('name').split(' (')[0], d.get('chksum')), []).append(d)
    policy = json.loads((rank.POLICY/'config.json').read_bytes())
    ep = rank.POLICY/'combined.el'
    m.need(m.digest(ep) == policy['pins'][str(ep)], 'Policy EL drift')
    entries, whole = rank.old.el_fields(ep.read_text())
    candidates = []; holds = []
    for g in inventory['top10']:
        field = g['field']
        if field not in ('id_i', 'fmt_outputs[3].tag.operand_a', 'fmt_outputs[4].tag.operand_a'):
            continue
        for row in g['members']:
            s = row['scope']; module = modules[s]
            ds = definitions[(g['module_family'], row['checksum'])]
            m.need(len(ds) == 1 and module.get('chksum') == row['module_checksum'], 'Unique compiled definition')
            d = ds[0]; offset = 0; found = None; protected = []
            for n in d.find('tglshape'):
                if n.tag == 'arrays':
                    protected.append(dict(kind=n.tag, attributes=dict(n.attrib), capacity=None)); continue
                width = 1 if n.tag == 'node' else abs(int(n.get('left'))-int(n.get('right')))+1
                if n.get('name') == field:
                    m.need(found is None, 'Duplicate target'); found = (n, offset)
                else:
                    protected.append(dict(kind=n.tag, attributes=dict(n.attrib), raw_range=[offset, offset+2*width]))
                offset += 2*width
            m.need(found is not None, 'Missing target')
            n, start = found; width = typed_guard(n, field)
            m.need(dict(n.attrib) == row['compiled_attributes'] and row['coordinates'] == list(range(start,start+2*width)),
                   'Actual complete both-direction raw binding')
            if field == 'id_i':
                parent = modules[s.rsplit('.',1)[0]].get('name')
                m.need(parent in ('fpnew_fma', 'fpnew_cast_multi'), 'Unknown rounding caller HOLD')
                reason = dict(caller=parent, connection=".id_i ('0)", width=34)
            else:
                fmt = int(re.search(r'\[(\d+)\]', field)[1]); values = disabled_guard(d, fmt)
                m.need(re.fullmatch(re.escape(m.PREFIX).replace('%d',r'[0-3]')+
                                   r'\.gen_operation_groups\[[0-4]\]\.i_opgroup_block', s), 'Exact reviewed TagType caller')
                m.need('.TagType       (vfpu_tag_t' in texts['vmfpu.sv'], 'TagType connection')
                reason = dict(compiled_parameters=values, format_index=fmt,
                              cast="TagType'(1'b1)", operand_above_low16=True)
            legal = set(range(width)); removed, ambiguous = rank.old.excluded_bits(entries.get((s,field), []), legal)
            if removed or ambiguous or any(s == w or s.startswith(w+'.') for w in whole) or any(
                    owner == s and field.startswith(name+'.') for owner,name in entries):
                holds.append(dict(scope=s, field=field, reason='KNOWN_EL_OWNERSHIP')); continue
            candidates.append(dict(**row, field=field, definition=dict(d.attrib), constant_hex='0x0',
                proof=reason, raw_full_range=[start,start+2*width], logical_bits=list(range(width)),
                both_directions=True, single_direction_serial_order_inferred=False, protected_objects=protected))
    pins[str(Path(__file__).resolve())] = m.digest(__file__)
    test = Path(__file__).with_name('test_prove_fpnew_tied_fields781.py'); pins[str(test)] = m.digest(test)
    m.check_pins(pins)
    return dict(schema='FPNEW_TIED_FIELDS781_STATIC_TYPED_CANDIDATES_V1', population=781,
        status='SOURCE_PROVEN_CANDIDATES_NOT_NATIVE_QUALIFIED', candidates=candidates, hold=holds,
        source_proof=proof, candidate_count=len(candidates), missing_directions=sum(x['raw_missing'] for x in candidates),
        pins=pins, MDA_capacity=None, MDA_not_inferred_from_declarations=True,
        initialization_X_not_waived=True, mixed_dynamic_fields='HOLD', official_denominator=None,
        predicted_percentage_gain=None, EDA_started=False, applied=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    output = p.parse_args().output.resolve()
    m.need(output.parent == m.OUT and not output.exists(), 'Fresh own output only')
    result = collect()
    with output.open('x') as f: json.dump(result, f, separators=(',', ':')); f.write('\n')
    print(json.dumps(dict(output=str(output), SHA=m.digest(output), candidates=result['candidate_count'],
                         missing_directions=result['missing_directions'])))
