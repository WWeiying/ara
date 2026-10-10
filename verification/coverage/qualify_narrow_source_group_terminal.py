"""Narrow source-group full terminal qualification; no simulation, coverage collection or admission."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

from types import SimpleNamespace
import run_narrow_source_group_simulation as runner
import coverage_bitmap_delta as bitmap
import collect_opivx_vsbc_strict as common
from qualify_store_fault_flush_terminal import elf_instruction
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log, parse_contract_summary

life, require = runner.life, runner.require
PRE, PRE_SEAL = runner.PRE, runner.PRE_SEAL
p = SimpleNamespace(NAME=runner.NAME, CHECKS=2130, FAULTS=('ng_fault',),
    CONFIG=[8,2,128,0,2,1], SENTINEL=0x7193a65bc24de80f,
    opcode=lambda i: runner.p.FAULT if i == 0 else None,
    buffer=runner.p.expected_buffer, shared=runner.p.shared,
    SOURCE=runner.p.prior.SOURCE, SOURCE_SEAL=runner.p.prior.SOURCE_SEAL,
    IMAGE_SHA=runner.p.prior.IMAGE_SHA)
STATUS = 'NARROW_SOURCE_GROUP_TERMINAL_PLAN_NOT_EXECUTED'
verify_prepared = runner.verify_prepared


def terminal(state, actual, started, prepared):
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and
        type(state.get('returncode')) is int and state['returncode'] == 0 and
        state.get('case') == p.NAME and state.get('timeout') is False and
        state.get('coverage_admitted') is False and state.get('admission_performed') is False and
        state.get('terminal_oracle_verified') is False, 'HOLD: successful OS return receipt required')
    require(actual == prepared and started['command'] == prepared['command'] and
        started['input_elf'] == str(runner.ELF) and started['elf_sha256'] == prepared['elf_sha256'] and
        started['image'] == str(life.IMAGE) and started['image_sha256'] == p.IMAGE_SHA and
        type(started['pid']) is int and started['pid'] > 0 and
        started['pid'] == started['process_group'] == state['pid'] and started['budget_s'] == 180 and
        started['foreground_lifetime'] is True and started['coverage_admitted'] is False,
        'Startup process/command/image/ELF identity differs')
    require(type(state.get('wall_seconds')) in (int, float) and
            math.isfinite(state['wall_seconds']) and state['wall_seconds'] >= 0, 'Invalid actual wall receipt')


def observed(rows, symbols, directory):
    sizes = dict(ng_before=48, ng_after=48, ng_rd=8, ng_trap=32, ng_count=8,
                 ng_source=528, ng_old=528, ng_dump=528, ng_recovered=528)
    footprints = [(symbols[n], symbols[n] + size) for n, size in sizes.items()]
    retired = [r for r in rows if r['event'] == 'retire']
    require(retired and [int(r['order']) for r in retired] == list(range(len(retired))), 'Incomplete retirement order')
    blob = runner.ELF.read_bytes()
    memory, reads, terminals, traps, handler_stores = {}, set(), [], [], []
    for r in retired:
        pc, word = int(r['pc'], 16), int(r['insn'], 16)
        require(int(r['trap']) in (0,1), 'Invalid retirement trap flag')
        require(elf_instruction(blob, pc, 2 if word & 3 != 3 else 4) == word and
                pc != symbols['trap_fail'], 'Retirement outside sealed ELF/fatal path')
        rm, wm, addr = int(r['mem_rmask'], 16), int(r['mem_wmask'], 16), int(r['mem_addr'], 16)
        if int(r['trap']):
            require((pc, word) in [(symbols[n], p.opcode(i)) for i, n in enumerate(p.FAULTS)] and
                    not rm and not wm, 'Unexpected trap retirement/memory effect')
            traps.append((pc, word)); continue
        require(pc not in [symbols[n] for n in p.FAULTS], 'Illegal CSR retired successfully')
        handler = symbols['ng_handler_begin'] <= pc < symbols['ng_handler_end']
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
        require([read('ng_trap', j * 8) for j in range(4)] ==
                [1, 2, symbols[n], p.opcode(i)], 'Exact trap ledger differs')
        require(read('ng_rd') == p.SENTINEL, 'RD sentinel changed')
        for array in ('ng_before', 'ng_after'):
            require([read(array, j * 8) for j in range(6)] == p.CONFIG, 'CSR preservation differs')
    require(read('ng_count') == 1, 'Trap count differs')
    for n in ('ng_source','ng_old','ng_dump','ng_recovered'):
        require(bytes(read(n,j,1) for j in range(528)) == p.buffer(n), 'Buffer/guard differs: '+n)
    ledger = Counter((symbols['ng_trap'] + j * 8, 8) for j in range(4))
    ledger[(symbols['ng_count'], 8)] = 1
    actual, frames = Counter(), []
    for a, size, word in handler_stores:
        if word & 127 == 0x23 and word >> 15 & 31 == 2:
            require(size == 8 and 0x80100000 <= a < 0x80200000, 'Handler stack write differs'); frames.append(a)
        else: actual[a, size] += 1
    require(actual == ledger and len(frames) == 3 and len(set(frames)) == 3, 'Handler exact store footprint differs')
    return dict(checks=p.CHECKS, failed_checks=0, traps=1, cause=2, exact_pc_tval=True,
        preserved_csrs_per_case=6, rd_preserved=True, full_buffer_bytes=2112,
        explicit_readback_bytes=len(reads), handler_store_words=8,
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
    for i in range(1):
        found = [s for s, r in starts.items() if int(r['insn'], 16) == p.opcode(i)]
        require(len(found) == 1, 'Missing/duplicate exact illegal narrowing request'); faults.extend(found)
    require(rejected == faults and not any(s in faults for s, v, c in ba), 'Exact single rejected/no-backend contract differs')
    va, vd, metadata, previous = Counter(), Counter(), {}, -1
    for r in vectors:
        event, cycle, seq, vid = r['event'], int(r['cycle']), int(r['arch_seq']), int(r['vid'])
        require(cycle >= previous and (int(r['nr_lanes']), int(r['vlen_bits'])) == (4, 1024), 'Native time/geometry differs')
        previous = cycle
        require(seq not in faults, 'Rejected narrowing produced native activity')
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
    recovered = [r for r in rows if r['event'] == 'retire' and int(r['pc'], 16) == symbols['ng_recovery']]
    require(len(recovered) == 1 and int(recovered[0]['insn'], 16) == 0x0341bc57 and not int(recovered[0]['trap']),
            'Missing exact recovery retirement')
    return dict(requests=sum(req.values()), responses=sum(resp.values()), exceptions=1,
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
    require(len(events) == text.count('Exception @') == len(tvals) == 1 and
        [(int(pc, 16), cause.strip()) for cycle, pc, cause in events] ==
        [(symbols[n], 'Illegal Instruction') for n in p.FAULTS] and
        [int(v, 16) for v in tvals] == [p.opcode(i) for i in range(1)], 'Exact tracer cause/PC/tval/order differs')
    return dict(exceptions=1, cause=2, exact_pc_tval=True, tracer_tail=tail)


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
    require(vector['status'] == 'PASS' and vector['compared_instructions'] == 3 and vector['compared_bytes'] == 1032 and
        vector['trapped_requests'] == control['rejected_arch_seqs'] and
        all(vector[k] == 0 for k in ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions')) and
        vector['first_mismatch'] is None and not vector['incomplete_requests'] and not vector['unretired_requests'],
        'Full vector comparison differs')
    expected = [c for c in reference if c.vector_writes]
    require([(int(r['pc'], 16), int(r['instruction'], 16), r['compared_bytes']) for r in vector['instructions']] ==
        [(c.pc, c.instruction, size) for c, size in zip(expected, (512, 512, 8))] and len(expected) == 3,
        'Vector record PC/opcode/byte population differs')
    lanes, vlen, activities = vc._parse_vector_trace(run / 'vector_trace.csv')
    starts, retires, rejected = vc._parse_architecture_mapping(run / 'commit_trace.csv')
    mapping = vc._map_spike_commits(vc._map_architecture_retires(starts, retires, rejected), reference)
    require((lanes, vlen) == (4, 1024) and rejected == set(control['rejected_arch_seqs']), 'Native geometry/rejections differ')
    wanted = {s: reference[i] for s, i in mapping.items() if reference[i].vector_writes}
    require({s for s, a in activities.items() if a.writes} == set(wanted), 'Extra/missing native writer')
    for seq, c in wanted.items():
        size = 8 if c.instruction == 0x0341bc57 else 512
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
            {(reg, b): (value >> (8 * b)) & 255 for reg, value in c.vector_writes.items()
             for b in range(128) if (reg-min(c.vector_writes))*128+b < size},
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
    require(summary['requests'] == summary['responses'] == control['requests'] and summary['exceptions'] == 1 and
        all(summary[k] == 0 for k in ('protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')), 'Protocol counters differ')


def prepare(output, RUN, RUN_SEAL):
    require(output.parent == life.OUT and output.resolve() == output and not output.exists(), 'Fresh direct plan required')
    record = RUN.with_name(RUN.name + '.prepared.json'); prepared = life.read_bound(record, RUN_SEAL)
    verify_prepared(RUN, prepared)
    deps = [Path(__file__).resolve(), Path(__file__).with_name('test_qualify_narrow_source_group_terminal.py'),
        Path(common.__file__).resolve(), Path(__file__).with_name('qualify_store_fault_flush_terminal.py'),
        Path(bitmap.__file__).resolve(), *sorted((life.ROOT / 'verification/ara_verify').glob('*.py'))]
    require(life.digest(Path(bitmap.__file__)) == 'e251f049f619ca86e4a9578a468ddca8619ac532ead0ed0c5661a7ee3756e0e3',
            'Frozen bitmap reader drift')
    pins = life.merge_pins(prepared['pins'], {str(x): life.digest(x) for x in deps})
    sources = life.read_bound(p.SOURCE, p.SOURCE_SEAL)
    pins = life.merge_pins(pins, {str(record): RUN_SEAL, **{str(life.ROOT / rel): sources[str(life.ROOT / rel)]
        for rel in ('hardware/tb/ara_commit_monitor.sv', 'hardware/tb/ara_tb.sv', 'hardware/src/lane/operand_requester.sv')}})
    life.check(pins); output.mkdir()
    plan = dict(status=STATUS, run=str(RUN), prepared=str(record), prepared_seal=RUN_SEAL,
        preflight=str(PRE / 'preflight-manifest.json'), preflight_seal=PRE_SEAL, pins=pins,
        expected_checks=p.CHECKS, exact_illegal_traps=1, static_baseline=735,
        raw_gain_requires_latest_formal_population_at_least=735, coverage_admitted=False,
        simulations_started=False, native_cycle_qualified=False)
    life.save(output / 'plan.json', plan)
    print(json.dumps(dict(plan=str(output / 'plan.json'), seal=life.digest(output / 'plan.json'), pins=len(pins))))


def target_hits(single, targets, RUN):
    require(single['tests']==[str(RUN/'code.vdb')] and len(targets)==2 and
            [(t['metric'],t['point']['raw_index']) for t in targets]==[('cond',224),('line',407)],
            'Exact two source-bound singleton targets required')
    hits=[]
    for t in targets:
        row=single['metrics'][t['metric']][t['scope']]
        require((row['width'],row['checksum'])==(t['width'],t['checksum']) and t['before735'] is False,
                'Target checksum/shape/baseline differs')
        bit=bool(int(row['bits'],16)>>(row['width']-1-t['point']['raw_index'])&1)
        hits.append(dict(t,actual_single_hit=bit,DVE_native_qualified=False))
    return hits


def collect(planpath, seal, out):
    plan = life.read_bound(planpath, seal)
    RUN, RUN_SEAL = Path(plan['run']), plan['prepared_seal']
    require(plan['status'] == STATUS and plan['run'] == str(RUN) and plan['prepared_seal'] == RUN_SEAL and
        RUN.parent == life.OUT and RUN.resolve() == RUN and
        plan['prepared'] == str(RUN.with_name(RUN.name+'.prepared.json')) and
        plan['coverage_admitted'] is False and plan['simulations_started'] is False and
        plan['native_cycle_qualified'] is False and plan['expected_checks']==2130 and
        plan['exact_illegal_traps']==1 and plan['static_baseline']==735 and
        plan['preflight'] == str(PRE / 'preflight-manifest.json') and plan['preflight_seal'] == PRE_SEAL and
        plan['raw_gain_requires_latest_formal_population_at_least'] == 735, 'Plan identity differs')
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
        single_inputs=out/'target-single-inputs.txt'
        single_inputs.write_text(str(life.IMAGE)+'.vdb\n'+str(RUN/'code.vdb')+'\n')
        singleton=bitmap.collect(single_inputs)
        require(all(pins.get(path)==sha for path,sha in singleton['input_hashes'].items()),
                'Singleton reader used unpinned actual data')
        hits=target_hits(singleton,pre['targets'],RUN)
        life.check(pins)
        for name, obj in (('scalar-comparison.json', scalar), ('vector-comparison.json', vector),
                          ('observed-memory.json', memory), ('lifecycle.json', control), ('trap-proof.json', trap),
                          ('actual-target-hits.json',hits)):
            life.save(out / name, obj)
        outputs = {str(x): life.digest(x) for x in out.iterdir() if x.is_file()}
        life.save(out / 'qualification.json', dict(status='NARROW_SOURCE_GROUP_FULL_SCALAR_VECTOR_CSR_TRAP_MEMORY_NATIVE_PASS_NOT_ADMITTED',
            pins=life.merge_pins(pins, outputs), checks=p.CHECKS, illegal_traps=1, UVM_errors=0,
            OS_returncode=0, terminal_source='FOREGROUND_RUNNER_OS_RETURN_RECEIPT',
            native_known_write_bytes=1032, full_memory_bytes=2112, software_reference_is_Spike=True,
            whole_ISA_qualified=False, static_baseline=735, raw_gain_requires_latest_formal_population_at_least=735,
            coverage_admitted=False, target_hits_verified=True,
            all_primary_targets_hit=all(h['actual_single_hit'] for h in hits), raw_gain_collected=False,
            native_cycle_qualified=False, simulation_retried=False))
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'qualification.json'), coverage_admitted=False)))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='QUALIFICATION_HOLD_NOT_ADMITTED', reason=str(error), pins=pins))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'collect'))
    parser.add_argument('--output', type=Path); parser.add_argument('--plan', type=Path); parser.add_argument('--seal')
    parser.add_argument('--run', type=Path); parser.add_argument('--prepared-seal')
    a = parser.parse_args()
    if a.mode == 'prepare':
        require(a.output is not None and not a.plan and not a.seal, 'Prepare arguments')
        require(a.run is not None and a.prepared_seal, 'Run/prepared seal required')
        prepare(a.output.absolute(), a.run.absolute(), a.prepared_seal)
    else:
        require(a.plan is not None and a.seal, 'Reviewed plan/seal required')
        if a.mode == 'collect':
            require(a.output is not None, 'Fresh collection output required'); collect(a.plan.absolute(), a.seal, a.output.absolute())
        else:
            plan = life.read_bound(a.plan, a.seal); require(plan['status'] == STATUS, 'Plan status differs')
            life.check(plan['pins']); print('VERIFY_PASS NO_DUT_READ NO_SIMULATION NOT_ADMITTED')
