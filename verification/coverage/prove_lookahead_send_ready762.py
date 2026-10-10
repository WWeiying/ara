"""Reset-reachable conservative two-slot proof; no EDA or application."""
import argparse
from collections import deque
from itertools import product
import json
from pathlib import Path

import capture_dispatcher_four762 as prior

life, require, native = prior.life, prior.require, prior.native
SOURCE = life.ROOT / 'hardware/src/vlsu/store_load_lookahead_pair.sv'
SOURCE_SHA = 'ba8ec0605fd37db5b9574c3f04bc6c962fa23a0582e6029999fcbb5a8d57ea20'
BOOK = life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
BASE_SHA = '6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_store_load_lookahead'
TARGETS = {23, 47}
E, P, S, F, R, V = range(6)
# Inputs deliberately overapproximate arbitration/locks/address matching.
# Accepted hints require an Empty slot; private response fire requires Fill
# or a same-cycle Send AR handshake. No other external correlation is needed.
EVENTS = tuple(product(range(2), repeat=8))


def step(q, event, inv, hit, beats=8):
    states, ptr, killed = q
    accept, ar, response, last, okay, normal, locked, replay_done = event
    indices = {kind: [i for i, state in enumerate(states) if state == kind] for kind in range(6)}
    idx = lambda kind: indices[kind][-1]
    busy = bool(indices[S] or indices[F])
    pf = bool(indices[S]) and ar
    ff = bool(indices[F] or pf) and response
    target = idx(F) if indices[F] else (idx(S) if indices[S] else 0)
    final = ptr == beats - 1
    d, k = list(states), list(killed)
    if not busy and indices[P]:
        d[idx(P)] = S
    for i, state in enumerate(states):
        bad = bool(inv & (1 << i)) or normal
        if state == E:
            k[i] = 0
            if accept and i == idx(E): d[i] = P if busy or indices[P] else S
        elif state == P:
            if bad: d[i] = E
        elif state == S:
            if pf: d[i] = F
            elif not locked and bad: d[i] = E
        elif state == R:
            if bad: d[i] = E
            elif hit == i: d[i] = V
        elif state == V and replay_done:
            d[i] = E
        if state in (P, S, F) and bad: k[i] = 1
    if ff:
        if last:
            d[target] = E if killed[target] or (inv & (1 << target)) or normal or not okay or not final else R
        if not okay or (final and not last): k[target] = 1
        ptr = 0 if last else min(ptr + 1, beats - 1)
    return tuple(d), ptr, tuple(k)


def invariant(q):
    states, ptr, _ = q
    private = sum(s in (S, F) for s in states)
    return private <= 1 and (private != 0 or ptr == 0) and (S not in states or ptr == 0)


def explore(beats=8):
    initial = ((E, E), 0, (0, 0))
    seen, todo, edges, send_ready = {initial}, deque([initial]), 0, []
    while todo:
        q = todo.popleft()
        require(invariant(q), 'Reset-reachable invariant counterexample')
        successors = {step(q, event, inv, hit, beats)
                      for event in EVENTS for inv in range(4) for hit in (-1, 0, 1)}
        edges += len(successors)
        for nxt in successors:
            require(invariant(nxt), 'One-step induction counterexample')
            if any(a == S and b == R for a, b in zip(q[0], nxt[0])):
                send_ready.append((q, nxt))
            if nxt not in seen:
                seen.add(nxt); todo.append(nxt)
    return dict(reachable_states=len(seen), unique_edges=edges, send_ready_edges=len(send_ready),
                states=sorted(seen))


def groups(shape, bits):
    metric = bits['metrics']['fsm'][SCOPE]
    require(metric['width'] == 48 and metric['checksum'] == '3008642282', 'Wrong FSM module')
    defs = [d for d in shape.iter('fsmdef') if d.get('chksum') == metric['checksum'] and
            any(i.get('name') == SCOPE for i in d.findall('fsminst'))]
    require(len(defs) == 1 and defs[0].get('file') == '586', 'Wrong frozen source identity')
    gs, offset, chosen = [], 0, set()
    for machine in defs[0].iter('fsmfsm'):
        ids = {s.get('id'): s.get('name') for s in machine.findall('state')}
        for mode, nodes in [('State', machine.findall('state')), ('Transition', machine.findall('transition'))]:
            rows = []
            for node in nodes:
                source = ids[node.get('fromid')] if mode == 'Transition' else None
                dest = ids[node.get('toid')] if source else node.get('name')
                target = offset in TARGETS
                if target:
                    require(mode == 'Transition' and source == 'Send' and dest == 'Ready' and
                            node.get('fromid') == '5' and node.get('toid') == '3' and node.get('line') == '203' and
                            not ((int(metric['bits'], 16) >> (47-offset)) & 1), 'Wrong/hit Send->Ready target')
                    chosen.add(offset)
                rows.append(dict(name=source+'->'+dest if source else dest, raw_index=offset,
                                 source=source, destination=dest, target=target, attributes=dict(node.attrib)))
                offset += 1
            gs.append(dict(scope=SCOPE, checksum=metric['checksum'], machine=dict(machine.attrib), mode=mode, rows=rows))
    require(offset == 48 and chosen == TARGETS and
            [g['machine']['name'] for g in gs] == ['state_q_0']*2+['state_q_1']*2, 'Incomplete 48-point binding')
    return gs


def prepare(path):
    require(path.parent == life.OUT and not path.exists(), 'Fresh independent evidence required')
    book = life.read_bound(BOOK, BOOK_SHA)
    require(book[str(SOURCE)] == SOURCE_SHA and life.digest(SOURCE) == SOURCE_SHA, 'Frozen source differs')
    admission = life.read_bound(prior.BASE/'admission-manifest.json', BASE_SHA)
    bitpath = prior.BASE/'combined-bits.json'
    bits = life.read_bound(bitpath, admission['output_pins'][str(bitpath)])
    ledger = prior.BASE/'combined-inputs.txt'
    require(life.digest(ledger) == admission['output_pins'][str(ledger)], 'Ledger differs')
    members = ledger.read_text().splitlines()
    require(members[1:] == bits['tests'] and len(members) == 763, 'Not formal762')
    design = native.Design(Path(members[0]))
    require(design.source(SCOPE)['resolved_path'] == str(SOURCE), 'Foreign compiled source')
    parameters = design.definition(SCOPE, 'tgl').get('param')
    require(parameters == 'Bytes=128,DataWidth=128,Beats=8,PtrWidth=3,ar_t=ara_axi_ar_chan_t,r_t=ara_axi_r_chan_t,req_t=ara_axi_req_t,resp_t=ara_axi_resp_t', 'Not frozen 8-beat specialization')
    shape = Path(members[0])/'snps/coverage/db/shape/fsm.verilog.shape.xml'
    require(life.digest(shape) == bits['design']['shape/fsm.verilog.shape.xml'], 'FSM shape differs')
    gs = groups(native.read_xml(shape), bits)
    proof = explore()
    require(proof['send_ready_edges'] == 0, 'Reachable target; no exclusion allowed')
    require(explore(1)['send_ready_edges'] > 0, 'Single-beat negative calibration failed')
    illegal = step(((S, E), 7, (0, 0)), (0, 1, 1, 1, 1, 0, 0, 0), 0, -1)
    require(illegal[0][0] == R, 'Arbitrary-state negative calibration failed')
    paths = [SOURCE, BOOK, bitpath, ledger, prior.BASE/'admission-manifest.json', shape,
             Path(__file__).resolve(), Path(__file__).with_name('test_prove_lookahead_send_ready762.py')]
    paths += [design.db/'design/verilog.design.xml', design.db/'auxiliary/verilog.sourceinfo.xml',
              design.db/'shape/tgl.verilog.shape.xml', design.db/'shape/tgl.verilog.info.xml']
    pins = {str(p): life.digest(p) for p in paths}
    life.check(pins)
    life.save(path, dict(status='SOURCE_BOUND_RESET_REACHABLE_SEND_READY2_PROOF_NOT_NATIVE_NOT_APPLIED',
        scope=SCOPE, population=762, parameters=parameters, targets=2, protected=46, groups=gs, pins=pins,
        proof=proof, negative_single_beat_reachable=True, negative_illegal_initial_state_reachable=True,
        reasoning=['At most one private Send/Fill owner.', 'Idle private channel and every Send have pointer zero.',
                   'Fill persists until RLAST; RLAST clears pointer before subsequent Pending promotion.',
                   'Same-cycle Send AR/R LAST at pointer zero is early LAST for Beats8 and selects Empty, not Ready.'],
        abstraction='Address/AR/lock/hit/replay/invalid/error inputs independently overapproximated; killed flags and RTL assignment priorities retained.',
        scope_limits='Known reset-established sequential states, settled combinational next-state; no claim for initial X, forced/corrupt state or Beats1. External reset goes Empty. No other transition waived.',
        native_qualified=False, application_approved=False))
    print(json.dumps(dict(path=str(path), seal=life.digest(path), states=proof['reachable_states'], edges=proof['unique_edges'])))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    prepare(p.parse_args().output.absolute())
