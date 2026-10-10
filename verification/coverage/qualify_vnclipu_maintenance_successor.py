"""Exact observed VNCLIPU maintenance proof; offline only, never admission."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

import qualify_vnclipu_parent_terminal as old
import ara_verify.vector_commit as vc

life, require = old.life, old.require
FAIL = life.OUT / 'vnclipu-terminal-qualified-parent-20261006-01/failure.json'
FAIL_SEAL = 'f6036390b935a0c4bf1abba6dc6911bc98fb99581574cad76307ccf127658e4f'
PARENT_PLAN = life.OUT / 'vnclipu-terminal-qualification-prepared-parent-20261006-01/plan.json'
PARENT_SEAL = 'd8c508a4c50f69faed9318b633a83feec1975dfd92a3feca1752b5828add5af7'
SEQ, PC, WORD = 124, 0x80002754, 0xba804857
# Exact observed allocations: (cycle, VID, vd, EEW, VL, completion).
PHASES = ((101170, 0, 16, 1, 64, 101186),
          (101171, 1, 8, 2, 32, 101194),
          (101196, 0, 16, 1, 2, 101203))


def reference_state(reference):
    state, matches = {}, []
    for c in reference:
        if c.pc == PC:
            matches.append(c)
            require(c.instruction == WORD and set(c.vector_writes) == {16} and
                    c.vector_vl == 2 and c.vector_vstart == 0 and c.vector_sew == 16 and
                    c.vector_tail_agnostic is False and c.vector_mask_agnostic is False,
                    'Recovery Spike identity/policy differs')
            pre = {r: state[r] for r in (8, 16)}
            post = c.vector_writes[16]
        state.update(c.vector_writes)
    require(len(matches) == 1, 'Exactly one recovery Spike commit required')
    require(all(pre[r].to_bytes(128, 'little') == old.p.expected_register(r, 0) for r in pre) and
            post.to_bytes(128, 'little') == old.p.expected_register(16, 2),
            'Spike pre/post differs from independent byte oracle')
    return pre, post


def maintenance(rows, vectors, reference):
    pre, post = reference_state(reference)
    starts = [r for r in rows if r['event'] == 'arch_start' and int(r['order']) == SEQ]
    require(len(starts) == 1 and int(starts[0]['insn'], 16) == WORD and
            int(starts[0]['cycle']) == 101168 and int(starts[0]['trans_id']) == 2,
            'Exact recovery architectural owner differs')
    retired = [r for r in rows if r['event'] == 'retire' and int(r['pc'], 16) == PC]
    require(len(retired) == 1 and int(retired[0]['insn'], 16) == WORD, 'Recovery retirement differs')
    control = [r for r in rows if int(r['order']) == SEQ and r['event'] in ('uop_alloc', 'uop_done')]
    expected = sorted((event, cycle, vid) for cycle, vid, _, _, _, done in PHASES
                      for event, cycle in (('uop_alloc', cycle), ('uop_done', done)))
    require(sorted((r['event'], int(r['cycle']), int(r['port'])) for r in control) == expected and
            all(int(r['insn'], 16) == WORD and int(r['trans_id']) == 2 for r in control),
            'Exact backend SID/owner/cycle differs')
    selected = [r for r in vectors if int(r['arch_seq']) == SEQ]
    require(all(r['event'] in ('alloc', 'done', 'write') and int(r['insn'], 16) == WORD and
                r['nr_lanes'] == '4' and r['vlen_bits'] == '1024' and r['use_vd'] == '1' and
                r['vstart'] == '0' for r in selected), 'Recovery vector owner/type differs')
    edges = [r for r in selected if r['event'] != 'write']
    wanted = sorted((event, time, vid, vd, eew, vl) for time, vid, vd, eew, vl, done in PHASES
                    for event, time in (('alloc', time), ('done', done)))
    require(sorted((r['event'], *(int(r[k]) for k in ('cycle', 'vid', 'vd', 'eew', 'vl'))) for r in edges)
            == wanted, 'Exact vector allocation/completion shape differs')
    groups = [[], [], []]
    for number, r in enumerate(selected):
        if r['event'] != 'write':
            continue
        cycle = int(r['cycle'])
        candidates = [i for i, (start, vid, vd, eew, vl, done) in enumerate(PHASES)
                      if start <= cycle <= done and (int(r['vid']), int(r['vd']), int(r['eew']), int(r['vl']))
                      == (vid, vd, eew, vl)]
        require(len(candidates) == 1, 'Unowned or mistyped maintenance write')
        i = candidates[0]
        lo, hi, source = ((101178, 101185, 3), (101187, 101193, 3), (101202, 101202, 0))[i]
        require(lo <= cycle <= hi and int(r['source']) == source and 0 <= int(r['lane']) < 4,
                'Maintenance cycle/source/lane differs')
        data, known = vc._write_data(r['wdata'])
        be = int(r['be'], 16)
        require(0 < be <= 255 and not (be & ~known), 'Unknown accepted maintenance byte')
        groups[i].append(vc.VectorWrite(number, cycle, SEQ, int(r['vid']), int(r['lane']),
            source, WORD, int(r['eew']), int(r['addr']), be, data, known))
    decoded = []
    for i, writes in enumerate(groups):
        require(len(writes) == (16 if i < 2 else 2), 'Missing/extra maintenance write rows')
        merged = {}
        for w in writes:
            one = vc._architectural_bytes([w], 4, 1024)
            require(not (set(one) & set(merged)), 'Duplicate accepted phase byte')
            merged.update(one)
        reg = 8 if i == 1 else 16
        require(set(merged) == {(reg, b) for b in range(128 if i < 2 else 4)},
                'Missing/extra maintenance or tail bytes')
        expected_value = pre[reg] if i < 2 else post
        require(all(value is not None and value == (expected_value >> (8*b)) & 255
                    for (_, b), (value, _) in merged.items()), 'Maintenance/prestate/result mismatch')
        decoded.append(merged)
    final = dict(decoded[0]); final.update(decoded[2])
    require(bytes(final[(16, b)][0] for b in range(128)) == post.to_bytes(128, 'little'),
            'Full128 destination poststate mismatch')
    return dict(arch_seq=SEQ, pc=hex(PC), instruction=hex(WORD), known_source_maintenance_bytes=128,
        destination_prestate_maintenance_bytes=128, destination_poststate_bytes=128,
        legal_result_bytes=4, source_register=8, destination_register=16,
        genuinely_unknown_bytes=0, independent_expected_byte_oracle=True)


def vector_gate(result, rows, vectors, reference):
    proof = maintenance(rows, vectors, reference)
    records = result['instructions']
    require(len(records) == 33 and result['skipped_unknown_bytes'] == 128 and
            sum(r['skipped_unknown_bytes'] for r in records[:-1]) == 0 and
            records[-1]['skipped_unknown_bytes'] == 128 and records[-1]['arch_seq'] == SEQ and
            int(records[-1]['pc'], 16) == PC and int(records[-1]['instruction'], 16) == WORD and
            records[-1]['compared_bytes'] == 128 and records[-1]['uops'] == 3 and
            records[-1]['write_events'] == 34, 'Unexpected generic skip population')
    # Only this independently proved non-destination maintenance population is classified.
    classified = deepcopy(result)
    classified['skipped_unknown_bytes'] = classified['instructions'][-1]['skipped_unknown_bytes'] = 0
    old.r1.vector_exact(classified, [81], reference)
    return dict(proof, generic_skipped_counter=128, generic_counter_is_not_true_unknown=True,
                other_skipped_bytes=0, coverage_admitted=False)


def prepare(output):
    require(output.parent == life.OUT and output.resolve() == output and not output.exists(), 'Fresh plan only')
    parent = life.read_bound(PARENT_PLAN, PARENT_SEAL)
    failure = life.read_bound(FAIL, FAIL_SEAL)
    require(failure['status'] == 'VNCLIPU_TERMINAL_QUALIFICATION_FAIL_NOT_ADMITTED' and
            failure['reason'] == 'ValueError: Full vector gate differs: skipped_unknown_bytes' and
            failure['post_failure_pin_error'] is None and failure['coverage_admitted'] is False,
            'Different original failure')
    pins = life.merge_pins(parent['pins'], failure['pins'])
    paths = [Path(__file__).resolve(), Path(__file__).with_name('test_qualify_vnclipu_maintenance_successor.py')]
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in paths})
    pins = life.merge_pins(pins, {str(PARENT_PLAN): PARENT_SEAL, str(FAIL): FAIL_SEAL})
    life.check(pins)
    output.mkdir()
    life.save(output/'plan.json', dict(status='VNCLIPU_MAINTENANCE_SUCCESSOR_PREPARED_NOT_COLLECTED',
        pins=pins, run=str(old.RUN), baseline=725, original_failure_seal=FAIL_SEAL,
        provenance='PARENT_AGENT_REVIEW_REQUIRED_BEFORE_OFFLINE_COLLECT',
        coverage_admitted=False, simulations_started=False, rtl_changed=False))
    return life.digest(output/'plan.json')


def collect(plan_path, seal, output):
    plan = life.read_bound(plan_path, seal); life.check(plan['pins'])
    require(plan['status'] == 'VNCLIPU_MAINTENANCE_SUCCESSOR_PREPARED_NOT_COLLECTED' and
            plan['run'] == str(old.RUN) and plan['original_failure_seal'] == FAIL_SEAL and
            plan['coverage_admitted'] is False, 'Successor plan identity differs')
    require(output.parent == life.OUT and output.resolve() == output and not output.exists(), 'Fresh collect only')
    pins = life.merge_pins(plan['pins'], {str(plan_path): seal}); output.mkdir()
    def read(name):
        path = old.RUN/name
        require(str(path) in pins and not path.is_symlink(), 'Unpinned runtime evidence')
        require(life.digest(path) == pins[str(path)], 'Runtime evidence drift')
        return path.read_bytes()
    try:
        pre = life.read_bound(old.p.PRE/'preflight-manifest.json', old.PRE_SEAL)
        prepared = life.read_bound(old.PREPARED, old.RUN_SEAL)
        old.binding(pre, prepared, life.read_bound(old.REVIEW, old.REVIEW_SEAL))
        old.terminal(json.loads(read('simulation-status.json')), json.loads(read('manifest.json')), prepared)
        rows = old.common.read_csv(read('commit_trace.csv'), old.common.COMMIT_FIELDS)
        vectors = old.common.read_csv(read('vector_trace.csv'), old.common.VECTOR_FIELDS)
        control = old.lifecycle(rows, vectors, pre['symbols'])
        old.logs(read('console.log').decode(), read('run.vcs.log').decode(), control)
        require(not old.check_contract_log(old.RUN/'run.vcs.log'), 'Full contract gate failed')
        observed = old.observed(rows, pre['symbols'])
        trap = old.tracer_exact(read('trace_hart_0.log').decode(), rows, pre['symbols'])
        read('trace_hart_0_commit.log')
        scalar = old.common.spike_trace.compare_commit_prefix(old.p.PRE/'spike.trace', old.RUN/'commit_trace.csv',
            0x80000000, terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
        old.common.scalar_exact(scalar, pre['reference_counts'])
        reference = old.p.shared.parse_spike_commits(old.p.PRE/'spike.trace')
        vector = old.common.compare_vector_commits(old.p.PRE/'spike.trace', old.RUN/'commit_trace.csv',
            old.RUN/'vector_trace.csv', 0x80000000)
        proof = vector_gate(vector, rows, vectors, reference)
        for name, value in [('scalar-comparison', scalar), ('vector-comparison-unmodified', vector),
                            ('maintenance-proof', proof), ('observed-signatures', observed),
                            ('lifecycle', control), ('trap-proof', trap)]:
            life.save(output/(name+'.json'), value)
        life.check(pins)
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in output.iterdir()})
        life.save(output/'qualification.json', dict(status='VNCLIPU_FULL_DUT_MAINTENANCE_QUALIFIED_NOT_ADMITTED',
            pins=pins, baseline=725, coverage_admitted=False, simulations_started=False, rtl_changed=False,
            raw_coverage_increment_not_collected=True, original_failure_preserved=True,
            generic_skipped_counter=128, proven_known_source_maintenance_bytes=128, genuinely_unknown_bytes=0))
        return life.digest(output/'qualification.json')
    except Exception as error:
        life.save(output/'failure.json', dict(status='VNCLIPU_SUCCESSOR_FAIL_NOT_ADMITTED',
            reason=type(error).__name__+': '+str(error), pins=pins, coverage_admitted=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'collect'))
    parser.add_argument('--output', type=Path); parser.add_argument('--plan', type=Path); parser.add_argument('--seal')
    a = parser.parse_args()
    if a.mode == 'prepare':
        require(a.output and not a.plan and not a.seal, 'Prepare arguments')
        print(prepare(a.output.absolute()))
    elif a.mode == 'verify':
        require(a.plan and a.seal and not a.output, 'Verify arguments')
        life.check(life.read_bound(a.plan, a.seal)['pins']); print('VERIFY_PASS_NOT_COLLECTED_NOT_ADMITTED')
    else:
        require(a.plan and a.seal and a.output, 'Collect arguments')
        print(collect(a.plan.absolute(), a.seal, a.output.absolute()))


if __name__ == '__main__': main()
