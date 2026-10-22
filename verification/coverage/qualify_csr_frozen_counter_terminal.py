"""Exact parent CSR terminal qualification and optional raw738 diagnostic; no admission/EDA."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import sys

import run_csr_frozen_counter_simulation as runner
import qualify_ptw_sfence_boundary_terminal as primitives
import coverage_bitmap_delta as bitmap
from ara_verify import spike_trace, vector_commit, contract

life, require = runner.life, runner.require
RUN = life.OUT / 'csr-frozen-counter-old-image-738-parent-20261007-01'
RUN_SEAL = 'dfff44ebf7f75e79dba389f4a034daca60bb650e3c810e9e92f258f5e555a95e'
RUNNER_SHA = 'e6b11a560e692aef2442cb354387a44cf1538bff6f210838dd89a04b28404cf4'
TEST_SHA = '0b7992616a3f2949cebbfebecc60b31d0d07e593caa9a40d74b7caafd44a390d'
MASK64 = (1 << 64) - 1


def terminal_gate(state, started, record):
    runner.exact_fields(state, dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0,
        case=runner.NAME, timeout=False, coverage_admitted=False, admission_performed=False,
        dut_self_check_verified=False, terminal_oracle_verified=False), 'Failed/nonterminal run')
    require(type(state['wall_seconds']) in (int, float) and 0 <= state['wall_seconds'] <= 120,
            'Bad elapsed-time receipt')
    runner.exact_fields(started, dict(budget_s=120, input_elf=str(runner.ELF), elf_sha256=runner.ELF_SHA,
        image=str(life.IMAGE), image_sha256=runner.IMAGE_SHA, command=record['command'],
        foreground_lifetime=True, coverage_admitted=False), 'Startup identity differs')
    require(type(started['pid']) is int and started['pid'] > 0 and
            type(state['pid']) is int and type(started['process_group']) is int and
            state['pid'] == started['pid'] == started['process_group'], 'Process ownership differs')
    require(not Path('/proc/%d' % started['pid']).exists(), 'Simulator PID present; HOLD')


def scalar_gate(result):
    runner.exact_fields(result, dict(status='TERMINAL_TOHOST_MATCH', entry='0x0000000080000000',
        rvfi_store_data_layout='unshifted', matched_instructions=782, matched_scalar_writes=434,
        matched_floating_writes=0, matched_scalar_memory_accesses=203,
        ara_committed_instructions=782, ara_retired_instructions=782, ara_trap_events=0,
        skipped_unobservable_register_values=0, stopped_at_unobservable=None, mismatch=None,
        terminal_ecall=None, aligned_vector_faults=[]), 'Incomplete scalar/CSR differential')
    require(result['terminal_tohost']['address'] == '0x0000000080001000' and
            result['terminal_tohost']['write_value'] == '0x1', 'Wrong scalar terminal')


def elf_file_bytes(data, address, size):
    require(data[:6] == b'\x7fELF\x02\x01', 'Not little-endian ELF64')
    offset = struct.unpack_from('<Q', data, 32)[0]
    stride, count = struct.unpack_from('<HH', data, 54)
    require(stride == 56 and offset + stride * count <= len(data), 'Malformed program headers')
    matches = []
    for i in range(count):
        kind, _, fileoff, vaddr, _, filesz, memsz, _ = struct.unpack_from('<IIQQQQQQ', data, offset + i * stride)
        if kind != 1:
            continue
        require(filesz <= memsz and fileoff + filesz <= len(data), 'Malformed PT_LOAD')
        if vaddr <= address and address + size <= vaddr + filesz:
            start = fileoff + address - vaddr
            matches.append(data[start:start + size])
    require(len(matches) == 1, 'Ambiguous/missing file-backed guard initial state')
    return matches[0]


def counter_csr_audit(commits):
    regs = {i: 0 for i in range(32)}
    values = {0x320: 0, 0xb00: None, 0xb02: None}
    cells, aliases, records = Counter(), Counter(), []
    for c in commits:
        insn = c.instruction
        addr, funct, rs, rd = insn >> 20, insn >> 12 & 7, insn >> 15 & 31, insn >> 7 & 31
        if insn & 127 == 0x73:
            require(funct in (1, 2, 3, 5, 6, 7) and addr in (0x300, 0x305, *values, 0xc00, 0xc02),
                    'Unexpected CSR/system opcode')
            operand = rs if funct >= 5 else regs[rs]
            target = addr - 0x100 if addr in (0xc00, 0xc02) else addr
            if target in values:
                before = values[target]
                writes = funct in (1, 5) or rs != 0
                if target != 0x320:
                    require(values[0x320] == 5, 'Counter observed/written outside freeze window')
                if rd:
                    require(before is not None and c.gpr_writes == {rd: before},
                            'Independent counter CSR old-value mismatch')
                    (aliases if addr != target else cells)[addr] += 1
                if addr != target:
                    require(not writes and funct == 2, 'Read-only alias modification')
                elif writes:
                    if funct in (1, 5):
                        after = operand
                    else:
                        require(before is not None, 'RMW before independent initialization')
                        after = before | operand if funct in (2, 6) else before & ~operand
                    after &= MASK64
                    if target == 0x320:
                        require(operand in (0, 2, 5), 'Unexpected inhibit mask')
                        after &= ~2
                        require(after in (0, 5), 'Unexpected running counter observation window')
                    values[target] = after
                records.append(dict(pc=hex(c.pc), insn=hex(insn), csr=hex(addr), operand=hex(operand),
                    expected_old=None if before is None else hex(before),
                    expected_new=None if values[target] is None else hex(values[target]), writes=writes))
        regs.update({r: v for r, v in c.gpr_writes.items() if r})
    require(cells == {0x320: 4, 0xb00: 16, 0xb02: 16} and aliases == {0xc00: 8, 0xc02: 8},
            'Counter CSR population differs')
    require(values == {0x320: 0, 0xb00: 0, 0xb02: 0}, 'Explicit final counter reset/inhibit differs')
    return dict(status='INDEPENDENT_FROZEN_COUNTER_CSR_STATE_EXACT', records=records,
                counter_cells=16, platform_dynamic_counter_values_compared=False,
                final_writes='MCYCLE/MINSTRET0 while frozen then inhibit0; running values never observed')


def architecture(rows, reference, symbols, guard_bytes):
    require(len(rows) == len(reference) == 782 and
            all(r['event'] == 'retire' and r['trap'] == 0 for r in rows), 'Partial/trapped/backend trace')
    require([r['order'] for r in rows] == list(range(782)), 'Retirement order differs')
    require(guard_bytes == struct.pack('<QQ', *runner.oracle.GUARDS), 'ELF independent guards differ')
    regs = {i: 0 for i in range(32)}
    observed, counts = [], Counter()
    for row, c in zip(rows, reference):
        require(c.instruction & 3 == 3 and row['pc'] == c.pc and row['insn'] == c.instruction,
                'PC/original opcode mismatch or unexpected RVC')
        require(not c.vector_writes and not c.fpr_writes, 'Unexpected reference vector/FP')
        expected_gpr = {r: v for r, v in c.gpr_writes.items() if r}
        actual_gpr = {row['rd']: row['rd_wdata']} if row['rd'] else {}
        require(actual_gpr == expected_gpr, 'Scalar GPR/CSR return mismatch')
        d = primitives.memory_decode(c.instruction)
        accesses = []
        if d is None:
            require(not c.memory_accesses and row['mem_rmask'] == row['mem_wmask'] == 0,
                    'Unknown memory effect')
        else:
            size = d['size']
            address = (regs[d['base']] + d['offset']) & MASK64
            mask = ((1 << size) - 1) << (address & 7)
            require(address % size == 0 and row['mem_addr'] == address, 'Memory address/alignment differs')
            if d['kind'] == 'write':
                value = regs[d['register']] & ((1 << (8 * size)) - 1)
                require(c.memory_accesses == ((address, value),) and not expected_gpr and
                        row['mem_rmask'] == 0 and row['mem_wmask'] == mask and
                        row['mem_wdata'] & ((1 << (8 * size)) - 1) == value, 'Store mask/data/source mismatch')
                require(address + size <= symbols['counter_guards'] or address >= symbols['counter_guards'] + 16,
                        'Guard byte modified')
                accesses = [(address, value)]
            else:
                require(c.memory_accesses == ((address, None),) and set(expected_gpr) == {d['register']} and
                        row['mem_rmask'] == mask and row['mem_wmask'] == 0, 'Load mask/destination differs')
                low = expected_gpr[d['register']] & ((1 << (8 * size)) - 1)
                extended = primitives.signed(low, 8 * size) if d['signed'] else low
                require(expected_gpr[d['register']] == extended & MASK64, 'Load sign extension differs')
            counts[d['kind']] += 1
        observed.append(primitives.SimpleNamespace(pc=c.pc, instruction=c.instruction, vector_writes={},
                        gpr_writes=actual_gpr, memory_accesses=accesses))
        regs.update(expected_gpr)
    require(sum(counts.values()) == 203, 'Incomplete scalar memory population')
    gold = runner.oracle.validate(observed, symbols)
    csr = counter_csr_audit(observed)
    return dict(status='CSR_FULL_SCALAR_MEMORY_COUNTER_GOLD_EXACT', scalar_retirements=782,
        memory_accesses=203, memory_counts=dict(counts), skipped_memory_events=0, oracle=gold,
        independent_counter_CSR=csr, guards='ELF independent initial values and no byte writes')


def baseline_gate(manifest, status, before):
    runner.exact_fields(status, dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=738,
                                   coverage_admitted=True), 'Not formal738 baseline')
    require(len(before['tests']) == len(set(before['tests'])) == 738 and
            str(RUN / 'code.vdb') not in before['tests'], 'Baseline duplicate/count differs')
    require(manifest['output_pins'] and str(runner.oracle.BASE / 'combined-bits.json') in manifest['output_pins'],
            'Baseline combined bitmap not sealed')


def raw_diagnostic(out, pins, targets):
    base = runner.oracle.BASE
    manifest_path = base / 'admission-manifest.json'
    require(str(manifest_path) in pins, 'Missing original738 admission pin')
    admission = life.read_bound(manifest_path, pins[str(manifest_path)])
    life.check(admission['output_pins'])
    pins = life.merge_pins(pins, admission['output_pins'])
    pins = life.merge_pins(pins, admission['input_pins'])
    before = json.loads((base / 'combined-bits.json').read_bytes())
    baseline_gate(admission, json.loads((base / 'status.json').read_bytes()), before)
    require(sum(len(rows) for rows in before['metrics'].values()) == 6162, 'Wrong compiled instance universe')
    life.check(pins)
    require((base / 'combined-inputs.txt').read_text().splitlines() ==
            [str(runner.oracle.BUILD / 'sim/simv.vdb'), *before['tests']], 'Baseline member order differs')
    # Raw collection is a diagnostic of an already-qualified singleton, never PASS admission.
    inputs = out / 'single-inputs.txt'
    with inputs.open('x') as stream:
        stream.write(str(runner.oracle.BUILD / 'sim/simv.vdb') + '\n' + str(RUN / 'code.vdb') + '\n')
    single = bitmap.collect(inputs)
    require(all(pins.get(p) == h for p, h in single['input_hashes'].items()), 'Singleton metric pins differ')
    require(single['design'] == before['design'], 'New image shape excluded')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    after = bitmap.combine(before, single)
    require(after['tests'] == before['tests'] + [str(RUN / 'code.vdb')] and len(set(after['tests'])) == 739,
            'Exact prefix/unique diagnostic singleton differs')
    delta = bitmap.delta(before, after)
    hits = []
    for t in targets:
        hit = dict(t)
        for name, data in (('before_hit', before), ('single_hit', single), ('union_hit', after)):
            row = data['metrics'][t['metric']][t['scope']]
            require((row['width'], row['checksum']) == (t['width'], t['checksum']), 'Target shape differs')
            hit[name] = bool(int(row['bits'], 16) & (1 << (row['width'] - 1 - t['raw_index'])))
        require(not hit['before_hit'], 'Static target no longer fresh')
        hits.append(hit)
    for name, value in (('single-bits.json', single), ('raw-delta.json', delta), ('target-hits.json', hits)):
        life.save(out / name, value)
    return pins, dict(baseline=738, full_instance_shapes_checked=sum(len(x) for x in before['metrics'].values()),
                     metrics=delta['metrics'], targets_hit=sum(h['single_hit'] for h in hits),
                     official_denominator_verified=False, diagnostic_only=True)


def collect(out, with_raw=False):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh independent output required')
    require(life.digest(Path(runner.__file__)) == RUNNER_SHA and
            life.digest(Path(runner.__file__).with_name('test_run_csr_frozen_counter_simulation.py')) == TEST_SHA,
            'Frozen runner/test drift')
    record = life.read_bound(RUN.with_name(RUN.name + '.prepared.json'), RUN_SEAL)
    require(life.read_bound(RUN / 'manifest.json', RUN_SEAL) == record, 'Executed manifest differs')
    # manifest() rederives the contract; prepare() deliberately refuses existing run directories.
    require(runner.manifest(RUN) == record, 'Reconstructed frozen execution binding differs')
    terminal_gate(json.loads((RUN / 'simulation-status.json').read_bytes()),
                  json.loads((RUN / 'started.json').read_bytes()), record)
    pins = dict(record['pins'])
    files = [RUN / name for name in ('manifest.json', 'simulation-status.json', 'started.json',
             'commit_trace.csv', 'vector_trace.csv', 'run.vcs.log', 'console.log')]
    files += [RUN.with_name(RUN.name + '.prepared.json'), Path(__file__).resolve(),
              Path(__file__).with_name('test_qualify_csr_frozen_counter_terminal.py')]
    for mod in (primitives, primitives.common, primitives.zero, primitives.reset_proof,
                primitives.compressed, primitives.design_parser, bitmap, spike_trace, vector_commit, contract):
        files.append(Path(mod.__file__).resolve())
    # Bind the actual transitive local Python implementation used by the replay.
    for mod in tuple(sys.modules.values()):
        name = getattr(mod, '__file__', None)
        if name and name.endswith('.py'):
            path = Path(name).resolve()
            if path.is_relative_to(life.ROOT / 'verification'):
                files.append(path)
    vdb = RUN / 'code.vdb'
    members = sorted(p for p in vdb.rglob('*') if p.is_file())
    require(members and not vdb.is_symlink() and not any(p.is_symlink() for p in vdb.rglob('*')), 'Aliased/missing VDB')
    files += members
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files})
    pins, source = primitives.reset_proof.source_contract(pins)
    life.check(pins)
    out.mkdir()
    try:
        pre = life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL)
        commits = spike_trace.parse_spike_commits(runner.PRE / 'spike.trace')
        reference = primitives.reference_prefix(commits, pre['symbols']['tohost'])
        require(runner.reference_counts(reference, 0x80000000, pre['symbols']['tohost']) == record['scalar_reference_counts'],
                'Reference prefix differs')
        scalar = spike_trace.compare_commit_prefix(runner.PRE / 'spike.trace', RUN / 'commit_trace.csv',
                   0x80000000, terminal_tohost_address=pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
        life.save(out / 'scalar-comparison.json', scalar)
        scalar_gate(scalar)
        rows = primitives.parse_rows(RUN / 'commit_trace.csv')
        arch = architecture(rows, reference, pre['symbols'],
                            elf_file_bytes(runner.ELF.read_bytes(), pre['symbols']['counter_guards'], 16))
        primitives.zero.vector_zero(RUN / 'vector_trace.csv')
        vector = vector_commit.compare_vector_commits(runner.PRE / 'spike.trace', RUN / 'commit_trace.csv',
                                                       RUN / 'vector_trace.csv', 0x80000000)
        life.save(out / 'vector-comparison.json', vector)
        primitives.vector_gate(vector)
        summary = primitives.log_gate((RUN / 'run.vcs.log').read_text())
        console = (RUN / 'console.log').read_text()
        primitives.log_gate(console, require_contract='[ARA_CONTRACT]' in console)
        for name, value in (('architecture-audit.json', arch), ('source-contract.json', source),
                            ('contract-audit.json', summary), ('vdb-inventory.json', {str(p): pins[str(p)] for p in members})):
            life.save(out / name, value)
        raw = None
        if with_raw:
            pins, raw = raw_diagnostic(out, pins, record['targets'])
        require(members == sorted(p for p in vdb.rglob('*') if p.is_file()), 'VDB membership changed')
        life.check(pins)
        outputs = {str(p): life.digest(p) for p in out.iterdir() if p.is_file()}
        result = dict(status='CSR_FULL_SCALAR_COUNTER_ORACLE_QUALIFIED_NOT_ADMITTED', run=str(RUN), run_seal=RUN_SEAL,
            pins=pins, output_pins=outputs, full_scalar_differential_qualified=True,
            full_scalar_memory_qualified=True, independent_counter_CSR_qualified=True,
            checks=54, observed_bytes=416, vector_status='UNOBSERVABLE_ZERO_DESTINATIONS',
            raw_diagnostic=raw, raw_baseline=738, coverage_admitted=False, admission_performed=False,
            simulations_started=False, rtl_changed=False, official_denominator_verified=False)
        life.save(out / 'qualification-seal.json', result)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'qualification-seal.json'),
                              status=result['status'], raw=raw)))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='QUALIFICATION_HOLD_NOT_ADMITTED',
                  reason=type(error).__name__ + ': ' + str(error), coverage_admitted=False))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--with-raw', action='store_true')
    a = p.parse_args()
    collect(a.output.absolute(), a.with_raw)


if __name__ == '__main__':
    main()
