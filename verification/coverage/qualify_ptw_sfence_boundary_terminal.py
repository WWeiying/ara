"""Terminal-only PTW scalar qualification; no simulation, raw union or admission."""
import argparse
from collections import Counter
import json
import inspect
from pathlib import Path
import re
from types import SimpleNamespace

import run_ptw_sfence_boundary_simulation as runner
import admit_gap97_offline as common
import admit_gap99_offline as zero
import check_operand_index_snapshot_offline_v2 as reset_proof
import scoped_rv64c_memory as compressed
import inventory_operand_debug as design_parser
from ara_verify import spike_trace, vector_commit, contract

life, require = runner.life, runner.require
RUN = life.OUT / 'ptw-sfence-boundary-old-image-parent-20261006-01'
RUN_SEAL = 'dab42b9f65171af71a64127d711b9f33bd3304d3ef5d25aed77ea3fdec53c943'
RUNNER_SHA = 'c9cd6cfc967fbfdcc4f7ce7b26d2b76425b4c79655be3f959332814f06254e77'
RUNNER_TEST_SHA = '8786fc821421762ec1fab60afe501f14ca870d45c77e72d0ca6c2bbcacbd4c42'
MASK64 = (1 << 64) - 1


def terminal_gate(state, started, record):
    runner.exact_fields(state, dict(status='SIMULATION_EXITED_NOT_ADMITTED', returncode=0,
        case=runner.NAME, timeout=False, coverage_admitted=False, admission_performed=False,
        dut_self_check_verified=False, terminal_oracle_verified=False), 'Failed/nonterminal simulator')
    require(type(state['wall_seconds']) in (int, float) and 0 <= state['wall_seconds'] < 360,
            'Invalid elapsed-time receipt')
    runner.exact_fields(started, dict(budget_s=300, input_elf=str(runner.ELF), elf_sha256=runner.ELF_SHA,
        image=str(life.IMAGE), image_sha256=runner.IMAGE_SHA, command=record['command'],
        foreground_lifetime=True, coverage_admitted=False), 'Startup receipt differs')
    require(type(started['pid']) is int and started['pid'] > 0 and
            started['pid'] == started['process_group'] == state['pid'], 'Process ownership differs')
    require(not Path('/proc/%d' % started['pid']).exists(), 'Simulator PID still present; HOLD')


def reference_prefix(commits, tohost):
    prefix = []
    for c in commits:
        if not prefix and c.pc != 0x80000000:
            continue
        prefix.append(c)
        if (tohost, 1) in c.memory_accesses:
            break
    require(prefix and prefix[-1].memory_accesses == ((tohost, 1),), 'Incomplete reference')
    require(not any(c.fpr_writes or c.vector_writes for c in prefix), 'Unexpected FP/vector reference')
    return prefix


def scalar_gate(result, reference):
    runner.exact_fields(result, dict(status='TERMINAL_TOHOST_MATCH', entry='0x0000000080000000',
        rvfi_store_data_layout='unshifted', matched_instructions=len(reference),
        matched_scalar_writes=sum(len({r: v for r, v in c.gpr_writes.items() if r}) for c in reference),
        matched_floating_writes=0, matched_scalar_memory_accesses=sum(
            bool(c.memory_accesses) and spike_trace._scalar_memory_access(c.instruction) is not None
            for c in reference), ara_committed_instructions=len(reference),
        ara_retired_instructions=len(reference) + 2, ara_trap_events=2,
        skipped_unobservable_register_values=0, stopped_at_unobservable=None, mismatch=None,
        terminal_ecall=None, aligned_vector_faults=[]), 'Incomplete scalar qualification')
    require(result['terminal_tohost']['address'] == '0x0000000080001000' and
            result['terminal_tohost']['write_value'] == '0x1', 'Wrong scalar terminal')


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def memory_decode(insn):
    if insn & 3 != 3:
        return compressed.decode(insn)
    opcode, funct = insn & 127, insn >> 12 & 7
    if opcode not in (3, 0x23):
        return None
    if opcode == 3:
        require(funct in (0, 1, 2, 3, 4, 5, 6), 'Unknown scalar load width')
        size = 1 << (funct & 3)
        return dict(kind='read', size=size, base=insn >> 15 & 31, register=insn >> 7 & 31,
                    offset=signed(insn >> 20, 12), signed=funct < 4)
    require(funct in (0, 1, 2, 3), 'Unknown scalar store width')
    immediate = ((insn >> 25) << 5) | (insn >> 7 & 31)
    return dict(kind='write', size=1 << funct, base=insn >> 15 & 31, register=insn >> 20 & 31,
                offset=signed(immediate, 12))


def parse_rows(path):
    hexes = {'pc', 'insn', 'rd_wdata', 'mem_addr', 'mem_rmask', 'mem_wmask', 'mem_wdata'}
    rows = [{k: v if k == 'event' else int(v, 16 if k in hexes else 10)
             for k, v in row.items()} for row in common.read_csv(path, common.COMMIT_FIELDS)]
    require(rows and all(r['event'] == 'retire' and r['trap'] in (0, 1) and
            0 <= r['rd'] < 32 and 0 <= r['insn'] <= 0xffffffff and
            0 <= r['mem_rmask'] <= 255 and 0 <= r['mem_wmask'] <= 255 for r in rows),
            'Unknown native event/mask/destination')
    require([r['order'] for r in rows] == list(range(len(rows))) and
            all(a['cycle'] <= b['cycle'] for a, b in zip(rows, rows[1:])), 'Reordered retirement')
    return rows


def architecture(rows, reference, symbols):
    require([r['order'] for r in rows] == list(range(len(rows))), 'Retirement order differs')
    require(all(r['event'] == 'retire' for r in rows), 'Unexpected backend/CVX event')
    traps = [r for r in rows if r['trap']]
    expected_pcs = [0x40000000 + (slot + 1) * 4096 + 32 for slot in (3, 35)]
    require([r['pc'] for r in traps] == expected_pcs and all(r['insn'] == 0x73 and
            r['rd'] == r['rd_wdata'] == r['mem_rmask'] == r['mem_wmask'] == 0 for r in traps),
            'Wrong precise S-ECALL trap PC/opcode/effects')
    clean = [r for r in rows if not r['trap']]
    require(len(clean) == len(reference) and len(rows) == len(reference) + 2, 'Partial scalar alignment')
    registers = {i: 0 for i in range(32)}
    counts, observed, csr_records, terminals = Counter(), [], [], []
    for row, c in zip(clean, reference):
        require(row['pc'] == c.pc and row['insn'] == c.instruction, 'PC/original opcode mismatch')
        require(not c.fpr_writes and not c.vector_writes, 'Unexpected reference destination')
        expected_gpr = {r: value for r, value in c.gpr_writes.items() if r}
        actual_gpr = {row['rd']: row['rd_wdata']} if row['rd'] else {}
        require(actual_gpr == expected_gpr, 'Scalar GPR/CSR-return mismatch')
        d = memory_decode(c.instruction)
        accesses = []
        if d is None:
            require(not c.memory_accesses and row['mem_rmask'] == row['mem_wmask'] == 0,
                    'Unknown memory instruction/effect')
        else:
            size, reg = d['size'], d['register']
            addr = (registers[d['base']] + d['offset']) & MASK64
            mask = ((1 << size) - 1) << (addr & 7)
            require(addr % size == 0 and row['mem_addr'] == addr, 'Memory address/alignment mismatch')
            if d['kind'] == 'write':
                expected = registers[reg] & ((1 << (8 * size)) - 1)
                require(c.memory_accesses == ((addr, expected),) and not expected_gpr and
                        row['mem_rmask'] == 0 and row['mem_wmask'] == mask and
                        row['mem_wdata'] & ((1 << (8 * size)) - 1) == expected,
                        'Scalar/RVC store address/mask/data mismatch')
                accesses = [(addr, expected)]
                if addr == symbols['tohost']:
                    require(size == 8, 'Partial tohost')
                    terminals.append((row['order'], expected))
            else:
                require(c.memory_accesses == ((addr, None),) and set(expected_gpr) == {reg} and
                        row['mem_rmask'] == mask and row['mem_wmask'] == 0, 'Scalar/RVC load mismatch')
                expected = expected_gpr[reg]
                signed_load = d.get('signed', True)
                low = expected & ((1 << (8 * size)) - 1)
                expected_extension = (signed(low, 8 * size) if signed_load else low) & MASK64
                require(expected == expected_extension, 'Wrong load sign/zero extension')
            counts[d['kind']] += 1
            if c.instruction & 3 != 3:
                counts['compressed_' + d['kind']] += 1
        if c.instruction & 127 == 0x73 and c.instruction >> 12 & 7:
            rs1, funct = c.instruction >> 15 & 31, c.instruction >> 12 & 7
            csr_records.append(dict(order=row['order'], pc=hex(c.pc), instruction=hex(c.instruction),
                csr=hex(c.instruction >> 20), operand=rs1 if funct >= 5 else registers[rs1],
                returns=expected_gpr, expected_from='sealed Spike prior GPRs and exact full differential'))
        observed.append(SimpleNamespace(pc=c.pc, instruction=c.instruction, vector_writes={},
            gpr_writes=actual_gpr, memory_accesses=accesses))
        registers.update(expected_gpr)
        registers[0] = 0
    require(terminals == [(len(rows) - 1, 1)], 'Duplicate/early/wrong terminal')
    gold = runner.oracle.validate(observed, symbols)
    return dict(status='PTW_SCALAR_RVC_CSR_TRAP_OUTPUT_EXACT', scalar_retirements=len(clean),
        total_retirements=len(rows), trap_rows=traps, memory_accesses=sum(counts[k] for k in ('read', 'write')),
        memory_counts=dict(counts), skipped_memory_events=0, CSR_records=csr_records, oracle=gold,
        expected_from='independent sealed Spike, frozen GPR reset, mathematical output/PTE/guard oracle')


def vector_gate(result):
    expected = dict(status='UNOBSERVABLE', vector_destination_requests=0, prefix_vector_destination_requests=0,
        compared_instructions=0, compared_bytes=0, skipped_unknown_bytes=0, non_bit_exact_instructions=0,
        unobservable_instructions=0, incomplete_requests=[], unretired_requests=[], trapped_requests=[],
        verified_zero_write_traps=[], verified_identity_write_traps=[], verified_probed_load_faults=[],
        verified_trapped_destination_requests=[], first_mismatch=None, instructions=[], stopped_at_spike_index=None)
    runner.exact_fields(result, expected, 'Not exact zero-vector UNOBSERVABLE')


def log_gate(text, require_contract=True):
    summaries = []
    require(text.count('Core Test *** SUCCESS ***') == 1 and 'Core Test *** FAILED' not in text,
            'Missing/duplicate SUCCESS or failure')
    for line in text.splitlines():
        if '[ARA_CONTRACT]' in line:
            require(line.count('[ARA_CONTRACT]') == 1, 'Duplicate contract marker')
            summary = contract.parse_contract_summary(line.strip())
            require(summary is not None and all(v == 0 for v in summary.values()), 'Nonzero/malformed zero contract')
            summaries.append(summary)
        require('[ARA_CONTRACT_ERROR]' not in line and
                not re.search(r'\b(?:Error:|Fatal:|Error-\[|Fatal-\[)', line), 'Simulator/contract diagnostic')
        if re.search(r'\b(?:UVM_ERROR|UVM_FATAL)\b', line):
            require(re.fullmatch(r'\s*(?:UVM_ERROR|UVM_FATAL)\s*:\s*0+\s*', line) is not None,
                    'UVM diagnostic/nonzero summary')
    require(len(summaries) == (1 if require_contract else 0), 'Missing/duplicate contract summary')
    return summaries[0] if summaries else {}


def collect(run, seal, out):
    require(run == RUN and seal == RUN_SEAL, 'Only exact reviewed parent run permitted')
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh agent/parent output required')
    require(life.digest(Path(runner.__file__)) == RUNNER_SHA and
            life.digest(Path(runner.__file__).with_name('test_run_ptw_sfence_boundary_simulation.py')) == RUNNER_TEST_SHA,
            'Frozen runner/test drift')
    record = life.read_bound(run.with_name(run.name + '.prepared.json'), seal)
    require(life.read_bound(run / 'manifest.json', seal) == record, 'Executed manifest differs')
    runner.verify_prepared(run, record)
    state = json.loads((run / 'simulation-status.json').read_bytes())
    started = json.loads((run / 'started.json').read_bytes())
    terminal_gate(state, started, record)
    out.mkdir()
    pins = dict(record['pins'])
    try:
        files = [run / name for name in ('manifest.json', 'simulation-status.json', 'started.json',
                 'commit_trace.csv', 'vector_trace.csv', 'run.vcs.log', 'console.log')]
        files += [run.with_name(run.name + '.prepared.json'), Path(__file__).resolve(),
                  Path(__file__).with_name('test_qualify_ptw_sfence_boundary_terminal.py'),
                  Path(inspect.getfile(design_parser.Design)).resolve()]
        for module in (common, zero, reset_proof, compressed, design_parser, spike_trace, vector_commit, contract):
            files.append(Path(module.__file__).resolve())
        vdb = run / 'code.vdb'
        members = sorted(p for p in vdb.rglob('*') if p.is_file())
        require(members and not vdb.is_symlink() and not any(p.is_symlink() for p in vdb.rglob('*')),
                'Missing/aliased VDB inventory')
        files += members
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files})
        pins, source = reset_proof.source_contract(pins)
        life.check(pins)
        pre = life.read_bound(runner.PRE / 'preflight-manifest.json', runner.PRE_SEAL)
        reference = reference_prefix(spike_trace.parse_spike_commits(Path(pre['input_spike_trace'])), pre['symbols']['tohost'])
        require(runner.reference_counts(reference, 0x80000000, pre['symbols']['tohost']) == record['scalar_reference_counts'],
                'Executed reference-count contract differs')
        scalar = spike_trace.compare_commit_prefix(Path(pre['input_spike_trace']), run / 'commit_trace.csv',
            0x80000000, terminal_tohost_address=pre['symbols']['tohost'], rvfi_store_data_layout='unshifted')
        life.save(out / 'scalar-comparison.json', scalar)
        scalar_gate(scalar, reference)
        rows = parse_rows(run / 'commit_trace.csv')
        arch = architecture(rows, reference, pre['symbols'])
        zero.vector_zero(run / 'vector_trace.csv')
        vector = vector_commit.compare_vector_commits(Path(pre['input_spike_trace']), run / 'commit_trace.csv',
                                                       run / 'vector_trace.csv', 0x80000000)
        life.save(out / 'vector-comparison.json', vector)
        vector_gate(vector)
        summary = log_gate((run / 'run.vcs.log').read_text())
        # Console and VCS logfile may both contain the same contract record.
        console = (run / 'console.log').read_text()
        log_gate(console, require_contract='[ARA_CONTRACT]' in console)
        for name, value in (('architecture-audit.json', arch), ('source-contract.json', source),
                            ('contract-audit.json', summary), ('vdb-inventory.json', {str(p): pins[str(p)] for p in members})):
            life.save(out / name, value)
        require(members == sorted(p for p in vdb.rglob('*') if p.is_file()), 'VDB inventory changed')
        life.check(pins)
        outputs = {str(p): life.digest(p) for p in out.iterdir() if p.is_file()}
        result = dict(status='PTW_FULL_SCALAR_RVC_CSR_TRAP_QUALIFIED_NOT_ADMITTED', run=str(run), run_seal=seal,
            pins=pins, output_pins=outputs, full_scalar_differential_qualified=True,
            full_scalar_memory_qualified=True, vector_status='UNOBSERVABLE_ZERO_DESTINATIONS',
            observed_gold_checks=35, expected_S_ecalls=2, coverage_admitted=False, admission_performed=False,
            target_hit_claimed=False, raw_gain_not_collected=True, raw_gain_baseline_required=738,
            particular_younger_Iwalk_attribution_proven=False, PTW_cycle_probe_enabled=False)
        life.save(out / 'qualification-seal.json', result)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'qualification-seal.json'), status=result['status'])))
    except Exception as error:
        life.save(out / 'failure.json', dict(status='QUALIFICATION_HOLD_NOT_ADMITTED',
            reason=type(error).__name__ + ': ' + str(error), coverage_admitted=False))
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, default=RUN)
    p.add_argument('--run-seal', default=RUN_SEAL)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv)
    collect(a.run.absolute(), a.run_seal, a.output.absolute())


if __name__ == '__main__':
    main()
