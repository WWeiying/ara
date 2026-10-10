"""Case-specific full terminal qualification; no simulation, coverage collection or admission."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

import run_readonly_csr_simulation_v3 as adapter
import build_readonly_csr_preflight_v3 as preflight
import collect_opivx_vsbc_strict as common
from qualify_store_fault_flush_terminal import elf_instruction
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log, parse_contract_summary

p, life, require = preflight.frozen, adapter.life, adapter.require
RUN = life.OUT / 'readonly-csr-v3-old-image-parent-20261006-01'
RUN_SEAL = '919cc59c2b2a6c3fce82ac069caa9311474eae6415ef2ec2334b9dce127dfb93'
PRE = life.OUT / 'readonly-csr-preflight-v3-733-agent-20261006-01'
PRE_SEAL = 'cfc86e25e0784f6d41b4a6e8d93b66e19c5e97587a2cd02cd8a35b61e0e9a676'
STATUS = 'READONLY_CSR_TERMINAL_PLAN_NOT_EXECUTED'


def verify_prepared(run, prepared):
    require(run == RUN and prepared['preflight'] == str(PRE / 'preflight-manifest.json') and
            prepared['preflight_seal'] == PRE_SEAL, 'Exact parent run/preflight identity required')
    pre = preflight.verify(PRE, PRE_SEAL)
    ns = adapter.load_adapter()
    deps = [Path(adapter.prior.__file__).resolve(), Path(adapter.prior.frozen.__file__).resolve(),
            Path(adapter.__file__).resolve(), Path(adapter.__file__).with_name('test_run_readonly_csr_simulation_v3.py')]
    pins = life.merge_pins(pre['pins'], preflight.image_inputs())
    pins = life.merge_pins(pins, {str(x): life.digest(x) for x in deps})
    pins = life.merge_pins(pins, {str(PRE / 'preflight-manifest.json'): PRE_SEAL,
        str(Path(ns['frozen'].__file__).resolve()): ns['LIFECYCLE_SHA']})
    expected = dict(case=p.NAME, output=str(run), preflight=str(PRE / 'preflight-manifest.json'),
        preflight_seal=PRE_SEAL, command=ns['command'](run, PRE), pins=pins, timeout_s=600,
        elf_sha256=pre['elf_sha256'], image_sha256=p.IMAGE_SHA, old_image_files_checked=66,
        software_checks=p.CHECKS, exact_illegal_traps=12, targets=pre['targets'], static_baseline=733,
        raw_gain_requires_latest_formal_population_at_least=734, foreground_lifetime=True,
        automatic_retry=False, coverage_admitted=False, admission_performed=False,
        native_cycle_qualified=False, parent_review_required=True,
        terminal_qualification_required='Full scalar/vector/ELF/store/CSR/trap/postpins, not software PASS alone',
        systemd_policy=dict(RuntimeMaxSec=660, TimeoutStopSec=10, KillMode='control-group'))
    require(prepared == expected, 'Exact prepared command/fields/pins differ')
    life.check(prepared['pins']); return pre


def terminal(state, actual, started, prepared):
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and
        type(state.get('returncode')) is int and state['returncode'] == 0 and
        state.get('case') == p.NAME and state.get('timeout') is False and
        state.get('coverage_admitted') is False and state.get('admission_performed') is False and
        state.get('terminal_oracle_verified') is False, 'HOLD: successful OS return receipt required')
    require(actual == prepared and started['command'] == prepared['command'] and
        started['input_elf'] == str(PRE / 'input.elf') and started['elf_sha256'] == prepared['elf_sha256'] and
        started['image'] == str(life.IMAGE) and started['image_sha256'] == p.IMAGE_SHA and
        type(started['pid']) is int and started['pid'] > 0 and
        started['pid'] == started['process_group'] == state['pid'] and started['budget_s'] == 600 and
        started['foreground_lifetime'] is True and started['coverage_admitted'] is False,
        'Startup process/command/image/ELF identity differs')
    require(type(state.get('wall_seconds')) in (int, float) and
            math.isfinite(state['wall_seconds']) and state['wall_seconds'] >= 0, 'Invalid actual wall receipt')


def observed(rows, symbols, directory):
    sizes = dict(rc_before=960, rc_after=960, rc_rd=96, rc_traps=384, rc_count=8,
        rc_index=8, rc_pc=8, rc_opcode=8, rc_source=144, rc_dump=144, rc_result=144)
    footprints = [(symbols[n], symbols[n] + size) for n, size in sizes.items()]
    retired = [r for r in rows if r['event'] == 'retire']
    require(retired and [int(r['order']) for r in retired] == list(range(len(retired))), 'Incomplete retirement order')
    blob = (directory / 'input.elf').read_bytes()
    memory, reads, terminals, traps, handler_stores = {}, set(), [], [], []
    for r in retired:
        pc, word = int(r['pc'], 16), int(r['insn'], 16)
        require(elf_instruction(blob, pc, 2 if word & 3 != 3 else 4) == word and
                pc != symbols['trap_fail'], 'Retirement outside sealed ELF/fatal path')
        rm, wm, addr = int(r['mem_rmask'], 16), int(r['mem_wmask'], 16), int(r['mem_addr'], 16)
        if int(r['trap']):
            require((pc, word) in [(symbols[n], p.opcode(i)) for i, n in enumerate(p.FAULTS)] and
                    not rm and not wm, 'Unexpected trap retirement/memory effect')
            traps.append((pc, word)); continue
        require(pc not in [symbols[n] for n in p.FAULTS], 'Illegal CSR retired successfully')
        handler = symbols['rc_handler_begin'] <= pc < symbols['rc_handler_end']
        if handler:
            require(int(r['rd']) in (0, 2, 5, 6, 7), 'Handler writes protected scalar register')
            if word & 127 == 0x73 and word >> 12 & 7:
                fn, rs = word >> 12 & 7, word >> 15 & 31
                writes = fn in (1, 5) or (fn in (2, 3, 6, 7) and rs != 0)
                require(not writes or word >> 20 == 0x341, 'Handler writes protected CSR')
        access = common.scalar_memory(word)
        if access is None:
            require(not rm and not wm, 'Unknown scalar memory effect'); continue
        kind, size = access; mask = ((1 << size) - 1) << (addr & 7)
        require(addr % size == 0 and rm == (mask if kind == 'read' else 0) and
                wm == (mask if kind == 'write' else 0), 'Scalar memory mask/alignment differs')
        if kind == 'write':
            value = int(r['mem_wdata'], 16) & ((1 << (8 * size)) - 1)
            if addr == symbols['tohost']: terminals.append(r)
            if handler: handler_stores.append((addr, size, word))
        elif any(a <= addr and addr + size <= b for a, b in footprints):
            require(int(r['rd']) != 0, 'Unobservable oracle readback')
            value = int(r['rd_wdata'], 16) & ((1 << (8 * size)) - 1)
            reads.update(range(addr, addr + size))
        else: continue
        memory.update({addr + i: b for i, b in enumerate(value.to_bytes(size, 'little'))})
    expected_traps = [(symbols[n], p.opcode(i)) for i, n in enumerate(p.FAULTS)]
    require(traps == [] or traps == expected_traps, 'Partial/duplicate trap-marked RVFI inventory')
    require(terminals == [retired[-1]], 'Missing/extra/post-terminal tohost')
    require(reads == {i for a, b in footprints for i in range(a, b)}, 'Incomplete full oracle footprint readback')
    def read(n, offset=0, size=8):
        a = symbols[n] + offset
        require(all(a + j in memory for j in range(size)), 'Missing signature bytes: ' + n)
        return int.from_bytes(bytes(memory[a + j] for j in range(size)), 'little')
    require(read('g75_result', size=4) == p.CHECKS and
        read('g75_result', 4, 4) == read('num_failed', size=4) == 0 and read('tohost') == 1,
        'Software checks/terminal differ')
    for i, n in enumerate(p.FAULTS):
        require([read('rc_traps', (i * 4 + j) * 8) for j in range(4)] ==
                [1, 2, symbols[n], p.opcode(i)], 'Exact trap ledger differs')
        require(read('rc_rd', i * 8) == p.SENTINEL, 'RD sentinel changed')
        for array in ('rc_before', 'rc_after'):
            require([read(array, (i * 10 + j) * 8) for j in range(10)] == p.CONFIG, 'CSR preservation differs')
    require([read(n) for n in ('rc_count', 'rc_index', 'rc_pc', 'rc_opcode')] ==
            [12, 11, symbols[p.FAULTS[11]], p.opcode(11)], 'Trap count/control ledger differs')
    for n in ('rc_source', 'rc_dump', 'rc_result'):
        require(bytes(read(n, j, 1) for j in range(144)) == p.buffer(n), 'Buffer/guard differs: ' + n)
    ledger = Counter((symbols['rc_traps'] + i * 32 + j * 8, 8) for i in range(12) for j in range(4))
    ledger[(symbols['rc_count'], 8)] = 12
    actual, frames = Counter(), []
    for a, size, word in handler_stores:
        if word & 127 == 0x23 and word >> 15 & 31 == 2:
            require(size == 8 and 0x80100000 <= a < 0x80200000, 'Handler stack write differs'); frames.append(a)
        else: actual[a, size] += 1
    require(actual == ledger and len(frames) == 36 and len(set(frames)) == 3, 'Handler exact store footprint differs')
    return dict(checks=p.CHECKS, failed_checks=0, traps=12, cause=2, exact_pc_tval=True,
        preserved_csrs_per_case=10, rd_preserved=True, full_buffer_bytes=432,
        explicit_readback_bytes=len(reads), handler_store_words=96,
        elf_matched_retirements=len(retired), trap_marked_retirements=len(traps))


def lifecycle(rows, vectors, symbols):
    starts, pending, live, intervals = {}, {}, {}, defaultdict(list)
    req, resp, ba, bd, rejected = Counter(), Counter(), Counter(), Counter(), []
    previous = -1
    for r in rows:
        event, cycle, seq, tid = r['event'], int(r['cycle']), int(r['order']), int(r['trans_id'])
        require(cycle >= previous, 'Commit time reversed'); previous = cycle
        if event == 'arch_start':
            require(seq >= 0 and seq not in starts and tid not in pending, 'Duplicate architectural/live request')
            starts[seq], pending[tid] = r, [seq, False]
        elif event == 'cvx_req':
            require(tid in pending and not pending[tid][1], 'Unknown/duplicate CVX request')
            owner = pending[tid][0]
            require(int(r['insn'], 16) == int(starts[owner]['insn'], 16), 'CVX request opcode differs')
            pending[tid][1] = True; req[owner] += 1
        elif event == 'cvx_resp':
            require(tid in pending and pending[tid][1] and seq == -1 and
                int(r['pc'], 16) == int(r['insn'], 16) == 0 and int(r['trap']) in (0, 1), 'Unknown CVX response')
            owner = pending.pop(tid)[0]; resp[owner] += 1
            if int(r['trap']): rejected.append(owner)
        elif event in ('uop_alloc', 'uop_done'):
            vid = int(r['port'])
            require(seq in starts and 0 <= vid < 8 and tid == int(starts[seq]['trans_id']) and
                int(r['insn'], 16) == int(starts[seq]['insn'], 16), 'Backend identity differs')
            word = int(r['insn'], 16)
            require(word & 127 in (0x07, 0x27, 0x57) and not
                    (word & 127 == 0x57 and word >> 12 & 7 == 7), 'CSR/config/illegal backend allocation')
            if event == 'uop_alloc':
                require(vid not in live, 'Live SID reused')
                item = dict(seq=seq, start=cycle, end=None); live[vid] = item; intervals[vid].append(item)
                ba[seq, vid, cycle] += 1
            else:
                require(vid in live and live[vid]['seq'] == seq and cycle >= live[vid]['start'], 'Unowned backend completion')
                live.pop(vid)['end'] = cycle; bd[seq, vid, cycle] += 1
        else: require(event == 'retire', 'Unknown commit event')
    require(not pending and not live and req == resp == Counter(starts.keys()) and
        Counter((s, v) for s, v, c in ba.elements()) == Counter((s, v) for s, v, c in bd.elements()),
        'Request/response/backend conservation differs')
    faults = []
    for i in range(12):
        found = [s for s, r in starts.items() if int(r['insn'], 16) == p.opcode(i)]
        require(len(found) == 1, 'Missing/duplicate exact illegal CSR request'); faults.extend(found)
    require(rejected == faults and not any(s in faults for s, v, c in ba), 'Exact twelve rejected/no-backend contract differs')
    va, vd, metadata, previous = Counter(), Counter(), {}, -1
    for r in vectors:
        event, cycle, seq, vid = r['event'], int(r['cycle']), int(r['arch_seq']), int(r['vid'])
        require(cycle >= previous and (int(r['nr_lanes']), int(r['vlen_bits'])) == (4, 1024), 'Native time/geometry differs')
        previous = cycle
        require(seq not in faults, 'Rejected CSR produced native activity')
        if event == 'config': continue
        require(seq in starts and 0 <= vid < 8 and int(r['insn'], 16) == int(starts[seq]['insn'], 16) and
                event in ('alloc', 'done', 'write'), 'Unknown native event/opcode/owner')
        if event == 'alloc':
            key = seq, vid, cycle
            require(key not in metadata, 'Duplicate native allocation'); metadata[key] = r; va[key] += 1
        else:
            eligible = [a for a in intervals[vid] if a['seq'] == seq and a['start'] <= cycle <= a['end']]
            require(len(eligible) == 1, 'Native write/done outside exact SID owner lifetime')
            key = seq, vid, eligible[0]['start']
            require(key in metadata and all(r[k] == metadata[key][k] for k in ('insn', 'use_vd', 'vd', 'eew', 'vl', 'vstart')),
                    'Native metadata drift')
            if event == 'done': vd[seq, vid, cycle] += 1
            else: require(int(r['use_vd']) == 1 and 0 <= int(r['lane']) < 4, 'Invalid native destination writer')
    require(va == ba and vd == bd, 'Native/commit exact lifecycle differs')
    recovered = [r for r in rows if r['event'] == 'retire' and int(r['pc'], 16) == symbols['rc_recovery']]
    require(len(recovered) == 1 and int(recovered[0]['insn'], 16) == 0x0281b557 and not int(recovered[0]['trap']),
            'Missing exact recovery retirement')
    return dict(requests=sum(req.values()), responses=sum(resp.values()), exceptions=12,
        rejected_arch_seqs=faults, rejected_backend_uops=0, rejected_vrf_activities=0,
        backend_uops=sum(ba.values()), exact_SID_owner_checked=True)


def tracer_exact(text, rows, symbols):
    pattern = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual = [m.groups() for line in text.splitlines() if (m := pattern.match(line))]
    retired = [r for r in rows if r['event'] == 'retire']
    wanted = [(str(int(r['cycle'])), 'M', '%016x' % int(r['pc'], 16), '%08x' % int(r['insn'], 16)) for r in retired]
    require(actual[:len(wanted)] == wanted, 'Full tracer/RVFI retirement prefix differs')
    tail = actual[len(wanted):]
    require(not tail or tail == [(wanted[-1][0], 'M', '%016x' % (int(wanted[-1][2], 16) + 4), '0000a001')],
            'Unknown post-terminal tracer tail')
    events = re.findall(r'Exception @\s*(\d+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)', text)
    tvals = re.findall(r'tval: ([0-9a-fA-F]+)', text)
    require(len(events) == text.count('Exception @') == len(tvals) == 12 and
        [(int(pc, 16), cause.strip()) for cycle, pc, cause in events] ==
        [(symbols[n], 'Illegal Instruction') for n in p.FAULTS] and
        [int(v, 16) for v in tvals] == [p.opcode(i) for i in range(12)], 'Exact tracer cause/PC/tval/order differs')
    return dict(exceptions=12, cause=2, exact_pc_tval=True, tracer_tail=tail)


def scalar_exact(result, expected, observed_result):
    fixed = dict(status='TERMINAL_TOHOST_MATCH', entry='0x0000000080000000',
        rvfi_store_data_layout='unshifted', skipped_unobservable_register_values=0,
        stopped_at_unobservable=None, aligned_vector_faults=[], mismatch=None, terminal_ecall=None,
        vector_state_compared=False, ara_trap_events=observed_result['trap_marked_retirements'])
    fixed.update(expected); fixed.update(ara_committed_instructions=expected['matched_instructions'],
        ara_retired_instructions=expected['matched_instructions'] + observed_result['trap_marked_retirements'])
    require(all(k in result and type(result[k]) is type(v) and result[k] == v for k, v in fixed.items()),
            'Full scalar/reference comparison differs')


def native_exact(vector, control, reference, run):
    require(vector['status'] == 'PASS' and vector['compared_instructions'] == 3 and vector['compared_bytes'] == 264 and
        vector['trapped_requests'] == control['rejected_arch_seqs'] and
        all(vector[k] == 0 for k in ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions')) and
        vector['first_mismatch'] is None and not vector['incomplete_requests'] and not vector['unretired_requests'],
        'Full vector comparison differs')
    expected = [c for c in reference if c.vector_writes]
    require([(int(r['pc'], 16), int(r['instruction'], 16), r['compared_bytes']) for r in vector['instructions']] ==
        [(c.pc, c.instruction, size) for c, size in zip(expected, (128, 128, 8))] and len(expected) == 3,
        'Vector record PC/opcode/byte population differs')
    lanes, vlen, activities = vc._parse_vector_trace(run / 'vector_trace.csv')
    starts, retires, rejected = vc._parse_architecture_mapping(run / 'commit_trace.csv')
    mapping = vc._map_spike_commits(vc._map_architecture_retires(starts, retires, rejected), reference)
    require((lanes, vlen) == (4, 1024) and rejected == set(control['rejected_arch_seqs']), 'Native geometry/rejections differ')
    wanted = {s: reference[i] for s, i in mapping.items() if reference[i].vector_writes}
    require({s for s, a in activities.items() if a.writes} == set(wanted), 'Extra/missing native writer')
    for seq, c in wanted.items():
        size = 8 if c.instruction == 0x0281b557 else 128
        producer = 0 if size == 8 else 4
        writes, seen = activities[seq].writes, set()
        require(activities[seq].eew == 0 and activities[seq].vl == size and activities[seq].vstart == 0,
                'Native architectural context differs')
        for w in writes:
            require(w.source == producer and w.be & ~w.known_be == 0 and w.eew == 0,
                    'Unknown/wrong native producer/context')
            for b in range(8):
                if w.be & (1 << b):
                    key = w.addr, w.lane, b
                    require(key not in seen, 'Duplicate accepted native byte'); seen.add(key)
        actual = vc._architectural_bytes(writes, 4, 1024)
        require({k: v for k, (v, _) in actual.items()} ==
            {(reg, b): (value >> (8 * b)) & 255 for reg, value in c.vector_writes.items() for b in range(size)},
            'Exact accepted native destination bytes differ')


def logs(console, log, control):
    for text in (console, log):
        require(not re.search(r'Fatal:|Error:|Fatal-\[|Error-\[|\[ARA_CONTRACT_ERROR\]|Core Test \*\*\* FAILED', text),
                'Simulator/protocol error')
        for line in text.splitlines():
            if re.search(r'\bUVM_(ERROR|FATAL)\b', line):
                require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0+\s*', line), 'Unexpected UVM error')
    require(log.count('Core Test *** SUCCESS ***') == 1, 'Missing/extra software terminal marker')
    summaries = [parse_contract_summary(l.strip()) for l in console.splitlines() if '[ARA_CONTRACT]' in l]
    require(len(summaries) == 1 and summaries[0] is not None, 'Missing/extra protocol summary')
    summary = summaries[0]
    require(summary['requests'] == summary['responses'] == control['requests'] and summary['exceptions'] == 12 and
        all(summary[k] == 0 for k in ('protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')), 'Protocol counters differ')


def prepare(output):
    require(output.parent == life.OUT and output.resolve() == output and not output.exists(), 'Fresh direct plan required')
    record = RUN.with_name(RUN.name + '.prepared.json'); prepared = life.read_bound(record, RUN_SEAL)
    verify_prepared(RUN, prepared)
    deps = [Path(__file__).resolve(), Path(__file__).with_name('test_qualify_readonly_csr_terminal.py'),
        Path(common.__file__).resolve(), Path(__file__).with_name('qualify_store_fault_flush_terminal.py'),
        *sorted((life.ROOT / 'verification/ara_verify').glob('*.py'))]
    pins = life.merge_pins(prepared['pins'], {str(x): life.digest(x) for x in deps})
    sources = life.read_bound(p.SOURCE, p.SOURCE_SEAL)
    pins = life.merge_pins(pins, {str(record): RUN_SEAL, **{str(life.ROOT / rel): sources[str(life.ROOT / rel)]
        for rel in ('hardware/tb/ara_commit_monitor.sv', 'hardware/tb/ara_tb.sv', 'hardware/src/lane/operand_requester.sv')}})
    life.check(pins); output.mkdir()
    plan = dict(status=STATUS, run=str(RUN), prepared=str(record), prepared_seal=RUN_SEAL,
        preflight=str(PRE / 'preflight-manifest.json'), preflight_seal=PRE_SEAL, pins=pins,
        expected_checks=p.CHECKS, exact_illegal_traps=12, static_baseline=733,
        raw_gain_requires_latest_formal_population_at_least=734, coverage_admitted=False,
        simulations_started=False, native_cycle_qualified=False)
    life.save(output / 'plan.json', plan)
    print(json.dumps(dict(plan=str(output / 'plan.json'), seal=life.digest(output / 'plan.json'), pins=len(pins))))


def collect(planpath, seal, out):
    plan = life.read_bound(planpath, seal)
    require(plan['status'] == STATUS and plan['run'] == str(RUN) and plan['prepared_seal'] == RUN_SEAL and
        plan['preflight'] == str(PRE / 'preflight-manifest.json') and plan['preflight_seal'] == PRE_SEAL and
        plan['raw_gain_requires_latest_formal_population_at_least'] == 734, 'Plan identity differs')
    life.check(plan['pins'])
    require((RUN / 'simulation-status.json').is_file(), 'No terminal receipt: do not read active trace')
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh direct collection required')
    pins = life.merge_pins(plan['pins'], {str(planpath): seal})
    def read(path):
        require(path.resolve() == path and not path.is_symlink(), 'Aliased evidence')
        raw = path.read_bytes(); sha = hashlib.sha256(raw).hexdigest()
        require(life.digest(path) == sha, 'Terminal evidence changed while reading')
        pins[str(path)] = sha; return raw
    prepared = life.read_bound(Path(plan['prepared']), RUN_SEAL)
    terminal(json.loads(read(RUN / 'simulation-status.json')), json.loads(read(RUN / 'manifest.json')),
             json.loads(read(RUN / 'started.json')), prepared)
    out.mkdir()
    try:
        pre = verify_prepared(RUN, prepared); symbols = pre['symbols']
        rows = common.read_csv(read(RUN / 'commit_trace.csv'), common.COMMIT_FIELDS)
        vectors = common.read_csv(read(RUN / 'vector_trace.csv'), common.VECTOR_FIELDS)
        control = lifecycle(rows, vectors, symbols); memory = observed(rows, symbols, PRE)
        console, log = read(RUN / 'console.log').decode(), read(RUN / 'run.vcs.log').decode()
        logs(console, log, control)
        require(not check_contract_log(RUN / 'run.vcs.log'), 'Protocol log errors')
        trap = tracer_exact(read(RUN / 'trace_hart_0.log').decode(), rows, symbols)
        read(RUN / 'trace_hart_0_commit.log')
        reference = p.shared.parse_spike_commits(PRE / 'spike.trace')
        scalar = common.spike_trace.compare_commit_prefix(PRE / 'spike.trace', RUN / 'commit_trace.csv',
            0x80000000, terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
        scalar_exact(scalar, common.reference_counts(reference, symbols), memory)
        vector = common.compare_vector_commits(PRE / 'spike.trace', RUN / 'commit_trace.csv', RUN / 'vector_trace.csv', 0x80000000)
        native_exact(vector, control, reference, RUN)
        db = RUN / 'code.vdb'; files = sorted(x for x in db.rglob('*') if x.is_file())
        require(files and all(any(x.name == m + '.verilog.data.xml' for x in files) for m in ('line', 'cond', 'branch', 'fsm')),
                'Incomplete raw VDB witness')
        for path in files: read(path)
        life.check(pins)
        for name, obj in (('scalar-comparison.json', scalar), ('vector-comparison.json', vector),
                          ('observed-memory.json', memory), ('lifecycle.json', control), ('trap-proof.json', trap)):
            life.save(out / name, obj)
        outputs = {str(x): life.digest(x) for x in out.iterdir() if x.is_file()}
        life.save(out / 'qualification.json', dict(status='READONLY_CSR_FULL_SCALAR_VECTOR_CSR_TRAP_MEMORY_NATIVE_PASS_NOT_ADMITTED',
            pins=life.merge_pins(pins, outputs), checks=p.CHECKS, illegal_traps=12, UVM_errors=0,
            OS_returncode=0, terminal_source='FOREGROUND_RUNNER_OS_RETURN_RECEIPT',
            native_known_write_bytes=264, full_memory_bytes=432, software_reference_is_Spike=True,
            whole_ISA_qualified=False, static_baseline=733, raw_gain_requires_latest_formal_population_at_least=734,
            coverage_admitted=False, target_hits_verified=False, raw_gain_collected=False,
            native_cycle_qualified=False, simulation_retried=False))
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'qualification.json'), coverage_admitted=False)))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='QUALIFICATION_HOLD_NOT_ADMITTED', reason=str(error), pins=pins))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'collect'))
    parser.add_argument('--output', type=Path); parser.add_argument('--plan', type=Path); parser.add_argument('--seal')
    a = parser.parse_args()
    if a.mode == 'prepare':
        require(a.output is not None and not a.plan and not a.seal, 'Prepare arguments')
        prepare(a.output.absolute())
    else:
        require(a.plan is not None and a.seal, 'Reviewed plan/seal required')
        if a.mode == 'collect':
            require(a.output is not None, 'Fresh collection output required'); collect(a.plan.absolute(), a.seal, a.output.absolute())
        else:
            plan = life.read_bound(a.plan, a.seal); require(plan['status'] == STATUS, 'Plan status differs')
            life.check(plan['pins']); print('VERIFY_PASS NO_DUT_READ NO_SIMULATION NOT_ADMITTED')
