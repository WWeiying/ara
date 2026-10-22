"""Terminal cached R1 offline architecture/raw coverage audit; no launch or admission."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import run_narrow_reject_r1_cached_simulation as runner
import collect_opivx_vsbc_strict as common
import coverage_bitmap_delta as bitmap

preflight = runner.preflight
oracle = preflight.original
life, require = runner.life, runner.require
RUN = life.OUT / 'narrow-reject-r1-cached-old-image-719-20261006-01'
PRE_SEAL = 'd84184ea823564af4af9475bc6d31c25f7cb7a2de9429b45751ef4633b080d28'
RUN_SEAL = '98b82c45f2bbde8c00c9b27f2de0f2bad9f079896ddc28e79ab218f99d969377'
BASE = oracle.review.BASE
DESIGN = Path(str(life.IMAGE) + '.vdb')
WORDS = [int(c['word'], 16) for c in oracle.CASES]
TRACER_FIXTURE = common.RUN/'trace_hart_0.log'


def terminal(state, actual, prepared):
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and
            type(state.get('returncode')) is int and state['returncode'] == 0 and
            state.get('case') == preflight.NAME and state.get('coverage_admitted') is False and
            state.get('admission_performed') is False, 'Failed/nonterminal simulation')
    require(actual == prepared, 'Actual run manifest/ELF/command differs')


def lifecycle(rows, vectors, symbols):
    starts, pending, uops, done = {}, {}, {}, {}
    requests, responses, rejected = [], [], []
    allocs, completions = Counter(), Counter()
    for r in rows:
        event, seq, tid = r['event'], int(r['order']), int(r['trans_id'])
        if event == 'arch_start':
            require(seq not in starts and tid not in pending, 'Duplicate arch/live transaction')
            starts[seq], pending[tid] = r, [seq, False]
        elif event == 'cvx_req':
            require(tid in pending and not pending[tid][1], 'Unknown/duplicate request')
            s = pending[tid][0]
            require(int(r['insn'], 16) == int(starts[s]['insn'], 16), 'Request opcode differs')
            pending[tid][1] = True
            requests.append(s)
        elif event == 'cvx_resp':
            require(tid in pending and pending[tid][1], 'Unknown/duplicate response')
            require(seq == -1 and int(r['insn'], 16) == int(r['pc'], 16) == 0,
                    'Frozen response placeholder differs')
            s = pending.pop(tid)[0]
            responses.append(s)
            require(int(r['trap']) in (0, 1), 'Malformed response trap')
            if int(r['trap']): rejected.append(s)
        elif event in ('uop_alloc', 'uop_done'):
            key = (seq, int(r['port']))
            require(seq in starts and int(r['insn'], 16) == int(starts[seq]['insn'], 16) and
                    int(r['cycle']) >= int(starts[seq]['cycle']), 'Backend identity/time differs')
            if event == 'uop_alloc':
                require(key not in uops, 'Live backend VID reused')
                uops[key] = r; allocs[key] += 1
            else:
                require(key in uops and int(r['cycle']) >= int(uops[key]['cycle']), 'Unallocated backend done')
                uops.pop(key); completions[key] += 1
        else:
            require(event == 'retire' and not int(r['trap']), 'Unknown event/RVFI trap')
    require(not pending and Counter(requests) == Counter(responses) == Counter(starts.keys()),
            'Incomplete request/response conservation')
    require(not uops and allocs == completions, 'Incomplete backend execution')
    bad = [s for s, r in starts.items() if int(r['insn'], 16) in WORDS]
    require(len(bad) == 24 and [int(starts[s]['insn'], 16) for s in bad] == WORDS and rejected == bad,
            'Not exact ordered24 rejection population')
    require(not any(s in bad for s, _ in allocs), 'Illegal instruction allocated backend')
    good = [s for s, r in starts.items() if int(r['insn'], 16) == oracle.RECOVERY]
    require(len(good) == 1 and any(s == good[0] for s, _ in allocs), 'Legal recovery unexecuted')
    retired = [r for r in rows if r['event'] == 'retire' and int(r['insn'], 16) == oracle.RECOVERY]
    require(len(retired) == 1 and int(retired[0]['pc'], 16) == symbols['gnr_recovery'],
            'Recovery retirement differs')
    va, vd, vp = Counter(), Counter(), {}
    for r in vectors:
        event, seq, key = r['event'], int(r['arch_seq']), (int(r['arch_seq']), int(r['vid']))
        require(int(r['nr_lanes']) == 4 and int(r['vlen_bits']) == 1024, 'Vector configuration differs')
        require(seq not in bad, 'Illegal vector activity including config')
        if event == 'config': continue
        require(seq in starts and event in ('alloc', 'done', 'write') and
                int(r['insn'], 16) == int(starts[seq]['insn'], 16), 'Vector ownership/opcode differs')
        if event == 'alloc':
            require(key not in vp, 'Live vector VID reused')
            vp[key] = r; va[key] += 1
        else:
            a = vp.get(key)
            if a is None and event == 'write':
                a = done.get(key)
                require(a is not None and int(r['cycle']) == int(a['cycle']), 'Write outside completion cycle')
            require(a is not None and int(r['cycle']) >= int(a['cycle']) and
                    all(r[k] == a[k] for k in ('insn', 'use_vd', 'vd', 'eew', 'vl', 'vstart')),
                    'Vector allocation/completion/write metadata differs')
            if event == 'done':
                vp.pop(key); done[key] = r; vd[key] += 1
    require(not vp and va == vd == allocs, 'Commit/vector backend population differs')
    return dict(requests=len(requests), responses=len(responses), exceptions=24,
                rejected_arch_seqs=bad, recovery_arch_seq=good[0], backend_uops=sum(allocs.values()),
                rejected_backend_uops=0, rejected_vrf_activities=0,
                response_placeholder_not_used_as_opcode_identity=True)


def observed(rows, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    require(retired and [int(r['order']) for r in retired] == list(range(len(retired))), 'Incomplete retire order')
    memory, loads, stores, terminals = {}, set(), [], []
    start, end = symbols['gnr_dump'], symbols['gnr_dump'] + 26*32*18*8
    badpcs = {symbols['gnr_bad_%02d' % n] for n in range(24)}
    handler_entries = 0
    for r in retired:
        insn, pc, address = int(r['insn'], 16), int(r['pc'], 16), int(r['mem_addr'], 16)
        require(not int(r['trap']) and pc not in badpcs | {symbols['trap_fail']}, 'Illegal/fatal retirement')
        handler = symbols['gnr_handler'] <= pc < symbols['gnr_handler_end']
        handler_entries += pc == symbols['gnr_handler']
        if handler:
            require(int(r['rd']) in (0, 5, 6, 7), 'Handler modified protected register')
            if insn & 127 == 0x73 and (insn >> 12) & 7:
                fn, rs = (insn >> 12) & 7, (insn >> 15) & 31
                writes = fn in (1, 5) or (fn in (2, 3, 6, 7) and rs != 0)
                require(not writes or insn >> 20 in (0x300, 0x340, 0x341), 'Protected handler CSR modified')
        rm, wm = int(r['mem_rmask'], 16), int(r['mem_wmask'], 16)
        access = common.scalar_memory(insn)
        if access:
            kind, width = access
            mask = ((1 << width)-1) << (address & 7)
            require(address % width == 0 and rm == (mask if kind == 'read' else 0) and
                    wm == (mask if kind == 'write' else 0), 'Scalar memory mask/alignment differs')
            if kind == 'write':
                value = int(r['mem_wdata'], 16) & ((1 << (width*8))-1)
                memory.update({address+i: b for i, b in enumerate(value.to_bytes(width, 'little'))})
                if handler: stores.append((address, width))
                if address == symbols['tohost']: terminals.append(r)
            elif start <= address < end:
                require(int(r['rd']) != 0 and address+width <= end, 'Unobservable snapshot load')
                value = int(r['rd_wdata'], 16) & ((1 << (width*8))-1)
                memory.update({address+i: b for i, b in enumerate(value.to_bytes(width, 'little'))})
                loads.update(range(address, address+width))
        else:
            require(not rm and not wm, 'Unknown memory effects')
    require(handler_entries == 24 and terminals == [retired[-1]], 'Handler/terminal population differs')
    require(loads == set(range(start, end)), 'Incomplete explicit 26snapshot/guard readback')
    def read(name, offset=0, width=8):
        addr = symbols[name]+offset
        require(all(addr+i in memory for i in range(width)), 'Missing signature bytes: '+name)
        return int.from_bytes(bytes(memory[addr+i] for i in range(width)), 'little')
    oracle.signatures(read, symbols)
    require(read('tohost') == 1, 'NonPASS terminal')
    allowed = Counter({(symbols['gnr_ledger']+i*8, 8): 1 for i in range(24*12)})
    allowed[symbols['gnr_traps'], 8] = 24
    require(Counter(stores) == allowed, 'Handler exact312 stores differ')
    return dict(checks=15489, failed_checks=0, snapshots=26, illegal_traps=24, observed_vrf_bytes=106496,
                guard_bytes=13312, explicit_dump_read_bytes=119808, handler_store_words=312,
                trap_vstart=1, post_mret_vstart=1, context_restored=True, retirements=len(retired))


def tracer_exact(text, rows, symbols):
    regex = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual = [m.groups() for line in text.splitlines() if (m := regex.match(line))]
    retired = [r for r in rows if r['event'] == 'retire']
    wanted = [(str(int(r['cycle'])), 'M', r['pc'], r['insn']) for r in retired]
    require(wanted and actual[:len(wanted)] == wanted, 'Full tracer/retire prefix differs')
    tail = actual[len(wanted):]
    require(not tail or tail == [(wanted[-1][0], 'M', '%016x' % (int(wanted[-1][2], 16)+4), '0000a001')],
            'Unexpected post-terminal tracer tail')
    events = re.findall(r'Exception @\s*([0-9a-fA-F]+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)', text)
    require(len(events) == text.count('Exception @') == 24 and
            [(int(e[1], 16), e[2]) for e in events] ==
            [(symbols['gnr_bad_%02d' % n], 'Illegal Instruction') for n in range(24)] and
            [int(v, 16) for v in re.findall(r'tval: ([0-9a-fA-F]+)', text)] == WORDS,
            'Exact24 ordered exception PC/cause/tval differs')
    return dict(illegal_exceptions=24, cause=2, pcs=[symbols['gnr_bad_%02d' % n] for n in range(24)],
                tvals=WORDS, tracer_tail=tail)


def vector_exact(result, rejected, reference):
    fixed = dict(status='PASS', compared_instructions=33, skipped_unknown_bytes=0,
                 non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024, selected_index=None,
                 stopped_at_spike_index=None, trapped_requests=rejected, first_mismatch=None,
                 unobservable_instructions=0, incomplete_requests=[], unretired_requests=[])
    for k, v in fixed.items():
        require(k in result and type(result[k]) is type(v) and result[k] == v, 'Full vector gate differs: '+k)
    records = result['instructions']
    expected = [(c.pc, c.instruction) for c in reference if c.vector_writes]
    require(len(expected) == len(records) == 33 and
            [(int(r['pc'], 16), int(r['instruction'], 16)) for r in records] == expected, 'Vector identity differs')
    require([r['compared_bytes'] for r in records[:32]] == [128]*32 and
            4 <= records[-1]['compared_bytes'] <= 128 and
            result['compared_bytes'] == sum(r['compared_bytes'] for r in records), 'Incomplete vector byte population')
    require(all(r['status'] == 'PASS' and r['skipped_unknown_bytes'] == r['unknown_write_bytes'] ==
                r['mismatch_count'] == 0 and r['first_mismatch'] is None for r in records), 'Vector record differs')


def target_hits(before, single, targets):
    require(single['tests'] == [str(RUN/'code.vdb')] and str(RUN/'code.vdb') not in before['tests'], 'Duplicate VDB')
    hits = []
    for t in targets:
        m, s, i = t['metric'], t['scope'], t['point']['raw_index']
        old, new = before['metrics'][m][s], single['metrics'][m][s]
        require((old['width'], old['checksum']) == (new['width'], new['checksum']) ==
                (t['bitmap_width'], t['metric_checksum']), 'Target shape drift')
        require(0 <= i < old['width'], 'Invalid raw target')
        bit = 1 << (old['width']-1-i)
        require(not int(old['bits'], 16)&bit, 'Target was already hit in719')
        hits.append(dict(metric=m, scope=s, point=t['point'], hit719=False,
                         hit_single=bool(int(new['bits'], 16)&bit)))
    return hits


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh prepare directory')
    prepared_path = RUN.with_name(RUN.name+'.prepared.json')
    prepared = life.read_bound(prepared_path, RUN_SEAL)
    pre = preflight.verify(runner.PRE, PRE_SEAL); runner.validate(pre)
    require(prepared['command'] == runner.command(RUN) and prepared['preflight_seal'] == PRE_SEAL and
            prepared['output'] == str(RUN) and prepared['timeout_s'] == 1800, 'Prepared command differs')
    pins = life.merge_pins(prepared['pins'], {str(prepared_path): RUN_SEAL})
    paths = [Path(__file__).resolve(), Path(__file__).with_name('test_collect_narrow_reject_r1_cached_strict.py'), TRACER_FIXTURE,
             Path(bitmap.__file__).resolve(), *sorted((life.ROOT/'verification/ara_verify').glob('*.py'))]
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in paths}); life.check(pins)
    plan = dict(status='R1_CACHED_STRICT_COLLECTOR_PREPARED_NOT_EXECUTED', run=str(RUN), baseline=str(BASE),
                baseline_tests=719, preflight_seal=PRE_SEAL, prepared_run_seal=RUN_SEAL, pins=pins,
                reference_counts=pre['reference_counts'], targets=pre['targets'], coverage_admitted=False,
                simulations_started=False, exclusions_generated=False,
                baseline_policy='719 diagnostic only; any later admission requires fresh authorized latest-base union')
    out.mkdir(); life.save(out/'plan.json', plan)
    print(json.dumps(dict(plan=str(out/'plan.json'), seal=life.digest(out/'plan.json'), pins=len(pins))))


def collect(plan_path, seal, out):
    plan = life.read_bound(plan_path, seal); life.check(plan['pins'])
    require(plan['status'] == 'R1_CACHED_STRICT_COLLECTOR_PREPARED_NOT_EXECUTED' and
            plan['run'] == str(RUN) and plan['baseline'] == str(BASE), 'Sealed plan identity differs')
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh audit directory')
    require((RUN/'simulation-status.json').is_file(), 'HOLD no terminal status; audit not started')
    pins = life.merge_pins(plan['pins'], {str(plan_path): seal})
    def read(path):
        path = Path(path).absolute()
        require(path.resolve() == path and not path.is_symlink(), 'Aliased evidence')
        pins.update(life.merge_pins(pins, {str(path): life.digest(path)}))
        return path.read_bytes()
    out.mkdir()
    try:
        state = json.loads(read(RUN/'simulation-status.json'))
        prepared = life.read_bound(RUN.with_name(RUN.name+'.prepared.json'), RUN_SEAL)
        terminal(state, json.loads(read(RUN/'manifest.json')), prepared)
        pre = life.read_bound(runner.PRE/'preflight-manifest.json', PRE_SEAL); runner.validate(pre)
        require(plan['targets'] == pre['targets'] and plan['reference_counts'] == pre['reference_counts'], 'Plan gate drift')
        before = json.loads(read(BASE/'combined-bits.json'))
        require(len(before['tests']) == len(set(before['tests'])) == 719 and
                read(BASE/'combined-inputs.txt').decode().splitlines() == [str(DESIGN), *before['tests']],
                'Exact719 membership/order differs')
        rows = common.read_csv(read(RUN/'commit_trace.csv'), common.COMMIT_FIELDS)
        vectors = common.read_csv(read(RUN/'vector_trace.csv'), common.VECTOR_FIELDS)
        console, log = read(RUN/'console.log').decode(), read(RUN/'run.vcs.log').decode()
        tracer = read(RUN/'trace_hart_0.log').decode(); read(RUN/'trace_hart_0_commit.log')
        for p in sorted((RUN/'code.vdb').rglob('*')):
            if p.is_file(): read(p)
        control = lifecycle(rows, vectors, pre['symbols'])
        data = observed(rows, pre['symbols']); trap = tracer_exact(tracer, rows, pre['symbols'])
        contracts = re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)', console)
        require(len(contracts) == 1 and tuple(map(int, contracts[0])) ==
                (control['requests'], control['responses'], 24, 0, 0) and
                not common.check_contract_log(RUN/'run.vcs.log'), 'Contract/conservation differs')
        require(log.count('Core Test *** SUCCESS ***') == 1, 'Missing software SUCCESS')
        scalar = common.spike_trace.compare_commit_prefix(runner.PRE/'spike.trace', RUN/'commit_trace.csv',
                    0x80000000, terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar, plan['reference_counts'])
        reference = oracle.shared.parse_spike_commits(runner.PRE/'spike.trace')
        vector = common.compare_vector_commits(runner.PRE/'spike.trace', RUN/'commit_trace.csv', RUN/'vector_trace.csv', 0x80000000)
        vector_exact(vector, control['rejected_arch_seqs'], reference)
        life.check(pins)
        life.save(out/'diagnostic-inputs.json', [str(DESIGN), str(RUN/'code.vdb')])
        with (out/'diagnostic-inputs.txt').open('x') as stream:
            stream.write(str(DESIGN)+'\n'+str(RUN/'code.vdb')+'\n')
        single = bitmap.collect(out/'diagnostic-inputs.txt')
        pins = life.merge_pins(pins, single['input_hashes'])
        hits = target_hits(before, single, plan['targets'])
        proposed = bitmap.combine(before, single); delta = bitmap.delta(before, proposed)
        life.check(pins)
        for name, value in [('scalar-comparison.json', scalar), ('vector-comparison.json', vector),
                            ('observed-signatures.json', data), ('lifecycle.json', control), ('trap-proof.json', trap),
                            ('single-raw-bits.json', single), ('raw-union.proposed.json', proposed),
                            ('raw-bitmap-delta.json', delta), ('target-hits.json', hits), ('evidence-pins.json', pins)]:
            life.save(out/name, value)
        outputs = {str(p): life.digest(p) for p in out.iterdir() if p.is_file()}
        status = dict(status='R1_CACHED_STRICT_CANDIDATE_VERIFIED_NOT_ADMITTED', pins=life.merge_pins(pins, outputs),
                      baseline_tests=719, candidate_tests=1, new_admitted=0, raw_delta=delta['metrics'],
                      targets_hit=sum(h['hit_single'] for h in hits), targets_total=45, coverage_admitted=False,
                      simulations_started=False, official_DVE_report=False, rtl_changed=False,
                      baseline_policy=plan['baseline_policy'])
        life.save(out/'status.json', status)
        print(json.dumps(dict(output=str(out), seal=life.digest(out/'status.json'), status=status['status'],
                              raw_delta=delta['metrics'], targets_hit=status['targets_hit'])))
    except Exception as error:
        # Seal all available terminal evidence, including failed-run VDBs; never promote it.
        for p in sorted(RUN.rglob('*')):
            if p.is_file() and not p.is_symlink() and p.resolve() == p and str(p) not in pins:
                pins[str(p)] = life.digest(p)
        pin_error = None
        try: life.check(pins)
        except Exception as drift: pin_error = str(drift)
        life.save(out/'failure.json', dict(status='STRICT_AUDIT_FAIL_NOT_ADMITTED', reason=str(error),
                  pin_error=pin_error, pins=pins, coverage_admitted=False, simulations_started=False,
                  rtl_changed=False, retry_performed=False))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify', 'collect'))
    p.add_argument('--output', type=Path); p.add_argument('--plan', type=Path); p.add_argument('--seal')
    a = p.parse_args()
    if a.mode == 'prepare':
        require(a.output and not a.plan and not a.seal, 'Prepare arguments'); prepare(a.output.absolute())
    else:
        require(a.plan and a.seal, 'Sealed plan required')
        if a.mode == 'verify':
            require(not a.output, 'Read-only verify'); plan = life.read_bound(a.plan, a.seal); life.check(plan['pins'])
            print('VERIFY_PASS R1_CACHED_COLLECTOR NOT_EXECUTED_NOT_ADMITTED')
        else:
            require(a.output, 'Fresh audit output required'); collect(a.plan.absolute(), a.seal, a.output.absolute())


if __name__ == '__main__': main()
