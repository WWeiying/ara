"""Offline exact scalar, memory, native VRF and raw matrix qualification; no admit."""
import argparse
import json
from pathlib import Path
from types import ModuleType
import run_fclass_divsqrt783 as runner
import collect_c910_float_edge_initialized777 as reused

life, require, p = runner.life, runner.require, runner.p
common, control, memory, vc = reused.common, reused.control, reused.memory, reused.vc


def terminal(run, manifest):
    state = json.loads((run / 'simulation-status.json').read_bytes())
    actual = json.loads((run / 'manifest.json').read_bytes())
    started = json.loads((run / 'started.json').read_bytes())
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and type(state.get('returncode')) is int
        and state['returncode'] == 0 and type(state.get('timeout')) is bool and state['timeout'] is False
        and state.get('case') == runner.NAME and state.get('coverage_admitted') is False
        and state.get('admission_performed') is False, 'Strict actual successful terminal')
    require(actual == dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
        and started['command'] == manifest['command'] and started['input_elf'] == str(runner.ELF)
        and started['elf_sha256'] == runner.ELF_SHA and started['image'] == str(life.IMAGE)
        and started['image_sha256'] == runner.IMAGE_SHA and type(started['pid']) is int and started['pid'] > 0
        and type(started['budget_s']) is int and started['budget_s'] == runner.BUDGET
        and started['pid'] == started['process_group'] == state['pid']
        and started['foreground_lifetime'] is True and type(state['wall_seconds']) in (int, float)
        and 0 <= state['wall_seconds'] <= runner.BUDGET + 30, 'Exact execution identity and 900s budget')
    return state


def reference_prefix(pre):
    commits = p.build.parse_spike_commits(Path(pre['reference']))
    start = next(i for i, c in enumerate(commits) if c.pc == 0x80000000)
    reference = commits[start:start + runner.INSTRUCTIONS]
    require(start == 5 and len(reference) == runner.INSTRUCTIONS and
        reference[-1].memory_accesses == ((pre['symbols']['tohost'], 1),), 'Complete reference boundary')
    require(p.validate(Path(pre['reference']), pre['symbols']) ==
        {k: v for k, v in pre['counts'].items() if k != 'runtime'}, 'Sealed independent gold replay')
    return reference


def expected_footprint(symbols, saved_fcsr):
    wanted = {}
    def region(name, data):
        wanted.update({symbols[name] + i: v for i, v in enumerate(data)})
    guard = p.GUARD.to_bytes(8, 'little') * 2
    for name, index in (('matrix_a', 0), ('matrix_b', 1), ('matrix_dst', 2)):
        region(name, b''.join(guard + p.images(16 << (cell // 25), cell % 25)[index] + guard for cell in range(75)))
    ledger = []
    for cell in range(75):
        w, phase = 16 << (cell // 25), cell % 25
        rm = p.inputs(w, phase, 0)[1]; flags = p.images(w, phase)[3]
        ledger.extend((256 // w, 256 // w, 11 + (cell // 25) * 8, 0, 0, rm * 32 + flags))
    region('matrix_ledger', b''.join(v.to_bytes(8, 'little') for v in ledger))
    required_reads = set(wanted)
    region('matrix_fcsr_restore', saved_fcsr.to_bytes(8, 'little') * 2)
    region('g75_result', (2251).to_bytes(4, 'little') + bytes(4))
    region('num_failed', bytes(4)); region('matrix_checks', (2251).to_bytes(4, 'little'))
    return wanted, required_reads


def footprint(rows, symbols, reference):
    saved = [c for c in reference if c.instruction & 127 == 0x73 and c.instruction >> 20 == 3
        and c.instruction >> 12 & 7 == 2 and c.instruction >> 15 & 31 == 0]
    require(saved and len(saved[0].gpr_writes) == 1, 'Initial FCSR owner')
    wanted, required_reads = expected_footprint(symbols, next(iter(saved[0].gpr_writes.values())))
    observed, reads, terminals = {}, set(), []
    retired = [r for r in rows if r['event'] == 'retire']
    require(len(retired) == len(reference) == runner.INSTRUCTIONS and
        [int(r['order']) for r in retired] == list(range(runner.INSTRUCTIONS)), 'Complete ordered retirement stream')
    for row, c in zip(retired, reference):
        insn = int(row['insn'], 16)
        require((int(row['pc'], 16), insn) == (c.pc, c.instruction) and not int(row['trap'])
            and c.pc != symbols['trap_fail'], 'Exact retirement PC/opcode/no trap')
        rm, wm = int(row['mem_rmask'], 16), int(row['mem_wmask'], 16)
        access = common.scalar_memory(insn)
        if access is None:
            require(not rm and not wm, 'Unknown scalar memory effect'); continue
        kind, width = access; address = int(row['mem_addr'], 16); mask = ((1 << width) - 1) << (address & 7)
        require(address % width == 0 and 0x80000000 <= address and address + width <= 0x80040000
            and rm == (mask if kind == 'read' else 0) and wm == (mask if kind == 'write' else 0), 'Memory bounds/byte masks')
        value = int(row['rd_wdata'] if kind == 'read' else row['mem_wdata'], 16) & ((1 << (width * 8)) - 1)
        if kind == 'read' and any(address + i in required_reads for i in range(width)):
            require(int(row['rd']) != 0, 'Required unobservable read')
        if kind == 'write' and address == symbols['tohost']: terminals.append((row, value))
        for i in range(width):
            if address + i in wanted:
                observed[address + i] = value >> (8 * i) & 255
                if kind == 'read': reads.add(address + i)
    require(required_reads <= reads and observed == wanted and terminals == [(retired[-1], 1)], 'All gold/CSR/guard bytes and unique tohost1')
    return dict(checks=2251, cases=75, failures=0, required_read_bytes=len(required_reads), CSR_values=452)


def native_state(reference, activities, mapping, symbols):
    require(all(seq in mapping for seq in activities), 'Unmapped native activity')
    roles = {symbols['matrix_' + op + str(w)]: (op, w) for w in (16, 32, 64)
        for op in ('load_a', 'load_b', 'class', 'div', 'sqrt', 'store')}
    init = {symbols['matrix_initial_v' + str(v)]: v for v in (8, 16, 24)}
    counts = dict(load_a=0, load_b=0, store=0, arithmetic=0); initialized = []; writers = []
    for seq, index in sorted(mapping.items()):
        c = reference[index]; a = activities.get(seq); role = roles.get(c.pc)
        if c.pc in init:
            reg = init[c.pc]
            require(a is not None and a.instruction == c.instruction and a.allocations > 0
                and a.allocations == a.completions and a.use_vd and a.vd == reg
                and a.eew == 0 and a.vl == 1024 and a.vstart == 0, 'Native initialization owner/context')
            expected = {(r, b): 0 for r in range(reg, reg + 8) for b in range(128)}
            check_writes(a, c, expected, 0, 0, seq); initialized.append(reg); continue
        if role is None:
            require(not c.vector_writes and (a is None or not a.writes), 'Unexpected/config VRF writer'); continue
        op, w = role; counter = op if op in counts else 'arithmetic'; cell = counts[counter]; counts[counter] += 1
        require(cell < 75 and w == 16 << (cell // 25) and a is not None and a.instruction == c.instruction
            and a.allocations > 0 and a.allocations == a.completions and a.vl == 256 // w
            and a.vstart == 0 and a.eew == {16: 1, 32: 2, 64: 3}[w], 'Native phase/context/lifecycle')
        if op == 'store':
            require(not a.use_vd and not a.writes and not c.vector_writes, 'Store must not write VRF'); continue
        image_index = {'load_a': 0, 'load_b': 1}.get(op, 2); reg = (8, 16, 24)[image_index]
        if counter == 'arithmetic': require(op == p.inputs(w, cell % 25, 0)[0], 'Exact arithmetic phase role')
        image = p.images(w, cell % 25)[image_index]
        require(a.use_vd and a.vd == reg and c.vector_writes == {reg: int.from_bytes(image, 'little')}, 'Independent active+tail reference')
        expected = {(reg, b): v for b, v in enumerate(image)}
        check_writes(a, c, expected, 4 if image_index < 2 else 1, a.eew, seq)
        writers.append(dict(arch_seq=seq, pc=c.pc, opcode=c.instruction, role=op, cell=cell, compared_bytes=32))
    require(initialized == [8, 16, 24] and set(counts.values()) == {75} and len(writers) == 225, 'All initialized groups and all300 operations')
    return dict(initialization_bytes=3072, active_bytes=7200, writers=writers, operations=counts, skip=0)


def check_writes(a, c, expected, source, eew, seq):
    writes = [w for w in a.writes if w.source == source]; seen = set()
    require(writes and all(w.source in (source, 3) for w in a.writes), 'Missing/unknown primary writer')
    for w in writes:
        require(w.arch_seq == seq and w.instruction == c.instruction and w.eew == eew
            and 0 <= w.lane < 4 and 0 < w.be <= 255 and not w.be & ~w.known_be, 'Accepted primary owner/BE/known bytes')
        for b in range(8):
            if w.be & (1 << b):
                key = w.addr, w.lane, b
                require(key not in seen, 'Duplicate primary byte'); seen.add(key)
    actual = vc._architectural_bytes(writes, 4, 1024)
    require(set(actual) == set(expected) and all(actual[k][0] == v for k, v in expected.items()), 'Exact native gold byte set')


def vector_gate(result):
    require(result['status'] == 'PASS' and result['first_mismatch'] is None and result['stopped_at_spike_index'] is None
        and result['vector_destination_requests'] == result['prefix_vector_destination_requests'] == result['compared_instructions'] == 228
        and result['compared_bytes'] >= 10272
        and all(type(result[k]) is int and result[k] == 0 for k in
            ('skipped_unknown_bytes', 'non_bit_exact_instructions', 'unobservable_instructions'))
        and not result['incomplete_requests'] and not result['unretired_requests'] and not result['trapped_requests']
        and all(r['unknown_write_bytes'] == r['skipped_unknown_bytes'] == r['mismatch_count'] == 0 for r in result['instructions']), 'Complete vector differential, no unknown/prefix/partial')


def gain(run, out, manifest):
    base, before, ledger = runner.baseline(); folder = run / 'code.vdb/snps/coverage/db/testdata' / runner.NAME
    require(list(folder.parent.iterdir()) == [folder] and str(run / 'code.vdb') not in ledger, 'Unique candidate VDB')
    metadata = reused.coverage_identity(folder, run, manifest, Path(ledger[0]))
    inputs = out / 'single-inputs.txt'; inputs.write_text(ledger[0] + '\n' + str(run / 'code.vdb') + '\n')
    single = runner.template.inherited.bitmap.collect(inputs)
    require(single['design'] == before['design'], 'Exact native design identity')
    # No population admission or full merged VDB is created.
    targets_path = runner.PRE.parent / 'dynamic-targets783.json'
    targets = life.read_bound(targets_path, runner.preflight()['input_pins'][str(targets_path)])
    require(targets['population'] == 783 and targets['baseline_seal'] == runner.BASE_SHA
        and targets['target_missing_slots'] == sum(len(t['missing_coordinates']) for t in targets['targets']) == 236
        and targets['class_padding_excluded_from_targets'] is True, 'Exact dynamic-only target inventory')
    scopes = sorted({t['scope'] for t in targets['targets']})
    sample, sha = runner.template.inherited.toggle.rows(folder / 'tgl.verilog.data.xml', scopes)
    hits = []
    for t in targets['targets']:
        row = sample[t['scope']]
        require(row['checksum'] == t['checksum'] and max(t['missing_coordinates']) < row['width'], 'Exact target native shape')
        hit = [i for i in t['missing_coordinates'] if int(row['bits'], 16) >> (row['width'] - 1 - i) & 1]
        hits.append(dict(scope=t['scope'], signal=t['signal'], checksum=t['checksum'], positions=hit))
    combined = runner.template.inherited.bitmap.combine(before, single)
    delta = runner.template.inherited.bitmap.delta(before, combined)
    life.save(out / 'single-bits.json', single); life.save(out / 'raw-delta783.json', delta)
    return dict(baseline=783, targets=hits, target_new_slots=sum(len(x['positions']) for x in hits),
        target_capacity=236, four_metrics=delta['metrics'], official_percentage=None,
        serialized_direction_labels_bound=False, coverage_admitted=False), metadata


def collect(run, seal, out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent offline output')
    manifest = life.read_bound(run.with_name(run.name + '.prepared.json'), seal)
    require(manifest == runner.prepare(run, existing=True), 'Executed runner contract/pins differ')
    terminal(run, manifest); pre = runner.preflight(); reference = reference_prefix(pre)
    pins = reused.inherited.evidence_pins(run, seal, manifest)
    modules, seen = [reused, common, control, memory, vc], set()
    while modules:
        module = modules.pop()
        if id(module) in seen: continue
        seen.add(id(module)); file = getattr(module, '__file__', None)
        if file:
            path = Path(file).resolve()
            if path.suffix == '.py' and life.ROOT / 'verification' in path.parents:
                pins[str(path)] = life.digest(path)
                modules.extend(v for v in vars(module).values() if isinstance(v, ModuleType))
    for path in (Path(__file__), Path(__file__).with_name('test_collect_fclass_divsqrt783.py'),
        Path(reused.__file__), Path(common.__file__), Path(control.__file__), Path(memory.__file__), Path(vc.__file__)):
        pins[str(path.resolve())] = life.digest(path)
    life.check(pins); out.mkdir()
    try:
        rows = common.read_csv((run / 'commit_trace.csv').read_bytes(), common.COMMIT_FIELDS)
        vector_rows = common.read_csv((run / 'vector_trace.csv').read_bytes(), common.VECTOR_FIELDS)
        lifecycle = control.lifecycle(rows, vector_rows); reused.inherited.logs(run, lifecycle)
        scalar = common.spike_trace.compare_commit_prefix(Path(pre['reference']), run / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'], rtl_exception_log=run / 'trace_hart_0.log', rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar, common.reference_counts(reference, pre['symbols']))
        mem = memory.scalar_memory_exact(rows, reference)
        require(mem['scalar_memory_accesses'] == 30460, 'All compressed and uncompressed memory events')
        sig = footprint(rows, pre['symbols'], reference)
        lanes, vlen, activities = vc._parse_vector_trace(run / 'vector_trace.csv')
        activities = reused.store_adapter.restore_stores(activities, vector_rows)
        starts, retires, rejected = vc._parse_architecture_mapping(run / 'commit_trace.csv')
        require((lanes, vlen) == (4, 1024) and not rejected, 'Geometry/no trapped native requests')
        mapping = vc._map_spike_commits(vc._map_architecture_retires(starts, retires, rejected), reference)
        native = native_state(reference, activities, mapping, pre['symbols'])
        diff = vc.compare_vector_commits(Path(pre['reference']), run / 'commit_trace.csv', run / 'vector_trace.csv', 0x80000000)
        vector_gate(diff); raw, raw_pins = gain(run, out, manifest)
        pins = life.merge_pins(pins, raw_pins)
        pins = life.merge_pins(pins, {str(f): life.digest(f) for f in out.iterdir() if f.is_file()}); life.check(pins)
        result = dict(status='FCLASS_DIVSQRT783_FULL_ARCHITECTURE_NATIVE_RAW_QUALIFIED_NOT_ADMITTED',
            run=str(run), prepared_seal=seal, terminal=terminal(run, manifest), scalar=scalar, scalar_memory=mem,
            signature=sig, native=native, vector=diff, lifecycle=lifecycle, raw_gain=raw,
            input_pins=pins, coverage_admitted=False, RTL_modified=False, EDA_launched=False)
        life.save(out / 'qualification.json', result); print('QUALIFIED_NOT_ADMITTED', life.digest(out / 'qualification.json'), flush=True)
    except Exception as error:
        life.save(out / 'failure.json', dict(status='FAIL_OR_HOLD_NOT_ADMITTED', reason=str(error), no_retry=True)); raise


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__); cli.add_argument('--run', type=Path, required=True)
    cli.add_argument('--seal', required=True); cli.add_argument('--output', type=Path, required=True)
    a = cli.parse_args(); collect(a.run.resolve(), a.seal, a.output.resolve())
