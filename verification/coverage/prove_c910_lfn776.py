"""Exact compiled LFN logical bits; no raw orientation inference/native approval."""
import argparse
import json
from pathlib import Path
import re
import review_c910_top776 as review
import audit_remaining_toggle776 as audit

t, ROOT, OUT = review.t, review.ROOT, review.OUT


def source_guard(text):
    expected = {
        'ex4_doub_lfn': "{vfdsu_ex4_result_sign,11'h7fe,{52{1'b1}}}",
        'ex4_sing_lfn': "{32'hffffffff,vfdsu_ex4_result_sign,8'hfe,{23{1'b1}}}",
        'ex4_half_lfn': "{48'hffffffffffff,vfdsu_ex4_result_sign,5'h1e,{10{1'b1}}}",
        'ex4_bfloat_lfn': "{48'hffffffffffff,vfdsu_ex4_result_sign,8'hfe,{7{1'b1}}}",
        'ex4_rst_lfn': '(vfdsu_ex4_double)?ex4_doub_lfn[63:0]:vfdsu_ex4_single?ex4_sing_lfn[63:0]:vfdsu_ex4_half?ex4_half_lfn[63:0]:ex4_bfloat_lfn[63:0]',
    }
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    assignments = {}
    for name, expression in expected.items():
        actual = re.findall(r'\bassign\s+' + name + r'\s*\[63:0\]\s*=\s*([^;]+);', clean)
        t.require(len(actual) == 1 and re.sub(r'\s+', '', actual[0]) == expression, 'Exact LFN source expression: ' + name)
        assignments[name] = expression
    return assignments


def old_el_difference(mask, entries):
    logical = {bit for bit in range(64) if mask >> bit & 1}
    removed, single = audit.excluded_bits(entries, set(range(64)))
    return sorted(logical - removed - single), sorted(logical & removed), sorted(logical & single)


def collect():
    pins = {}
    def read(path, sha, binary=False):
        t.require(t.digest(path) == sha, 'Frozen input drift: ' + str(path)); pins[str(path)] = sha
        return path.read_bytes() if binary else path.read_text()
    config = json.loads(read(review.CONFIG, review.CONFIG_SHA))
    rank = json.loads(read(review.RANK, review.RANK_SHA))
    pack_path = ROOT / 'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_pack.v'
    expressions = source_guard(read(pack_path, config['pins'][str(pack_path)]))
    # Numeric model is checked against those exact concatenations, not floating-point conversion.
    t.require(review.LFN == {'FP64': (0x7fefffffffffffff, 63), 'FP32': (0xffffffff7f7fffff, 31),
                           'FP16': (0xffffffffffff7bff, 15), 'BF16_DEFAULT': (0xffffffffffff7f7f, 15)}, 'Exact numeric LFN model')
    shape_path = Path(next(p for p in rank['pins'] if p.endswith('tgl.verilog.shape.xml')))
    read(shape_path, rank['pins'][str(shape_path)], True); shape = t.xml(shape_path)
    params = {}
    for definition in shape.findall('tgldef'):
        name = definition.get('name', '')
        if not name.startswith('fpnew_divsqrt_th_64_multi '): continue
        fmt = int(re.search(r'FpFmtConfig=(\d+)', name)[1]); width = int(re.search(r'\bWIDTH=(\d+)', name)[1])
        t.require(fmt in review.FORMATS and width == {56: 64, 40: 32, 8: 16}[fmt], 'Exact parent format parameters')
        for instance in definition:
            if instance.tag == 'tglshape': continue
            params[instance.get('name')] = dict(format_mask=fmt, width=width, compiled_definition=name,
                wrapper_toggle_checksum=definition.get('chksum'))
    el_path = review.CONFIG.parent / 'combined.el'
    text = read(el_path, config['pins'][str(el_path)])
    t.require(audit.policy.records(text, config) == config['expected_union'], 'Exact approved775 canonical union')
    fields, whole = audit.el_fields(text)
    lfn = next(g for g in rank['top10'] if g['field'] == 'ex4_rst_lfn')
    result = []
    for member in lfn['members']:
        scope = member['scope']; parent = scope.split('.i_ct_vfdsu_top.')[0]
        t.require(parent in params and member['bounds'] == [63, 0], 'Exact LFN instance and bounds')
        matches = [d for d in shape.findall('tgldef') if d.get('chksum') == member['toggle_checksum'] and d.get('name', '').split(' (')[0] == 'ct_vfdsu_pack']
        t.require(len(matches) == 1, 'Unique compiled pack checksum')
        nodes = [n for n in matches[0].find('tglshape') if n.get('name') == 'ex4_rst_lfn']
        t.require(len(nodes) == 1 and nodes[0].tag == 'vectornode' and dict(nodes[0].attrib) == member['compiled_attributes'] and nodes[0].get('portnode') == '0', 'Exact internal typed LFN field')
        active_mask, active_ones = review.lfn_mask(review.FORMATS[params[parent]['format_mask']], False)
        mask, ones = review.lfn_mask(review.FORMATS[params[parent]['format_mask']], True)
        t.require(not any(bits == 'MDA_HOLD' for direction, bits, typ in fields.get((scope, 'ex4_rst_lfn'), [])), 'No inferred array selector')
        remaining, old, held = old_el_difference(mask, fields.get((scope, 'ex4_rst_lfn'), []))
        if scope in whole: old, remaining = sorted(set(old) | set(remaining)), []
        result.append(dict(scope=scope, native_label=member['native_label'], parameters=params[parent],
            compiled_typed=dict(nodes[0].attrib), pack_toggle_checksum=member['toggle_checksum'],
            enabled_mask=hex(active_mask), enabled_ones=hex(active_ones), conservative_mask=hex(mask), constant_ones=hex(ones),
            old_EL_both_directions_bits=old, old_EL_single_direction_HOLD_bits=held,
            source_candidate_logical_bits=remaining, reset_default='bfloat mux arm, both signs conservatively allowed',
            protection_bits=sorted(set(range(64)) - set(remaining)),
            missing_raw_slots_for_field_context_only=member['raw_missing_slots'],
            raw_slot_mapping=None, native_bitselection_qualified=False))
    t.require(len(result) == 17 and sum(r['parameters']['width'] == 64 for r in result) == 5 and
              sum(r['parameters']['width'] == 32 for r in result) == 4 and sum(r['parameters']['width'] == 16 for r in result) == 8, 'Exact seventeen source instances')
    for path in [Path(__file__), Path(__file__).with_name('test_prove_c910_lfn776.py'), Path(review.__file__), Path(audit.__file__)]:
        pins[str(path.resolve())] = t.digest(path)
    for p, sha in pins.items(): t.require(t.digest(p) == sha, 'Read-end source drift')
    return dict(status='SOURCE_COMPILED_LOGICAL_LFN_BITS_NOT_NATIVE_QUALIFIED_NOT_WAIVER', instances=result,
        source_assignments=expressions, pins=pins, initial_X_excluded=False, transient_sampling_excluded=False,
        EL_generated=False, EDA_launched=False, new_missing_directions=None, official_percentage=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output; result = collect()
    with out.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(output=str(out), sha=t.digest(out), instances=len(result['instances']),
        candidate_logical_bits=sum(len(r['source_candidate_logical_bits']) for r in result['instances']), native_qualified=False)))
