"""Scoped766-cache + admitted suffix ranking; no arrays flattening, EL or EDA."""
import argparse
import ast
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import re
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import prove_qbs_hit_congruence780 as p
import audit_qbs_engine_residual766 as a

BASE = p.OUT / 'akv-tile-range-admitted781-parent-20261008-01'
BASE_SHA = '720511a144576a95fee244a675635c96104b249c0f99ab3d6b8e0249de77f900'
FINITE = p.OUT / 'qbs-main-side-exact-batch780-agent-20261008-01.json'
FINITE_SHA = 'b3a125456ca92ebef722b83272f33b29333e4f1da488790b55eb2b85108bb600'


def category(field, bit=None):
    name, module = field['name'], field['module']
    terminal = name.rsplit('.', 1)[-1]
    if terminal == 'hit': return 'HIT_SIDE' if 'gen_side_row' in name else 'HIT_MAIN'
    if 'side_offset' in name: return 'SIDE_OFFSET'
    if terminal in ('selected', 'older', 'newer') and module == 'qbs_payload_buffer':
        return 'SELECTED_VALID' if bit == 8 else 'SELECTED_DATA'
    if 'byte_valid' in name or re.search(r'(^|[._])(?:be|strb|write_be)(?:_|\[|$)', name): return 'BE_STRB_VALID'
    if any(x in name for x in ('group_hit', 'word_match', 'byte_select')): return 'MAPPING_CONTROL'
    if any(x in name for x in ('location', 'target', 'offset', 'profile', 'layout', 'context', 'tag')): return 'METADATA'
    if any(x in name for x in ('cycles', 'counter', 'stall', 'wait')): return 'COUNTER_CONTROL'
    if any(x in name for x in ('data', 'result', 'operand', 'value', 'product', 'addend', 'mantissa')): return 'DATA'
    return 'OTHER_CONTROL_FLAGS'


def disabled_result(field, params):
    match = re.fullmatch(r'fmt_outputs\[([0-5])\]\.result', field['name'])
    if field['module'] != 'fpnew_opgroup_block' or match is None:
        return False
    fmt = int(match[1])
    p.m.require(params.get('Width') == 32 and params.get('NUM_FORMATS') == 6
                and params.get('FpFmtMask') == 32 and params.get('FmtUnitTypes') in (0, 1365, 2730),
                'Exact compiled FP32-only unit configuration')
    # fmt_logic_t is ascending [0:5]: decimal32 means format0, NOT format5.
    return fmt != 0 or params['FmtUnitTypes'] == 0


def collect():
    pins = {}
    def read(path, expected=None):
        path = Path(path)
        data = path.read_bytes()
        sha = p.hashlib.sha256(data).hexdigest()
        p.m.require(expected is None or expected == sha, 'Scoped input drift: ' + str(path))
        pins[str(path)] = sha
        return data
    manifest = json.loads(read(BASE / 'admission-manifest.json', BASE_SHA))
    p.m.require(manifest['coverage_admitted'] is True, 'Formal781 required')
    ledger_path = BASE / 'combined-inputs.txt'
    ledger = read(ledger_path, manifest['output_pins'][str(ledger_path)]).decode().splitlines()
    p.m.require(len(ledger) == len(set(ledger)) == 782, 'Exact781 population')
    cache = json.loads(read(p.CACHE, p.CACHE_SHA))
    prefix_path = next(Path(k) for k in cache['pins'] if k.endswith('/combined-inputs.txt'))
    prefix = read(prefix_path, cache['pins'][str(prefix_path)]).decode().splitlines()
    p.m.require(len(prefix) == 767 and ledger[:767] == prefix, 'Exact scoped766 prefix')
    scopes = {r['scope']: r for r in cache['scope_summaries']}
    p.m.require(len(scopes) == 102, 'Complete102 QBS scope inventory')
    union = {s: int(r['bits'], 16) for s, r in scopes.items()}
    for db in ledger[767:]:
        files = list((Path(db) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        p.m.require(len(files) == 1, 'One native suffix Toggle file')
        tree = ET.fromstring(gzip.decompress(read(files[0], manifest['input_pins'][str(files[0])])))
        rows = defaultdict(list)
        for n in tree.iter('instance_data'):
            if n.get('name') in scopes: rows[n.get('name')].append(n)
        for scope, row in scopes.items():
            p.m.require(len(rows[scope]) == 1, 'Missing/duplicate scoped native row')
            n = rows[scope][0]
            value = n.get('value')
            p.m.require(n.get('chksum') == row['checksum'] and len(value) == row['raw_width']
                        and set(value) <= {'0', '1'}, 'Frozen typed shape/width')
            union[scope] |= int(value, 2)
    shape_path = next(Path(k) for k in cache['pins'] if k.endswith('/shape/tgl.verilog.shape.xml'))
    read(shape_path, cache['pins'][str(shape_path)])
    # Recheck relevant27 source bytes, not historical ELF/images/whole input ledgers.
    texts = {}
    for field in cache['all_typed_fields']:
        binding = field['source_binding']
        path = Path(binding['path'])
        if str(path) not in pins:
            data = read(path, binding['sha256'])
            p.m.require(path.name not in texts, 'Ambiguous source basename')
            texts[path.name] = data.decode()
        p.m.require(pins[str(path)] == binding['sha256'], 'Conflicting source binding')
    facts = a.bound_facts(texts['qbs_pkg.sv'])
    p.m.require(facts == cache['source_parameter_facts'], 'All-profile source bounds changed')
    numeric_proof = a.source_contract(texts)
    opgroup, pkg, acc = (texts[k] for k in ('fpnew_opgroup_block.sv', 'fpnew_pkg.sv', 'qbs_fp_accumulator.sv'))
    p.m.require("localparam logic DONT_CARE = 1'b1;" in pkg
                and 'logic [0:NUM_FP_FORMATS-1]' in pkg, 'Literal value/ascending format mask')
    branch = opgroup.split('begin : disable_fmt', 1)[1].split('\n    end', 1)[0]
    p.m.require("assign fmt_outputs[fmt].result  = '{default: fpnew_pkg::DONT_CARE};" in branch
                and "FpFmtMask:     6'b100000" in acc and "Width:          32" in acc
                and "'{default: DISABLED}" in acc, 'Disabled-format literal/producer binding')
    finite = json.loads(read(FINITE, FINITE_SHA))
    qualified_bits = {(g['scope'], g['signal'], int(b)) for g in finite['target_groups']
                      for b in g['bit_missing_coordinates']}
    approved = json.loads(read(p.APPROVED / 'config.json', p.APPROVED_SHA))
    el_path = p.APPROVED / 'combined.el'
    el_text = read(el_path, approved['pins'][str(el_path)]).decode()
    parser = p.ROOT / 'verification/coverage/audit_remaining_toggle776.py'
    tree = ast.parse(read(parser).decode())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('el_fields', 'excluded_bits')]
    p.m.require(len(functions) == 2, 'Reviewed exact EL grammar')
    ns = dict(re=re, defaultdict=defaultdict, t=SimpleNamespace(require=p.m.require))
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(parser), 'exec'), ns)
    el, whole = ns['el_fields'](el_text)
    constants = defaultdict(set)
    for item in cache['source_constant_candidates']:
        high, low = item['candidate_bit_range']
        constants[item['scope'], item['name']].update(range(low, high + 1))
    classes, categories, modules, rows, field_records = Counter(), Counter(), Counter(), {}, []
    removed_count, qualified_count, raw_count = 0, 0, 0
    for field in cache['all_typed_fields']:
        scope, name, width = field['scope'], field['name'], field['width']
        info = scopes[scope]
        legal = set(range(width))
        entries = el.get((scope, name), [])
        if any(bits == 'MDA_HOLD' for _, bits, _ in entries):
            raise ValueError('Cannot infer multi-dimensional EL bit coordinate')
        removed, ambiguous = ns['excluded_bits'](entries, legal)
        p.m.require(not ambiguous, 'Single-direction EL requires separate typed review')
        disabled = disabled_result(field, info['integer_parameters'])
        counts, reasons = Counter(), set()
        for bit in range(width):
            coords = [field['raw_offset'] + 2 * bit + d for d in (0, 1)]
            missing = sum(not (union[scope] >> (info['raw_width'] - 1 - c)) & 1 for c in coords)
            raw_count += missing
            if not missing: continue
            if scope in whole or bit in removed:
                removed_count += missing
                continue
            cat = category(field, bit)
            identity = scope, name, bit
            if identity in qualified_bits:
                p.m.require(missing == 2, 'Qualified constant contradicted by latest781')
                status = 'SOURCE_BOUND_QUALIFIED_NOT_APPLIED'
                qualified_count += missing
            elif bit in constants[scope, name] or disabled:
                p.m.require(missing == 2, 'Literal/bound source proof contradicted by observed hit')
                status = 'SOURCE_BOUND_CANDIDATE_NATIVE_REQUIRED'
                reasons.add('DISABLED_FORMAT_INTERNAL_RESULT_LITERAL_ONE' if disabled else 'ALL_PROFILE_NUMERIC_BOUND')
            elif name.endswith('.hit'):
                status = 'MAPPING_FEASIBLE_STIMULUS_ARBITRATION_HOLD'
            else:
                status = 'UNKNOWN_RETAIN'
            classes[status] += missing
            categories[cat, status] += missing
            modules[field['module'], status] += missing
            counts[status] += missing
            row = rows.setdefault(scope, dict(module=field['module'], checksum=info['checksum'], missing=0))
            row['missing'] += missing
        if counts:
            field_records.append(dict(scope=scope, module=field['module'], signal=name, width=width,
                raw_offset=field['raw_offset'], counts=dict(counts), category=category(field),
                source_binding=field['source_binding'], source_reasons=sorted(reasons),
                compiled_parameters=info['integer_parameters']))
    p.m.require(raw_count == sum(scopes[s]['raw_width'] - bin(union[s]).count('1') for s in scopes),
                'Complete typed raw missing accounting')
    p.m.require(sum(classes.values()) + removed_count == raw_count and qualified_count == 9568,
                'Exact raw/EL/qualified partition')
    arrays = Counter(category(dict(name=x['attributes']['name'], module=x['module']))
                     for x in cache['all_arrays_without_binary_coordinate'])
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_rank_qbs_residual781.py'), Path(a.__file__)):
        read(path)
    return dict(schema='QBS_RESIDUAL781_TYPED_RANKING_V1', population=781, pins=pins,
        scopes=rows, raw_missing=raw_count, already_approved_EL_missing=removed_count,
        remaining_by_status=dict(classes), category_status=[dict(category=k[0], status=k[1], missing=v)
            for k, v in sorted(categories.items())], module_status=[dict(module=k[0], status=k[1], missing=v)
            for k, v in sorted(modules.items())],
        top60_fields=sorted(field_records, key=lambda r: sum(r['counts'].values()), reverse=True)[:60],
        new_source_candidates=[r for r in field_records if 'SOURCE_BOUND_CANDIDATE_NATIVE_REQUIRED' in r['counts']],
        source_numeric_proof=numeric_proof, profile_bounds=facts,
        arrays_unknown_by_category=dict(arrays), arrays_missing_directions=None,
        notes=['All9 profiles+ROW/R4 and activation ROW/M4/M8/access union preserved; pending writer b never recompact.',
               'Mapping feasible is NOT certified runtime reachability; Bacon owns positive-case arbitration work.',
               'side_offset arrays have no mapped serialized capacity; hit mask proof does NOT prove unmasked offset comparator constant.',
               'Disabled internal fmt_outputs.result literal1 only; active arithmetic, all tags/status/flags/interfaces/control remain retained.',
               'Qualified9568 is local native9440+128, NOT aggregate application; no percentage inferred from serialized slots.'],
        no_EDA=True, no_EL=True, official_percentage=None)


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--output', type=Path, required=True)
    a_cli = cli.parse_args()
    result = collect()
    with a_cli.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(output=str(a_cli.output), sha256=p.m.digest(a_cli.output),
                         raw_missing=result['raw_missing'], remaining=result['remaining_by_status'])))
