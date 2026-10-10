"""Static full-domain FP32 accumulator configuration tie-offs; no EDA/stimulus."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

import audit_qbs_engine_residual766 as q
import review_qbs_residual766_data_semantics as predecessor

BASE = q.OUT / 'qbs-payload-residual4-offline-admitted-767-agent-20261007-01'
BASE_SHA = 'a4dac6fb073fc665cb8f274557d04c8d2bf3ad9291a70bda03bcfdce3542b405'
COMPUTE = q.QBS + '.i_compute_engine'
ACC = COMPUTE + '.i_fp_accumulator'
FP = ACC + '.i_fpnew'
OUT = q.OUT / 'qbs-accumulator-config-constants-source-review767-agent-20261007-01.json'
SOURCE_PATHS = [q.SOURCE_DIR / 'qbs_fp_accumulator.sv', q.SOURCE_DIR / 'qbs_compute_engine.sv',
                q.PKG, q.ROOT / 'hardware/deps/fpnew/src/fpnew_pkg.sv',
                q.ROOT / 'hardware/deps/fpnew/src/fpnew_top.sv',
                q.ROOT / 'hardware/deps/fpnew/src/fpnew_opgroup_block.sv',
                q.ROOT / 'hardware/deps/common_cells/src/rr_arb_tree.sv']


def need(ok, why):
    if not ok: raise ValueError(why)


def source_contract(texts):
    acc = q.clean(texts['qbs_fp_accumulator.sv'])
    need(all(t in acc for t in ("Width:          32", "EnableVectors: 1'b0",
        "EnableNanBox:  1'b0", "FpFmtMask:     6'b100000", "IntFmtMask:    4'b0010",
        '.src_fmt_i      (FP32)', '.dst_fmt_i      (FP32)', '.int_fmt_i      (INT32)',
        ".vectorial_op_i (1'b0)", 'UnitTypes:',
        'fp_round_mode = roundmode_e\'(QbsNumericalRoundingMode);')), 'Frozen FP32 configuration changed')
    ops = re.findall(r'\bfp_operation\s*=\s*(\w+)\s*;', acc)
    need(Counter(ops) == Counter({'I2F': 3, 'MUL': 2, 'FMADD': 2}), 'Operation producer expanded')
    unit_body = acc.split('UnitTypes:', 1)[1].split('PipeConfig:', 1)[0]
    need(re.findall(r'default:\s*(\w+)', unit_body) ==
         ['PARALLEL', 'DISABLED', 'DISABLED', 'MERGED', 'DISABLED'], 'Operation unit mask changed')
    need("localparam logic DONT_CARE = 1'b1;" in texts['fpnew_pkg.sv'], 'Dont-care is not a real literal')
    block = texts['fpnew_opgroup_block.sv']
    for token in ('if (FpFmtMask[fmt] && (FmtUnitTypes[fmt] == fpnew_pkg::PARALLEL))',
                  'end else if (!FpFmtMask[fmt] || (FmtUnitTypes[fmt] == fpnew_pkg::DISABLED))',
                  "assign fmt_outputs[fmt].result  = '{default: fpnew_pkg::DONT_CARE};",
                  "assign fmt_out_valid[fmt] = 1'b0;", '.req_i  ( fmt_out_valid',
                  '.data_i ( fmt_outputs'):
        need(token in block, 'Disabled-format driving cone changed')
    arb = texts['rr_arb_tree.sv']
    for token in ('assign req_d = req_i;',
                  'assign sel =  ~req_d[l*2] | req_d[l*2+1] & rr_q[NumLevels-1-level];',
                  'assign data_nodes[Idx0]  = (sel) ? data_i[l*2+1] : data_i[l*2];',
                  "assign data_nodes[Idx0]  = DataType'('0);",
                  'assign sel =  ~req_nodes[Idx1] | req_nodes[Idx1+1] & rr_q[NumLevels-1-level];',
                  'assign data_nodes[Idx0]  = (sel) ? data_nodes[Idx1+1] : data_nodes[Idx1];'):
        need(token in arb, 'Arbiter propagation formula changed')
    return dict(width=32, formats=['FP32'], integer_formats=['INT32'], vectorial=False,
                operations=sorted(set(ops)), units=['PARALLEL', 'DISABLED', 'DISABLED', 'MERGED', 'DISABLED'],
                rounding='QbsNumericalRoundingMode fixed; no rounding/flag waiver',
                payload_values_unrestricted=True)


def tree(num_in, request_mask, rr, values):
    levels = (num_in - 1).bit_length()
    req = [0] * ((1 << levels) - 1); data = [None] * len(req)
    for level in range(levels - 1, -1, -1):
        for lane in range(1 << level):
            index = (1 << level) - 1 + lane
            if level == levels - 1:
                left = 2 * lane; right = left + 1
                if left >= num_in:
                    data[index] = 0
                elif right >= num_in:
                    req[index] = (request_mask >> left) & 1; data[index] = values[left]
                else:
                    a = (request_mask >> left) & 1; b = (request_mask >> right) & 1
                    sel = (not a) or (b and ((rr >> (levels - 1 - level)) & 1))
                    req[index] = a | b; data[index] = values[right if sel else left]
            else:
                left = (1 << (level + 1)) - 1 + 2 * lane; right = left + 1
                sel = (not req[left]) or (req[right] and ((rr >> (levels - 1 - level)) & 1))
                req[index] = req[left] | req[right]; data[index] = data[right if sel else left]
    return data


def constant_nodes(num_in, active, inactive_value):
    observed = [set() for _ in range((1 << ((num_in - 1).bit_length())) - 1)]
    values = [('ANY_RESULT_' + str(i)) if i in active else inactive_value for i in range(num_in)]
    # Every possible valid mask and every encoded priority, including idle invalid cycles.
    for mask in range(1 << num_in):
        if any((mask >> i) & 1 for i in range(num_in) if i not in active): continue
        for rr in range(1 << ((num_in - 1).bit_length())):
            for i, value in enumerate(tree(num_in, mask, rr, values)): observed[i].add(value)
    return {i: next(iter(v)) for i, v in enumerate(observed) if len(v) == 1 and isinstance(next(iter(v)), int)}


def rule(scope, name):
    if scope == FP:
        m = re.fullmatch(r'opgrp_outputs\[(\d+)\]\.result', name)
        return (0, 'DISABLED_OPGROUP_ROOT_ZERO') if m and int(m[1]) in (1, 2, 4) else None
    if scope == FP + '.i_arbiter':
        m = re.fullmatch(r'gen_arbiter.data_nodes\[(\d+)\]\.result', name)
        constants = constant_nodes(5, {0, 3}, 0)
        return (constants[int(m[1])], 'TOP_TREE_DISABLED_SUBTREE') if m and int(m[1]) in constants else None
    m = re.fullmatch(re.escape(FP) + r'\.gen_operation_groups\[(\d+)\]\.i_opgroup_block(\.i_arbiter)?', scope)
    if not m: return None
    group = int(m[1]); active = {0} if group in (0, 3) else set()
    if m[2]:
        n = re.fullmatch(r'gen_arbiter.data_nodes\[(\d+)\]\.result', name)
        constants = constant_nodes(6, active, 0xffffffff)
        return (constants[int(n[1])], 'FORMAT_TREE_LITERAL_AND_PADDING') if n and int(n[1]) in constants else None
    n = re.fullmatch(r'fmt_outputs\[(\d+)\]\.result', name)
    if n and int(n[1]) not in active: return (0xffffffff, 'DISABLED_FMT_RESULT_LITERAL_ONE')
    if not active and name == 'arbiter_output.result': return (0, 'DISABLED_GROUP_ARBITER_ROOT_ZERO')
    return None


def collect():
    a = predecessor.load_verified(); pins = {str(predecessor.AUDIT): predecessor.AUDIT_SHA, **a['pins']}
    book = q.load(q.f.BUILD / 'build-source-pins.json')
    texts = {}
    for p in SOURCE_PATHS:
        need(q.digest(p) == book[str(p)], 'Frozen source mismatch: ' + str(p))
        pins[str(p)] = book[str(p)]; texts[p.name] = p.read_text()
    domain = source_contract(texts)
    manifest = q.load(BASE / 'admission-manifest.json', BASE_SHA)
    pins[str(BASE / 'admission-manifest.json')] = BASE_SHA
    ledger = BASE / 'combined-inputs.txt'; pins[str(ledger)] = q.digest(ledger)
    need(pins[str(ledger)] == manifest['output_pins'][str(ledger)] and manifest['coverage_admitted'], 'Not admitted767')
    old = (q.BASE / 'combined-inputs.txt').read_text().splitlines(); new = ledger.read_text().splitlines()
    need(new[:-1] == old and len(new) == len(set(new)) == 768, 'Not exact766 prefix plus one admitted test')
    files = list((Path(new[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(files) == 1 and q.digest(files[0]) == manifest['input_pins'][str(files[0])], 'New native bitmap pin mismatch')
    pins[str(files[0])] = q.digest(files[0])
    scopes = q.bind_scopes(q.f.xml(q.DB / 'design/verilog.design.xml'), q.f.xml(q.DB / 'shape/tgl.verilog.info.xml'),
                          q.f.xml(q.DB / 'shape/tgl.verilog.shape.xml'))
    summaries = {p['scope']: p for p in a['scope_summaries']}
    rows = {s: dict(width=p['raw_width'], checksum=p['checksum'], bits=p['bits']) for s, p in summaries.items()
            if s == COMPUTE or s == ACC or s.startswith(ACC + '.')}
    found = set()
    with gzip.open(files[0], 'rb') as stream:
        for _, node in ET.iterparse(stream, events=('end',)):
            if node.tag != 'instance_data': continue
            s = node.get('name')
            if s in rows:
                value = node.get('value')
                need(s not in found and node.get('chksum') == rows[s]['checksum'] and len(value) == rows[s]['width']
                     and not set(value) - {'0', '1'}, '767 exact bitmap identity mismatch')
                rows[s]['bits'] = hex(int(rows[s]['bits'], 16) | int(value, 2)); found.add(s)
            node.clear()
    need(found == set(rows), 'Missing selected full compiled scopes')
    # Prove emitted active/disabled shapes independently of live bitmap values.
    for group in range(5):
        s = FP + '.gen_operation_groups[%d].i_opgroup_block' % group
        params = summaries[s]['integer_parameters']
        need(params['FpFmtMask'] == 32 and params['Width'] == 32 and params['EnableVectors'] == 0
             and params['FmtUnitTypes'] == (1365 if group == 0 else 2730 if group == 3 else 0), 'Compiled feature/unit mask mismatch')
        children = [p for p in summaries if p.startswith(s + '.') and
                    summaries[p]['module'] in ('fpnew_opgroup_fmt_slice', 'fpnew_opgroup_multifmt_slice')]
        need(len(children) == (1 if group in (0, 3) else 0), 'Unexpected instantiated numerical slice')
        arb = summaries[s + '.i_arbiter']['integer_parameters']
        need((arb['NumIn'], arb['LockIn'], arb['ExtPrio']) == (6, 0, 0), 'Arbiter locked/external alternate branch')
    need(summaries[FP + '.i_arbiter']['integer_parameters']['NumIn'] == 5, 'Top opgroup count mismatch')
    sources = {p.get('id'): Path(p.get('name')) for p in q.f.xml(q.DB / 'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
    records = []; arrays = []; candidates = []; ranked_scopes = []
    for s in sorted(rows):
        typed, memory = q.fields(scopes[s]['definition'], rows[s])
        ranked_scopes.append(dict(scope=s, module=scopes[s]['module'], missing=sum(p['missing'] for p in typed),
                                  raw_positions=rows[s]['width'], typed_objects=len(typed), arrays=len(memory)))
        for p in typed + memory:
            p['name'] = p['attributes']['name']
            p.update(scope=s, module=scopes[s]['module'], checksum=rows[s]['checksum'],
                     design_checksum=summaries[s]['design_checksum'])
            attrs = p['attributes']; file = sources[attrs.get('aux_file', attrs['file'])]
            line = int(attrs.get('aux_line_num', attrs['line_num']))
            need(q.digest(file) == book[str(file)], 'Actual field declaration pin mismatch')
            pins[str(file)] = book[str(file)]
            p['declaration_binding'] = dict(path=str(file), sha256=book[str(file)], line=line,
                                            text=file.read_text().splitlines()[line - 1])
            p['type_origin'] = dict(path=str(sources[attrs['file']]), line=int(attrs['line_num']))
            if p['kind'] == 'arrays': arrays.append(p); continue
            records.append(p)
            eligible = rule(s, p['name'])
            if eligible is not None:
                need(p['kind'] == 'vectornode' and p['width'] == 32 and attrs['left'] == '31' and attrs['right'] == '0'
                     and attrs['portnode'] == '0' and attrs['excluded'] == '0' and p['missing'] == 64,
                     'Configuration result candidate shape/observed toggle contradiction')
                candidates.append(dict(p, constant_value=hex(eligible[0]), source_reason=eligible[1], range=[31, 0]))
    keys = {(p['scope'], p['name']) for p in candidates}
    canonical_path = q.OUT / 'native-batch-full766-agent-20261007-01/applied.el'
    closure_path = q.OUT / 'native-batch-full766-offline-closure-agent-20261007-01/qualification.json'
    closure_sha = '0ed4bbb08ea2dda3ad7b8472698d7ee7964c54db3c3dc0d150284ee40e20d5e8'
    closure = q.load(closure_path, closure_sha)
    canonical_sha = closure['output_pins'][str(canonical_path)]
    need(q.digest(canonical_path) == canonical_sha, 'Prior canonical EL drift')
    pins[str(closure_path)] = closure_sha; pins[str(canonical_path)] = canonical_sha
    canonical_members = set(); current_scope = None
    for line in canonical_path.read_text().splitlines():
        if line.startswith('INSTANCE:'): current_scope = line.split(':', 1)[1].strip()
        match = re.match(r'Toggle (?:(?:0to1|1to0) )?([^\s"]+)', line)
        if match: canonical_members.add((current_scope, match[1]))
    need(not keys.intersection(canonical_members), 'Already-qualified canonical field overlap')
    protected = [p for p in records if (p['scope'], p['name']) not in keys]
    ranked_scopes.sort(key=lambda p: (-p['missing'], p['scope']))
    ranking = sorted(records, key=lambda p: (-p['missing'], -p['width'], p['scope'], p['name']))
    handoff = q.OUT / 'qbs-positive-power-scale-helmholtz-handoff767-agent-20261007-01.json'
    pins[str(handoff)] = q.digest(handoff)
    need(pins[str(handoff)] == '8ed2613ce28bf48cda3334a3994fa80cf1b926038a8a996539f025b5103f38cd', 'Parent entropy handoff drift')
    return dict(status='QBS_FP32_DISABLED_RESULT_MUX_CONSTANT_SOURCE_REVIEW767_NO_EDA', population=767,
        source_legal_domain=domain, ranking_scopes=ranked_scopes, top50_typed_objects=ranking[:50],
        candidate_objects=len(candidates), candidate_source_bits=sum(p['width'] for p in candidates),
        candidate_missing_serialized_positions=sum(p['missing'] for p in candidates), candidates=candidates,
        already_qualified766_canonical_overlap=0,
        protected_objects=len(protected), protected_full_complement=protected, protected_arrays=arrays,
        tree_enumeration=dict(format_active0=constant_nodes(6, {0}, 0xffffffff),
                              format_all_disabled=constant_nodes(6, set(), 0xffffffff),
                              top_active0_3=constant_nodes(5, {0, 3}, 0)),
        protected_policy=['All new QBS accumulator/compute logic', 'All status/fflags members even on disabled branches',
                          'All rounding, NaN/Inf/subnormal/overflow/underflow handling', 'All arbitration control/tag/handshake',
                          'All interfaces/ports', 'Live format0 result muxes and all legal numerical values'],
        fp_operands_mda=[p for p in arrays if p['scope'] == ACC and p['name'] == 'fp_operands'],
        source_conclusion='Prioritize exact config-literal data fields, not another low-entropy VCS run. Request parent review before native qualification.',
        not_claimed='Raw bit coordinates are diagnostic capacity, not native DVE denominator or measured percentage gain.',
        no_simulation=True, no_EDA=True, native_qualified=False, coverage_admitted=False, pins=pins)


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.texts = {p.name: p.read_text() for p in SOURCE_PATHS}

    def test_real_configuration_and_source_domain(self): source_contract(self.texts)

    def test_added_operation_or_format_rejected(self):
        for suffix in ('\nfp_operation = DIV;\n',):
            changed = dict(self.texts); changed['qbs_fp_accumulator.sv'] += suffix
            with self.assertRaises(ValueError): source_contract(changed)
        changed = dict(self.texts)
        changed['qbs_fp_accumulator.sv'] = changed['qbs_fp_accumulator.sv'].replace("6'b100000", "6'b110000")
        with self.assertRaises(ValueError): source_contract(changed)

    def test_x_literal_or_arbiter_formula_change_rejected(self):
        for name, old, new in [('fpnew_pkg.sv', "DONT_CARE = 1'b1;", "DONT_CARE = 1'bx;"),
                               ('rr_arb_tree.sv', 'assign req_d = req_i;', "assign req_d = '1;")]:
            changed = dict(self.texts); changed[name] = changed[name].replace(old, new)
            with self.assertRaises(ValueError): source_contract(changed)

    def test_arbiter_all_requests_priorities_and_unbounded_data(self):
        self.assertEqual(constant_nodes(6, {0}, 0xffffffff), {2: 0, 4: 0xffffffff, 5: 0xffffffff, 6: 0})
        self.assertEqual(constant_nodes(6, set(), 0xffffffff),
                         {0: 0, 1: 0xffffffff, 2: 0, 3: 0xffffffff, 4: 0xffffffff, 5: 0xffffffff, 6: 0})
        self.assertEqual(constant_nodes(5, {0, 3}, 0), {2: 0, 5: 0, 6: 0})
        self.assertNotIn(0, constant_nodes(6, {0}, 0xffffffff))
        self.assertNotIn(4, constant_nodes(6, {0, 3}, 0xffffffff))

    def test_protected_flags_active_format_and_new_algorithm(self):
        for scope, name in [(FP + '.gen_operation_groups[0].i_opgroup_block', 'fmt_outputs[0].result'),
                            (FP + '.i_arbiter', 'gen_arbiter.data_nodes[0].result'),
                            (ACC, 'fp_status.NV'), (ACC, 'entry_dot_value_q'),
                            (COMPUTE, 'phase_q')]: self.assertIsNone(rule(scope, name))

    def test_actual_latest767_typed_shape_and_partition(self):
        result = collect()
        self.assertEqual(result['candidate_objects'], 66)
        self.assertEqual(result['candidate_missing_serialized_positions'], 4224)
        self.assertTrue(all(p['attributes']['portnode'] == '0' for p in result['candidates']))
        self.assertFalse(result['native_qualified'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test: unittest.main(argv=[__file__], verbosity=2)
    else:
        result = collect(); result['pins'][str(Path(__file__).resolve())] = q.digest(__file__)
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        print(json.dumps(dict(output=str(OUT), sha256=q.digest(OUT), objects=result['candidate_objects'],
                             missing=result['candidate_missing_serialized_positions'])))
