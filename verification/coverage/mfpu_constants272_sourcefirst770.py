"""Closed source-first batch for result176 plus internal operand96; never EDA."""
import argparse
import ast
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
CONFIG = OUT / 'mfpu-constants272-sourcefirst770-candidate-agent-20261007-01/config.json'
RESULT = OUT / 'mfpu-disabled-format-results176-source-review770-agent-20261007-01.json'
OPERAND = OUT / 'rr-unused-operand96-source-review770-agent-20261007-01.json'
RESULT_SHA = '98facbe20931f12f59cb80d798d224ae498e56c5522be741d7c28d3879207094'
OPERAND_SHA = '0804ba6e70ee2770a3600613c6f781936670ed951532ab8a4f1ba43b9e89ac25'
KEY = 'mfpu_constants272'
PREFIX = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_vfus.i_vmfpu.fpu_gen.i_fpnew_bulk'
SOURCE = ['hardware/src/lane/vmfpu.sv', 'hardware/deps/fpnew/src/fpnew_pkg.sv',
          'hardware/deps/fpnew/src/fpnew_top.sv', 'hardware/deps/fpnew/src/fpnew_opgroup_block.sv',
          'hardware/deps/common_cells/src/rr_arb_tree.sv']


def need(ok, why):
    if not ok:
        raise ValueError(why)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_pins(pins):
    for path, sha in pins.items():
        need(digest(path) == sha, 'Pinned input drift: ' + path)


def xml(path):
    raw = path.read_bytes()
    return ET.fromstring(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)


def function(path, name, environment=None):
    node = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    env = dict(environment or {})
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), env)
    return env[name]


def semantic_proof(texts):
    v, pkg, top, block, arb = (texts[Path(p).name] for p in SOURCE)
    units = v.split('localparam fpu_implementation_t FPUImplementation', 1)[1].split('PipeConfig:', 1)[0]
    need(re.findall(r'default:\s*(\w+)', units.split('UnitTypes:', 1)[1]) ==
         ['PARALLEL', 'MERGED', 'PARALLEL', 'MERGED', 'DISABLED'], 'Active producer domain changed')
    need("localparam logic DONT_CARE = 1'b1;" in pkg, 'Placeholder literal changed')
    need(re.search(r'elen_t operand_a;\s*strb_t flag_mask;\s*strb_t control;\s*}\s*vfpu_tag_t', v),
         'Packed operand position changed')
    need(block.count("assign fmt_outputs[fmt].tag     = TagType'(fpnew_pkg::DONT_CARE);") == 2,
         'Scalar packed tag cast changed')
    need(block.count("assign fmt_outputs[fmt].result  = '{default: fpnew_pkg::DONT_CARE};") == 2,
         'Result literal drivers changed')
    for token in ('.Implementation(FPUImplementation)',):
        need(token in re.sub(r'\s+', '', v), 'Actual implementation forwarding changed')
    for token in ('.FmtUnitTypes  ( Implementation.UnitTypes[opgrp] )',
                  '.FpFmtMask     ( Features.FpFmtMask', '.tag_o           ( opgrp_outputs[opgrp].tag',
                  '.req_i  ( opgrp_out_valid', '.data_i ( opgrp_outputs'):
        need(token in top, 'Actual top producer forwarding changed')
    for token in ('.req_i  ( fmt_out_valid', '.data_i ( fmt_outputs', '.data_o ( arbiter_output',
                  "assign fmt_out_valid[fmt] = 1'b0;"):
        need(token in block, 'Actual format producer forwarding changed')
    for token in ('assign req_d = req_i;', "assign data_nodes[Idx0]  = DataType'('0);",
                  'assign data_nodes[Idx0]  = (sel) ? data_i[l*2+1] : data_i[l*2];',
                  'assign data_nodes[Idx0]  = (sel) ? data_nodes[Idx1+1] : data_nodes[Idx1];'):
        need(token in arb, 'Pinned tree propagation changed')
    return {'unit_types': ['PARALLEL', 'MERGED', 'PARALLEL', 'MERGED', 'DISABLED'],
            'enabled_format_indices': [0, 1, 2], 'operand_cast_constant': 0,
            'reason': 'Packed scalar cast1 zero extends; operand_a is above16 flag_mask/control bits. No active tag operand is constant.'}


def constants(tree, num, active, inactive, disabled_requests_zero=False):
    values = ['ANY_ACTIVE_' + str(i) if i in active else inactive for i in range(num)]
    seen = [set() for _ in range((1 << ((num - 1).bit_length())) - 1)]
    # Result placeholders need the source's disabled-valid tie-off; zero tags do not.
    for requests in range(1 << num):
        if disabled_requests_zero and any(requests & (1 << i) for i in range(num) if i not in active):
            continue
        for priority in range(1 << ((num - 1).bit_length())):
            for index, value in enumerate(tree(num, requests, priority, values)):
                seen[index].add(value)
    return {i: next(iter(s)) for i, s in enumerate(seen)
            if len(s) == 1 and isinstance(next(iter(s)), int)}


def parameters(definition, expected):
    text = definition.get('param', definition.get('name'))
    for key, value in expected.items():
        need(re.search(r'\b' + key + '=' + str(value) + r'(?=[, )])', text),
             'Compiled specialization changed: ' + key)


def target_guard(node):
    need((node['kind'], node['type'], node['portnode'], node['excluded'], node['left'], node['right']) ==
         ('vectornode', '1', '0', '0', '63', '0'), 'Only exact internal64 vectors')
    need(node['name'].endswith('.result') or node['name'].endswith('.tag.operand_a'),
         'No control/status/flag/port promotion')


def contract(c):
    need(c['key'] == KEY and c['population'] == 770 and
         c['qualification_origin'] == 'SOURCE_PROVEN_FIRST_FULL_SESSION', 'Closed source role')
    need(c['binding_state'] == 'FRESH_COMPLETE_BEFORE_REQUIRED' and
         all(c[k] is False for k in ('local_qualified', 'ready_for_union', 'population_application',
                                     'launch_authorized', 'EDA_launched')), 'No source-to-native promotion')
    need(all(c[k] is None for k in ('native_reference', 'native_targets', 'el', 'qualification_seal',
                                    'official_percentage')), 'No guessed native authority')
    need(len(c['instances']) == 44, 'Exact44 scopes')
    ids = set()
    for inst in c['instances']:
        targets = {n['name'] for n in inst['targets']}
        protected = {n['name'] for n in inst['protected']}
        need(not targets & protected and len(targets) + len(protected) ==
             inst['expected_compiled_typed_objects'], 'Full typed complement partition')
        for n in inst['targets']:
            target_guard(n['attributes'])
            need(n['native_label'] is None and n['logical_bits'] == 64 and
                 n['missing_slots'] == 128, 'Fresh native binding required')
            identity = (inst['scope'], n['name'])
            need(identity not in ids, 'Duplicate target'); ids.add(identity)
    need(len(ids) == 272 and c['candidate_bits'] == 17408 and
         c['missing_serialized_positions'] == 34816, 'Exact272 union')
    need(all(x['all_fields_protected'] for x in c['protected_children']), 'Child guard loss')
    return c


def collect():
    need(digest(RESULT) == RESULT_SHA and digest(OPERAND) == OPERAND_SHA, 'Source review seal drift')
    result, operand = (json.loads(p.read_bytes()) for p in (RESULT, OPERAND))
    need(result['baseline'] == operand['population'] == 770 and
         not result['native_qualified'] and not operand['native_qualified'] and
         not result['coverage_admitted'] and not operand['coverage_admitted'], 'Source-only predecessors')
    pins = {}
    for record in (result, operand):
        for path, sha in record['pins'].items():
            need(path not in pins or pins[path] == sha, 'Pin closure conflict'); pins[path] = sha
    pins.update({str(RESULT): RESULT_SHA, str(OPERAND): OPERAND_SHA})
    db = OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db'
    for path in (db/'shape/tgl.verilog.info.xml', Path(__file__).resolve(),
                 Path(__file__).with_name('test_mfpu_constants272_sourcefirst770.py')):
        pins[str(path)] = digest(path)
    check_pins(pins)
    proof = semantic_proof({Path(p).name: (ROOT/p).read_text() for p in SOURCE})
    tree = function(ROOT/'verification/coverage/review_qbs_accum_config_constants767.py', 'tree')
    groups = {g: {0, 1, 2} if g in (0, 2) else {0} if g in (1, 3) else set() for g in range(5)}
    zero = {g: constants(tree, 6, active, 0) for g, active in groups.items()}
    ones = {g: constants(tree, 6, active, (1 << 64)-1, True) for g, active in groups.items()}
    top_zero = constants(tree, 5, {0, 1, 2, 3}, 0)
    need(constants(tree, 6, set(range(6)), 0) == {6: 0} and
         constants(tree, 5, set(range(5)), 0) == {6: 0}, 'Active producer negative regression')
    shape, info, design = (xml(db/p) for p in
                          ('shape/tgl.verilog.shape.xml', 'shape/tgl.verilog.info.xml', 'design/verilog.design.xml'))
    defs = {(d.get('name').split(' (')[0], d.get('chksum')): d for d in shape.findall('tgldef')}
    checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data')}
    sources = {n.get('id'): n.get('name') for n in xml(db/'auxiliary/verilog.sourceinfo.xml').iter('fileinfo')}
    nodes = {n.get('id'): (n, m) for m in design.findall('srcdef') for n in m.findall('srcinst')}
    def scope(key):
        n, _ = nodes[key]; parent = n.get('pid')
        return (scope(parent) + '.' if parent in nodes else '') + n.get('name')
    hierarchy = {scope(k): m for k, (_, m) in nodes.items()}
    audit_path = OUT/'toggle-outside-prepared-union770-static-agent-20261007-01.json'
    audit = json.loads(audit_path.read_bytes())
    actual = {s['scope']: s for s in audit['scopes']}
    picked = defaultdict(dict)
    for n in result['candidates']:
        picked[n['scope']][n['name']] = n['constant_hex']
    for row in operand['target_records']:
        for index, _, _ in row['selected_node_and_missing_coordinate_ranges']:
            name = 'gen_arbiter.data_nodes[%d].tag.operand_a' % index
            need(name not in picked[row['scope']], 'Predecessor overlap')
            picked[row['scope']][name] = '0x0'
    parser = function(ROOT/'verification/coverage/audit_toggle_stimulus769.py', 'exclusions',
                      {'re': re, 'require': need})
    for path in [Path(p) for p in pins if p.endswith('/combined.el') or p.endswith('/first.el')]:
        fields, whole = parser(path.read_text())
        need(not any((s, n) in fields for s in picked for n in picked[s]) and
             not any(s == w or s.startswith(w+'.') for s in picked for w in whole), 'Prepared EL overlap')
    instances = []
    for s, selected in sorted(picked.items()):
        match = re.fullmatch(re.escape(PREFIX).replace('%d', r'(\d+)') +
                             r'(?:\.gen_operation_groups\[(\d+)\]\.i_opgroup_block)?(\.i_arbiter)?', s)
        need(match and int(match[1]) in range(4), 'Exact vector MFPU scope')
        group = int(match[2]) if match[2] is not None else None
        arbiter = bool(match[3]); need(group is not None or arbiter, 'No wrapper target')
        row = actual[s]; mod = hierarchy[s]; chk = checks[s]
        need(chk == row['checksum'], 'Compiled info/actual checksum identity')
        d = defs[row['module'], chk]
        if arbiter:
            parameters(d, {'NumIn': 5 if group is None else 6, 'ExtPrio': 0,
                           'AxiVldRdy': 1, 'LockIn': 0, 'IdxWidth': 3})
        else:
            parameters(d, {'OpGroup': group, 'Width': 64, 'FpFmtMask': 56,
                           'FmtUnitTypes': 0 if group == 4 else 1365 if group in (0, 2) else 2730,
                           'NUM_FORMATS': 6})
        typed = [{'kind': n.tag, **n.attrib, 'compiled_xml': ET.tostring(n, encoding='unicode')}
                 for n in d.find('tglshape')]
        by_name = {n['name']: n for n in typed}
        need(len(by_name) == len(typed), 'Duplicate compiled typed name')
        residual = {n['name']: n for n in row['objects']}
        targets = []
        for name, value in sorted(selected.items()):
            n = by_name[name]; target_guard(n); raw = residual[name]
            need(raw['missing_slots'] == 128 and raw['missing_coordinates'] ==
                 list(range(raw['serialized_offset'], raw['serialized_offset']+128)), 'Exact actual770 whole field missing')
            operand_field = name.endswith('.tag.operand_a')
            if arbiter:
                index = int(re.fullmatch(r'gen_arbiter\.data_nodes\[(\d+)\].*', name)[1])
                expected = top_zero if group is None else zero[group] if operand_field else ones[group]
                need(index in expected and int(value, 16) == expected[index], 'Independent tree constant mismatch')
            else:
                fmt = re.fullmatch(r'fmt_outputs\[(\d+)\]\.result', name)
                need((fmt and int(fmt[1]) not in groups[group] and int(value, 16) == (1 << 64)-1) or
                     (name == 'arbiter_output.result' and group == 4 and int(value, 16) == 0), 'Literal producer target mismatch')
            decl = ROOT/('hardware/src/lane/vmfpu.sv' if operand_field else 'hardware/deps/fpnew/src/fpnew_opgroup_block.sv')
            storage = ROOT/('hardware/deps/common_cells/src/rr_arb_tree.sv' if arbiter else 'hardware/deps/fpnew/src/fpnew_opgroup_block.sv')
            need(sources[n['file']] == str(decl) and int(n['line_num']) == (943 if operand_field else 72) and
                 sources[n['aux_file']] == str(storage) and int(n['aux_line_num']) ==
                 (126 if arbiter else 223 if name == 'arbiter_output.result' else 80), 'Exact type/storage source binding')
            targets.append({'name': name, 'attributes': n, 'constant_hex': value, 'logical_bits': 64,
                            'missing_slots': 128, 'missing_coordinate_range': [raw['serialized_offset'], raw['serialized_offset']+127],
                            'source_type_file': str(decl), 'source_storage_file': str(storage), 'native_label': None})
        instances.append({'scope': s, 'module': row['module'], 'toggle_checksum': chk,
                          'design_module_checksum': mod.get('chksum'), 'compiled_parameters': d.get('param', d.get('name')),
                          'targets': targets, 'protected': [n for n in typed if n['name'] not in selected],
                          'expected_compiled_typed_objects': len(typed), 'expected_compiled_arrays': sum(n['kind'] == 'arrays' for n in typed),
                          'native_row_count': None})
    children = []
    for s, mod in sorted(hierarchy.items()):
        if s in picked or not any(s.startswith(p+'.') for p in picked): continue
        chk = checks.get(s)
        children.append({'scope': s, 'module': mod.get('name'), 'design_module_checksum': mod.get('chksum'),
                         'toggle_checksum': chk, 'all_fields_protected': True,
                         'typed_definition_required': chk is not None})
    config = {'schema': 'MFPU_CONSTANTS272_SOURCEFIRST770_CANDIDATE_V1', 'key': KEY, 'population': 770,
              'qualification_origin': 'SOURCE_PROVEN_FIRST_FULL_SESSION', 'binding_state': 'FRESH_COMPLETE_BEFORE_REQUIRED',
              'source_reviews': {str(RESULT): RESULT_SHA, str(OPERAND): OPERAND_SHA}, 'source_proof': proof,
              'symbolic_constants': {'format_result': ones, 'format_operand': zero, 'top_operand': top_zero,
                  'domain': 'All priorities0..7 and independent unrestricted active symbols. Result tree: every permitted request mask, disabled request bits0 by two literal fmt_out_valid drivers. Operand tree: every request mask including inactive requests. Includes idle/invalid/reset/flush cycles.'},
              'instances': instances, 'protected_children': children,
              'candidate_bits': 17408, 'missing_serialized_positions': 34816, 'prepared_overlap_positions': 0,
              'predecessor_status': 'Both source-only; no native/application receipt. Checked sealed combined768/LZC EL disjoint; no claim about unsealed concurrent Hooke preparation.',
              'local_qualified': False, 'qualification_seal': None, 'ready_for_union': False,
              'population_application': False, 'launch_authorized': False, 'EDA_launched': False,
              'native_reference': None, 'native_targets': None, 'el': None, 'official_percentage': None,
              'integration': {'owner': 'Hooke; handoff only, no existing registry/report/tool modified',
                  'closed_successor_registry_key': KEY, 'existing_registry_acceptance_not_assumed': True,
                  'before': 'Fresh full44-scope actual native inventory, all typed arrays and exact dimensions, exact root token/fullscope/checksum/type/storage source metadata; bijection with pinned compiled inventory. Bind native labels only from actual rows; all listed descendants protected.',
                  'qualification': 'Single isolated initial/apply/reset/reload/final group272 in next full session. All non-target excluded flags0 throughout; initial/reset/final target flags0; apply/reload exact targets only. Save native typed EL each applicable stage; exact whole object or complete two-direction pair, no partial/duplicate/mixed/extra members. Then separately apply union and check canonical difference.',
                  'protected': 'ALL interfaces/control/grants/priority/routing/storage/rounding/flags and active arithmetic values/tags remain untouched. No wholemodule or output-port exception.',
                  'gate': 'Terminal0 without timeout plus complete five-stage inventory/EL/complement verification required; otherwise preserve rejects and HOLD. No local launch/retry authority here.',
                  'coordination': 'Hooke deduplicate both prior seals against new batch receipts before integration; if already prepared elsewhere, use one owner/canonical family only. Do not touch active770 or padding51 sessions.'},
              'pins': pins}
    contract(config); check_pins(pins)
    return config


def verify(seal):
    need(digest(CONFIG) == seal, 'Exact config seal required')
    saved = contract(json.loads(CONFIG.read_bytes())); check_pins(saved['pins'])
    need(saved == json.loads(json.dumps(collect())), 'Independent source/config replay differs')
    return saved


def family(seal):
    c = verify(seal)
    return {'config': c, 'qualification_origin': c['qualification_origin'], 'local_qualified': False,
            'ready_for_union': False, 'reference': None, 'native_targets': None, 'el': None,
            'source_pins': c['pins'], 'reference_pins': {}, 'qualification_seal': None,
            'signals': {i['scope']: [n['name'] for n in i['targets']] for i in c['instances']}}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('mode', choices=['prepare', 'verify'])
    p.add_argument('--seal'); args = p.parse_args()
    if args.mode == 'prepare':
        need(not CONFIG.exists(), 'Fresh source-first output only'); c = collect()
        CONFIG.parent.mkdir(exist_ok=False); CONFIG.write_text(json.dumps(c, indent=2, sort_keys=True)+'\n')
        print(json.dumps({'config': str(CONFIG), 'seal': digest(CONFIG), 'pins': len(c['pins']),
                          'scopes': len(c['instances']), 'fields': 272, 'protected_children': len(c['protected_children']),
                          'native_binding': 'FRESH_BEFORE_REQUIRED', 'EDA_launched': False}))
    else:
        need(args.seal, 'Required pinned seal'); verify(args.seal)
        print('SOURCEFIRST272_VERIFY_PASS_NATIVE_QUALIFICATION_STILL_REQUIRED')
