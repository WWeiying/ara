"""Independent reset events/architecture evidence, not a replacement UVM report."""
import json
from pathlib import Path
import re
import run_gap115_active_reset as run
from ara_verify import uvm_dut as uvm

life, require = run.life, run.require
OUT = life.OUT/'gap115-two-epoch-postprocess-742-20261007-02'


def relative_events(events):
    require(bool(events), 'Missing epoch events')
    origin = events[0][0]
    require(all(a[0] <= b[0] for a, b in zip(events, events[1:])), 'Nonmonotonic epoch events')
    return [(row[0]-origin, *row[1:]) for row in events]


def traffic(events):
    pending = {}; requests = responses = 0
    for cycle, req, rid, insn, resp, sid, exc in events:
        # The frozen passive scoreboard accepts request before same-cycle response.
        if req:
            require(rid not in pending, 'Duplicate live CVXIF ID')
            pending[rid] = insn; requests += 1
        if resp:
            require(sid in pending and exc == 0, 'Orphan/exception CVXIF response')
            pending.pop(sid); responses += 1
    return dict(requests=requests, responses=responses, aborted=len(pending))


def backend(rows, vectors, cancelled):
    starts = {}; owners = {}; allocations = completions = writes = 0
    for row in rows:
        if row['event'] == 'arch_start':
            seq = int(row['order']); require(seq not in starts, 'Duplicate architectural owner')
            starts[seq] = (int(row['cycle']), int(row['insn'], 16))
    for row in vectors:
        event = row['event']
        if event == 'config': continue
        seq, vid, cycle = int(row['arch_seq']), int(row['vid']), int(row['cycle'])
        require(seq in starts and cycle >= starts[seq][0] and int(row['insn'], 16) == starts[seq][1],
                'Unbound/early backend event')
        if event == 'alloc':
            require(vid not in owners, 'Duplicate live VID')
            owners[vid] = (seq, cycle); allocations += 1
        else:
            require(event in ('write', 'done') and vid in owners and owners[vid][0] == seq and
                    cycle >= owners[vid][1], 'Orphan/late/wrong-owner backend event')
            if event == 'done': owners.pop(vid); completions += 1
            else:
                require(0 <= int(row['lane']) < 4 and 0 < int(row['be'], 16) <= 255,
                        'Unknown/empty backend write')
                writes += 1
    require({seq for seq, _ in owners.values()} == set(cancelled), 'Unexpected reset-cancelled owners')
    cu = sorted((r['event'][4:], int(r['order']), int(r['port']), int(r['cycle'])) for r in rows
                if r['event'] in ('uop_alloc', 'uop_done'))
    vu = sorted((r['event'], int(r['arch_seq']), int(r['vid']), int(r['cycle'])) for r in vectors
                if r['event'] in ('alloc', 'done'))
    require(cu == vu and allocations == completions+len(owners), 'Independent lifecycle/conservation differs')
    return dict(allocations=allocations, completions=completions, aborted=len(owners), write_events=writes,
                cancelled_arch_sequences=sorted(cancelled))


def events_audit(log, epochs, original, symbols):
    require(not re.search(r'(?m)^UVM_(?:ERROR|FATAL)\b|\[ARA_CONTRACT_ERROR\]|trace.*truncat', log),
            'Observed UVM/protocol error or truncation')
    require(log.count('[ARA_UVM_RESET_TEST] kind=read accepted=1 read_index=1') == 1 and
            log.count('[ARA_UVM_RESET_TEST] kind=read released=1') == 1, 'Exact read reset trigger differs')
    observed = list(uvm._RESET_OBSERVED.finditer(log))
    require(len(observed) == 2 and [int(m['epoch']) for m in observed] == [1, 2], 'UVM reset epochs differ')
    cut = int(observed[1]['cycle'])
    ue, ui = uvm._events(log, '[CVXIF/EVENT]', uvm._UVM_EVENT, 10)
    ce, ci = uvm._events(log, '[ARA_CONTRACT_TRACE]', uvm._CONTRACT_EVENT, 16)
    require(not ui and not ci and 0 < len(ue) < 100000 and 0 < len(ce) < 100000,
            'Incomplete/malformed CVXIF events')
    # UVM and contract clocks keep counting across reset; RVFI cycle_q resets.
    require(len(ue) == len(ce) and uvm._event_digest(ue) == uvm._event_digest(ce),
            'Global independent CVXIF event sequence differs')
    split = len([e for e in ue if e[0] < cut])
    pairs = [([e for e in ue if e[0] < cut], ce[:split]),
             ([e for e in ue if e[0] > cut], ce[split:])]
    require(not any(e[0] == cut for e in ue), 'Traffic in UVM reset cycle')
    cvx = []
    for (u, c), (rows, _) in zip(pairs, epochs):
        require(u and c and uvm._event_digest(u) == uvm._event_digest(c), 'Independent CVXIF epoch events differ')
        require(all(a[0] <= b[0] for a, b in zip(c, c[1:])), 'Nonmonotonic contract traffic')
        commits = [(int(r['cycle']), r['event'], int(r['trans_id']), int(r['insn'], 16), int(r['trap']))
                   for r in rows if r['event'] in ('cvx_req', 'cvx_resp')]
        flattened = [(e[0], name, key, insn, exc) for e in c for name, key, insn, exc in
                     ([('cvx_req', e[2], e[3], 0)] if e[1] else [])+
                     ([('cvx_resp', e[5], 0, e[6])] if e[4] else [])]
        normalized = [(cy, ev, key, insn if ev == 'cvx_req' else 0, exc) for cy, ev, key, insn, exc in commits]
        require(relative_events(normalized) == relative_events(flattened),
                'Commit/contract CVXIF identity/relative time differs')
        counts = traffic(c); require(counts['aborted'] == 0, 'Unexpected pending CVXIF reset cancellation')
        cvx.append(counts)
    require(original['contract_counts']['requests'] == cvx[1]['requests'] == 75 and
            original['contract_counts']['responses'] == cvx[1]['responses'] == 75 and
            original['contract_counts']['exceptions'] == original['contract_counts']['protocol_errors'] ==
            original['contract_counts']['outstanding'] == 0, 'Final independent contract disagrees')
    require(original['uvm_backend_event_sha256'] == original['vector_backend_event_sha256'] and
            original['uvm_backend_event_count'] == original['vector_backend_event_count'] < 100000,
            'UVM/vector independent backend events differ')
    first_rows, first_vectors = epochs[0]
    active = [r for r in first_vectors if r['event'] == 'alloc' and int(r['vl']) == 128 and
              int(r['eew']) == 3 and int(r['vd']) in (8, 16)]
    require(len(active) == 2 and {int(r['vd']) for r in active} == {8, 16}, 'Expected DIV/load active pair missing')
    sites = {8: (symbols['g115_div'], 0x8602e457), 16: (symbols['g115_first_ar_load'], 0x020f7807)}
    for r in active:
        pc, word = sites[int(r['vd'])]
        retires = [c for c in first_rows if c['event'] == 'retire' and int(c['pc'], 16) == pc]
        require(int(r['insn'], 16) == word and not any(v['event'] == 'done' and v['arch_seq'] == r['arch_seq']
                for v in first_vectors) and len(retires) == 1 and int(retires[0]['insn'], 16) == word and
                int(retires[0]['trap']) == 0 and int(retires[0]['cycle']) >= int(r['cycle']),
                'Cancelled backend completed or accepted architectural retirement differs')
    cancelled = {int(r['arch_seq']) for r in active}
    return dict(cvx_epochs=cvx, backend_epochs=[backend(*epochs[0], cancelled), backend(*epochs[1], set())],
                cancelled_allocations=active,
                axi_reset_trigger='Frozen TB index1 requires one actual Ara AR handshake before reset',
                axi_burst_conservation_verified=False,
                axi_missing_evidence='Frozen monitor exports no per-read AR/R events; check/report summaries absent',
                uvm_check_report_pass=False)


def collect():
    require(not OUT.exists(), 'Fresh postprocess output required')
    pre = life.read_bound(run.PRE/'preflight.json', life.digest(run.PRE/'preflight.json'))
    manifest = life.read_bound(run.RUN/'manifest.json', life.digest(run.RUN/'manifest.json'))
    require(manifest['pins'][str(run.PRE/'preflight.json')] == life.digest(run.PRE/'preflight.json'),
            'Executed preflight differs')
    pins = life.merge_pins(pre['pins'], manifest['pins'])
    status = json.loads((run.RUN/'simulation-status.json').read_bytes())
    require(status['returncode'] == 0, 'Simulation not clean terminal')
    paths = [run.RUN/n for n in ('manifest.json', 'simulation-status.json', 'failure.json', 'console.log',
                                'run.vcs.log', 'commit_trace.csv', 'vector_trace.csv')]
    paths += [run.PRE/'preflight.json', Path(__file__).resolve(), Path(__file__).with_name('test_postprocess_gap115_events_v2.py')]
    paths += [p for p in (run.RUN/'code.vdb').rglob('*') if p.is_file()]
    for path in paths: pins = life.merge_pins(pins, {str(path): life.digest(path)})
    old_dispatcher = life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    pins = life.merge_pins(pins, {str(old_dispatcher): '9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43'})
    life.check(pins); OUT.mkdir()
    try:
        audit = run.reset.check_real_uvm_log(run.RUN/'run.vcs.log', require_events=True, require_backend=True,
            require_axi=True, vector_trace=run.RUN/'vector_trace.csv', reset_kind='read')
        life.save(OUT/'original-uvm-audit.json', audit)
        cf, cr = run.reset.read_csv(run.RUN/'commit_trace.csv'); vf, vr = run.reset.read_csv(run.RUN/'vector_trace.csv')
        epochs, cycle = run.reset.split_epochs(cr, vr)
        events = events_audit((run.RUN/'run.vcs.log').read_text(), epochs, audit, pre['symbols'])
        life.save(OUT/'independent-event-audit.json', events)
        for index, (commits, vectors) in enumerate(epochs):
            ep = OUT/('epoch%d'%index); ep.mkdir()
            run.reset.write_csv(ep/'commit_trace.csv', cf, commits); run.reset.write_csv(ep/'vector_trace.csv', vf, vectors)
        memory = {}
        for row in epochs[1][0]:
            if row['event'] == 'retire':
                store = run.shared.shared.scalar_store(row)
                if store: memory.update({store[0]+i: b for i, b in enumerate(store[1])})
        def value(name, offset=0, size=8):
            address = pre['symbols'][name]+offset
            require(all(address+i in memory for i in range(size)), 'Missing recovery byte')
            return int.from_bytes(bytes(memory[address+i] for i in range(size)), 'little')
        run.oracle(value)
        scalar = run.shared.shared.spike_trace.compare_commit_prefix(run.PRE/'spike.trace', OUT/'epoch1/commit_trace.csv',
            0x80000000, terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
        life.save(OUT/'recovery-scalar.json', scalar); run.shared.shared.scalar_exact(scalar, pre['counts'])
        vector = run.shared.shared.compare_vector_commits(run.PRE/'spike.trace', OUT/'epoch1/commit_trace.csv',
                                                        OUT/'epoch1/vector_trace.csv', 0x80000000)
        life.save(OUT/'recovery-vector.json', vector)
        require(vector['status'] == 'PASS' and vector['compared_instructions'] == 35 and
                vector['compared_bytes'] == 7168 and vector['skipped_unknown_bytes'] ==
                vector['non_bit_exact_instructions'] == vector['unobservable_instructions'] == 0 and
                not vector['incomplete_requests'] and not vector['unretired_requests'] and
                all(i['unknown_write_bytes'] == i['skipped_unknown_bytes'] == i['mismatch_count'] == 0
                    for i in vector['instructions']), 'Exact recovery vector contract differs')
        require((run.RUN/'console.log').read_text().count('Core Test *** SUCCESS ***') == 1 and
                not run.shared.shared.check_contract_log(run.RUN/'run.vcs.log'), 'Terminal/contract error')
        base = run.shared.reviewed.base.BASE
        book = life.read_bound(base/'admission-manifest.json', run.shared.reviewed.base.BASE_SHA)
        before = life.read_bound(base/'combined-bits.json', book['output_pins'][str(base/'combined-bits.json')])
        inputs = OUT/'measurement-inputs.txt'
        with inputs.open('x') as stream:
            stream.write(str(run.shared.reviewed.base.capture.BUILD/'sim/simv.vdb')+'\n'+str(run.RUN/'code.vdb')+'\n')
        single = run.shared.shared.bitmap.collect(inputs)
        delta = run.shared.shared.bitmap.delta(before, run.shared.shared.bitmap.combine(before, single))
        hits = []
        for lane in range(4):
            scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_vfus.i_vmfpu.i_simd_div'%lane
            old, new = before['metrics']['fsm'][scope], single['metrics']['fsm'][scope]
            require(new['width'] == old['width'] == 29 and new['checksum'] == old['checksum'] == '1353388720',
                    'SIMD native shape differs')
            for index in (9, 24):
                bit = 1 << (28-index)
                hits.append(dict(scope=scope, raw_index=index, before=bool(int(old['bits'], 16)&bit),
                                 single=bool(int(new['bits'], 16)&bit)))
        life.check(pins); life.save(OUT/'input-pins.json', pins); life.save(OUT/'single-bits.json', single)
        life.save(OUT/'qualification.json', dict(status='EVENTS_AND_ARCH_RECOVERY_PASS_AXI_ACCOUNTING_HOLD_NOT_ADMITTED',
            checks=679, reset_cycle=cycle, targets=hits, delta=delta, coverage_admitted=False,
            uvm_check_report_pass=False, axi_burst_conservation_verified=False,
            original_failure_preserved=str(run.RUN/'failure.json')))
    except Exception as exc:
        life.save(OUT/'failure.json', dict(reason=str(exc), coverage_admitted=False)); raise


if __name__ == '__main__': collect()
