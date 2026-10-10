"""Bounded offline722 operand parameter dedup and condition taxonomy; no waivers."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import audit_operand_parameter_dedup_716_v2 as prior
from closure_point_inventory import definition, points, read_xml

ROOT, OUT, require = prior.ROOT, prior.OUT, prior.require
BASE = OUT / 'gap104-offline-admitted-722-20261006-02'
BASE_SHA = 'b9ad9d11e0eeb709ebcf3e4bd6d5ccbdd94d4a229e9c80b144ef10cf8213415a'
SIX = OUT / 'branch-combo-six-policy-population-722-20261006-01/config.json'
SIX_SHA = '3df4ba085eafcccc3c6b40080a77abbdb314fb638492758c5ff7088950083fbc'
sha = prior.shared.shared.sha


def branch_decision(point, hit, existing, all_zero):
    proof = prior.guards(point) if all_zero else []
    require(not (hit and proof), 'Measured hit contradicts parameter proof')
    if proof:
        label = 'PROVEN_GUARD_ALREADY_EXISTING_POLICY' if existing else 'NEW_CONFIG_PROOF_NATIVE_HOLD'
    elif existing:
        label = 'EXISTING_POLICY_NO_NEW_PROOF'
    else:
        label = 'PROTECTED_HIT' if hit else 'PROTECTED_ZERO_NO_CONFIG_PROOF'
    return label, proof


def condition_binding(data_checksum, info_checksum):
    require(data_checksum in (None, info_checksum), 'Condition checksum conflict')
    return 'HOLD_NO_PER_INSTANCE_CHECKSUM' if info_checksum is None else 'COMPILED_ONLY_NOT_NATIVE'


def audit():
    pins = {}

    def pin(path, expected=None):
        path = Path(path).absolute()
        actual = sha(path)
        require(expected is None or actual == expected, 'Input drift: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == actual, 'Concurrent input drift')
        pins[str(path)] = actual
        return path

    def read(path, expected=None):
        return json.loads(pin(path, expected).read_bytes())

    admission = read(BASE / 'admission-manifest.json', BASE_SHA)
    bits = read(BASE / 'combined-bits.json', admission['output_pins'][str(BASE / 'combined-bits.json')])
    require(len(bits['tests']) == len(set(bits['tests'])) == 722, 'Exact formal722 required')
    config = read(SIX, SIX_SHA)
    require(config['population'] == 722 and config['admission_manifest_sha256'] == BASE_SHA,
            'Wrong policy population')
    build_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    build = read(build_path, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    for relative in ('hardware/src/lane/operand_queue.sv', 'hardware/src/lane/operand_queues_stage.sv',
                     'hardware/include/ara_pkg.sv'):
        source = ROOT / relative
        pin(source, build[str(source)])
    design = prior.shared.shared.Design(OUT / 'repaired-aligned-build-20260930-01/sim/simv.vdb')
    for relative, expected in bits['design'].items():
        pin(design.db / relative, expected)
    for relative in ('shape/tgl.verilog.shape.xml', 'auxiliary/verilog.sourceinfo.xml',
                     'shape/branch.verilog.info.xml', 'shape/line.verilog.info.xml',
                     'shape/tgl.verilog.info.xml', 'shape/cond.verilog.info.xml'):
        pin(design.db / relative)
    condition_root = read_xml(design.db / 'shape/cond.verilog.shape.xml')
    cond_info = {n.get('name'): n.get('chksum') for n in
                 read_xml(design.db / 'shape/cond.verilog.info.xml').iter('instance_data')}
    counts, scopes, rows = Counter(), {}, []
    for scope, old in config['groups']['operand']['plan']['scopes'].items():
        name = scope.rsplit('i_operand_queue_', 1)[-1]
        require(design.source(scope)['resolved_path'] == str(ROOT / 'hardware/src/lane/operand_queue.sv'),
                'Wrong compiled operand source')
        signature = design.definition(scope, 'tgl').get('name')
        all_zero = name in prior.NAMES
        params = prior.parameters(signature) if all_zero else None
        record = bits['metrics']['branch'][scope]
        node = design.definition(scope, 'branch')
        require(record['width'] == 101 and record['checksum'] in (None, node.get('chksum')),
                'Branch shape drift')
        targets = {p['raw_index']: p for p in old['targets']}
        protected = {p['raw_index']: p for p in old['protected']}
        require(not targets.keys() & protected.keys() and len(targets) + len(protected) == 101,
                'Policy partition incomplete')
        stat = Counter()
        for point in points('branch', node, 101):
            index = point['raw_index']
            approved = targets.get(index, protected.get(index))
            require(approved['selector'] == point['native_id'] + ',' + point['vector']
                    and approved['spec_checksum'] == point['attributes']['chksum'], 'Exact policy coordinate drift')
            hit = bool(int(record['bits'], 16) & (1 << (100 - index)))
            label, proof = branch_decision(point, hit, index in targets, all_zero)
            stat[label] += 1
            counts[label] += 1
            rows.append(dict(scope=scope, module_checksum=design.hierarchy[scope].get('chksum'),
                             metric_checksum=node.get('chksum'), point=point, hit722=hit,
                             classification=label, config_proof=proof, new_native_qualified=False))
        cond = bits['metrics']['cond'][scope]
        state = condition_binding(cond['checksum'], cond_info.get(scope))
        scopes[scope] = dict(compiled_parameter_signature=signature, all_zero_parameters=params,
                            branch_counts=dict(stat), condition_width=cond['width'],
                            condition_hits=bin(int(cond['bits'], 16)).count('1'),
                            condition_bitmap_checksum=cond['checksum'], condition_info_checksum=cond_info.get(scope),
                            condition_binding_status=state, new_condition_proof_candidates=0,
                            producer_path_and_false_guard_arms_remain_protected=True)
    summaries = {}
    for scope, record in bits['metrics']['cond'].items():
        if not ('i_payload_buffer' == scope.rsplit('.', 1)[-1] or scope.endswith('.i_dispatcher')):
            continue
        groups = defaultdict(lambda: dict(positions=0, hits=0, zeros=0))
        entries = {}
        checksum = cond_info.get(scope)
        condition_binding(record['checksum'], checksum)
        require(checksum is not None, 'Summary expression identity unavailable')
        node = definition(condition_root, design.hierarchy[scope], checksum)
        for point in points('cond', node, record['width']):
            hit = bool(int(record['bits'], 16) & (1 << (record['width'] - 1 - point['raw_index'])))
            key = point['native_id']
            if key not in entries:
                entries[key] = dict(expression=point['expression'], attributes=point['attributes'],
                                    spec=point['spec'], truth_table=point['truth_table'], positions=0, hits=0, zeros=0)
            group = groups[point['attributes']['optype']]
            for row in (group, entries[key]):
                row['positions'] += 1
                row['hits'] += int(hit)
                row['zeros'] += int(not hit)
        hits = bin(int(record['bits'], 16)).count('1')
        summaries[scope] = dict(width=record['width'], hits=hits, zeros=record['width'] - hits,
                                module_checksum=design.hierarchy[scope].get('chksum'), checksum=checksum,
                                raw_optype_taxonomy=dict(groups),
                                largest_zero_expression_groups=sorted(entries.values(), key=lambda r: -r['zeros'])[:12],
                                classification='RAW_INSTRUMENTATION_NOT_CONTROL_REACHABILITY',
                                new_waiver_candidates=0)
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_audit_operand_condition_scope_722.py'),
                 Path(prior.__file__).resolve()):
        pin(path)
    for name, expected in pins.items():
        require(sha(name) == expected, 'Final input drift')
    return dict(status='FORMAL722_SCOPE_ASSESSMENT_NO_NEW_WAIVERS', admission_sha256=BASE_SHA,
                policy_config_sha256=SIX_SHA, counts=dict(counts), scopes=scopes, branch_points=rows,
                raw_condition_summaries=summaries, input_pins=pins,
                assessment_limit='Parameter proof checked only for the12 all-zero specialized instances. '
                    'Other compiled parameter variants are retained without inferring omitted defaults. '
                    'optype16/23 are instrumentation tags, not evidence of structural unreachability or control coverage. '
                    'Masked data, conversion opcodes, ready/flush/reset, neutral/reduction and false guard arms '
                    'require separate producer/reachability proof; zero count alone grants no waiver. '
                    'All outside-policy points remain protected, including all conditions/lines/toggles/FSM.',
                new_native_qualified=False, exclusions_generated=False, application_approval=False,
                dve_started=False, rtl_changed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.absolute()
    require(output.parent == OUT and output.resolve() == output and not output.exists(), 'Fresh direct output required')
    result = audit()
    prior.shared.shared.save(output, result)
    print(json.dumps(dict(output=str(output), sha256=sha(output), counts=result['counts'])))


if __name__ == '__main__':
    main()
