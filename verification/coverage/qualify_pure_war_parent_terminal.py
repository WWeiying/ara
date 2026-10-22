"""Offline pure-WAR terminal qualification; no simulation, raw collection or admission."""
from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import re

import build_pure_war_preflight as p
import run_pure_war_simulation as runner
import collect_opivx_vsbc_strict as common
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log, parse_contract_summary

life, require = p.life, p.require
RUN = life.OUT / 'pure-war-old-image-parent-20261006-01'
PREPARED = RUN.with_name(RUN.name + '.prepared.json')
RUN_SEAL = '451934511f1c7014169a180f53868e530f227849193c19d8c7252592c60d5493'
PLAN_STATUS = 'PURE_WAR_OFFLINE_QUALIFICATION_PREPARED_NOT_EXECUTED'


def binding(pre, prepared):
    runner.validate(pre)
    require(prepared['case'] == p.NAME and prepared['preflight_seal'] == runner.PRE_SEAL and
            prepared['preflight'] == str(runner.PRE / 'preflight-manifest.json') and
            prepared['output'] == str(RUN) and prepared['command'] == runner.command(RUN) and
            prepared['timeout_s'] == 600 and prepared['baseline_tests'] == 727 and
            prepared['targets'] == pre['targets'] and prepared['scalar_reference_counts'] == pre['reference_counts'] and
            prepared['image_sha256'] == runner.IMAGE_SEAL and prepared['elf_sha256'] == runner.ELF_SEAL and
            prepared['test_supplement_seal'] == runner.SUPPLEMENT_SEAL and
            prepared['coverage_admitted'] is False and prepared['admission_performed'] is False,
            'Prepared scope/ELF/command contract differs')


def terminal(state, actual, started, prepared):
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and type(state.get('returncode')) is int and
            state['returncode'] == 0 and state.get('case') == p.NAME and state.get('timeout') is False and
            state.get('coverage_admitted') is False and state.get('admission_performed') is False and
            state.get('terminal_oracle_verified') is False, 'Failed/nonterminal simulation')
    require(actual == dict(prepared, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'),
            'Actual runtime command/ELF/authorization differs')
    require(type(started.get('pid')) is int and started['pid'] > 0 and
            started['pid'] == started['process_group'] == state['pid'] and started['budget_s'] == 600 and
            started['input_elf'] == str(runner.PRE / 'input.elf') and started['elf_sha256'] == runner.ELF_SEAL and
            started['image'] == str(life.IMAGE) and started['image_sha256'] == runner.IMAGE_SEAL and
            started['command'] == prepared['command'] and started['foreground_lifetime'] is True and
            started['coverage_admitted'] is False, 'Startup identity/budget differs')


def lifecycle(rows, vectors, symbols):
    starts, pending, current, intervals = {}, {}, {}, defaultdict(list)
    requests, responses, allocations, completions = [], [], Counter(), Counter()
    backend_alloc, backend_done = Counter(), Counter()
    previous = -1
    for r in rows:
        event, cycle, seq, tid = r['event'], int(r['cycle']), int(r['order']), int(r['trans_id'])
        require(cycle >= previous, 'Commit cycles out of order'); previous = cycle
        if event == 'arch_start':
            require(seq >= 0 and seq not in starts and tid not in pending, 'Duplicate architecture/live transaction')
            starts[seq], pending[tid] = r, [seq, False]
        elif event == 'cvx_req':
            require(tid in pending and not pending[tid][1], 'Unknown/duplicate request')
            s = pending[tid][0]
            require(int(r['insn'], 16) == int(starts[s]['insn'], 16), 'Request opcode differs')
            pending[tid][1] = True; requests.append(s)
        elif event == 'cvx_resp':
            require(tid in pending and pending[tid][1] and seq == -1 and
                    int(r['pc'], 16) == int(r['insn'], 16) == int(r['trap']) == 0,
                    'Unknown/rejected response or placeholder drift')
            responses.append(pending.pop(tid)[0])
        elif event in ('uop_alloc', 'uop_done'):
            vid = int(r['port']); key = seq, vid
            require(seq in starts and 0 <= vid < 8 and tid == int(starts[seq]['trans_id']) and
                    int(r['insn'], 16) == int(starts[seq]['insn'], 16) and cycle >= int(starts[seq]['cycle']),
                    'Backend owner/SID/opcode/time differs')
            if event == 'uop_alloc':
                require(vid not in current, 'Live global SID reused')
                interval = dict(seq=seq, vid=vid, start=cycle, end=None)
                current[vid] = interval; intervals[vid].append(interval)
                allocations[key] += 1; backend_alloc[seq, vid, cycle] += 1
            else:
                require(vid in current and current[vid]['seq'] == seq and cycle >= current[vid]['start'],
                        'Unallocated/wrong-owner backend completion')
                current.pop(vid)['end'] = cycle
                completions[key] += 1; backend_done[seq, vid, cycle] += 1
        else:
            require(event == 'retire' and not int(r['trap']), 'Unknown commit event/retirement trap')
    require(not pending and Counter(requests) == Counter(responses) == Counter(starts.keys()), 'Request/response conservation')
    require(not current and allocations == completions, 'Incomplete backend execution')
    va, vd, metadata = Counter(), Counter(), {}
    previous = -1
    for r in vectors:
        cycle, seq, vid, event = int(r['cycle']), int(r['arch_seq']), int(r['vid']), r['event']
        require(cycle >= previous and int(r['nr_lanes']) == 4 and int(r['vlen_bits']) == 1024, 'Vector cycle/configuration differs')
        previous = cycle
        if event == 'config': continue
        require(seq in starts and event in ('alloc', 'done', 'write') and
                int(r['insn'], 16) == int(starts[seq]['insn'], 16), 'Vector owner/opcode differs')
        if event == 'alloc':
            key = seq, vid, cycle
            require(key not in metadata, 'Duplicate native allocation')
            metadata[key] = r; va[key] += 1
        else:
            # The monitor writes OLD metadata on same-cycle completion/reallocation (NBA).
            eligible = [a for a in intervals[vid] if a['start'] < cycle]
            if not eligible: eligible = [a for a in intervals[vid] if a['start'] == cycle]
            require(eligible, 'Native event has no SID history')
            owner = eligible[-1]; key = owner['seq'], vid, owner['start']
            require(owner['seq'] == seq and owner['start'] <= cycle <= owner['end'] and key in metadata,
                    'Native event differs from current SID/completion owner')
            require(all(r[k] == metadata[key][k] for k in ('insn', 'use_vd', 'vd', 'eew', 'vl', 'vstart')),
                    'Native metadata differs')
            if event == 'done': vd[seq, vid, cycle] += 1
            else:
                require(int(r['use_vd']) == 1 and 0 <= int(r['lane']) < 4 and 0 <= int(r['source']) < 5,
                        'Invalid native write configuration')
    require(va == backend_alloc and vd == backend_done, 'Commit/native allocation/completion identities differ')
    targets = []
    for name, word in (('gpw_div', p.DIV), ('gpw_load', p.LOAD)):
        owned = [s for s, r in starts.items() if int(r['insn'], 16) == word]
        retired = [r for r in rows if r['event'] == 'retire' and int(r['insn'], 16) == word]
        require(len(owned) == len(retired) == 1 and int(retired[0]['pc'], 16) == symbols[name] and
                any(s == owned[0] for s, _ in allocations), 'Target architecture/backend/real-PC identity differs')
        targets.append(owned[0])
    require(targets[1] == targets[0] + 1, 'DIV/load architectural requests not adjacent')
    return dict(requests=len(requests), responses=len(responses), exceptions=0,
                backend_uops=sum(allocations.values()), DIV_arch_seq=targets[0], load_arch_seq=targets[1],
                retire_before_backend_done_allowed=True, current_SID_owner_checked=True,
                arch_start_placeholder_not_used_as_real_PC=True, source_lifetime_probes_observed=False,
                source_lifetime_stall_proven=False, directly_observed_per_owner_AXI=False)


def observed(rows, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    require(retired and [int(r['order']) for r in retired] == list(range(len(retired))), 'Incomplete retire order')
    ranges = [(symbols[n], symbols[n] + size) for n, size in
              (('gpw_dump', 9216), ('gpw_seed', 4608), ('gpw_base', 144))]
    memory, loads, terminals, pair = {}, set(), [], []
    for i, r in enumerate(retired):
        insn, pc, address = int(r['insn'], 16), int(r['pc'], 16), int(r['mem_addr'], 16)
        require(not int(r['trap']) and pc != symbols['trap_fail'], 'Trap/fatal retirement')
        if pc in (symbols['gpw_div'], symbols['gpw_load']): pair.append((i, pc, insn))
        rm, wm = int(r['mem_rmask'], 16), int(r['mem_wmask'], 16)
        access = common.scalar_memory(insn)
        if access is None:
            require(not rm and not wm, 'Unknown scalar memory effect'); continue
        kind, width = access; mask = ((1 << width) - 1) << (address & 7)
        require(address % width == 0 and rm == (mask if kind == 'read' else 0) and
                wm == (mask if kind == 'write' else 0), 'Scalar memory mask/alignment differs')
        if kind == 'write':
            value = int(r['mem_wdata'], 16) & ((1 << (width * 8)) - 1)
            if address == symbols['tohost']: terminals.append(r)
        elif any(start <= address < end for start, end in ranges):
            require(int(r['rd']) != 0 and any(start <= address and address + width <= end for start, end in ranges),
                    'Unobservable/truncated full readback')
            value = int(r['rd_wdata'], 16) & ((1 << (width * 8)) - 1)
            loads.update(range(address, address + width))
        else: continue
        memory.update({address + b: v for b, v in enumerate(value.to_bytes(width, 'little'))})
    require(terminals == [retired[-1]], 'Extra/nonfinal tohost')
    require(len(pair) == 2 and pair[1][0] == pair[0][0] + 1 and
            [(pc, word) for _, pc, word in pair] == [(symbols['gpw_div'], p.DIV), (symbols['gpw_load'], p.LOAD)],
            'Retired pair identity/adjacency differs')
    require(loads == {a for start, end in ranges for a in range(start, end)}, 'Incomplete fullVRF/source/guard readback')
    def read(name, offset=0, width=8):
        address = symbols[name] + offset
        require(all(address + i in memory for i in range(width)), 'Missing raw signature: ' + name)
        return int.from_bytes(bytes(memory[address + i] for i in range(width)), 'little')
    p.signatures(read, symbols); require(read('tohost') == 1, 'NonPASS terminal')
    return dict(checks=1765, failed_checks=0, snapshots=2, fullVRF_bytes=8192,
                snapshot_guard_bytes=1024, source_bytes=4224, source_guard_bytes=528,
                explicit_read_bytes=len(loads), CSR_restoration=True)


def native_exact(activities, mapping, reference):
    expected = {s: reference[index] for s, index in mapping.items() if reference[index].vector_writes}
    require(len(expected) == 34 and {s for s, a in activities.items() if a.writes} == set(expected), 'Native writer population differs')
    total = 0
    for seq, commit in expected.items():
        activity = activities[seq]; require(activity.instruction == commit.instruction, 'Native opcode differs')
        source = 1 if commit.instruction == p.DIV else 4
        seen = set()
        for w in activity.writes:
            require(w.arch_seq == seq and w.instruction == commit.instruction and w.source == source and w.eew == 0 and
                    0 <= w.lane < 4 and 0 <= w.be <= 255 and w.be & ~w.known_be == 0, 'Native source/EEW/unknown data differs')
            for byte in range(8):
                if not w.be & (1 << byte): continue
                key = w.addr, w.lane, byte
                require(key not in seen, 'Duplicate accepted native byte'); seen.add(key)
        actual = vc._architectural_bytes(activity.writes, 4, 1024)
        wanted = {(reg, b): (value >> (8 * b)) & 255 for reg, value in commit.vector_writes.items() for b in range(128)}
        require({key: value for key, (value, _) in actual.items()} == wanted, 'Native full register bytes differ/missing/overscope')
        total += len(wanted)
    require(total == 6144, 'Native byte population differs')
    return dict(architectural_writers=34, known_bytes=6144, skipped_unknown_bytes=0,
                DIV_source='MFPU', load_and_seed_source='VLDU', duplicate_bytes=0)


def vector_exact(result, reference):
    fixed = dict(status='PASS', compared_instructions=34, compared_bytes=6144, skipped_unknown_bytes=0,
                 non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024, selected_index=None,
                 stopped_at_spike_index=None, trapped_requests=[], first_mismatch=None,
                 unobservable_instructions=0, incomplete_requests=[], unretired_requests=[])
    for k, v in fixed.items(): require(k in result and type(result[k]) is type(v) and result[k] == v, 'Full vector gate differs: ' + k)
    records = result['instructions']; expected = [c for c in reference if c.vector_writes]
    require(len(records) == len(expected) == 34 and
            [(int(r['pc'], 16), int(r['instruction'], 16)) for r in records] == [(c.pc, c.instruction) for c in expected],
            'Vector PC/opcode population differs')
    require([r['compared_bytes'] for r in records] == [128] * 32 + [1024, 1024], 'Full m8 byte population differs')
    require(all(r['status'] == 'PASS' and r['skipped_unknown_bytes'] == r['unknown_write_bytes'] ==
                r['mismatch_count'] == 0 and r['first_mismatch'] is None for r in records), 'Vector record differs')


def logs(console, vcslog, control):
    for text in (console, vcslog):
        require(not re.search(r'Fatal:|Error:|Fatal-\[|Error-\[|\[ARA_CONTRACT_ERROR\]|Core Test \*\*\* FAILED', text), 'Fatal/failure/protocol diagnostic')
    require(vcslog.count('Core Test *** SUCCESS ***') == 1, 'Missing/extra SUCCESS')
    summaries = [parse_contract_summary(line.strip()) for line in console.splitlines() if '[ARA_CONTRACT]' in line]
    require(len(summaries) == 1 and summaries[0] is not None, 'Contract summary missing/multiple/malformed')
    counts = summaries[0]
    require(counts['requests'] == counts['responses'] == control['requests'] > 0 and counts['exceptions'] == 0 and
            all(counts[k] == 0 for k in ('protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')), 'Contract nonzero errors/stalls/exception')


def tracer_exact(text, rows):
    pattern = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual = [m.groups() for line in text.splitlines() if (m := pattern.match(line))]
    wanted = [(str(int(r['cycle'])), 'M', r['pc'], r['insn']) for r in rows if r['event'] == 'retire']
    require(wanted and actual[:len(wanted)] == wanted and 'Exception @' not in text, 'Tracer/retire identity or unexpected exception')
    tail = actual[len(wanted):]
    require(not tail or tail == [(wanted[-1][0], 'M', '%016x' % (int(wanted[-1][2], 16) + 4), '0000a001')], 'Unexpected tracer tail')
    return dict(exceptions=0, matched_retirements=len(wanted), allowed_terminal_tail=len(tail))


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct plan directory')
    pre = life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL)
    prepared = life.read_bound(PREPARED, RUN_SEAL); binding(pre, prepared)
    pins = life.merge_pins(pre['pins'], prepared['pins'])
    paths = [Path(__file__).resolve(), Path(__file__).with_name('test_qualify_pure_war_parent_terminal.py'),
             Path(common.__file__).resolve(), *sorted((life.ROOT / 'verification/ara_verify').glob('*.py'))]
    sourcepath = life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    sourcepins = json.loads(sourcepath.read_bytes())
    for name in ('hardware/tb/ara_commit_monitor.sv', 'hardware/include/ara_pkg.sv'):
        path = life.ROOT / name; pins = life.merge_pins(pins, {str(path): sourcepins[str(path)]})
    pins = life.merge_pins(pins, {str(path): life.digest(path) for path in paths})
    pins = life.merge_pins(pins, {str(runner.PRE / 'preflight-manifest.json'): runner.PRE_SEAL, str(PREPARED): RUN_SEAL,
                                str(sourcepath): life.digest(sourcepath)})
    life.check(pins)
    out.mkdir(); life.save(out / 'plan.json', dict(status=PLAN_STATUS, run=str(RUN), pins=pins,
        preflight_seal=runner.PRE_SEAL, parent_prepared_seal=RUN_SEAL,
        provenance='PARENT_AGENT_EXECUTION_AND_AUTHORIZATION_WITHIN_USER_GOAL',
        preflight_baseline=727, raw_gain_requires_latest_formal_baseline_at_least=729,
        source_lifetime_probes_observed=False, coverage_admitted=False, actualDUT_read=False, simulations_started=False))
    print(json.dumps(dict(plan=str(out / 'plan.json'), seal=life.digest(out / 'plan.json'), pins=len(pins))))


def collect(plan_path, seal, out):
    plan = life.read_bound(plan_path, seal); life.check(plan['pins'])
    require(plan['status'] == PLAN_STATUS and plan['run'] == str(RUN) and
            plan['preflight_seal'] == runner.PRE_SEAL and plan['parent_prepared_seal'] == RUN_SEAL, 'Plan identity differs')
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh qualification directory')
    require((RUN / 'simulation-status.json').is_file(), 'HOLD: no terminal status')
    pins = life.merge_pins(plan['pins'], {str(plan_path): seal}); out.mkdir()
    def read(name):
        path = RUN / name
        require(path.resolve() == path and not path.is_symlink(), 'Aliased run evidence')
        raw = path.read_bytes(); pins[str(path)] = life.digest(path)
        require(pins[str(path)] == hashlib.sha256(raw).hexdigest(), 'Evidence changed while reading')
        return raw
    try:
        pre = life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL)
        prepared = life.read_bound(PREPARED, RUN_SEAL)
        terminal(json.loads(read('simulation-status.json')), json.loads(read('manifest.json')), json.loads(read('started.json')), prepared)
        rows = common.read_csv(read('commit_trace.csv'), common.COMMIT_FIELDS)
        vectors = common.read_csv(read('vector_trace.csv'), common.VECTOR_FIELDS)
        control = lifecycle(rows, vectors, pre['symbols'])
        logs(read('console.log').decode('utf-8'), read('run.vcs.log').decode('utf-8'), control)
        require(not check_contract_log(RUN / 'run.vcs.log'), 'Full contract log gate failed')
        signature = observed(rows, pre['symbols'])
        trace = tracer_exact(read('trace_hart_0.log').decode('utf-8'), rows); read('trace_hart_0_commit.log')
        reference = p.shared.parse_spike_commits(runner.PRE / 'spike.trace')
        require(p.validate(reference, pre['symbols'], (runner.PRE / 'spike.trace').read_text()) == pre['validation'], 'Independent reference replay differs')
        scalar = common.spike_trace.compare_commit_prefix(runner.PRE / 'spike.trace', RUN / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
        life.save(out / 'scalar-comparison.json', scalar)
        common.scalar_exact(scalar, pre['reference_counts'])
        vector = common.compare_vector_commits(runner.PRE / 'spike.trace', RUN / 'commit_trace.csv', RUN / 'vector_trace.csv', 0x80000000)
        life.save(out / 'vector-comparison.json', vector)
        vector_exact(vector, reference)
        starts, retires, rejected = vc._parse_architecture_mapping(RUN / 'commit_trace.csv')
        require(not rejected, 'Unexpected rejected request')
        mapping = vc._map_spike_commits(vc._map_architecture_retires(starts, retires, rejected), reference)
        lanes, vlen, activities = vc._parse_vector_trace(RUN / 'vector_trace.csv')
        require((lanes, vlen) == (4, 1024), 'Native geometry differs')
        native = native_exact(activities, mapping, reference)
        life.check(pins)
        for name, value in (('observed-signatures.json', signature), ('lifecycle.json', control),
                            ('tracer-proof.json', trace), ('native-byte-proof.json', native)):
            life.save(out / name, value)
        outputs = {str(path): life.digest(path) for path in out.iterdir() if path.is_file()}
        life.save(out / 'qualification.json', dict(status='PURE_WAR_FULL_DUT_QUALIFIED_NOT_ADMITTED',
            pins=life.merge_pins(pins, outputs), run=str(RUN), preflight_baseline=727,
            raw_gain_requires_latest_formal_baseline_at_least=729, raw_coverage_increment_not_collected=True,
            source_lifetime_probes_observed=False, source_lifetime_stall_proven=False,
            target_hit_verified=False, directly_observed_per_owner_AXI=False,
            coverage_admitted=False, simulations_started=False, rtl_changed=False))
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'qualification.json'), admitted=0)))
    except Exception as error:
        drift = None
        try: life.check(pins)
        except Exception as e: drift = str(e)
        life.save(out / 'failure.json', dict(status='PURE_WAR_TERMINAL_QUALIFICATION_FAIL_NOT_ADMITTED',
            reason=type(error).__name__ + ': ' + str(error), pins=pins, post_failure_pin_error=drift, coverage_admitted=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'collect')); parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path); parser.add_argument('--seal'); a = parser.parse_args()
    if a.mode == 'prepare':
        require(a.output is not None and a.plan is None and a.seal is None, 'Prepare needs fresh output only'); prepare(a.output.absolute())
    else:
        require(a.plan is not None and a.seal is not None, 'Fixed plan/seal required')
        if a.mode == 'verify':
            plan = life.read_bound(a.plan, a.seal); require(plan['status'] == PLAN_STATUS and plan['run'] == str(RUN), 'Plan identity')
            life.check(plan['pins']); print('VERIFY_PASS NO_ACTUAL_DUT_READ NO_VCS admitted0')
        else:
            require(a.output is not None, 'Fresh actual qualification output required'); collect(a.plan.absolute(), a.seal, a.output.absolute())


if __name__ == '__main__': main()
