#!/usr/bin/env python3
"""Read-only functional audit of the original known-old mask restart ELF.

The campaign runner owns image/source pins, subprocess exit and timeout checks.
This helper checks completed functional evidence, not image provenance or VDB
compatibility. It never invokes the frozen runner, admits coverage, or launches
EDA. Reuse the sealed ELF; recompiling it requires a new reference contract.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import collect_mask_compare_restart_known786 as frozen


def native_state(reference, activities, mapping, symbols, rows):
    """Frozen byte/state oracle with the corrected ALU producer ID (0, not 1).

    Kept here because the sealed checker must not be changed. Source IDs are
    assigned in operand_requester.sv: ALU=0, MFPU=1, MASKU=2, SLDU=3, LDU=4.
    Every other postimage/context/policy check is retained from native_state.
    """
    require, vc, p = frozen.require, frozen.vc, frozen.p
    state, records, counts, compare_case = {}, [], Counter(), 0
    require(all(s in mapping for s in activities), 'Unmapped native activity')
    writer_names = ('mc_init_a', 'mc_init_b', 'mc_clear24', 'mc_load2',
                    'mc_clear1', 'mc_compare', 'mc_xor')
    store_names = ('mc_mask_store', 'mc_a_read', 'mc_b_read', 'mc_x_read', 'mc_v2_read')
    for seq, index in sorted(mapping.items()):
        c, a = reference[index], activities.get(seq)
        name = next((n for n in writer_names + store_names if c.pc == symbols[n]), None)
        if a is None:
            require(name is None and not c.vector_writes, 'Missing backend writer/store')
            continue
        require(a.instruction == c.instruction and a.allocations == a.completions and
                a.allocations > 0, 'Native opcode/lifecycle')
        for w in a.writes:
            require(w.arch_seq == seq and w.instruction == c.instruction and
                    0 <= w.lane < 4 and 0 <= w.eew <= 3 and 0 < w.be < 256 and
                    w.be & ~w.known_be == 0, 'Unique owner/known accepted native bytes')
        actual = vc._architectural_bytes(a.writes, 4, 1024)
        if name in store_names:
            frozen.request_context(rows, seq, c.instruction,
                                   8 if name == 'mc_mask_store' else 128, 0, 0, False)
            require(not c.vector_writes and not a.use_vd, 'Store not an architectural writer')
            if actual:
                require(all(w.source == 3 for w in a.writes), 'Only identity transport on store')
                for w in a.writes:
                    individual = vc._architectural_bytes([w], 4, 1024)
                    require(all(reg in state and v == (state[reg] >> (8*b) & 255)
                                for (reg, b), (v, _) in individual.items()),
                            'Store identity transport changed native prestate')
            counts[name] += 1
        elif c.vector_writes:
            require(name in writer_names and actual, 'Classified writer with accepted bytes')
            compare = name == 'mc_compare'
            start = p.STARTS[compare_case] if compare else 0
            vl = 64 if name in ('mc_compare', 'mc_xor') else 128
            vd = next(iter(c.vector_writes))
            frozen.request_context(rows, seq, c.instruction, vl, start, vd, True)
            require(a.vl == vl and a.vstart == start and a.eew == 0 and
                    a.vd == vd and a.use_vd, 'Native writer context')
            source_id = 4 if name in ('mc_init_a', 'mc_init_b', 'mc_load2', 'mc_clear1') else 2 if compare else 0
            require(all(w.source == source_id for w in a.writes), 'Exact writer producer')
            if compare:
                require(vd == 1 and c.instruction >> 26 == 26 and
                        c.instruction >> 12 & 7 == 0 and c.instruction >> 20 & 31 == 8 and
                        c.instruction >> 15 & 31 == 16 and c.instruction >> 25 & 1 == 1,
                        'Exact unmasked VMSLTU.vv identity')
                require(state.get(1) == int.from_bytes(p.old_bytes(0), 'little') and
                        state.get(2) == int.from_bytes(p.old_bytes(1), 'little') and
                        all(reg == 1 and 0 <= b < 128 for reg, b in actual),
                        'Known v1/v2 prestate/exact vd')
                require({(1, b) for b in range(start//8, 8)} <= set(actual),
                        'Every active mask byte has actual accepted native write')
                after = state[1]
                for (reg, b), (value, _) in actual.items():
                    after = (after & ~(255 << (8*b))) | (value << (8*b))
                proof = frozen.mask_postimage(state[1], after, start)
                state[1] = after
                compare_case += 1
            else:
                gold = {(reg, b): (value >> (8*b)) & 255
                        for reg, value in c.vector_writes.items() for b in range(128)}
                if name == 'mc_xor':
                    require(24 in state, 'Proven initial complete xor destination')
                    require(all(reg == 24 and b < 64 for reg, b in actual), 'Only defined active xor bytes')
                    require(set(actual) == {(24, b) for b in range(64)}, 'All active xor bytes present')
                    require(all(value == gold[k] for k, (value, _) in actual.items()), 'Strict xor defined bytes')
                    for (reg, b), (value, _) in actual.items():
                        state[reg] = (state[reg] & ~(255 << (8*b))) | (value << (8*b))
                    require(state[24] == c.vector_writes[24], 'Full known TU xor postimage')
                else:
                    require({k: v for k, (v, _) in actual.items()} == gold, 'Strict full load/clear image')
                    state.update(c.vector_writes)
                proof = dict(strict_postimage=True)
            counts[name] += 1
            records.append(dict(arch_seq=seq, pc=c.pc, opcode=c.instruction, kind=name, proof=proof))
        else:
            require(not actual, 'Unclassified native VRF writer')
    require(counts == Counter(mc_init_a=1, mc_init_b=1, mc_clear24=1, mc_load2=1,
                             mc_clear1=3, mc_compare=3, mc_xor=3, mc_mask_store=3,
                             mc_a_read=3, mc_b_read=3, mc_x_read=3, mc_v2_read=3),
            'Complete exact writer/store population')
    require(state.get(2) == int.from_bytes(p.old_bytes(1), 'little'), 'Native adjacent v2 remained unchanged')
    return dict(status='FULL_DEFINED_AND_LEGAL_MASK_POSTIMAGE_NATIVE_PASS', counts=dict(counts),
                primary_writers=13, defined_mask_bits=192, mask_tail_bits_checked=2880,
                unknown_active_bytes_skipped=0, whole_destination_skipped=False, instructions=records)


def native(directory, reference, symbols):
    vc, require = frozen.vc, frozen.require
    lanes, vlen, activities = vc._parse_vector_trace(directory / 'vector_trace.csv')
    starts, retires, rejected = vc._parse_architecture_mapping(directory / 'commit_trace.csv')
    require((lanes, vlen) == (4, 1024) and not rejected, 'Geometry/no rejected requests')
    arch = vc._map_architecture_retires(starts, retires, rejected)
    mapping = vc._map_spike_commits(arch, reference)
    require(all(arch[s].pc == reference[i].pc and arch[s].instruction == reference[i].instruction
                for s, i in mapping.items()), 'Exact PC/opcode/arch_seq mapping')
    rows = frozen.common.read_csv((directory / 'vector_trace.csv').read_bytes(), frozen.common.VECTOR_FIELDS)
    return native_state(reference, activities, mapping, symbols, rows)


def reference_contract():
    """Bind the frozen software oracle, not the unrelated old RTL/VDB pins."""
    runner, life, require = frozen.runner, frozen.life, frozen.require
    pre = life.read_bound(runner.PRE, runner.PRE_SHA)
    require(pre['status'] == 'MASK_COMPARE_RESTART_HOST_SPIKE_PASS_NOT_DUT' and
            pre['ELF'] == str(runner.ELF) and
            Path(pre['reference']) == runner.PRE.parent / 'spike.trace' and
            pre['counts']['checks'] == 2705 and pre['counts']['cases'] == 3 and
            pre['counts']['explicit_VRF_writers'] == 13 and
            pre['counts']['defined_mask_bits'] == 192 and
            pre['counts']['unknown_active_bits_skipped'] == 0 and
            pre['counts']['runtime']['entry_to_tohost_instructions'] == 58822 and
            pre['counts']['runtime']['all_runtime_memory_widths_decoded'] is True,
            'Exact original software reference contract')
    files = [runner.ELF, Path(pre['reference']), frozen.p.APP,
             Path(frozen.p.__file__).resolve(), Path(frozen.p.old.__file__).resolve(),
             Path(frozen.p.old.mature.old.rvc.__file__).resolve()]
    files += [runner.PRE.parent / name for name in (
        'spike-command.json', 'spike-terminal.json', 'compile-command.json',
        'disassembly.txt', 'build.log')]
    require(all(str(path) in pre['input_pins'] for path in files),
            'Every software oracle input must have its original seal')
    pins = {str(path): pre['input_pins'][str(path)] for path in files}
    pins[str(runner.PRE)] = runner.PRE_SHA
    require(pins[str(runner.ELF)] == runner.ELF_SHA, 'Original ELF identity')
    life.check(pins)
    return pre, pins


def audit(directory):
    """Return strict functional evidence or raise on missing/incorrect evidence.

    Required files are commit_trace.csv, vector_trace.csv, run.vcs.log,
    console.log and trace_hart_0.log. A local input.elf, when supplied by the
    campaign, must match the original sealed ELF. No files are modified.
    """
    directory = Path(directory).resolve(strict=True)
    require, life, common = frozen.require, frozen.life, frozen.common
    require(directory.is_dir(), 'Expected completed case directory')
    required = [directory / name for name in (
        'commit_trace.csv', 'vector_trace.csv', 'run.vcs.log',
        'console.log', 'trace_hart_0.log')]
    require(all(path.is_file() and path.stat().st_size > 0 for path in required),
            'Missing or empty completed functional evidence')
    pre, pins = reference_contract()
    modules = (frozen, frozen.mature, common, frozen.control, frozen.memory,
               frozen.vc, common.spike_trace)
    files = required + [Path(__file__).resolve()]
    files += [Path(module.__file__).resolve() for module in modules]
    local_elf = directory / 'input.elf'
    if local_elf.exists():
        require(life.digest(local_elf) == frozen.runner.ELF_SHA,
                'Local ELF differs from sealed restart reproducer')
        files.append(local_elf)
    pins = life.merge_pins(pins, {str(path): life.digest(path) for path in files})
    life.check(pins)

    reference = frozen.reference_prefix(pre)
    rows = common.read_csv((directory / 'commit_trace.csv').read_bytes(),
                           common.COMMIT_FIELDS)
    vectors = common.read_csv((directory / 'vector_trace.csv').read_bytes(),
                              common.VECTOR_FIELDS)
    lifecycle = frozen.control.lifecycle(rows, vectors)
    frozen.mature.logs(directory, lifecycle)
    scalar = common.spike_trace.compare_commit_prefix(
        Path(pre['reference']), directory / 'commit_trace.csv', 0x80000000,
        terminal_tohost_address=pre['symbols']['tohost'],
        rtl_exception_log=directory / 'trace_hart_0.log',
        rvfi_store_data_layout='unshifted')
    common.scalar_exact(scalar, common.reference_counts(reference, pre['symbols']))
    signature = frozen.footprint(rows, pre['symbols'])
    memory = frozen.memory.scalar_memory_exact(rows, reference)
    native_proof = native(directory, reference, pre['symbols'])
    life.check(pins)
    return dict(
        status='PASS', scope='original mask restart ELF: strict functional evidence',
        directory=str(directory), elf_sha256=frozen.runner.ELF_SHA,
        scalar=scalar, scalar_memory=memory, signature=signature,
        native=native_proof, lifecycle=lifecycle, input_pins=pins,
        image_provenance_verified=False, process_exit_verified=False,
        campaign_terminal_and_image_checks_required=True,
        coverage_admitted=False, coverage_merged=False, EDA_launched=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path,
                        help='Optional new JSON file; never overwrite existing evidence')
    args = parser.parse_args()
    result = audit(args.directory)
    text = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output is None:
        print(text, end='')
    else:
        with args.output.open('x') as stream:
            stream.write(text)


if __name__ == '__main__':
    main()
