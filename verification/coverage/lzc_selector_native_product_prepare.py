#!/usr/bin/env python3
"""Offline product selector preparation; no DVE/VCS launch or exclusion authority."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from inventory_operand_debug import Design, ROOT
from inventory_lzc_selector_branches_705 import structural_node
from lzc_selector_candidates import selector_expression
from lzc_selector_native_prepare import (
    BUILD, SOURCE, SOURCE_SHA256, compiled_parameters, compiled_points, require, sha, write,
)
from lzc_native_records import parse_records

OUT = ROOT / 'verification/out'
BASE = OUT / 'gap98-offline-admitted-707-20261006-02'
ROOT_EVIDENCE = OUT / 'lzc_selector_native_measurement-705-20261006-02'


def check_pins(pins):
    for name, expected in pins.items():
        path = Path(name).resolve()
        require(path.is_relative_to(ROOT), 'Pin outside integration workspace')
        require(sha(path) == expected, 'Input drift: ' + name)


def ternary_expression(level, index):
    left = f'(((2 ** ({level} + 1)) - 1) + ({index} * 2))'
    return (f'({selector_expression(level, index)} ? gen_lzc.index_nodes[{left}] : '
            f'gen_lzc.index_nodes[({left} + 1)])')


def eligible(point, width, metric):
    require(metric in ('branch', 'cond'), 'Unsupported metric')
    attrs = point['attributes']
    coords = (attrs.get('generate_info') if metric == 'branch'
              else point.get('spec', {}).get('generate_info'))
    match = re.fullmatch(r'level=(\d+),l=(\d+)', coords or '')
    require(match is not None, 'Exact generate coordinates required')
    level, index = map(int, match.groups())
    selector = selector_expression(level, index)
    if metric == 'branch':
        require(point.get('vector') == '0', 'Seed is not the calibrated true-arm shape position')
    if metric == 'cond':
        require(attrs.get('optype') == '23', 'op16 remains HOLD')
        require(point.get('vector') == '1', 'Only unreachable true selector permitted')
        require(point['expression'] == ternary_expression(level, index)
                and attrs.get('exprstr') == point['expression']
                and attrs.get('width') == '1'
                and point.get('truth_table') == dict(ncols='1', nrows='2', vecs='01'),
                'Not exact full selector ternary')
    probe = dict(point, expression=selector, attributes={
        'generate_info': coords, 'totalbranches': '2'}) if metric == 'cond' else point
    node = structural_node(probe, width)
    require(node is not None and node['reachable_selector_values'] == [0],
            'Selector true is not structurally unreachable')
    return node


def candidate_record(scope, metric, point, params, module_checksum, metric_checksum):
    require('.i_operand_queue_mfpu_' in scope and
            re.fullmatch(r'.+\.leading_zero_e(?:16_i|32)', scope) is not None,
            'Exact LZC child required, not queue/parent instance')
    require(params['WIDTH'] in (10, 23) and params['MODE'] == 1, 'Wrong compiled family')
    proof = eligible(point, params['WIDTH'], metric)
    # XML identifiers are provenance only, never a native selection request.
    return dict(key=f'{scope}|{metric}|{point["raw_index"]}', scope=scope, metric=metric,
                parameters=params, module_checksum=module_checksum,
                metric_checksum=metric_checksum, point_checksum=point['attributes']['chksum'],
                expression=point['expression'], xml_provenance=point,
                structural_proof=proof, unreachable_selector_value=1,
                native_id=None, native_vector_id=None, native_qualified=False,
                allowed_native_selector='true only; no false capture',
                decision='PRODUCT_NATIVE_DISCOVERY_AND_PARENT_REVIEW_REQUIRED')


def validate_condition_singleton(text, candidate):
    """Future saved native ID is learned from EL, never copied from XML/root IDs."""
    require(candidate['metric'] == 'cond', 'Condition candidate required')
    eligible(candidate['xml_provenance'], candidate['parameters']['WIDTH'], 'cond')
    records = parse_records(text)
    require(len(records) == 1, 'Exactly one child condition vector required')
    record = records[0]
    wanted = {k: candidate[k] for k in (
        'scope', 'module_checksum', 'metric_checksum', 'point_checksum', 'expression')}
    wanted.update(width='1', bit='-1', vector='1')
    require(all(record[k] == v for k, v in wanted.items()), 'Product native signature differs')
    return record


def validate_branch_singleton(text, candidate):
    require(candidate['metric'] == 'branch', 'Branch candidate required')
    eligible(candidate['xml_provenance'], candidate['parameters']['WIDTH'], 'branch')
    checksum = scope = None
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        if line.startswith('CHECKSUM:'):
            require(checksum is None, 'Only one native checksum header allowed')
            m = re.fullmatch(r'CHECKSUM: "(\d+) (\d+)"', line)
            require(m is not None, 'Malformed native checksum')
            checksum = m.groups()
        elif line.startswith('INSTANCE:'):
            require(checksum is not None and scope is None, 'Only one exact child allowed')
            scope = line.partition(':')[2].strip()
        elif line.startswith('ANNOTATION:'):
            require(scope is not None and re.fullmatch(r'ANNOTATION: "[^"\n]*"', line),
                    'Malformed annotation')
        else:
            m = re.fullmatch(r'Branch (\d+) "(\d+)" "([^"\n]+)" \((\d+)\) "([^"\n]+)"', line)
            require(m is not None and scope is not None, 'Non-singleton branch syntax')
            records.append(m.groups())
    require(len(records) == 1, 'Exactly one branch arm required')
    identity, point_checksum, expression, arm, signature = records[0]
    require(scope == candidate['scope'] and checksum == (
        candidate['module_checksum'], candidate['metric_checksum']) and
        point_checksum == candidate['point_checksum'] and expression == candidate['expression'] and
        arm == '0' and signature == candidate['expression'] + ' 1',
        'Product branch true-arm signature differs')
    return dict(scope=scope, native_id=identity, arm=arm, signature=signature,
                module_checksum=checksum[0], metric_checksum=checksum[1],
                point_checksum=point_checksum, expression=expression)


def prepare(output):
    require(output.parent == OUT and not output.exists(), 'Fresh direct output directory required')
    pins = {}

    def pin(path, expected=None):
        path = Path(path).resolve()
        require(path.is_relative_to(ROOT), 'Input outside integration workspace')
        value = sha(path)
        require(expected is None or expected == value, 'Input drift: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == value, 'Conflicting pin')
        pins[str(path)] = value

    def load(path):
        pin(path)
        return json.loads(path.read_bytes())

    summary = load(ROOT_EVIDENCE / 'native-summary.json')
    check_pins(load(ROOT_EVIDENCE / 'native-summary.sha256.json'))
    check_pins(summary['input_artifact_sha256'])
    for path, digest in summary['input_artifact_sha256'].items():
        pin(path, digest)
    require(summary['independent_calibration_cases'] == 8 and
            summary['protection']['all_final_global_files_empty'] and
            not summary['old_processor_exclusions_applied'] and not summary['processor_test_admission'],
            'Independent root evidence required')
    require(summary['mapping']['branch'] == dict(native_id='0', false_arm='1', true_arm='0') and
            summary['mapping']['ternary']['follows'] == 'selector, not result parity' and
            not summary['mapping']['boolean']['native_independently_addressable'],
            'Root semantic calibration differs')
    bitmap = load(BASE / 'combined-bits.json')
    state = load(BASE / 'status.json')
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            state['aggregate_passed'] == 707 and len(bitmap['tests']) == len(set(bitmap['tests'])) == 707,
            'Exact latest707-02 admitted population required')
    pin(BASE / 'combined-inputs.txt')
    for path, digest in bitmap['input_hashes'].items():
        pin(path, digest)
    pin(SOURCE, SOURCE_SHA256)
    require(load(BUILD / 'build-source-pins.json')[str(SOURCE)] == SOURCE_SHA256,
            'Old compiled LZC source drift')
    design = Design(BUILD / 'sim/simv.vdb')
    for relative, digest in bitmap['design'].items():
        pin(design.db / relative, digest)
    for name in ('branch', 'cond', 'tgl'):
        for suffix in ('info', 'shape'):
            pin(design.db / f'shape/{name}.verilog.{suffix}.xml')
    branches = load(OUT / 'lzc-selector-branch-candidates-705-20261006-01.json')
    conditions = load(OUT / 'lzc-selector-condition-candidates-705-20261006-01.json')
    require(len(branches['rows']) == 60 and not branches['native_qualified'] and
            not branches['exclusions_applied'], 'Seed branch structure changed')
    require(Counter(r['decision'] for r in conditions['rows']) == {
        'RETAIN_HIT': 22, 'STRUCTURAL_CANDIDATE_NATIVE_REQUIRED': 60,
        'HOLD_TERNARY_NATIVE_SEMANTICS': 60}, 'Seed condition structure changed')
    params = {r['scope']: r['parameters'] for r in branches['rows']}
    seeds = [(r['scope'], 'branch', r['point']) for r in branches['rows']]
    seeds += [(r['point']['scope'], 'cond', r['point']) for r in conditions['rows']
              if r['decision'] == 'HOLD_TERNARY_NATIVE_SEMANTICS']
    targets, retained, protected, cache = [], [], [], {}
    for scope, metric, seed in seeds:
        require(design.source(scope)['resolved_path'] == str(SOURCE), 'Foreign child source')
        require(compiled_parameters(design.definition(scope, 'tgl')) == params[scope],
                'Compiled child parameters drift')
        for family in ('branch', 'cond'):
            if (scope, family) not in cache:
                node, population = compiled_points(design, scope, family)
                raw = bitmap['metrics'][family][scope]
                require(raw['checksum'] == node.get('chksum') and raw['width'] == len(population),
                        'Latest707 metric ownership/width drift')
                cache[scope, family] = node, population
                protected.append(dict(scope=scope, metric=family,
                    module_checksum=design.hierarchy[scope].get('chksum'),
                    metric_checksum=node.get('chksum'), points=population,
                    policy='Every non-target native-visible position unchanged; XML-only op16 HOLD'))
        node, population = cache[scope, metric]
        point = population[seed['raw_index']]
        require(all(seed.get(k) == v for k, v in point.items()), 'Seed exact compiled point drift')
        candidate = candidate_record(scope, metric, point, params[scope],
                                     design.hierarchy[scope].get('chksum'), node.get('chksum'))
        record = bitmap['metrics'][metric][scope]
        hit = bool(int(record['bits'], 16) & (1 << (record['width'] - 1 - point['raw_index'])))
        if hit:
            retained.append(dict(candidate, decision='RETAIN_HIT_707'))
        else:
            targets.append(candidate)
    require(len({r['key'] for r in targets + retained}) == len(seeds), 'Duplicate product position')
    holds = [r for r in conditions['rows'] if r['point']['attributes']['optype'] == '16']
    for name in (Path(__file__).name, 'test_lzc_selector_native_product_prepare.py',
                 'inventory_operand_debug.py', 'inventory_lzc_selector_branches_705.py',
                 'lzc_selector_candidates.py', 'lzc_selector_native_prepare.py',
                 'lzc_padding_proof.py', 'closure_point_inventory.py', 'lzc_native_records.py',
                 'reviewed_20261004/audit_readonly.py'):
        pin(Path(__file__).parent / name)
    plan = dict(status='PREPARED_707_PRODUCT_PARENT_REVIEW_REQUIRED_NO_LAUNCH',
        base=str(BASE), tests=707, source_sha256=SOURCE_SHA256,
        calibration_summary=str(ROOT_EVIDENCE / 'native-summary.json'),
        targets=targets, retained_hit=retained, op16_hold=holds, protected=protected,
        counts=dict(Counter(r['metric'] for r in targets)),
        native_ids_inferred_from_xml=False, native_ids_transferred_from_root=False,
        application_approval=False, native_qualified=False, tools_launched=False,
        stages=[
            'Parent reviews this static plan; no execution command is provided.',
            'Separately approve bounded host DVE read-only child expression/branch-tree discovery on a fresh sandbox; exact707 input population, no EL load/exclude/reset.',
            'Bind discovered native IDs using exact child, module/metric/point checksums, full expression and native vector/arm signatures; never XML or root numeric IDs.',
            'Parent reviews a fresh successor capture script and complete visible-native protection inventory before any temporary singleton exclusion.',
            'Capture only proven-unreachable true Branch arm0 or op23 vector1; false arm/vector and all op16 protected. Each singleton must save/reset/reload/save/reset with exact signature parity.',
            'Offline verify before/selected/reset/reloaded/final global audits, collateral protection, exact singleton EL, byte parity and empty reset/final files; child product coverage true must be missing.',
            'Parent separately decides processor application. This tool neither captures nor authorizes application.'
        ],
        bounds=dict(discovery_host_timeout_seconds=300, capture_host_timeout_seconds=300,
                    singleton_targets_per_session=1, maximum_capture_sessions=len(targets)),
        limitations=['Root calibration proves reachable selector semantics, not product padded-node native identity.',
                     'Structural proof is two-state only; no four-state initialization proof.',
                     'op16 cannot be independently native-addressed; hidden XML-only state is not certified.',
                     'Product true observations/signatures and complete native inventories remain pending.'],
        pins=pins)
    check_pins(pins)
    output.mkdir()
    write(output / 'product-plan.json', plan)
    write(output / 'product-plan.sha256.json', {str(output / 'product-plan.json'): sha(output / 'product-plan.json')})
    print(json.dumps(dict(status=plan['status'], counts=plan['counts'],
                         child_scopes=len(params), protected_xml_positions=sum(len(r['points']) for r in protected),
                         op16_hold=len(holds), retained_hit=len(retained), pins=len(pins))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output.resolve())


if __name__ == '__main__':
    main()
