"""Exact padded-selector X/0 closure; no EDA, no qualification/application promotion."""
import argparse
from itertools import product
import json
from pathlib import Path
import re
import sys

import lzc_selector_native_product_batch_v5_launch as measured
from lzc_native_records import parse_records
from lzc_selector_native_prepare import SOURCE, SOURCE_SHA256, BUILD, compiled_parameters, compiled_points
from inventory_operand_debug import Design

OUT = measured.v4.batch.product.OUT
DEFAULT_BATCH = OUT / 'lzc_selector_native_product_batch-707-20261006-05'
RESULT_SHA = '0b17dd43d026a74ca9ec0e9e826fe4386319e14a912e671d201fa595a1dd3872'
require, sha, write = measured.require, measured.sha, measured.write


def sv_or(a, b):
    require(a in '01XZ' and b in '01XZ', 'Not a four-state bit')
    if '1' in (a, b):
        return '1'
    return '0' if a == b == '0' else 'X'


def sv_eq_one(a):
    require(a in '01XZ', 'Not a four-state bit')
    return 'X' if a in 'XZ' else a


def source_contract(text):
    expected = [
        'assign sel_nodes[2 ** level - 1 + k] = in_tmp[k * 2] | in_tmp[k * 2 + 1];',
        'assign sel_nodes[2 ** level - 1 + k] = in_tmp[k * 2];',
        "assign sel_nodes[2 ** level - 1 + k] = 1'b0;",
        'assign sel_nodes[2 ** level - 1 + l] =\n              sel_nodes[2 ** (level + 1) - 1 + l * 2] | sel_nodes[2 ** (level + 1) - 1 + l * 2 + 1];'
    ]
    actual = re.findall(r'assign\s+sel_nodes\[[^;]+;', text)
    require(actual == expected, 'Complete selector driver templates differ')
    require(re.findall(r'\bsel_nodes\[[^\n;]+\]\s*(?:<=|=(?!=))', text) ==
            [s.split(' =', 1)[0].split('assign ', 1)[1] + ' =' for s in expected],
            'Unreviewed selector assignment')
    require("if (unsigned'(k) * 2 > WIDTH - 1) begin : g_out_of_range" in text
            and 'logic [2**NumLevels-1:0] sel_nodes' in text
            and 'localparam int unsigned NumLevels = $clog2(WIDTH);' in text,
            'Padding or uninitialized logic declaration drift')
    return dict(driver_templates=expected, selector_storage='uninitialized four-state logic',
                no_explicit_initial_value=True, padding_leaf_driver="1'b0",
                internal_driver='bitwise OR of two children', reset_port_present=False,
                reset_contract='LZC has no reset input/state; upstream reset/X cannot enter a padded-only cone.')


def padded_cone(width, level, index):
    require(width in (10, 23), 'Only compiled WIDTH10/23 family')
    levels = (width - 1).bit_length()
    require(0 <= level < levels and 0 <= index < 2 ** level, 'Invalid tree coordinate')
    node = dict(level=level, index=index, selector_array_index=2 ** level - 1 + index)
    if level == levels - 1:
        require(index * 2 > width - 1, 'Real input enters candidate cone')
        node.update(driver="1'b0", real_input_dependencies=[], initial_domain=['X'],
                    all_schedule_prefix_values=['X', '0'], settled_value='0', propagation_round_bound=1)
    else:
        children = [padded_cone(width, level + 1, index * 2 + side) for side in (0, 1)]
        domain = sorted({sv_or(a, b) for a, b in product('X0', repeat=2)})
        require(domain == ['0', 'X'], 'X/0 OR closure failed')
        node.update(driver='OR', children=children, real_input_dependencies=[], initial_domain=['X'],
                    all_schedule_prefix_values=['X', '0'], settled_value='0',
                    propagation_round_bound=1 + max(c['propagation_round_bound'] for c in children))
    return node


def prove_candidate(candidate):
    require(candidate['metric'] == 'cond' and candidate['xml_provenance']['attributes']['optype'] == '23',
            'Only exact ternary condition; branch/op16 HOLD')
    structural = measured.v4.batch.product.eligible(candidate['xml_provenance'],
                                                    candidate['parameters']['WIDTH'], 'cond')
    require(structural == candidate['structural_proof'] and not structural['left_real_bits'],
            'Structural cone drift')
    cone = padded_cone(candidate['parameters']['WIDTH'], structural['level'] + 1,
                       structural['index'] * 2)
    predicate = {sv_eq_one(v) for v in cone['all_schedule_prefix_values']}
    require(predicate == {'X', '0'}, 'Known true is reachable')
    return dict(key=candidate['key'], scope=candidate['scope'], left_selector_cone=cone,
                predicate_possible_values=['X', '0'], known_true_unreachable_before_and_after_settling=True,
                false_only_after_quiescence=True, transient_X_is_not_false=True,
                any_real_input_including_X_Z_has_no_fanin=True,
                propagation_bound_role='Abstract dependency update rounds under fair zero-delay scheduling, '
                    'not measured simulator delta count or wall time.',
                initial_delta_contract='Every selector starts X. Constant padded leaves can update only to0; '
                    'internal OR can update only toX or0 in any event order. No schedule prefix can produce1. '
                    'Quiescence after fair acyclic propagation yields0. No init-X vector is waived.',
                forced_or_deposited_internal_values_and_extra_drivers_excluded=True)


def prepare(batch, output):
    require(output.parent == OUT and not output.exists(), 'Fresh direct output required')
    plan = measured.reviewed_plan(batch)
    result = measured.verify(batch, plan)
    saved = json.loads((batch / 'batch-result.json').read_bytes())
    require(sha(batch / 'batch-result.json') == RESULT_SHA and
            all(saved[k] == value for k, value in result.items()), 'Sealed measured result drift')
    status = json.loads((batch / 'batch-status.json').read_bytes())
    require(status['returncode'] == 0 and status['status'] == result['status']
            and result['native_signature_qualified_candidates'] == 60 and result['counts'] == {'cond': 60}
            and result['branch_hold'] == 60 and result['native_position_state_checks'] == 51240
            and result['global_final_empty'] and result['all_roundtrips_identical']
            and not result['four_state_initialization_qualified'], 'Exact60/60 measured gates differ')
    pins = {}
    for group in (plan['pins'], saved['input_sha256'], status['artifacts']):
        for name, expected in group.items():
            require(name not in pins or pins[name] == expected, 'Conflicting sealed artifact pin: ' + name)
            pins[name] = expected
    for path in (batch / 'batch-status.json', batch / 'batch-result.json', batch / 'batch-result.sha256.json',
                 Path(__file__).resolve(), Path(__file__).with_name('test_lzc_selector_native_four_state_proof.py'),
                 Path(measured.__file__).resolve(), SOURCE):
        pins[str(path)] = sha(path)
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and str(OUT.parent) in str(Path(name).resolve()):
            path = Path(name).resolve()
            require(str(path) not in pins or pins[str(path)] == sha(path), 'Imported proof dependency drift')
            pins[str(path)] = sha(path)
    require(sha(SOURCE) == SOURCE_SHA256 and
            json.loads((BUILD / 'build-source-pins.json').read_bytes())[str(SOURCE)] == SOURCE_SHA256,
            'Source not frozen compiled image')
    contract = source_contract(SOURCE.read_text())
    design = Design(BUILD / 'sim/simv.vdb')
    rows, blocks, seen, proofs = plan['protection_rows'], [], set(), []
    qualified = []
    for record in result['results']:
        candidate = record['candidate']
        require(candidate['key'] not in seen, 'Duplicate candidate')
        seen.add(candidate['key'])
        require(candidate['module_checksum'] == design.hierarchy[candidate['scope']].get('chksum')
                and compiled_parameters(design.definition(candidate['scope'], 'tgl')) == candidate['parameters'],
                'Actual compiled child identity drift')
        node, points = compiled_points(design, candidate['scope'], 'cond')
        require(node.get('chksum') == candidate['metric_checksum'] and
                points[candidate['xml_provenance']['raw_index']] == candidate['xml_provenance'],
                'Exact compiled condition signature drift')
        proofs.append(prove_candidate(candidate))
        target = next(t for t in plan['targets'] if t['candidate']['key'] == candidate['key'])
        data = (batch / ('case-%03d' % target['number']) / 'first.el').read_text()
        native = measured.v4.batch.product.validate_condition_singleton(data, candidate)
        require(native == record['native_record'], 'Measured native identity changed')
        blocks.append(data.rstrip() + '\n')
        qualified.append(dict(candidate=candidate, native_record=native, position=record['position'],
                              four_state_source_proof=True, parent_application_review_required=True))
    joined = '\n'.join(blocks)
    require(parse_records(joined) == [r['native_record'] for r in qualified], 'Exact joined60 native set drift')
    for name, expected in pins.items():
        require(sha(name) == expected, 'Proof input drift: ' + name)
    output.mkdir()
    write(output / 'candidate60.el', joined)
    pins[str(output / 'candidate60.el')] = sha(output / 'candidate60.el')
    report = dict(status='EXACT60COND_FOUR_STATE_SOURCE_PROOF_PARENT_REVIEW_NOT_APPLICATION',
                  measured_batch=str(batch), measured_batch_result_sha256=RESULT_SHA,
                  frozen_four_state_initialization_qualified=False,
                  source_four_state_closure_proved=True, source_contract=contract, proofs=proofs,
                  candidates=qualified, native_qualified_conditions=60, branch_hold=60, op16='HOLD',
                  source_proof_limit='Static SV X/0 cone induction for unforced single-driver compiled design. '
                      'No simulator initial-delta trace or native instrumentation behavior on X was measured. '
                      'Native true/false semantic calibration and signature roundtrip are separate sealed evidence. '
                      'Parent must accept this explicit source/monitor contract before application; '
                      'never rewrite or bypass the frozen four-state flag.',
                  global_visible_positions=4200, retained_protected_positions=4140,
                  exact_protection_rows=rows, native_position_state_checks=51240,
                  same_session_roundtrip_verified=True, global_final_empty=True,
                  native_instrumentation_X_semantics_measured=False, combined60_reloaded_in_DVE=False,
                  future_independent_population_application_required=True,
                  application_approval=False, processor_waivers_applied=0, dve_started=False, pins=pins)
    write(output / 'review.json', report)
    write(output / 'review.sha256.json', {str(output / 'review.json'): sha(output / 'review.json')})
    print(json.dumps(dict(output=str(output), seal=sha(output / 'review.json'), candidates=60,
                         branch_hold=60, source_four_state_closure_proved=True, application_approval=False)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=DEFAULT_BATCH)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.batch.resolve(strict=True), args.output.absolute())


if __name__ == '__main__':
    main()
