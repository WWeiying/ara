"""Static extension of frozen ALUA24 proof, with actual795 bitmap checks."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import review_alua_ext24_producers794 as old
from inventory_operand_debug import Design
from closure_point_inventory import points
from branch720_next_report_contract import native_inventory

ROOT, OUT = old.ROOT, old.OUT
BASE = OUT / 'scalar-div-subnormal-offline-admitted795-parent-20261008-01/admission-manifest.json'
BASE_SHA = '4d13a15758c65791a43798467bb63c516d0747d631f6fede476eb63202001660'
PRIOR = OUT / 'alua-ext24-producers794-source-review-agent-20261008-02.json'
PRIOR_SHA = '3e62bd6913ffa00819e7188592feb7a82bed6b3e3ce29964de90185a166cbad5'
WIDE_OPS = ['VFADD', 'VFSUB', 'VFADD', 'VFSUB', 'VFMUL',
            'VFMACC', 'VFNMACC', 'VFMSAC', 'VFNMSAC']


def wide_routes(text):
    text = old.code(text)
    result = []
    for match in re.finditer(r'ara_req\.conversion_vs1\s*=\s*OpQueueConversionWideFP2;', text):
        before = text[:match.start()]
        block = list(re.finditer(r"6'b([01]{6}): begin", before))[-1]
        body = before[block.start():]
        assignments = re.findall(r'ara_req\.op\s*=\s*ara_pkg::(\w+)\s*;', body)
        old.require(len(assignments) == 1, 'Ambiguous WideFP2 opcode producer')
        result.append(dict(line=before.count('\n') + 1,
                           funct6=block[1], opcode=assignments[0]))
    old.require([x['opcode'] for x in result] == WIDE_OPS,
                'WideFP2 no longer restricted to MFPU arithmetic')
    return result


def classify(group, point, lane):
    vector = point['native_vector']['vector']
    active = [n for n in group.iter('branch_citem')
              if vector[-int(n.get('index'))] == '1']
    outer = [n.get('name').strip() for n in active if n.get('index') in
             {'1', '8', '14', '19', '26', '32', '37', '46', '53', '60'}]
    old.require(len(outer) == 1, 'Missing/ambiguous outer conversion case')
    conversion = outer[0]
    def flag(line):
        matches = [n for n in group.iter('branch_expr') if n.get('id') == str(line)]
        old.require(len(matches) == 1, 'Missing compiled predicate')
        return vector[-int(matches[0].get('index'))]
    if conversion in old.FORBIDDEN:
        return 'EXCLUDED_BY_VS1_PRODUCER_DOMAIN'
    if conversion == 'OpQueueAdjustFPCvt':
        return 'EXCLUDED_BY_VS1_PRODUCER_DOMAIN'
    if conversion == 'OpQueueConversionWideFP2':
        return 'WIDEFP2_PRODUCERS_ROUTE_ONLY_TO_MFPU'
    if conversion in {'OpQueueConversionSExt2', 'OpQueueConversionZExt2'}:
        if flag(339 if conversion.endswith('SExt2') else 368) == '0':
            return 'CONFIG_SUPPORT_INT_EXT2_TRUE'
    if conversion == 'OpQueueReductionZExt':
        if flag(396) == '0':
            return 'CONFIG_SUPPORT_REDUCT_TRUE'
        if flag(397) != str(int(lane == 0)):
            return 'FIXED_LANE_ID_REDUCTION_BRANCH'
    if conversion == 'default' and flag(460) == '1' and flag(461) == '1':
        return 'CONFIG_SUPPORT_NTRVAL_FALSE'
    return None


def collect():
    old.require(old.sha(PRIOR) == PRIOR_SHA and old.sha(BASE) == BASE_SHA,
                'Frozen authority drift')
    prior = json.loads(PRIOR.read_text())
    old.require(old.collect() == prior, 'Frozen24 source replay changed')
    pins = dict(prior['input_pins'], **{str(PRIOR): PRIOR_SHA, str(BASE): BASE_SHA})
    manifest = json.loads(BASE.read_text())
    old.require(manifest['coverage_admitted'] is True and
                manifest['baseline_seal'] == '02ee7424a6b21d8073097d8a6389be4393d76fc7a3ab31ce410f1c24f70de8cf',
                'Not exact admitted795 successor')
    bitmap_path = BASE.parent / 'combined-bits.json'
    expected = manifest['output_pins'][str(bitmap_path)]
    old.require(old.sha(bitmap_path) == expected, 'Published795 raw bitmap drift')
    pins[str(bitmap_path)] = expected
    bitmap = json.loads(bitmap_path.read_text())
    old.require(len(bitmap['tests']) == 795, 'Wrong population count')
    config = json.loads((OUT / 'current-population794-soc61-parent-20261008-01/config.json').read_text())
    design = Design(Path(config['input_ledger'][0]))
    for relative, expected in bitmap['design'].items():
        path = design.db / relative
        old.require(old.sha(path) == expected, '795 compiled identity changed')
        pins[str(path)] = expected
    el = OUT / 'current-population794-soc61-parent-20261008-01/combined.el'
    old.require(old.sha(el) == pins[str(el)], 'Qualified inherited EL changed')
    _, directives = native_inventory(el.read_bytes())
    owned = set()
    for scope, _, line in directives:
        match = re.match(r'^Branch (\d+) "(\d+)" "[^"\n]*" \((\d+)\) ', line)
        old.require(match is not None, 'Opaque inherited Branch ownership')
        owned.add((scope, match[1], match[2], match[3]))
    dispatch = (OUT / 'old-image-source-evidence-20261006-01/ara_dispatcher.sv').read_text()
    route_evidence = wide_routes(dispatch)
    sequencer = (ROOT / 'hardware/src/ara_sequencer.sv').read_text()
    old.require('[VMUL:VFWREDOSUM]    : vfu = VFU_MFpu;' in sequencer,
                'VFU opcode classifier changed')
    stage = old.code((ROOT / 'hardware/src/lane/operand_queues_stage.sv').read_text())
    alu_a = stage[:stage.index(') i_operand_queue_alu_a (')]
    for parameter, value in [('SupportIntExt2', "1'b1"), ('SupportIntExt4', "1'b1"),
                             ('SupportIntExt8', "1'b1"), ('SupportReduct', "1'b1"),
                             ('SupportNtrVal', "1'b0"), ('FPUSupport', 'FPUSupportNone')]:
        old.require(re.search(r'\.' + parameter + r'\s*\(\s*' + re.escape(value) + r'\s*\)', alu_a),
                    'AluA literal parameter changed: ' + parameter)
    pkg = old.code((ROOT / 'hardware/include/ara_pkg.sv').read_text())
    operation_enum = re.search(r'typedef enum logic.*?\{(.*?)\}\s*ara_op_e;', pkg, re.S)[1]
    tokens = re.findall(r'\b(?:V[A-Z][A-Z0-9_]*|VMUL)\b', operation_enum)
    lower, upper = tokens.index('VMUL'), tokens.index('VFWREDOSUM')
    old.require(all(lower <= tokens.index(op) <= upper for op in WIDE_OPS),
                'WideFP2 opcode escaped MFPU enum range')
    candidates, inherited, protected, dynamic, other_groups = [], [], [], [], []
    for lane in range(4):
        scope = prior['group5_protected_complement'][lane]['scope']
        row = bitmap['metrics']['branch'][scope]
        definition = design.definition(scope, 'branch')
        old.require(definition.get('chksum') == '1417162425' and
                    row['checksum'] in (None, '1417162425'), '795 branch shape checksum mismatch')
        group = next(n for n in definition.iter('branch_spec') if n.get('id') == '5')
        old.require(group.get('chksum') == '718333796', 'Group5 checksum mismatch')
        raw = format(int(row['bits'], 16), '0%db' % row['width'])
        full_points = points('branch', definition, row['width'])
        old.require(len(full_points) == row['width'], 'Complete Branch serializer partition changed')
        grouped = [p for p in full_points if p['native_id'] == '5']
        for node in definition.iter('branch_spec'):
            if node.get('id') != '5':
                ids = [p['vector'] for p in full_points if p['native_id'] == node.get('id')]
                other_groups.append(dict(scope=scope, group=node.get('id'),
                                         checksum=node.get('chksum'),
                                         protected_vectors=ids))
        old.require(len(grouped) == 46, 'Full group5 partition changed')
        for point in grouped:
            reason = classify(group, point, lane)
            key = (scope, '5', group.get('chksum'), point['vector'])
            hit = raw[point['raw_index']] == '1'
            item = dict(scope=scope, lane=lane, module_checksum='1417162425',
                        group_checksum='718333796', current795_hit=hit,
                        already_EL_owned=key in owned, reason=reason, point=point)
            if reason:
                old.require(not hit, 'Counterexample: proved unreachable branch actually hit')
                (inherited if key in owned else candidates).append(item)
            else:
                protected.append(item)
                if point['vector'] == '44':
                    dynamic.append(item)
    old.require(len(candidates) + len(inherited) + len(protected) == 184,
                'Full four-scope partition incomplete')
    old_set = {(t['scope'], t['vector']) for t in prior['targets']}
    new_set = {(t['scope'], t['point']['vector']) for t in candidates}
    old.require(old_set <= new_set, 'Lost frozen24 candidate')
    for path, expected in pins.items():
        old.require(old.sha(Path(path)) == expected, 'Read-end input drift')
    pins[str(Path(__file__).resolve())] = old.sha(Path(__file__).resolve())
    return dict(status='ALUA_GROUP5_795_SOURCE_ONLY_EXACT_UNREACHABLE_CANDIDATES',
                population=795, input_pins=pins, prior24_unchanged=True,
                candidates=candidates, inherited_proved_vectors=inherited,
                protected_group5_vectors=protected, total_group5_vectors=184,
                protected_other_branch_groups=other_groups,
                protection='Only listed candidate vectors of group5 are source-reviewed. Every other group/vector, all other metrics, ports, control and dynamic producer bits remain protected.',
                candidate_count=len(candidates), additional_to_frozen24=len(candidates)-24,
                reasons=dict(Counter(t['reason'] for t in candidates)),
                widefp2_all_nine_producers=route_evidence,
                proof='Frozen24 unconditional domain excludes vf4/vf8 and AdjustFPCvt. Each of nine WideFP2 vs1 producers has an MFPU opcode; PE classifier routes it to MFPU, never AluA. AluA MaskUnit forces None. Source-literal guards and constant per-instance lane_id rule out only contradictory paths within their active conversion case. Reset/hold/FIFO domain induction is inherited without alteration.',
                limitations=['Source-only review, not native point-label qualification or formal-tool certificate.',
                             'SExt2/ZExt2 default-EEW leaves and all other unclassified vectors are protected, not assumed unreachable.',
                             'Branch vector expressions are diagnostic compiled shape identities; no native EL selector fabricated.'],
                dynamic_protected_short_vadd_vectors=dynamic,
                finite_dynamic_case=dict(opcode='vadd.vv v24,v8,v16', vtype='e8,m1,tu,mu',
                    VL=4, vstart=0, vm=1, source='initialized distinct full128-byte v8/v16 and destination v24',
                    current795_missing_coordinates=sum(not x['current795_hit'] for x in dynamic),
                    recommendation='DO_NOT_RUN_ALREADY_HIT_IN795' if all(x['current795_hit'] for x in dynamic) else 'STATIC_ONLY_NOT_AUTHORIZED',
                    prediction='All four lanes receive AluA conv=None/eew=EW8/elem_count=1. At initial elem_count_q=0: last_packet=1, incomplete_packet=1; SupportNtrVal=0 selects group5 vector44, raw_index32. This path is dynamic and must remain protected.',
                    oracle='bytewise add modulo256 for four active elements, preserve other124 destination bytes and all non-destination VRF/CSR/memory guards; full native source/destination snapshots. No runtime authorized.'),
                MFPU_B12_status='NOT_EXPANDED_IN_THIS_PACKET', EDA_started=False,
                EL_created=False, native_qualified=False, official_percentage=None,
                supersedes='01/02 are draft receipts. This final packet adds full other-Branch protection and explicit795 dedup for the legal short-VL path; frozen24 proof is unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    old.require(not args.output.exists(), 'Preserve earlier evidence')
    result = collect()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(result['status'], result['candidate_count'], result['additional_to_frozen24'], old.sha(args.output))
