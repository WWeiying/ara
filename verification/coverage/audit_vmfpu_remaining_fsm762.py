"""Frozen VMFPU FSM reachability audit only; no EDA, exclusion, or admission."""
import argparse
from itertools import product
from pathlib import Path
import re

import rank_admitted_fsm_gaps762 as rank

life, require = rank.life, rank.require
PRIORITY = life.OUT / 'admitted762-fsm-priority-parent-20261007-01.json'
PRIORITY_SHA = '67c936292c506e29d3e13b244b39dd9bab284ac2988f4c1f918b8d4335548d90'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
BUILD = life.OUT / 'repaired-aligned-build-20260930-01'
SOURCE = life.ROOT / 'hardware/src/lane/vmfpu.sv'
SOURCE_SHA = '1f8288ed2a50f8fa59a7ea3d6f3a7e3138f5219bbb1af52e864d9dfe359d8307'
RESET_POSITIONS = ({11, 16, 19, 32, 35}, {11, 16, 19, 23, 32})
HANDOFF = ({30, 33, 36}, {30})


def source_controls(text):
    assignments = re.findall(r'mfpu_state_d\s*=\s*([^;]+);', text)
    require(len(assignments) == 16, 'State assignment inventory changed')
    require(assignments.count('LN0_REDUCTION_COMMIT') == 1 and
            assignments.count('SIMD_REDUCTION') == 1, 'Extra lane-restricted entry')
    rx = text.split('      INTER_LANES_REDUCTION_RX: begin')[1].split(
        '      LN0_REDUCTION_COMMIT: begin')[0]
    require("if (lane_id_i == '0) begin" in rx, 'Missing lane polarity')
    lane_entry = rx.split("if (lane_id_i == '0) begin", 1)[1]
    require(lane_entry.index('mfpu_state_d = SIMD_REDUCTION;') <
            lane_entry.index('end else begin') < lane_entry.index('mfpu_state_d = LN0_REDUCTION_COMMIT;'),
            'Lane entry polarity/ordering changed')
    require(text.count('vinsn_queue_d.issue_cnt -= 1;') == 2 and
            text.count('vinsn_queue_d.issue_cnt += 1;') == 1,
            'Queue issue counter has another writer')
    normal = text.split('      NO_REDUCTION: begin')[1].split('      INTRA_LANE_REDUCTION: begin')[0]
    wait = text.split('      MFPU_WAIT: begin')[1].split('      default:;')[0]
    require('vinsn_queue_d.issue_cnt -= 1;' in normal and
            'vinsn_queue_d.issue_cnt -= 1;' in wait, 'Queue decrement moved')
    require("if (vinsn_queue_d.issue_cnt == '0 && !prevent_commit) begin" in text and
            "if (mfpu_state_q == NO_REDUCTION) begin" in text and
            "mfpu_state_q            <= NO_REDUCTION;" in text,
            'Acceptance/commit/reset guard changed')
    return dict(state_assignment_count=len(assignments), queue_decrement_sites=2,
                queue_increment_sites=1, restricted_entry_sites=2)


def induction(depth=4):
    # Source-derived queue abstraction, not an RTL solver or DUT observation.
    # Reduction owns an outstanding queue entry until WAIT. Data, VL, masks,
    # ready/valid and ordinary commit may vary without decrementing that entry.
    checked = 0
    for q, finishing, accepting, full, commit in product(
            range(1, depth + 1), range(2), range(2), range(2), range(2)):
        before_accept = q
        require(before_accept > 0, 'Lost reduction owner before WAIT')
        acceptance_state_override = accepting and not full and before_accept == 0
        require(not acceptance_state_override, 'Direct reduction handoff')
        after = q + int(bool(accepting and not full and q < depth))
        require(after > 0, 'Reduction owner lost after accept')
        checked += 1
    return dict(depth=depth, boolean_queue_cases=checked, counterexamples=0,
                basis='Positive outstanding reduction entry; decrement only NO_REDUCTION/WAIT',
                quantified='All legal positive counts; arbitrary data/SEW/VL/mask/round/handshakes',
                boundary='Known legal reset-reachable queue protocol; not X/delta/fault-injected states')


def classify(lane, point):
    require(0 <= lane < 4 and point['machine'] == 'mfpu_state_q', 'Wrong lane/machine')
    pos = point['raw_position']
    if point['kind'] == 'State':
        require((pos, point['name']) == ((3, 'LN0_REDUCTION_COMMIT') if lane == 0 else
                                      (7, 'SIMD_REDUCTION')), 'Unexpected remaining state')
        return 'FIXED_LANE_ENTRY_UNREACHABLE_SOURCE_CANDIDATE'
    if pos in RESET_POSITIONS[lane != 0]:
        require(point['name'].endswith('->NO_REDUCTION') and point['source_line'] == '2733',
                'Reset identity differs')
        return 'REACHABLE_EXTERNAL_RESET_MISSING_PROTECTED'
    require((pos in HANDOFF[lane != 0] and point['source_line'] == '740') or
            (lane == 0 and pos == 36 and point['source_line'] == '742'),
            'Unexpected remaining transition')
    require(point['name'] in {'OSUM_REDUCTION->INTRA_LANE_REDUCTION',
                            'SIMD_REDUCTION->INTRA_LANE_REDUCTION',
                            'SIMD_REDUCTION->OSUM_REDUCTION'}, 'Wrong handoff identity')
    return 'QUEUE_OWNER_INDUCTION_UNREACHABLE_SOURCE_CANDIDATE'


def collect():
    priority = life.read_bound(PRIORITY, PRIORITY_SHA)
    life.check(priority['pins'])
    require(priority['population'] == 762, 'Priority population drift')
    # Independently regenerate exact raw identities and the prior exclusion flags.
    actual = rank.collect()
    require(priority['instances'] == actual['instances'], 'Priority differs from raw762/shape')
    bookpath = BUILD / 'build-source-pins.json'
    book = life.read_bound(bookpath, BOOK_SHA)
    paths = [SOURCE, life.ROOT / 'hardware/src/ara.sv',
             life.ROOT / 'hardware/src/lane/lane.sv',
             life.ROOT / 'hardware/src/lane/vector_fus_stage.sv',
             life.ROOT / 'hardware/include/ara_pkg.sv',
             life.ROOT / 'hardware/src/ara_dispatcher.sv']
    pins = {str(p): book[str(p)] for p in paths[:-1]}
    dispatcher_snapshot = life.OUT / 'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    pins[str(dispatcher_snapshot)] = book[str(paths[-1])]
    life.check(pins)
    require(pins[str(SOURCE)] == SOURCE_SHA, 'Not frozen VMFPU')
    contract = source_controls(SOURCE.read_text())
    ara, lane, fus, pkg = [p.read_text() for p in paths[1:-1]]
    dispatcher = dispatcher_snapshot.read_text()
    require('.lane_id_i                       (lane[idx_width(NrLanes)-1:0]' in ara and
            '.lane_id_i              (lane_id_i' in lane and
            '.lane_id_i            (lane_id_i' in fus, 'Lane constant propagation differs')
    require('MfpuInsnQueueDepth = 4;' in pkg and
            'ara_req.op             = ara_pkg::VFREDUSUM;' in dispatcher and
            'ara_req.fp_rm   = acc_req_i.frm;' in dispatcher, 'Legal reduction producer differs')
    rows = []
    for lane_id in range(4):
        scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_vfus.i_vmfpu' % lane_id
        row = next(x for x in actual['instances'] if x['scope'] == scope)
        require(row['checksum'] == '3873291691', 'Compiled VMFPU FSM checksum')
        for point in row['missing']:
            if not point['already_native_qualified_exclusion']:
                rows.append(dict(scope=scope, lane=lane_id, checksum=row['checksum'],
                                 **point, classification=classify(lane_id, point)))
    counts = {c: sum(x['classification'] == c for x in rows)
              for c in sorted({x['classification'] for x in rows})}
    require(len(rows) == 30 and sorted(counts.values()) == [4, 6, 20], 'Remaining gap count')
    bits = life.read_bound(rank.BASE / 'combined-bits.json',
                          actual['pins'][str(rank.BASE / 'combined-bits.json')])
    prior = [p for p in bits['tests'] if any(t in p.lower() for t in ('vfred', 'external-reset', 'fpu-external'))]
    shape_path = next(Path(p) for p in actual['pins'] if p.endswith('/shape/fsm.verilog.shape.xml'))
    definition = next(n for n in rank.original.q.toggle.xml(shape_path).iter('fsmdef')
                      if n.get('chksum') == '3873291691')
    compiled = dict(definition=definition.attrib,
                    machines=[dict(attributes=m.attrib,
                                   states=[s.attrib for s in m.findall('state')],
                                   transitions=[t.attrib for t in m.findall('transition')])
                              for m in definition.iter('fsmfsm')],
                    raw_scope_vectors={scope: row for scope, row in bits['metrics']['fsm'].items()
                                       if scope.endswith('.i_vmfpu')},
                    native_selector_inferred_from_raw_ids=False)
    require(len(compiled['raw_scope_vectors']) == 4 and
            all(r['width'] == 37 for r in compiled['raw_scope_vectors'].values()),
            'VMFPU compiled capacity changed')
    lines = SOURCE.read_text().splitlines()
    excerpts = [dict(first_line=a, last_line=b, text='\n'.join(lines[a-1:b]))
                for a, b in ((695, 745), (2220, 2351), (2490, 2530), (2590, 2670), (2728, 2762))]
    pins.update(actual['pins'])
    for p in (PRIORITY, bookpath, Path(__file__).resolve(),
              Path(__file__).with_name('test_audit_vmfpu_remaining_fsm762.py'),
              Path(__file__).with_name('external_reset_driver.tcl')):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    return dict(status='VMFPU762_SOURCE_AUDIT_NATIVE_HOLD_NO_APPLICATION', population=762,
        pins=pins, source_contract=contract, source_excerpts=excerpts,
        compiled_identity=compiled, queue_induction=induction(), points=rows, counts=counts,
        scope_boundary='Fixed four lane IDs, reset-reachable legal known controls. No arbitrary X/delta claim.',
        parameter_reasoning='Lane restriction independent of SEW/VL/LMUL/FP support; queue owner '
                            'argument holds for any positive supported queue depth, instantiated depth4.',
        prior_related_inputs=prior, focused_stimulus=dict(
            name='vmfpu_ured_intra_external_reset', launch_ready=False, budget_seconds=600,
            setup='FS/VS enabled, frm=RNE, e64m8 VL128, vm=1, vstart=0; v8..v15=1.0, v1 seed=2.0',
            instruction='vfredusum.vs v2,v8,v1',
            producer_chain='OPFVV func6=000001 -> VFREDUSUM -> VFU_MFpu -> queue owner '
                           'positive -> next_mfpu_state=INTRA_LANE_REDUCTION',
            trigger='At negedge observe all four mfpu_state_q==1 and each queue issue_cnt>0, '
                    'then only external ara_tb.rst_n=0 for four full clocks; restart same ELF',
            predicted_raw_positions=[dict(lane=i, raw_position=19,
                                          name='INTRA_LANE_REDUCTION->NO_REDUCTION') for i in range(4)],
            predicted_gain='Up to4 FSM transitions, not measured or guaranteed; no new state expected',
            gold='Finite exact sum128+seed2=130.0 binary64 0x4060400000000000, fflags0; '
                 'Spike complete scalar/vector/CSR/fullVRF/immutable guards on fresh recovery epoch',
            audit='Epoch0 may abort; require stage/owner snapshot, exact external reset causality '
                  'and four clocks; no stale completion/write crossing; epoch1 full terminal oracle',
            dedup='Existing vfredusum and C910 reset cases have different cancellation machine; '
                  'all four raw19 remain zero in exact762, so neither proves this edge',
            blocker='Frozen shared external_reset_driver.tcl rejects mfpu_state_q paths; '
                    'needs reviewed precise selector successor, not internal force or NOP tuning',
            protected='All20 reachable reset arcs and all other FSM/control points remain protected'),
        native_status='HOLD: source candidates only; no typed native qualification or exclusion generated')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == life.OUT and not out.exists(), 'Fresh audit output required')
    result = collect()
    life.save(out, result)
    print(result['counts'])
    print('audit_sha256=' + life.digest(out))
