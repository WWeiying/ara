"""Offline strict VMACC qualification and exact773 diagnostic; no EDA/admission."""
import argparse
import json
from pathlib import Path
import shlex

import run_vmacc_c_fifo773 as runner
import collect_opivx_vsbc_strict as common
import qualify_queue_mask_source_lifetime_terminal as control
import qualify_sv39_alias770_known_tail as memory
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log, parse_contract_summary

life, require, p = runner.life, runner.require, runner.p


def terminal(run, manifest):
    state = json.loads((run / 'simulation-status.json').read_bytes())
    actual = json.loads((run / 'manifest.json').read_bytes())
    started = json.loads((run / 'started.json').read_bytes())
    require(state.get('status') == 'SIMULATION_EXITED_NOT_ADMITTED' and
            type(state.get('returncode')) is int and state['returncode'] == 0 and
            state.get('timeout') is False and state.get('case') == runner.NAME and
            state.get('coverage_admitted') is False and state.get('admission_performed') is False,
            'Not successful600s terminal')
    require(actual == dict(manifest, authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL') and
            started['command'] == manifest['command'] and started['input_elf'] == str(runner.ELF) and
            started['elf_sha256'] == runner.ELF_SHA and started['image'] == str(life.IMAGE) and
            started['image_sha256'] == runner.IMAGE_SHA and type(started['pid']) is int and
            started['pid'] > 0 and started['pid'] == started['process_group'] == state['pid'] and
            started['budget_s'] == 600 and started['foreground_lifetime'] is True, 'Run/ELF/image/PID binding')
    return state


def footprint(rows, symbols):
    source, phases = p.old.golden()
    guard = p.old.GUARD.to_bytes(8, 'little') * 2
    wanted = {}
    def region(name, data):
        wanted.update({symbols[name] + i: v for i, v in enumerate(data)})
    region('vmacc_ring_source', source)
    region('vmacc_ring_vrf', b''.join(guard + phase + guard for phase in phases))
    region('vmacc_ring_csr', b''.join(value.to_bytes(8, 'little') for vl in (1024, 1020, 1024, 4)
                                     for value in (vl, 3, 0, 0, 0)))
    required_reads = set(wanted)
    region('g75_result', (2344).to_bytes(4, 'little') + bytes(4))
    region('num_failed', bytes(4))
    region('vmacc_ring_checks', (2344).to_bytes(4, 'little'))
    observed, reads, terminals = {}, set(), []
    retired = [r for r in rows if r['event'] == 'retire']
    require(len(retired) == 36339 and [int(r['order']) for r in retired] == list(range(len(retired))),
            'Full retirement population/order')
    for r in retired:
        word = int(r['insn'], 16)
        require(not int(r['trap']) and int(r['pc'], 16) != symbols['trap_fail'], 'Unexpected trap')
        access = common.scalar_memory(word)
        rm, wm = int(r['mem_rmask'], 16), int(r['mem_wmask'], 16)
        if access is None:
            require(not rm and not wm, 'Unknown scalar memory effect')
            continue
        kind, width = access
        address = int(r['mem_addr'], 16)
        mask = ((1 << width) - 1) << (address & 7)
        require(address % width == 0 and 0x80000000 <= address and address + width <= 0x80040000 and
                rm == (mask if kind == 'read' else 0) and wm == (mask if kind == 'write' else 0),
                'Memory bounds/alignment/mask')
        value = int(r['rd_wdata'] if kind == 'read' else r['mem_wdata'], 16) & ((1 << (8 * width)) - 1)
        if kind == 'read' and any(address + i in required_reads for i in range(width)):
            require(int(r['rd']) != 0, 'Unobservable required readback')
        if kind == 'write' and address == symbols['tohost']:
            terminals.append((r, value))
        for i in range(width):
            if address + i in wanted:
                observed[address + i] = value >> (8 * i) & 255
                if kind == 'read':
                    reads.add(address + i)
    require(required_reads <= reads and observed == wanted, 'Every fullVRF/source/guard/CSR signature')
    require(terminals == [(retired[-1], 1)], 'Exactly final tohost1')
    target = [r for r in retired if int(r['pc'], 16) == symbols['vmacc_ring_op']]
    require(len(target) == 12, 'Exactly12 retired VMACC operations')
    return dict(checks=2344, failures=0, full_VRF_bytes=16384, source_guard_bytes=2080,
                CSR_values=20, full_explicit_read_bytes=len(required_reads), retired_VMACC=12)


def native(run, reference):
    result = vc.compare_vector_commits(Path(runner.preflight()['reference']), run / 'commit_trace.csv',
                                       run / 'vector_trace.csv', 0x80000000)
    for key, value in dict(status='PASS', compared_instructions=19, skipped_unknown_bytes=0,
                           non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024,
                           trapped_requests=[], first_mismatch=None, incomplete_requests=[],
                           unretired_requests=[], unobservable_instructions=0).items():
        require(result.get(key) == value, 'Full vector comparison: ' + key)
    writers = [c for c in reference if c.vector_writes]
    records = result['instructions']
    require([(int(r['pc'], 16), int(r['instruction'], 16)) for r in records] ==
            [(c.pc, c.instruction) for c in writers], 'Every vector PC/opcode identity')
    lanes, vlen, activities = vc._parse_vector_trace(run / 'vector_trace.csv')
    starts, retires, rejected = vc._parse_architecture_mapping(run / 'commit_trace.csv')
    require((lanes, vlen) == (4, 1024) and not rejected, 'Native geometry/no rejected requests')
    mapping = vc._map_spike_commits(vc._map_architecture_retires(starts, retires, rejected), reference)
    expected = {s: reference[i] for s, i in mapping.items() if reference[i].vector_writes}
    require(len(expected) == 19 and {s for s, a in activities.items() if a.writes} == set(expected),
            'Exact native writer population')
    required_total, observed_total, target_allocations = 0, 0, []
    for seq, c in expected.items():
        a = activities[seq]
        require(a.instruction == c.instruction and a.vl == c.vector_vl and a.vstart == 0 and
                a.allocations == a.completions and a.allocations > 0, 'Native complete owner/context')
        source = 4 if c.instruction & 127 == 7 else 1 if c.instruction >> 26 == 0x2d else 0
        seen = set()
        for w in a.writes:
            require(w.arch_seq == seq and w.instruction == c.instruction and w.source == source and
                    w.eew == 0 and w.be & ~w.known_be == 0 and 0 <= w.lane < 4, 'Native source/EEW/known data')
            for b in range(8):
                if w.be & (1 << b):
                    key = w.addr, w.lane, b
                    require(key not in seen, 'Duplicate native accepted byte')
                    seen.add(key)
        actual = vc._architectural_bytes(a.writes, 4, 1024)
        base = min(c.vector_writes)
        required = {(base + i // 128, i % 128) for i in range(c.vector_vl)}
        gold = {(r, b): (v >> (8 * b)) & 255 for r, v in c.vector_writes.items() for b in range(128)}
        require(required <= set(actual) <= set(gold) and
                all(value == gold[key] for key, (value, _) in actual.items()),
                'Every active byte plus any observed known preserved tail')
        required_total += len(required)
        observed_total += len(actual)
        if source == 1:
            target_allocations.append(dict(arch_seq=seq, vl=a.vl, vstart=a.vstart, eew=0, allocations=a.allocations))
    require(required_total == 18420 and len(target_allocations) == 12 and
            [r['vl'] for r in target_allocations] == [1024] * 4 + [1020] * 4 + [1024] * 4,
            'Source-derived required bytes and actual VMACC allocation sequence')
    require(result['compared_bytes'] == observed_total and all(r['status'] == 'PASS' and
            r['unknown_write_bytes'] == r['skipped_unknown_bytes'] == r['mismatch_count'] == 0 for r in records),
            'Vector observed byte accounting')
    return result, dict(required_active_bytes=required_total, observed_known_bytes=observed_total,
                        observed_preserved_tail_bytes=observed_total - required_total,
                        allocations=target_allocations, duplicate_accepted_bytes=0)


def gain(run, out, manifest):
    base = life.read_bound(p.old.BASE / 'admission-manifest.json', p.old.SEAL)
    before_path = p.old.BASE / 'combined-bits.json'
    before = life.read_bound(before_path, base['output_pins'][str(before_path)])
    ledger = (p.old.BASE / 'combined-inputs.txt').read_text().splitlines()
    require(len(ledger) == len(set(ledger)) == 774 and before['tests'] == ledger[1:] and
            str(run / 'code.vdb') not in ledger, 'Exact773 ledger/no duplicate')
    design = Path(ledger[0])
    for name, sha in before['design'].items():
        path = design / 'snps/coverage/db' / name
        require(base['input_pins'][str(path)] == sha == life.digest(path), 'Frozen compiled shape/hash')
    folder = run / 'code.vdb/snps/coverage/db/testdata' / runner.NAME
    require(list(folder.parent.iterdir()) == [folder], 'Exactly one native test')
    records = runner.toggle.xml(folder / 'siminfo.xml').findall('srctest')
    require(len(records) == 1 and shlex.split(records[0].get('cmdline', '')) == manifest['command'] and
            records[0].get('workdir') == str(run) and
            int(records[0].get('finishtime', '0')) > int(records[0].get('starttime', '0')) > 0,
            'Native actual command/cwd/completed identity')
    inputs = out / 'single-inputs.txt'
    inputs.write_text(str(design) + '\n' + str(run / 'code.vdb') + '\n')
    single = runner.bitmap.collect(inputs)
    require(single['design'] == before['design'], 'Actual candidate design compatible')
    combined = runner.bitmap.combine(before, single)
    delta = runner.bitmap.delta(before, combined)
    sample, sha = runner.toggle.rows(folder / 'tgl.verilog.data.xml', list(manifest['scoped_toggle_before']))
    scoped = runner.toggle.gains(manifest['scoped_toggle_before'],
                               runner.toggle.union(manifest['scoped_toggle_before'], sample))
    hits = [dict(scope=t['scope'], name=t['name'], serialized_position=i)
            for t in manifest['targets'] for i in t['zeros'] if i in scoped[t['scope']]]
    for name, value in (('single-bits.json', single), ('proposed-combined-bits.json', combined),
                        ('raw-delta.json', delta), ('scoped-toggle-gain.json', scoped)):
        life.save(out / name, value)
    return dict(baseline=773, four_metrics=delta['metrics'], target_hits=hits, target_hit_count=len(hits),
                target_unhit_count=144 - len(hits), scoped_toggle_new_slots=sum(map(len, scoped.values())),
                official_percentage=None, native_direction_order_claimed=False)


def collect(run, seal, out):
    require(not out.exists() and out.parent == life.OUT, 'Fresh qualification output')
    manifest = life.read_bound(run.with_name(run.name + '.prepared.json'), seal)
    require(manifest['case'] == runner.NAME and manifest['command'] == runner.command(run) and
            manifest['timeout_s'] == 600 and manifest['baseline_seal'] == p.old.SEAL, 'Prepared run binding')
    out.mkdir()
    try:
        life.check(manifest['pins'])
        terminal(run, manifest)
        pre = runner.preflight()
        reference = p.old.build.parse_spike_commits(Path(pre['reference']))
        p.vector_gold(reference)
        reference = reference[5:5 + 36339]
        rows = common.read_csv((run / 'commit_trace.csv').read_bytes(), common.COMMIT_FIELDS)
        vectors = common.read_csv((run / 'vector_trace.csv').read_bytes(), common.VECTOR_FIELDS)
        lifecycle = control.lifecycle(rows, vectors)
        signature = footprint(rows, pre['symbols'])
        log = (run / 'run.vcs.log').read_text()
        for text in (log, (run / 'console.log').read_text()):
            require(not any(token in text for token in ('Fatal:', 'Fatal-[', 'Error:', 'Error-[', 'Core Test *** FAILED')),
                    'Simulator failure diagnostic')
        require(log.count('Core Test *** SUCCESS ***') == 1 and not check_contract_log(run / 'run.vcs.log'),
                'Software SUCCESS/protocol')
        contracts = [parse_contract_summary(line.strip()) for line in log.splitlines() if '[ARA_CONTRACT]' in line]
        require(len(contracts) == 1 and contracts[0] is not None and
                contracts[0]['requests'] == contracts[0]['responses'] == lifecycle['requests'] and
                all(contracts[0][k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding', 'req_stalled', 'resp_stalled')),
                'Complete zero-error/exception protocol')
        scalar = common.spike_trace.compare_commit_prefix(Path(pre['reference']), run / 'commit_trace.csv', 0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'], rtl_exception_log=run / 'trace_hart_0.log',
            rvfi_store_data_layout='unshifted')
        expected = common.reference_counts(reference, pre['symbols'])
        require(all(scalar.get(k) == v for k, v in expected.items()) and scalar['status'] == 'TERMINAL_TOHOST_MATCH' and
                scalar['mismatch'] is None and scalar['skipped_unobservable_register_values'] == 0 and
                scalar['stopped_at_unobservable'] is None and not scalar['aligned_vector_faults'] and
                scalar['ara_trap_events'] == 0, 'Complete scalar/GPR/memory differential')
        exact_memory = memory.scalar_memory_exact(rows, reference)
        require('Exception @' not in (run / 'trace_hart_0.log').read_text(), 'Unexpected tracer exception')
        vector, native_proof = native(run, reference)
        raw_gain = gain(run, out, manifest)
        pins = dict(manifest['pins'])
        for directory in (run, out):
            pins = life.merge_pins(pins, {str(f): life.digest(f) for f in directory.rglob('*') if f.is_file()})
        life.check(pins)
        life.save(out / 'qualification.json', dict(status='VMACC_FULL_ARCHITECTURE_NATIVE_RAW773_PASS_NOT_ADMITTED',
            run=str(run), prepared_seal=seal, scalar=scalar, scalar_memory=exact_memory, vector=vector,
            native=native_proof, signature=signature, lifecycle=lifecycle, raw_gain=raw_gain,
            input_pins=pins, coverage_admitted=False, RTL_modified=False, EDA_launched=False))
        print('QUALIFIED', life.digest(out / 'qualification.json'), raw_gain, flush=True)
    except Exception as error:
        life.save(out / 'failure.json', dict(status='FAIL_OR_HOLD_NOT_ADMITTED',
            reason=type(error).__name__ + ': ' + str(error), coverage_admitted=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.run.resolve(), args.seal, args.output.resolve())
