"""Offline VNCLIPU terminal qualification only. Never launch or admit."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from types import FunctionType

import build_vnclipu_reject_preflight as p
import run_vnclipu_reject_simulation as runner
import collect_opivx_vsbc_strict as common
import collect_narrow_reject_r1_cached_strict as r1
from ara_verify.contract import check_contract_log, parse_contract_summary

life, require = p.life, p.require
ROOT = life.ROOT
PRE_SEAL = '050ae5ca2acd8883847eb9fff51195df17b801ac2f341f27aa79b3fab2856927'
RUN = life.OUT / 'vnclipu-reject-old-image-parent-20261006-01'
PREPARED = RUN.with_name(RUN.name + '.prepared.json')
RUN_SEAL = 'ef5c7e20913f9009894db4ae6ca24e4709bfc20ad61412d328e347621c2f16a3'
REVIEW = life.OUT / 'vnclipu-reject-parent-review-20261006-01.json'
REVIEW_SEAL = 'ed23c293f8118bf7d81d130ff7dec7e24603e0aceb79cedac7373927179e85bd'


def binding(pre, prepared, review):
    runner.validate(pre)
    require(prepared['case'] == p.NAME and prepared['preflight_seal'] == PRE_SEAL and
            prepared['preflight'] == str(p.PRE / 'preflight-manifest.json') and
            prepared['output'] == str(RUN) and prepared['command'] == runner.command(RUN) and
            prepared['timeout_s'] == 1200 and prepared['baseline_tests'] == 725 and
            prepared['targets'] == pre['targets'] and prepared['scalar_reference_counts'] == pre['reference_counts'] and
            prepared['coverage_admitted'] is False and prepared['admission_performed'] is False,
            'Prepared scope/ELF/command contract differs')
    require(review['status'] == 'PARENT_SOURCE_REVIEW_AND_CORRECTED_NEGATIVE_TEST_PASS_NOT_DUT_PASS' and
            review['prepared_sha256'] == RUN_SEAL and review['preflight_sha256'] == PRE_SEAL and
            review['baseline_tests'] == 725 and review['vcs_authorized'] is True and
            review['supplement_tests_passed'] == 2 and review['coverage_admitted'] is False and
            review['rtl_changed'] is False, 'Parent independent review/authorization differs')
    require(review['supplement_test'] == 'verification/coverage/test_vnclipu_wrong_pc_parent.py' and
            review['supplement_test_sha256'] == 'af44f15550eced74e0dafec8dddcfa15435c02de54c8c4965c24da0296d46913',
            'Wrong corrected negative test')


def terminal(state, actual, prepared):
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and type(state.get('returncode')) is int and
            state['returncode'] == 0 and state.get('case') == p.NAME and state.get('coverage_admitted') is False and
            state.get('admission_performed') is False, 'Failed/nonterminal simulation')
    expected = dict(prepared, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
    require(actual == expected, 'Actual runtime command/ELF/authorization differs')


def lifecycle(rows, vectors, symbols):
    # Isolate two case constants without modifying the frozen generic module globals.
    generic = FunctionType(common.lifecycle.__code__, dict(common.lifecycle.__globals__, BAD=p.BAD, RECOVERY=p.RECOVERY))
    result = generic(rows, vectors, {'gvs_recovery': symbols['gvc_recovery']})
    starts = {int(r['order']): r for r in rows if r['event'] == 'arch_start'}
    live, completed = {}, {}
    for r in rows:
        event, seq = r['event'], int(r['order'])
        if event == 'cvx_resp':
            require(seq == -1 and int(r['pc'], 16) == int(r['insn'], 16) == 0 and int(r['trap']) in (0, 1),
                    'Frozen response placeholder/trap differs')
        if event not in ('uop_alloc', 'uop_done'):
            continue
        key = seq, int(r['port'])
        require(int(r['insn'], 16) == int(starts[seq]['insn'], 16) and int(r['cycle']) >= int(starts[seq]['cycle']),
                'Backend owner/opcode/time differs')
        if event == 'uop_alloc':
            require(key not in live, 'Live backend VID reused'); live[key] = int(r['cycle'])
        else:
            require(key in live and int(r['cycle']) >= live.pop(key), 'Unallocated/premature backend done')
            completed[key] = int(r['cycle'])
    require(not live, 'Pending backend execution')
    vlive, vdone = {}, {}
    for r in vectors:
        if r['event'] == 'config':
            continue
        key = int(r['arch_seq']), int(r['vid'])
        if r['event'] == 'alloc':
            require(key not in vlive, 'Live vector VID reused'); vlive[key] = r
        else:
            alloc = vlive.get(key)
            if alloc is None and r['event'] == 'write':
                alloc = vdone.get(key)
                require(alloc is not None and int(r['cycle']) == completed.get(key), 'Write outside completion cycle')
            require(alloc is not None and int(r['cycle']) >= int(alloc['cycle']) and
                    all(r[k] == alloc[k] for k in ('insn', 'use_vd', 'vd', 'eew', 'vl', 'vstart')),
                    'Vector allocation/write/done metadata differs')
            if r['event'] == 'done':
                vlive.pop(key); vdone[key] = r
    require(not vlive, 'Pending vector execution')
    require(p.BAD & 127 == 0x57, 'Bad encoding is not ordinary arithmetic')
    return dict(result, rejected_AXI_requests_causal_proof=True, directly_observed_per_owner_AXI=False,
        AXI_proof='Frozen arithmetic opcode + dispatcher rejection + no backend/VLSU allocation; '
                  'ara.sv routes Ara AXI through VLSU. No claim of zero global/concurrent bus activity.',
        response_or_arch_start_placeholder_not_used_as_real_PC=True)


def observed(rows, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    require(retired and [int(r['order']) for r in retired] == list(range(len(retired))), 'Incomplete retire order')
    memory, loads, stores, terminals = {}, set(), [], []
    ranges = [(symbols[n], symbols[n] + size) for n, size in (('gvc_dump', 13824), ('gvc_seed', 4608))]
    entries = 0
    for r in retired:
        insn, pc, address = int(r['insn'], 16), int(r['pc'], 16), int(r['mem_addr'], 16)
        require(not int(r['trap']) and pc not in (symbols['gvc_bad'], symbols['trap_fail']), 'Illegal/fatal retirement')
        handler = symbols['gvc_handler'] <= pc < symbols['gvc_handler_end']; entries += pc == symbols['gvc_handler']
        if handler:
            require(int(r['rd']) in (0, 5, 6, 7), 'Protected handler GPR')
            if insn & 127 == 0x73 and (insn >> 12) & 7:
                fn, rs = (insn >> 12) & 7, (insn >> 15) & 31
                writes = fn in (1, 5) or (fn in (2, 3, 6, 7) and rs != 0)
                require(not writes or insn >> 20 in (0x340, 0x341), 'Protected handler CSR')
        rm, wm = int(r['mem_rmask'], 16), int(r['mem_wmask'], 16)
        access = common.scalar_memory(insn)
        if access is None:
            require(not rm and not wm, 'Unknown memory effect'); continue
        kind, width = access; mask = ((1 << width) - 1) << (address & 7)
        require(address % width == 0 and rm == (mask if kind == 'read' else 0) and
                wm == (mask if kind == 'write' else 0), 'Memory mask/alignment differs')
        if kind == 'write':
            value = int(r['mem_wdata'], 16) & ((1 << (width * 8)) - 1)
            if handler: stores.append((address, width))
            if address == symbols['tohost']: terminals.append(r)
        elif any(start <= address < end for start, end in ranges):
            require(int(r['rd']) != 0 and any(start <= address and address + width <= end for start, end in ranges),
                    'Unobservable/truncated readback')
            value = int(r['rd_wdata'], 16) & ((1 << (width * 8)) - 1)
            loads.update(range(address, address + width))
        else:
            continue
        memory.update({address + i: b for i, b in enumerate(value.to_bytes(width, 'little'))})
    require(entries == 1 and terminals == [retired[-1]], 'Handler/terminal population differs')
    require(loads == {a for start, end in ranges for a in range(start, end)}, 'Incomplete explicit fullVRF/source/guard readback')
    def read(name, offset=0, width=8):
        address = symbols[name] + offset
        require(all(address + i in memory for i in range(width)), 'Missing raw signature: ' + name)
        return int.from_bytes(bytes(memory[address + i] for i in range(width)), 'little')
    p.signatures(read, symbols)
    require(read('tohost') == 1, 'NonPASS tohost')
    allowed = {(symbols['gvc_ledger'] + i * 8, 8) for i in range(12)} | {(symbols['gvc_traps'], 8)}
    require(Counter(stores) == Counter(allowed), 'Handler exact13 stores differ')
    return dict(checks=p.CHECKS, failed_checks=0, snapshots=3, fullVRF_bytes=12288,
                snapshot_guard_bytes=1536, source_bytes=4096, source_guard_bytes=512,
                explicit_read_bytes=len(loads), handler_store_words=13, trap_vstart=1,
                post_mret_vstart=1, precise_cause=2, precise_PC=symbols['gvc_bad'], precise_tval=p.BAD)


def tracer_exact(text, rows, symbols):
    pattern = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual = [m.groups() for line in text.splitlines() if (m := pattern.match(line))]
    wanted = [(str(int(r['cycle'])), 'M', r['pc'], r['insn']) for r in rows if r['event'] == 'retire']
    require(wanted and actual[:len(wanted)] == wanted, 'Full tracer/retire identity differs')
    tail = actual[len(wanted):]
    require(not tail or tail == [(wanted[-1][0], 'M', '%016x' % (int(wanted[-1][2], 16) + 4), '0000a001')],
            'Unexpected post-terminal tracer tail')
    events = re.findall(r'Exception @\s*([0-9a-fA-F]+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)', text)
    require(len(events) == text.count('Exception @') == 1 and int(events[0][1], 16) == symbols['gvc_bad'] and
            events[0][2] == 'Illegal Instruction' and
            [int(v, 16) for v in re.findall(r'tval: ([0-9a-fA-F]+)', text)] == [p.BAD], 'Exact real exception PC/cause/tval differs')
    return dict(exceptions=1, PC=symbols['gvc_bad'], cause=2, tval=p.BAD)


def logs(console, vcslog, control):
    for text in (console, vcslog):
        require(not re.search(r'Fatal:|Error:|Fatal-\[|Error-\[|\[ARA_CONTRACT_ERROR\]|Core Test \*\*\* FAILED', text),
                'Fatal/failure/protocol diagnostic')
    require(vcslog.count('Core Test *** SUCCESS ***') == 1, 'Missing/extra SUCCESS')
    summaries = [parse_contract_summary(line.strip()) for line in console.splitlines() if '[ARA_CONTRACT]' in line]
    require(len(summaries) == 1 and summaries[0] is not None, 'Contract summary malformed/multiple')
    counts = summaries[0]
    require(counts['requests'] == counts['responses'] == control['requests'] > 0 and counts['exceptions'] == 1 and
            all(counts[k] == 0 for k in ('protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')),
            'Nonzero fails/protocol/stall/outstanding or exception count differs')


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct plan directory')
    pre = life.read_bound(p.PRE / 'preflight-manifest.json', PRE_SEAL)
    prepared = life.read_bound(PREPARED, RUN_SEAL); review = life.read_bound(REVIEW, REVIEW_SEAL)
    binding(pre, prepared, review)
    pins = life.merge_pins(pre['pins'], prepared['pins'])
    paths = [Path(__file__).resolve(), Path(__file__).with_name('test_qualify_vnclipu_parent_terminal.py'),
        ROOT / review['supplement_test'], Path(common.__file__).resolve(), Path(r1.__file__).resolve(),
        *sorted((ROOT / 'verification/ara_verify').glob('*.py'))]
    sourcepins_path = life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    sourcepins = json.loads(sourcepins_path.read_bytes())
    for name in ('hardware/src/ara.sv', 'hardware/src/ara_sequencer.sv', 'hardware/src/vlsu/vlsu.sv',
                 'hardware/src/vlsu/vldu.sv', 'hardware/src/vlsu/vstu.sv', 'hardware/tb/ara_commit_monitor.sv'):
        path = ROOT / name
        pins = life.merge_pins(pins, {str(path): sourcepins[str(path)]})
    pins = life.merge_pins(pins, {str(path): life.digest(path) for path in paths})
    pins = life.merge_pins(pins, {str(p.PRE / 'preflight-manifest.json'): PRE_SEAL,
        str(PREPARED): RUN_SEAL, str(REVIEW): REVIEW_SEAL, str(ROOT / review['supplement_test']): review['supplement_test_sha256']})
    life.check(pins)
    plan = dict(status='VNCLIPU_OFFLINE_QUALIFICATION_PREPARED_NOT_EXECUTED', run=str(RUN), pins=pins,
        preflight_seal=PRE_SEAL, parent_prepared_seal=RUN_SEAL, parent_review_seal=REVIEW_SEAL,
        provenance='PARENT_AGENT_INDEPENDENT_EXECUTION_AND_AUTHORIZATION_WITHIN_USER_GOAL',
        baseline=725, coverage_admitted=False, actualDUT_read=False, simulations_started=False)
    out.mkdir(); life.save(out / 'plan.json', plan)
    print(json.dumps(dict(plan=str(out / 'plan.json'), seal=life.digest(out / 'plan.json'), pins=len(pins))))


def collect(plan_path, seal, out):
    plan = life.read_bound(plan_path, seal); life.check(plan['pins'])
    require(plan['status'] == 'VNCLIPU_OFFLINE_QUALIFICATION_PREPARED_NOT_EXECUTED' and plan['run'] == str(RUN), 'Plan identity')
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh independent qualification directory')
    require((RUN / 'simulation-status.json').is_file(), 'HOLD: no terminal status')
    pins = life.merge_pins(plan['pins'], {str(plan_path): seal}); out.mkdir()
    def read(name):
        path = RUN / name
        require(path.resolve() == path and not path.is_symlink(), 'Aliased run evidence')
        raw = path.read_bytes(); pins[str(path)] = life.digest(path)
        require(life.digest(path) == hashlib.sha256(raw).hexdigest(), 'Evidence changed during read')
        return raw
    try:
        pre = life.read_bound(p.PRE / 'preflight-manifest.json', PRE_SEAL)
        prepared = life.read_bound(PREPARED, RUN_SEAL)
        terminal(json.loads(read('simulation-status.json')), json.loads(read('manifest.json')), prepared)
        rows = common.read_csv(read('commit_trace.csv'), common.COMMIT_FIELDS)
        vectors = common.read_csv(read('vector_trace.csv'), common.VECTOR_FIELDS)
        control = lifecycle(rows, vectors, pre['symbols'])
        console, vcslog = read('console.log').decode('utf-8'), read('run.vcs.log').decode('utf-8')
        logs(console, vcslog, control)
        require(not check_contract_log(RUN / 'run.vcs.log'), 'Generic full contract gate failed')
        observed_result = observed(rows, pre['symbols'])
        trap = tracer_exact(read('trace_hart_0.log').decode('utf-8'), rows, pre['symbols']); read('trace_hart_0_commit.log')
        reference = p.shared.parse_spike_commits(p.PRE / 'spike.trace')
        scalar = common.spike_trace.compare_commit_prefix(p.PRE / 'spike.trace', RUN / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar, pre['reference_counts'])
        vector = common.compare_vector_commits(p.PRE / 'spike.trace', RUN / 'commit_trace.csv', RUN / 'vector_trace.csv', 0x80000000)
        r1.vector_exact(vector, [control['exception_arch_seq']], reference)
        life.check(pins)
        for name, data in (('scalar-comparison.json', scalar), ('vector-comparison.json', vector),
                           ('observed-signatures.json', observed_result), ('lifecycle.json', control), ('trap-proof.json', trap)):
            life.save(out / name, data)
        outputs = {str(path): life.digest(path) for path in out.iterdir() if path.is_file()}
        life.save(out / 'qualification.json', dict(status='VNCLIPU_FULL_DUT_QUALIFIED_NOT_ADMITTED',
            pins=life.merge_pins(pins, outputs), baseline=725, raw_coverage_increment_not_collected=True,
            coverage_admitted=False, simulations_started=False, rtl_changed=False,
            directly_observed_per_owner_AXI=False, causal_AXI_proof=True))
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'qualification.json'), admitted=0)))
    except Exception as error:
        drift = None
        try: life.check(pins)
        except Exception as e: drift = str(e)
        life.save(out / 'failure.json', dict(status='VNCLIPU_TERMINAL_QUALIFICATION_FAIL_NOT_ADMITTED',
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
            plan = life.read_bound(a.plan, a.seal); life.check(plan['pins']); print('VERIFY_PASS NO_ACTUAL_DUT_READ NO_VCS admitted0')
        else:
            require(a.output is not None, 'Fresh actual qualification output required'); collect(a.plan.absolute(), a.seal, a.output.absolute())


if __name__ == '__main__': main()
