"""Source/compiled-shape successor review; frozen native capture stays untouched."""
import argparse
import csv
import gzip
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import fma_product_native as one

life, require = one.life, one.require
CAPTURE = life.OUT / 'fma-datapath-108-native-agent-20261007-02'
CAPTURE_SHA = '8d3c1c3e285b03de9b94244506b3a22436a8c59803680c981f4206b85b7dd9ee'
SUMMARY = life.OUT / 'raw741-dve-parent-20261007-01/summary.csv'
SUMMARY_SHA = '67356d1bbdf6ceb36a54080c3ac89cd6340897a2538e3b2e6feb4012a54cc7c7'
GROUPS = {
    'operand_numeric_payload': {'inp_pipe_operands_q', 'operand_a', 'operand_b', 'operand_c'},
    'exponent_alignment': {'exponent_a', 'exponent_b', 'exponent_c', 'exponent_addend',
        'exponent_product', 'exponent_difference', 'tentative_exponent', 'addend_shamt'},
    'mantissa_multiply_add': {'mantissa_a', 'mantissa_b', 'mantissa_c', 'product',
        'product_shifted', 'addend_after_shift', 'addend_sticky_bits', 'addend_shifted',
        'sum_raw', 'sum', 'tentative_sign', 'final_sign'},
    'numeric_pipeline_payload': {'exponent_product_q', 'exponent_difference_q',
        'tentative_exponent_q', 'addend_shamt_q', 'sum_q', 'final_sign_q',
        'mid_pipe_exp_prod_q', 'mid_pipe_exp_diff_q', 'mid_pipe_tent_exp_q',
        'mid_pipe_add_shamt_q', 'mid_pipe_sum_q', 'mid_pipe_final_sign_q'},
    'normalization_numeric_result': {'sum_lower', 'leading_zero_count',
        'leading_zero_count_sgn', 'norm_shamt', 'normalized_exponent', 'sum_shifted',
        'final_mantissa', 'sum_sticky_bits', 'final_exponent'},
}
SOURCE_BOUNDARIES = [
    dict(lines=[99, 158], selection='Only inp_pipe_operands_q numeric payload; pipeline enables/handshake and every metadata/control field retained'),
    dict(lines=[164, 220], selection='Only adjusted operand_a/b/c numeric fields; classifier info and operation selector controls retained'),
    dict(lines=[279, 399], selection='Exponent/sign/alignment/mantissa multiplication and add result; boolean decision/reduced-sticky/carry injection controls retained'),
    dict(lines=[400, 482], selection='Only numeric exponent/shift/sum/sign transport, including stage-zero copies; enable/valid/ready/op/special/status/sticky/tag/mask/aux retained'),
    dict(lines=[488, 574], selection='Local normalization numeric values only; lzc child, empty flag and reduced sticky remain retained'),
    dict(lines=[577, 712], selection='Rounding interface, rounding child, flags/status, post-round result mux and output pipeline all retained'),
]


def group(node):
    if node.get('portnode') != '0':
        return None
    base = node.get('name', '').split('.', 1)[0]
    return next((name for name, members in GROUPS.items() if base in members), None)


def dimensions(node):
    if node.tag == 'node':
        return []
    if node.tag == 'vectornode':
        return [[int(node.get('left')), int(node.get('right'))]]
    require(node.tag == 'arrays', 'Unknown shape node type')
    pairs = []
    for kind in ('packedrange', 'unpackedrange'):
        values = list(map(int, node.get(kind, '').split()))
        require(len(values) % 2 == 0, 'Malformed array bounds')
        pairs.extend([values[i:i + 2] for i in range(0, len(values), 2)])
    require(pairs, 'Empty array shape')
    return pairs


def width(node):
    result = 1
    for left, right in dimensions(node):
        result *= abs(left - right) + 1
    return result


def native_name(node):
    return node.get('name') + ''.join('[' + str(a) + ':' + str(b) + ']' for a, b in dimensions(node))


def protection_reason(node):
    name = node.get('name', '')
    if node.get('portnode') != '0':
        return 'ALL_PORTS_RETAINED'
    if name.startswith(('pre_round_', 'rounded_', 'round_sticky_', 'regular_', 'result_', 'out_pipe_result')):
        return 'ROUNDING_OR_POST_ROUND_OUTPUT_BOUNDARY_RETAINED'
    if any(x in name for x in ('status', '_stat_', 'sticky_before', 'sticky_after', 'mid_pipe_sticky')):
        return 'STATUS_OR_REDUCED_STICKY_RETAINED'
    return 'CONTROL_METADATA_SPECIAL_HANDLING_OR_UNCLASSIFIED_RETAINED'


def review(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh agent-owned output required')
    capture = life.read_bound(CAPTURE / 'capture-result.json', CAPTURE_SHA)
    require(capture['status'] == 'EXACT_108_FMA_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS', 'Native predecessor not qualified')
    life.check(capture['pins'])
    prior = life.read_bound(one.REVIEW, one.REVIEW_SHA)
    pins = {**capture['pins'], str(CAPTURE / 'capture-result.json'): CAPTURE_SHA, str(SUMMARY): SUMMARY_SHA}
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_review_fma_arithmetic_scope.py')):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    shape_path = next(life.ROOT / p['path'] for p in prior['compiled_pins'] if p['path'].endswith('tgl.verilog.shape.xml'))
    root = ET.fromstring(gzip.decompress(shape_path.read_bytes()))
    formats, instances = [], []
    for fmt in prior['formats']:
        modules = [m for m in root.findall('tgldef') if m.get('chksum') == fmt['toggle_checksum']]
        require(len(modules) == 1 and modules[0].get('name') == fmt['compiled_parameter_definition'], 'Compiled specialization differs')
        targets, protected = [], []
        for node in modules[0].find('tglshape'):
            item = dict(node.attrib, shape_kind=node.tag, dimensions=dimensions(node), logical_bits=width(node), native_name=native_name(node))
            category = group(node)
            if category:
                require(node.get('excluded') == '0' and node.get('file') == '381', 'Excluded/foreign candidate')
                item['source_group'] = category
                targets.append(item)
            else:
                item['reason'] = protection_reason(node)
                protected.append(item)
        require({s['name'] for s in fmt['signals']} <= {t['name'] for t in targets}, 'Lost qualified nine signals')
        old = sum(s['width'] for s in fmt['signals'])
        formats.append(dict(format=fmt['format'], toggle_checksum=fmt['toggle_checksum'],
            compiled_parameter_definition=fmt['compiled_parameter_definition'], targets=targets, protected=protected,
            target_objects=len(targets), target_logical_bits=sum(t['logical_bits'] for t in targets),
            prior_nine_logical_bits=old, additional_logical_bits=sum(t['logical_bits'] for t in targets) - old))
    for index, instance in enumerate(prior['instances']):
        fmt = next(f for f in formats if f['format'] == instance['format'])
        inventory = CAPTURE / ('native_before_' + str(index) + '.tsv')
        rows = list(csv.DictReader(io.StringIO(inventory.read_text()), delimiter='\t'))
        targets = []
        for t in fmt['targets']:
            matches = [r for r in rows if r['name'] == t['native_name']]
            require(len(matches) == 1, 'Missing/ambiguous observed native object: ' + t['native_name'])
            targets.append(dict(t, observed_native=matches[0]))
        instances.append(dict(instance, targets=targets, all_descendants_retained=True,
                              native_identity_source=str(inventory), native_roundtrip_qualified_for_expansion=False))
    total = sum(t['logical_bits'] for i in instances for t in i['targets'])
    summary = list(csv.DictReader(io.StringIO(SUMMARY.read_text())))
    system = next(r for r in summary if r['Name'] == 'i_system')
    result = dict(schema='FP32_FP64_INTERNAL_ARITHMETIC_SOURCE_REVIEW_V1',
        status='SOURCE_REVIEW_READY_EXPANDED_NATIVE_ROUNDTRIP_REQUIRED_NOT_APPLIED',
        policy='REUSED_UNCHANGED_IP_INTEGRATION_SCOPE_NOT_UNREACHABILITY',
        selection_independent_of_coverage=True, population='741 fixed historical image; no population report rewritten',
        source_boundaries=SOURCE_BOUNDARIES, source_groups={k: sorted(v) for k, v in GROUPS.items()},
        formats=formats, instances=instances, target_objects=sum(len(i['targets']) for i in instances),
        logical_bits=total, prior_qualified_objects=108, prior_qualified_logical_bits=8368,
        additional_logical_bits=total - 8368, nominal_two_direction_slots=2 * total,
        nominal_slots_are_not_official_denominator=True, official_denominator_reduction=None,
        reason_denominator_unknown='Frozen raw741 summary has percentages only. Constant-bit/autoexcluded/scoring policy requires actual same-session native summary/counts after expanded EL; no projected percentage claim.',
        raw741_i_system=system, evidence=prior['evidence'], evidence_limits=prior['scope_rules']['evidence_limits'],
        upstream_commit=prior['fpnew_upstream_commit'], source_pins=prior['source_pins'], baseline=prior['baseline'],
        protection='All ports; valid/ready/reset/flush/enables/op/rnd/classifier/special predicates/status/mask/tag/aux; reduced sticky flags; rounding interfaces and post-round result transport; every child and every other module retained.',
        excluded_formats=['FP16', 'BF16', 'FP8', 'scalar FPU', 'QBS'],
        modified_logic_retained=['fpnew_cast_multi', 'fpnew_divsqrt_multi', 'fpnew_opgroup_multifmt_slice', 'fpnew_pkg', 'ct_vfdsu_round', 'wrappers'],
        no_exhaustive_validation_claim=True, expanded_native_qualified=False, aggregate_applied=False, pins=pins)
    life.check(pins)
    out.mkdir()
    life.save(out / 'source-review.json', result)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'source-review.json'), objects=result['target_objects'],
        logical_bits=total, additional_logical_bits=total - 8368, pins=len(pins))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review(args.output.absolute())
