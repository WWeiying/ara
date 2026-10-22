"""Exact raw705 FP16 pack candidates; no EL, native approval or application."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

from inventory_operand_debug import Design, ROOT
from closure_point_inventory import points
from fp16_pack_lower_bound_proof import load_proof, read_bound, require

OUT = ROOT / 'verification/out'
BASE = OUT / 'gap96-offline-admitted-705-20261006-01'
BITMAP_SHA = '30139b06d8d16a70c39eb1938f3b191ca9e7b8057da85241a8bd0d8ead90b7e0'
STATUS_SHA = 'da0dafbe2e32e4b2d30a5bd5b51de504e0d0baa0874da8a7477c141c76897ea0'
METADATA = {
    'shape/branch.verilog.info.xml': 'e590433e98d78fd00a644dacba88e9fc67b8375f201e380ac7f06573cb15a7fd',
    'shape/tgl.verilog.info.xml': '5603b64b35df34925586b68ba6bf429c7e92836b239c94e9c193c666e3d70b0a',
    'shape/tgl.verilog.shape.xml': '243ae4d4d29b7ee2190ef35a39482f7287c78a260128315b666d500e90f18ae7',
}


def case_table(definition):
    specs = [s for s in definition.iter('branch_spec') if s.get('id') == '7']
    require(len(specs) == 1, 'Missing exact case spec')
    spec = specs[0]
    require(spec.get('chksum') == '1926128194' and spec.get('totalbranches') == '55'
            and spec.get('file_id') == '370', 'Case spec identity differs')
    cases = spec.findall('branch_cexpr')
    require(len(cases) == 1 and cases[0].get('exprstr') == 'vfdsu_ex4_expnt_rst[12:0]',
            'Wrong pack exponent selector')
    items = cases[0].findall('branch_citem')
    require(len(items) == 54, 'Case inventory differs')
    table = {}
    for vector, item in enumerate(items[:53]):
        match = re.fullmatch(r"13'h([0-9a-f]+)\s*", item.get('name', ''))
        require(match is not None and item.get('index') == str(vector + 1), 'Bad case item')
        value = int(match.group(1), 16)
        signed = value - 8192 if value & 4096 else value
        require(signed == 1 - vector, 'Case constant ordering differs')
        table[str(vector)] = dict(signed=signed, item=dict(item.attrib))
    require(items[-1].get('name') == 'default' and items[-1].get('index') == '54', 'Default differs')
    vectors = spec.findall('branch_vector')
    require(len(vectors) == 55, 'Native vector inventory differs')
    for i, node in enumerate(vectors):
        expected = 1 << i if i < 53 else (1 << 53) | (1 << (54 if i == 53 else 55))
        require(node.get('id') == str(i) and int(node.get('vector'), 2) == expected,
                'Native case path differs')
    return table


def classify(point, table, hit):
    if point['native_id'] != '7':
        return 'OTHER_PACK_BRANCH', None
    require(point['line'] == '178' and point['file_id'] == '370' and
            point['attributes']['chksum'] == '1926128194', 'Point ownership differs')
    vector = int(point['vector'])
    require(point['raw_index'] == 82 - vector, 'Raw case identity differs')
    if vector >= 53:
        require(vector in (53, 54), 'Invalid default path')
        return 'PROTECTED_DEFAULT', None
    case = table[str(vector)]
    if case['signed'] <= -26:
        require(not hit, 'Observed hit contradicts source candidate')
        return 'SOURCE_PROOF_CANDIDATE_NATIVE_PENDING', case
    return ('PROTECTED_MINUS25_BOUNDARY' if case['signed'] == -25 else
            'PROTECTED_REACHABLE_OR_UNCLASSIFIED'), case


def build_inventory():
    pins = {}
    proof, sources = load_proof(pins)
    bitmap = json.loads(read_bound(BASE / 'combined-bits.json', BITMAP_SHA, pins))
    status = json.loads(read_bound(BASE / 'status.json', STATUS_SHA, pins))
    require(status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and status['aggregate_passed'] == 705,
            'Not admitted raw705')
    require(len(bitmap['tests']) == len(set(bitmap['tests'])) == 705, 'Population differs')
    design = Design(OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb')
    for relative, expected in dict(bitmap['design'], **METADATA).items():
        read_bound(design.db / relative, expected, pins)
    path = OUT / 'gap56-operand-independent-review-20261004-01/review.py'
    read_bound(path, '796091cd4288818c46412604509872bf401933369302b09a9cecb6fc91a993fb', pins)
    spec = importlib.util.spec_from_file_location('fp16_pack_compiled_parameters', path)
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    candidates, protected, statistics, identities = [], [], [], set()
    for scope, record in sorted(bitmap['metrics']['branch'].items()):
        if not scope.endswith('.x_ct_vfdsu_pack'):
            continue
        match = re.search(r'\.gen_lanes\[(\d+)\].*\.gen_num_lanes\[([23])\]\.', scope)
        if not match:
            continue
        identity = tuple(map(int, match.groups()))
        require(identity not in identities, 'Duplicate physical instance')
        identities.add(identity)
        require(record['width'] == 143 and record['checksum'] == '839910393', 'Pack metric differs')
        wrapper = scope.split('.i_ct_vfdsu_top.', 1)[0]
        parameters = review.signature(design.definition(wrapper, 'tgl'))
        require(len(parameters) == 1 and all(parameters[0].get(k) == v for k, v in
                {'WIDTH': 16, 'FpFmtConfig': 8, 'NumPipeRegs': 3, 'PipeConfig': 3,
                 'NUM_INP_REGS': 1, 'NUM_OUT_REGS': 2}.items()), 'Compiled format/pipeline differs')
        ara = scope.split('.gen_lanes[', 1)[0]
        ara_params = review.signature(design.definition(ara, 'tgl'))
        require(len(ara_params) == 1 and all(ara_params[0].get(k) == v for k, v in
                {'FPUSupport': 56, 'VLEN': 1024, 'NrLanes': 4}.items()), 'Compiled Ara config differs')
        source = design.source(scope)['resolved_path']
        require(source in pins and Path(source).name == 'ct_vfdsu_pack.v', 'Source ownership differs')
        definition = design.definition(scope, 'branch')
        require(definition.get('chksum') == record['checksum'], 'Definition checksum differs')
        table = case_table(definition)
        scope_rows = []
        for point in points('branch', definition, 143):
            hit = bool(int(record['bits'], 16) & (1 << (142 - point['raw_index'])))
            decision, case = classify(point, table, hit)
            row = dict(scope=scope, metric_checksum=record['checksum'], point=point, case=case,
                       raw_hit=hit, decision=decision, source=source, parameters=parameters[0])
            (candidates if decision.startswith('SOURCE_PROOF') else protected).append(row)
            scope_rows.append(row)
        statistics.append(dict(scope=scope, candidates=sum(r['decision'].startswith('SOURCE_PROOF') for r in scope_rows),
                               protected=sum(not r['decision'].startswith('SOURCE_PROOF') for r in scope_rows),
                               boundary_hits=sum(r['decision'] == 'PROTECTED_MINUS25_BOUNDARY' and r['raw_hit'] for r in scope_rows),
                               reachable_or_unclassified_zero=sum(r['decision'] == 'PROTECTED_REACHABLE_OR_UNCLASSIFIED' and not r['raw_hit'] for r in scope_rows)))
    require(identities == {(a, b) for a in range(4) for b in (2, 3)}, 'Physical inventory differs')
    require(len(candidates) == 208 and len(protected) == 936, 'Candidate/protection counts differ')
    require(sum(s['boundary_hits'] for s in statistics) == 1 and
            sum(s['reachable_or_unclassified_zero'] for s in statistics) == 118, 'Raw705 retention differs')
    for name in ('fp16_pack_lower_bound_proof.py', 'test_fp16_pack_lower_bound_proof.py',
                 'inventory_fp16_pack_lower_bound_705.py', 'test_inventory_fp16_pack_lower_bound_705.py',
                 'inventory_operand_debug.py', 'closure_point_inventory.py'):
        read_bound(Path(__file__).parent / name, None, pins)
    for path, sha in list(pins.items()):
        read_bound(Path(path), sha, pins)
    return dict(status='FP16_PACK705_SOURCE_CANDIDATES_NOT_NATIVE_APPROVAL', tests=705,
                candidate_count=208, protected_count=936, proof=proof, scope_statistics=statistics,
                candidates=candidates, protected=protected, pins=pins, native_qualified=False,
                exclusions_applied=False, official_percentage_claim=False, pack_other_cases_preserved=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.absolute()
    require(output.parent == OUT and not output.exists(), 'Fresh direct output required')
    result = build_inventory()
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                          candidates=208, protected=936)))


if __name__ == '__main__':
    main()
