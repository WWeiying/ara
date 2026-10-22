"""Terminal-only store-burst qualification; no active trace reads, VCS or admission."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

import run_store_fifo_burst_simulation as runner
import collect_opivx_vsbc_strict as common
import qualify_pure_war_parent_terminal as reviewed
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log, parse_contract_summary

p, life, require = runner.p, runner.life, runner.require
RUN = life.OUT / 'store-fifo-burst-old-image-729-agent-20261006-01'
PREPARED = RUN.with_name(RUN.name + '.prepared.json')
PRE_SEAL = '713f47a0032fb597cdddb12d809f68ee5f67a0bdacd3ab538d25ecb6084021b9'
RUN_SEAL = 'fa74f8704a11cf0928804146f6c0c8a2f881356d8875532f7d47aa5ee48035c2'
PLAN_STATUS = 'STORE_BURST_OFFLINE_QUALIFICATION_PREPARED_NO_DUT_READ'


def binding(pre, prepared):
    runner.validate(pre)
    require(prepared['preflight_seal'] == PRE_SEAL and
            prepared['preflight'] == str(runner.PRE / 'preflight-manifest.json') and
            prepared['output'] == str(RUN) and prepared['command'] == runner.command(RUN) and
            prepared['timeout_s'] == 600 and prepared['baseline_tests'] == 729 and
            prepared['targets'] == pre['targets'] and
            prepared['scalar_reference_counts'] == pre['reference_counts'] and
            prepared['image_sha256'] == runner.frozen.IMAGE_SEAL and
            prepared['elf_sha256'] == pre['input_elf_sha256'] and
            prepared['coverage_admitted'] is False and prepared['admission_performed'] is False,
            'Prepared input/command binding differs')


def terminal(state, actual, started, prepared):
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and
            type(state.get('returncode')) is int and state['returncode'] == 0 and
            state.get('case') == p.NAME and state.get('timeout') is False and
            state.get('coverage_admitted') is False and state.get('admission_performed') is False and
            state.get('terminal_oracle_verified') is False, 'HOLD: no successful OS terminal receipt')
    require(actual == prepared, 'Actual command/pins differ from reviewed preparation')
    require(type(started.get('pid')) is int and started['pid'] > 0 and
            started['pid'] == started['process_group'] == state['pid'] and
            started['budget_s'] == 600 and started['input_elf'] == str(runner.PRE / 'input.elf') and
            started['elf_sha256'] == prepared['elf_sha256'] and started['image'] == str(life.IMAGE) and
            started['image_sha256'] == prepared['image_sha256'] and
            started['command'] == prepared['command'] and started['foreground_lifetime'] is True and
            started['coverage_admitted'] is False, 'Actual startup identity/budget differs')
    require(type(state.get('wall_seconds')) in (int, float) and state['wall_seconds'] >= 0,
            'Missing runner wall receipt')


def ranges(symbols):
    return [(symbols[name], symbols[name] + size) for name, size in
            [('sfb_dest', 8064), ('sfb_seed', 144), ('sfb_dump', 1008), ('sfb_cfg', 448)]]


def observed(rows, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    require(retired and [int(r['order']) for r in retired] == list(range(len(retired))), 'Incomplete retirement order')
    memory, read_bytes, terminals, stores, gpr = {}, set(), [], [], {0: 0}
    begin = symbols['sfb_burst_begin']
    for row in retired:
        pc, insn = int(row['pc'], 16), int(row['insn'], 16)
        require(not int(row['trap']) and pc != symbols['trap_fail'], 'Unexpected trap/fatal retirement')
        if begin <= pc < symbols['sfb_burst_end']:
            require((pc - begin) % 4 == 0, 'Unaligned burst retirement')
            index = (pc - begin) // 4
            require(insn == p.burst_words()[index], 'Burst opcode/no-fence contract differs')
            if index % 2 == 0:
                phase, store = divmod(len(stores), 8)
                require(phase < 7 and index == store * 2 and
                        gpr.get(10) == symbols['sfb_dest'] + (phase * 8 + store) * 144 + 8,
                        'Store phase/order/actual a0 base differs')
                stores.append(dict(pc=hex(pc), base=hex(gpr[10]), VL=p.LENGTHS[phase],
                                   architectural_expected_bytes=4 * p.LENGTHS[phase]))
        rd = int(row['rd'])
        if rd:
            require(not re.search('[xz]', row['rd_wdata'], re.I), 'Unknown retired scalar register')
            gpr[rd] = int(row['rd_wdata'], 16)
        address = int(row['mem_addr'], 16)
        rm, wm = int(row['mem_rmask'], 16), int(row['mem_wmask'], 16)
        access = common.scalar_memory(insn)
        if access is None:
            require(not rm and not wm, 'Unknown scalar memory effect')
            continue
        kind, width = access
        mask = ((1 << width) - 1) << (address & 7)
        require(address % width == 0 and rm == (mask if kind == 'read' else 0) and
                wm == (mask if kind == 'write' else 0), 'Scalar memory mask/alignment differs')
        if kind == 'write':
            value = int(row['mem_wdata'], 16) & ((1 << (width * 8)) - 1)
            if address == symbols['tohost']:
                terminals.append(row)
        elif any(start <= address < end for start, end in ranges(symbols)):
            require(rd != 0 and any(start <= address and address + width <= end for start, end in ranges(symbols)),
                    'Unobservable/truncated readback')
            value = int(row['rd_wdata'], 16) & ((1 << (width * 8)) - 1)
            read_bytes.update(range(address, address + width))
        else:
            continue
        memory.update({address + i: b for i, b in enumerate(value.to_bytes(width, 'little'))})
    require(len(stores) == 56 and terminals == [retired[-1]], 'Incomplete56/extra/nonfinal terminal')
    require(read_bytes == {a for start, end in ranges(symbols) for a in range(start, end)}, 'Incomplete scalar memory footprint/readback')
    def read(name, offset=0, width=4):
        address = symbols[name] + offset
        require(all(address + i in memory for i in range(width)), 'Missing signature bytes: ' + name)
        return int.from_bytes(bytes(memory[address + i] for i in range(width)), 'little')
    require(read('g75_result') == 2360 and read('g75_result', 4) == read('num_failed') == 0 and
            read('tohost', width=8) == 1, 'Software signature/terminal differs')
    for phase in range(7):
        for store in range(8):
            for word in range(36):
                require(read('sfb_dest', ((phase * 8 + store) * 36 + word) * 4) == p.destination(phase, word),
                        'Destination active/tail/guard differs')
        for word in range(36):
            require(read('sfb_dump', (phase * 36 + word) * 4) == p.source(word), 'Source VRF dump/guards differ')
        for when in range(2):
            require([read('sfb_cfg', ((phase * 2 + when) * 4 + i) * 8, 8) for i in range(4)] ==
                    [p.LENGTHS[phase], 16, 0, 128], 'Actual before/after CSR differs')
    for word in range(36):
        require(read('sfb_seed', word * 4) == p.source(word), 'Source memory/guard differs')
    return dict(checks=2360, failed_checks=0, retired_target_stores=56, store_bases=stores,
                explicit_scalar_read_bytes=len(read_bytes), active_destination_bytes=3840,
                untouched_destination_tail_bytes=3328, destination_guard_bytes=896,
                source_memory_bytes=144, complete_source_dump_bytes=1008,
                directly_observed_per_owner_AXI=False, FIFO_push_pop_measured=False)


def lifecycle(rows, vectors, mapping, reference):
    starts, pending, current, intervals = {}, {}, {}, defaultdict(list)
    requests, responses, ba, bd = [], [], Counter(), Counter()
    previous = -1
    for r in rows:
        event, cycle, seq, tid = r['event'], int(r['cycle']), int(r['order']), int(r['trans_id'])
        require(cycle >= previous, 'Commit cycles out of order'); previous = cycle
        if event == 'arch_start':
            require(seq >= 0 and seq not in starts and tid not in pending, 'Duplicate architectural/live transaction')
            starts[seq], pending[tid] = r, [seq, False]
        elif event == 'cvx_req':
            require(tid in pending and not pending[tid][1], 'Unknown/duplicate request')
            seq = pending[tid][0]
            require(r['insn'] == starts[seq]['insn'], 'Request opcode differs')
            pending[tid][1] = True; requests.append(seq)
        elif event == 'cvx_resp':
            require(tid in pending and pending[tid][1] and seq == -1 and
                    int(r['trap']) == int(r['pc'], 16) == int(r['insn'], 16) == 0, 'Rejected/unknown response')
            responses.append(pending.pop(tid)[0])
        elif event in ('uop_alloc', 'uop_done'):
            vid = int(r['port'])
            require(seq in starts and 0 <= vid < 8 and tid == int(starts[seq]['trans_id']) and
                    r['insn'] == starts[seq]['insn'] and cycle >= int(starts[seq]['cycle']), 'Backend owner/opcode/time differs')
            if event == 'uop_alloc':
                require(vid not in current, 'Live SID reused')
                current[vid] = dict(seq=seq, start=cycle, end=None)
                intervals[vid].append(current[vid]); ba[seq, vid, cycle] += 1
            else:
                require(vid in current and current[vid]['seq'] == seq and cycle >= current[vid]['start'], 'Unowned backend completion')
                current.pop(vid)['end'] = cycle; bd[seq, vid, cycle] += 1
        else:
            require(event == 'retire' and int(r['trap']) == 0, 'Unknown event/retirement trap')
    require(not pending and Counter(requests) == Counter(responses) == Counter(starts.keys()), 'CVXIF conservation differs')
    require(not current and Counter((s, v) for s, v, _ in ba.elements()) ==
            Counter((s, v) for s, v, _ in bd.elements()), 'Backend conservation differs')
    va, vd, metadata, previous = Counter(), Counter(), {}, -1
    for r in vectors:
        cycle, seq, vid, event = int(r['cycle']), int(r['arch_seq']), int(r['vid']), r['event']
        require(cycle >= previous and int(r['nr_lanes']) == 4 and int(r['vlen_bits']) == 1024, 'Vector cycle/geometry differs')
        previous = cycle
        if event == 'config':
            continue
        require(seq in starts and event in ('alloc', 'done', 'write') and r['insn'] == starts[seq]['insn'], 'Unknown vector owner/event')
        if event == 'alloc':
            key = seq, vid, cycle
            require(key not in metadata, 'Duplicate native allocation')
            metadata[key] = r; va[key] += 1
        else:
            eligible = [a for a in intervals[vid] if a['start'] < cycle]
            if not eligible:
                eligible = [a for a in intervals[vid] if a['start'] == cycle]
            require(eligible, 'No native SID history')
            owner = eligible[-1]; key = owner['seq'], vid, owner['start']
            require(owner['seq'] == seq and owner['start'] <= cycle <= owner['end'] and key in metadata,
                    'Native SID owner mismatch')
            require(all(r[k] == metadata[key][k] for k in ('insn', 'use_vd', 'vd', 'eew', 'vl', 'vstart')), 'Native metadata drift')
            if event == 'done':
                vd[seq, vid, cycle] += 1
            else:
                require(int(r['use_vd']) == 1 and 0 <= int(r['lane']) < 4 and 0 <= int(r['source']) < 5, 'Invalid native writer')
    require(va == ba and vd == bd, 'Commit/native lifecycle identities differ')
    target_sequences = [seq for seq, index in sorted(mapping.items()) if reference[index].instruction == p.STORE]
    require(len(target_sequences) == 56 and len(set(target_sequences)) == 56, 'Not56 mapped stores')
    burst_begin = p_symbols(reference)['sfb_burst_begin']
    for ordinal, seq in enumerate(target_sequences):
        phase, store = divmod(ordinal, 8)
        commit = reference[mapping[seq]]
        require(commit.pc == burst_begin + store * 8 and any(s == seq for s, _, _ in ba),
                'Store PC/backend execution missing')
        native = [r for (s, _, _), r in metadata.items() if s == seq]
        require(native and all(int(r['use_vd']) == 0 and int(r['vl']) == p.LENGTHS[phase] and
                              int(r['vstart']) == 0 and int(r['eew']) == 2 for r in native), 'Store native VL/EEW/write contract differs')
    return dict(requests=len(requests), responses=len(responses), exceptions=0,
                backend_uops=sum(ba.values()), target_store_sequences=target_sequences,
                current_SID_owner_checked=True, placeholder_PC_not_used=True,
                FIFO_push_pop_measured=False, directly_observed_per_owner_AXI=False)


def p_symbols(reference):
    # The eight store words are unique to the bounded burst in the sealed ELF.
    matches = [c.pc for c in reference if c.instruction == p.STORE]
    require(len(matches) == 56, 'Reference store population differs')
    return dict(sfb_burst_begin=matches[0])


def vector_exact(result, reference):
    fixed = dict(status='PASS', compared_instructions=1, compared_bytes=128, skipped_unknown_bytes=0,
                 non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024, selected_index=None,
                 stopped_at_spike_index=None, trapped_requests=[], first_mismatch=None,
                 unobservable_instructions=0, incomplete_requests=[], unretired_requests=[])
    for key, value in fixed.items():
        require(key in result and type(result[key]) is type(value) and result[key] == value, 'Full vector comparison differs: ' + key)
    expected = [c for c in reference if c.vector_writes]
    records = result['instructions']
    require(len(expected) == len(records) == 1 and
            [(int(r['pc'], 16), int(r['instruction'], 16)) for r in records] == [(c.pc, c.instruction) for c in expected] and
            records[0]['compared_bytes'] == 128 and records[0]['status'] == 'PASS' and
            records[0]['skipped_unknown_bytes'] == records[0]['unknown_write_bytes'] == records[0]['mismatch_count'] == 0 and
            records[0]['first_mismatch'] is None, 'Exact vector writer record differs')


def native_exact(activities, mapping, reference):
    expected = {seq: reference[index] for seq, index in mapping.items() if reference[index].vector_writes}
    require(len(expected) == 1 and {seq for seq, activity in activities.items() if activity.writes} == set(expected),
            'Native writer population differs')
    for seq, commit in expected.items():
        activity, seen = activities[seq], set()
        require(activity.instruction == commit.instruction, 'Native activity opcode differs')
        for w in activity.writes:
            require(w.arch_seq == seq and w.instruction == commit.instruction and w.source == 4 and w.eew == 2 and
                    0 <= w.lane < 4 and 0 <= w.be <= 255 and w.be & ~w.known_be == 0, 'Native source/EEW/unknown differs')
            for byte in range(8):
                if w.be & (1 << byte):
                    key = w.addr, w.lane, byte
                    require(key not in seen, 'Duplicate native accepted byte'); seen.add(key)
        actual = vc._architectural_bytes(activity.writes, 4, 1024)
        wanted = {(8, b): (commit.vector_writes[8] >> (8 * b)) & 255 for b in range(128)}
        require({key: value for key, (value, _) in actual.items()} == wanted, 'Full native source seed differs')
    return dict(architectural_writers=1, known_bytes=128, skipped_unknown_bytes=0, duplicate_bytes=0,
                source='VLDU', directly_observed_per_owner_AXI=False)


def logs(console, vcslog, control):
    for text in (console, vcslog):
        require(not re.search(r'Fatal:|Error:|Fatal-\[|Error-\[|\[ARA_CONTRACT_ERROR\]|Core Test \*\*\* FAILED', text),
                'Simulator/protocol/failure diagnostic')
        for line in text.splitlines():
            if re.search(r'\bUVM_(?:ERROR|FATAL)\b', line):
                require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0+\s*', line) is not None,
                        'HOLD: UVM error, no scalar policy override for RVV store case')
    require(vcslog.count('Core Test *** SUCCESS ***') == 1, 'Missing/extra CoreSUCCESS')
    summaries = [parse_contract_summary(line.strip()) for line in console.splitlines() if '[ARA_CONTRACT]' in line]
    require(len(summaries) == 1 and summaries[0] is not None, 'Malformed/multiple contract summary')
    counts = summaries[0]
    require(counts['requests'] == counts['responses'] == control['requests'] > 0 and
            counts['exceptions'] == 0 and all(counts[k] == 0 for k in
            ('protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')), 'Incomplete/error/stalled contract')
    return dict(UVM_errors=0, UVM_fatals=0, contract=counts)


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct plan directory')
    pre = life.read_bound(runner.PRE / 'preflight-manifest.json', PRE_SEAL)
    prepared = life.read_bound(PREPARED, RUN_SEAL)
    binding(pre, prepared)
    pins = life.merge_pins(pre['pins'], prepared['pins'])
    dependencies = [Path(__file__).resolve(), Path(__file__).with_name('test_qualify_store_fifo_burst_terminal.py'),
                    Path(common.__file__).resolve(), Path(reviewed.__file__).resolve(),
                    *sorted((life.ROOT / 'verification/ara_verify').glob('*.py'))]
    sourcepins = life.read_bound(p.SOURCE_PINS, p.SOURCE_SEAL)
    monitor = life.ROOT / 'hardware/tb/ara_commit_monitor.sv'
    pins = life.merge_pins(pins, {str(monitor): sourcepins[str(monitor)]})
    pins = life.merge_pins(pins, {str(path): life.digest(path) for path in dependencies})
    pins = life.merge_pins(pins, {str(runner.PRE / 'preflight-manifest.json'): PRE_SEAL, str(PREPARED): RUN_SEAL})
    life.check(pins)
    out.mkdir()
    life.save(out / 'plan.json', dict(status=PLAN_STATUS, run=str(RUN), pins=pins,
        preflight_seal=PRE_SEAL, parent_prepared_seal=RUN_SEAL,
        targets=pre['targets'], baseline_tests=729, actualDUT_read=False,
        simulations_started=False, coverage_admitted=False, UVM_override_allowed=False,
        raw_gain_requires_latest_formal_baseline_at_least=729,
        directly_observed_per_owner_AXI=False, FIFO_push_pop_measured=False))
    print(json.dumps(dict(plan=str(out / 'plan.json'), seal=life.digest(out / 'plan.json'), pins=len(pins), actualDUT_read=False)))


def collect(plan_path, seal, out):
    plan = life.read_bound(plan_path, seal); life.check(plan['pins'])
    require(plan['status'] == PLAN_STATUS and plan['run'] == str(RUN) and
            plan['preflight_seal'] == PRE_SEAL and plan['parent_prepared_seal'] == RUN_SEAL, 'Plan binding differs')
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh qualification directory')
    # No trace or simulator log is opened until the foreground runner has a terminal receipt.
    require((RUN / 'simulation-status.json').is_file(), 'HOLD: no terminal receipt; active traces must not be read')
    pins = life.merge_pins(plan['pins'], {str(plan_path): seal})
    def read(name):
        path = RUN / name
        require(path.resolve() == path and not path.is_symlink(), 'Aliased run evidence')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(life.digest(path) == digest, 'Evidence changed while reading')
        pins[str(path)] = digest
        return raw
    state = json.loads(read('simulation-status.json'))
    pre = life.read_bound(runner.PRE / 'preflight-manifest.json', PRE_SEAL)
    prepared = life.read_bound(PREPARED, RUN_SEAL)
    terminal(state, json.loads(read('manifest.json')), json.loads(read('started.json')), prepared)
    out.mkdir()
    try:
        rows = common.read_csv(read('commit_trace.csv'), common.COMMIT_FIELDS)
        vectors = common.read_csv(read('vector_trace.csv'), common.VECTOR_FIELDS)
        reference = p.shared.parse_spike_commits(runner.PRE / 'spike.trace')
        require(p.validate(reference, pre['symbols'], (runner.PRE / 'spike.trace').read_text()) == pre['validation'], 'Sealed reference oracle differs')
        starts, retires, rejected = vc._parse_architecture_mapping(RUN / 'commit_trace.csv')
        require(not rejected, 'Rejected request')
        mapping = vc._map_spike_commits(vc._map_architecture_retires(starts, retires, rejected), reference)
        control = lifecycle(rows, vectors, mapping, reference)
        log_proof = logs(read('console.log').decode('utf-8'), read('run.vcs.log').decode('utf-8'), control)
        require(not check_contract_log(RUN / 'run.vcs.log'), 'Full contract log gate failed')
        signature = observed(rows, pre['symbols'])
        tracer = reviewed.tracer_exact(read('trace_hart_0.log').decode('utf-8'), rows)
        read('trace_hart_0_commit.log')
        scalar = common.spike_trace.compare_commit_prefix(runner.PRE / 'spike.trace', RUN / 'commit_trace.csv',
            0x80000000, terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
        life.save(out / 'scalar-comparison.json', scalar)
        common.scalar_exact(scalar, pre['reference_counts'])
        vector = common.compare_vector_commits(runner.PRE / 'spike.trace', RUN / 'commit_trace.csv', RUN / 'vector_trace.csv', 0x80000000)
        life.save(out / 'vector-comparison.json', vector)
        vector_exact(vector, reference)
        lanes, vlen, activities = vc._parse_vector_trace(RUN / 'vector_trace.csv')
        require((lanes, vlen) == (4, 1024), 'Native geometry differs')
        native = native_exact(activities, mapping, reference)
        life.check(pins)
        for name, value in [('observed-memory.json', signature), ('lifecycle.json', control), ('logs.json', log_proof),
                            ('tracer-proof.json', tracer), ('native-byte-proof.json', native)]:
            life.save(out / name, value)
        outputs = {str(path): life.digest(path) for path in out.iterdir() if path.is_file()}
        life.save(out / 'qualification.json', dict(status='STORE_FIFO_BURST_FULL_DUT_SCALAR_VECTOR_MEMORY_QUALIFIED_NOT_ADMITTED',
            pins=life.merge_pins(pins, outputs), run=str(RUN), baseline_tests=729, checks=2360,
            native_known_bytes=128, full_scalar_reference_instructions=pre['reference_counts']['matched_instructions'],
            terminal_source='FOREGROUND_RUNNER_OS_RETURN_RECEIPT', OS_returncode=state['returncode'],
            UVM_errors=0, UVM_override_applied=False, full_ISA_signoff=False,
            coverage_admitted=False, simulations_started=False, rtl_changed=False,
            raw_coverage_increment_not_collected=True, target_hit_verified=False,
            raw_gain_requires_latest_formal_baseline_at_least=729,
            directly_observed_per_owner_AXI=False, FIFO_push_pop_measured=False))
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'qualification.json'), coverage_admitted=False)))
    except Exception as error:
        drift = None
        try:
            life.check(pins)
        except Exception as pin_error:
            drift = str(pin_error)
        life.save(out / 'failure.json', dict(status='STORE_BURST_QUALIFICATION_HOLD_NOT_ADMITTED',
                  reason=type(error).__name__ + ': ' + str(error), pins=pins,
                  post_failure_pin_error=drift, coverage_admitted=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'collect'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--seal')
    args = parser.parse_args()
    if args.mode == 'prepare':
        require(args.output is not None and args.plan is None and args.seal is None, 'Prepare requires fresh output only')
        prepare(args.output.absolute())
    else:
        require(args.plan is not None and args.seal is not None, 'Fixed plan and seal required')
        if args.mode == 'verify':
            plan = life.read_bound(args.plan, args.seal)
            require(plan['status'] == PLAN_STATUS and plan['run'] == str(RUN), 'Plan identity differs')
            life.check(plan['pins']); print('VERIFY_PASS NO_ACTIVE_DUT_READ NO_VCS')
        else:
            require(args.output is not None, 'Collect requires fresh output')
            collect(args.plan.absolute(), args.seal, args.output.absolute())


if __name__ == '__main__':
    main()
