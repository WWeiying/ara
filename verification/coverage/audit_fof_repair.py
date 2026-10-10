"""Read-only acceptance of the original Sv39 FOF ELF on a new source image.

audit(directory) needs commit_trace.csv, vector_trace.csv, trace_hart_0.log,
console.log and run.vcs.log. An optional input.elf must match ORIGINAL_ELF.
The campaign owns new image/source/config provenance and process exit checks.
This module neither checks historical RTL pins nor launches tools or admits VDBs.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import gap112_sv39_fof as oracle
import qualify_queue_mask_source_lifetime_terminal as control
from qualify_store_fault_flush_terminal import elf_instruction
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log, parse_contract_summary
from ara_verify.trace import is_vector_instruction

life, require, common = oracle.life, oracle.require, oracle.prior.strict
ROOT = Path(__file__).resolve().parents[2]
PRE = ROOT / 'verification/out/gap112-sv39-fof-preflight-740-agent-20261007-01'
ORIGINAL_ELF = PRE / 'input.elf'
ELF_SHA = '61a11149018eb03eeb3b0ab4fbe6428d1dc557f1aef43437cd528400ab14eeba'
PRE_SHA = '44e370f3b6996bf433c725594d5f1eee543cf62c3ed7e5ba575c4a432600e7b9'
CASE = oracle.NAME
FOF, DIV, RECOVERY, MASK = 0x0103e407, 0x838eec57, 0x0203e607, 0x7e002057


def simulation_command(image, directory):
    """Return original reproducer arguments only; do not execute anything."""
    directory = Path(directory).resolve()
    return [str(Path(image).resolve()), '-l', 'run.vcs.log', '+NO_FSDB',
            '+ntb_random_seed=1', '+PRELOAD=' + str(ORIGINAL_ELF),
            '+TESTCASE=' + CASE, '+COMMIT_TOHOST=80001000',
            '+COMMIT_TRACE=' + str(directory / 'commit_trace.csv'),
            '+VECTOR_TRACE=' + str(directory / 'vector_trace.csv'),
            '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(directory / 'code.vdb'),
            '-cm_name', CASE]


def reference_contract():
    pre = life.read_bound(PRE / 'preflight-manifest.json', PRE_SHA)
    require(pre['status'] == 'GAP112_SV39_PREFLIGHT_PASS_NOT_DUT' and
            pre['elf_sha256'] == ELF_SHA, 'Original software preflight identity')
    # Select software evidence explicitly. Never life.check(pre['pins']): that
    # historical manifest also contains the broken RTL and old simulator image.
    paths = [ORIGINAL_ELF, PRE / 'spike.trace', PRE / 'symbols.json',
             PRE / 'linked-proof.json', PRE / 'validation.json',
             Path(oracle.__file__).resolve(), Path(oracle.prior.__file__).resolve()]
    pins = {str(p): pre['pins'][str(p)] for p in paths}
    pins[str(PRE / 'preflight-manifest.json')] = PRE_SHA
    require(pins[str(ORIGINAL_ELF)] == ELF_SHA, 'Original ELF seal')
    life.check(pins)
    symbols = json.loads((PRE / 'symbols.json').read_text())
    require(symbols == pre['symbols'], 'Exact linked symbols')
    reference = oracle.shared.parse_spike_commits(PRE / 'spike.trace')
    validation = oracle.validate(reference, symbols, (PRE / 'spike.trace').read_text())
    require(validation == pre['validation'], 'Independent full software oracle')
    counts = common.reference_counts(reference, symbols)
    start = next(i for i, c in enumerate(reference) if c.pc == 0x80000000)
    reference = reference[start:start + counts['matched_instructions']]
    require(counts == pre['reference_counts'] and counts['matched_instructions'] == 83732 and
            reference[-1].memory_accesses == ((symbols['tohost'], 1),),
            'Full sealed entry-tohost reference')
    return reference, symbols, pins


def trap_contract(rows, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    require(retired and [int(r['order']) for r in retired] == list(range(len(retired))),
            'Full contiguous retirement order')
    traps = [r for r in retired if int(r['trap'])]
    require(len(traps) == 1 and int(traps[0]['trap']) == 1 and
            int(traps[0]['pc'], 16) == symbols['sf_ecall'] and
            int(traps[0]['insn'], 16) == 0x73 and int(traps[0]['rd']) == 0 and
            int(traps[0]['mem_rmask'], 16) == int(traps[0]['mem_wmask'], 16) == 0,
            'Exactly one scalar S ECALL; no FOF/other architectural trap')
    return [r for r in retired if not int(r['trap'])]


def scalar_exact(result, reference, symbols):
    counts = common.reference_counts(reference, symbols)
    expected = dict(counts, status='TERMINAL_TOHOST_MATCH', entry='0x0000000080000000',
                    rvfi_store_data_layout='unshifted', skipped_unobservable_register_values=0,
                    stopped_at_unobservable=None, aligned_vector_faults=[], ara_trap_events=1,
                    mismatch=None, terminal_ecall=None, vector_state_compared=False,
                    ara_retired_instructions=counts['matched_instructions'] + 1,
                    ara_committed_instructions=counts['matched_instructions'])
    for key, value in expected.items():
        require(key in result and type(result[key]) is type(value) and result[key] == value,
                'Complete scalar differential differs: ' + key)


def scalar_memory_exact(rows, reference):
    """Supplement the shared comparator with compressed scalar memory effects."""
    retired = [r for r in rows if r['event'] == 'retire' and not int(r['trap'])]
    require(len(retired) == len(reference), 'Full scalar memory instruction population')
    accesses = compressed = 0
    for r, c in zip(retired, reference):
        require((int(r['pc'], 16), int(r['insn'], 16)) == (c.pc, c.instruction),
                'Scalar memory instruction identity')
        rm, wm = int(r['mem_rmask'], 16), int(r['mem_wmask'], 16)
        access = common.scalar_memory(c.instruction)
        if access is None:
            require(not rm and not wm, 'Unmodeled scalar memory effect')
            continue
        kind, width = access
        require(kind in ('read', 'write') and len(c.memory_accesses) == 1, 'Scalar memory model')
        address, value = c.memory_accesses[0]
        mask = ((1 << width) - 1) << (address & 7)
        require(int(r['mem_addr'], 16) == address and address % width == 0 and
                rm == (mask if kind == 'read' else 0) and
                wm == (mask if kind == 'write' else 0), 'Scalar memory address/mask')
        if kind == 'write':
            require(value is not None and int(r['mem_wdata'], 16) & ((1 << (width * 8)) - 1) ==
                    value & ((1 << (width * 8)) - 1), 'Scalar store value including compressed')
        else:
            require(value is None, 'Scalar read reference shape')
        accesses += 1
        compressed += int(c.instruction & 3 != 3)
    return dict(instructions=len(reference), scalar_memory_accesses=accesses,
                compressed_memory_accesses=compressed, unmodeled_memory_effects=0)


def observed(rows, symbols, blob):
    retired = trap_contract(rows, symbols)
    want = oracle.expected_memory(symbols)
    ranges = [(symbols[n], symbols[n] + size) for n, size in oracle.SIZES.items()
              if n not in ('g75_result', 'num_failed')]
    required_reads = {a for lo, hi in ranges for a in range(lo, hi)}
    data, reads, terminals, handler = {}, set(), [], []
    resumed = False
    code = {}
    for r in retired:
        pc, word = int(r['pc'], 16), int(r['insn'], 16)
        if pc not in code:
            code[pc] = elf_instruction(blob, pc, 2 if word & 3 != 3 else 4)
        require(pc != symbols['trap_fail'] and word == code[pc], 'ELF/trap retirement differs')
        resumed |= pc == symbols['sf_m_resume']
        access = common.scalar_memory(word)
        rm, wm = int(r['mem_rmask'], 16), int(r['mem_wmask'], 16)
        if access is None:
            require(not rm and not wm, 'Unmodeled scalar memory effect')
            continue
        kind, width = access
        address = int(r['mem_addr'], 16)
        mask = ((1 << width) - 1) << (address & 7)
        require(kind in ('read', 'write') and address % width == 0 and
                0x80000000 <= address < address + width <= 0x80200000 and
                rm == (mask if kind == 'read' else 0) and
                wm == (mask if kind == 'write' else 0), 'Scalar RAM/mask/alignment')
        if kind == 'write':
            value = int(r['mem_wdata'], 16) & ((1 << (width * 8)) - 1)
            if address == symbols['tohost']:
                terminals.append((r, value))
            if symbols['sf_handler'] <= pc < symbols['sf_handler_end']:
                handler.append((address, width))
        elif resumed and any(address + j in required_reads for j in range(width)):
            require(int(r['rd']) != 0, 'Unobservable post-return oracle read')
            value = int(r['rd_wdata'], 16) & ((1 << (width * 8)) - 1)
            reads.update(range(address, address + width))
        else:
            continue
        data.update({address + j: (value >> (8 * j)) & 255 for j in range(width)})
    require(resumed and required_reads <= reads, 'Incomplete post-return full RAM/context readback')
    require(all(data.get(a) == b for a, b in want.items()),
            'Independent page/source/DIV/neighbor/prefix/recovery/guard/ledger oracle differs')
    def read(name, offset=0):
        address = symbols[name] + offset
        require(all(address + j in data for j in range(8)), 'Missing context bytes')
        return int.from_bytes(bytes(data[address + j] for j in range(8)), 'little')
    before = [read('sf_before', i * 8) for i in range(15)]
    after = [read('sf_after', i * 8) for i in range(15)]
    require(before == after and before[0] == 0 and before[2] == symbols['trap_fail'],
            'Exact fifteen-CSR M context restoration')
    require(read('sf_record', 24) & 0x8000021888 == 0x800, 'Trap S privilege')
    require(handler == [(symbols['sf_count'], 8)] +
            [(symbols['sf_record'] + 8 * i, 8) for i in range(10)], 'Exact one handler footprint')
    require(terminals == [(retired[-1], 1)], 'Unique final successful tohost')
    return dict(checks=2294, failures=0, independent_defined_bytes=len(want),
                post_return_readback_bytes=len(required_reads), restored_context_csrs=15,
                fof_VL=1, fof_vstart=0, ecall_traps=1, fof_traps=0)


def native_state(reference, activities, mapping, symbols):
    require(all(seq in mapping for seq in activities), 'Unmapped native request')
    require(Counter(mapping.values()) == Counter(i for i, c in enumerate(reference)
                                                if is_vector_instruction(c.instruction)),
            'Every vector/CSR retirement mapped exactly once')
    state, last_write, records, kinds = {}, {}, [], Counter()
    for seq, index in sorted(mapping.items()):
        c, activity = reference[index], activities.get(seq)
        if activity is None:
            require(not c.vector_writes and c.instruction & 127 != 0x27,
                    'Missing native writer/store')
            continue
        a = activity
        require(a.instruction == c.instruction and a.allocations == a.completions == 1,
                'Native opcode/exact single-uop completion')
        for w in a.writes:
            require(w.arch_seq == seq and w.instruction == c.instruction and
                    0 <= w.lane < 4 and 0 <= w.eew <= 3 and 0 < w.be < 256 and
                    w.be & ~w.known_be == 0, 'Unknown/invalid accepted native write')
        actual = vc._architectural_bytes(a.writes, 4, 1024)
        gold = {}
        if not c.vector_writes:
            require(c.instruction & 127 == 0x27 and not a.use_vd and
                    all(w.source == 3 for w in a.writes), 'Unclassified nonarchitectural writer')
            kind = 'IDENTITY_TRANSPORT'
        else:
            require(a.use_vd and a.vd == (c.instruction >> 7 & 31) and a.vstart == 0,
                    'Native destination/vstart context')
            require(c.vector_sew == 32 and c.vector_vstart == 0 and
                    c.vector_tail_agnostic is False and c.vector_mask_agnostic is False,
                    'Exact TU/MU reference context')
            if c.pc == symbols['sf_fof']:
                require(c.instruction == FOF and a.eew == 2 and a.vl == 4 and
                        c.vector_vl == 1 and all(w.source == 4 for w in a.writes), 'FOF native context')
                gold = {(8, b): (oracle.prior.WORD >> (8 * b)) & 255 for b in range(4)}
                kind = 'FOF_DEFINED_PREFIX'
            elif c.instruction == MASK:
                require(a.vl == 64 and all(w.source == 2 for w in a.writes), 'Mask writer context')
                gold = {(0, b): 255 for b in range(8)}
                kind = 'MASK_ACTIVE64'
            else:
                require(c.instruction & 127 == 7 or c.pc == symbols['sf_long_div'],
                        'Unexpected architectural writer')
                producer = 1 if c.pc == symbols['sf_long_div'] else 4
                require(a.eew == 2 and a.vl == c.vector_vl and
                        all(w.source == producer for w in a.writes), 'Load/DIV producer/context')
                count = 32 if c.pc == symbols['sf_recovery_load'] else 128
                gold = {(reg, b): (value >> (8 * b)) & 255
                        for reg, value in c.vector_writes.items() for b in range(count)}
                kind = ('DIV' if producer == 1 else 'RECOVERY' if count == 32 else 'FULL_LOAD')
            require(all(key in actual and actual[key][0] == value for key, value in gold.items()),
                    'Missing/incorrect defined destination bytes')
        before = dict(state)
        permitted = 0
        for w in a.writes:
            for key, (value, _) in vc._architectural_bytes([w], 4, 1024).items():
                require(w.cycle > last_write.get(key, -1), 'Out-of-order overlapping native writers')
                reg, byte = key
                if kind == 'FOF_DEFINED_PREFIX' and reg == 8 and 4 <= byte < 16:
                    permitted += 1
                elif kind == 'MASK_ACTIVE64' and reg == 0 and byte >= 8:
                    require(value == 255 or key in before and value | before[key] == value,
                            'Unproved mask-tail old/ones policy')
                elif key in gold:
                    require(value == gold[key], 'Corrupt earlier accepted byte hidden by later write')
                else:
                    # No zero-initialized VRF assumption: untouched TU tails are
                    # fine; writing a tail requires concrete matching prestate.
                    require(key in before and value == before[key],
                            'Unproved tail/non-destination/transport prestate')
        state.update({key: value for key, (value, _) in actual.items()})
        last_write.update({key: w.cycle for key, (_, w) in actual.items()})
        kinds[kind] += 1
        records.append(dict(arch_seq=seq, pc=hex(c.pc), instruction=hex(c.instruction),
                            kind=kind, defined_bytes=len(gold), accepted_bytes=len(actual),
                            fof_spurious_byte_events=permitted))
    require(kinds == Counter(FULL_LOAD=2, DIV=1, MASK_ACTIVE64=1,
                             FOF_DEFINED_PREFIX=1, RECOVERY=1, IDENTITY_TRANSPORT=4),
            'All six writers and four stores required')
    return dict(status='PASS', primary_writers=6, stores=4,
                defined_compared_bytes=sum(r['defined_bytes'] for r in records),
                unknown_accepted_bytes=0, whole_instruction_skipped=0,
                fof_relaxation='Only original active suffix: v8 bytes4..15; not other writers/tails',
                whole_VRF_initial_state_qualified=False, records=records)


def native(directory, reference, symbols):
    lanes, vlen, activities = vc._parse_vector_trace(directory / 'vector_trace.csv')
    starts, retires, rejected = vc._parse_architecture_mapping(directory / 'commit_trace.csv')
    require((lanes, vlen) == (4, 1024) and not rejected, 'Geometry/rejected CVX request')
    arch = vc._map_architecture_retires(starts, retires, rejected)
    mapping = vc._map_spike_commits(arch, reference)
    require(len(arch) == len(retires) == len(mapping), 'Missing/unmapped vector retirement')
    return native_state(reference, activities, mapping, symbols)


def tracer_exact(text, rows, symbols):
    pattern = re.compile(r'^\s*\d+ns\s+(\d+)\s+([MSU])\s+([0-9a-fA-F]{16})\s+\d+\s+([0-9a-fA-F]{8})\b')
    actual = [m.groups() for line in text.splitlines() if (m := pattern.match(line))]
    retired = trap_contract(rows, symbols)
    wanted = [(str(int(r['cycle'])),
               'S' if symbols['sf_s_entry'] <= int(r['pc'], 16) < symbols['sf_s_end'] else 'M',
               '%016x' % int(r['pc'], 16), '%08x' % int(r['insn'], 16)) for r in retired]
    require(actual[:len(wanted)] == wanted, 'Full tracer retirement/privilege differential')
    tail = actual[len(wanted):]
    require(not tail or tail == [(wanted[-1][0], 'M',
                                 '%016x' % (int(wanted[-1][2], 16) + 4), '0000a001')],
            'Unexpected post-terminal tracer tail')
    events = re.findall(r'Exception @\s*(\d+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)', text)
    require(len(events) == text.count('Exception @') == 1 and
            int(events[0][1], 16) == symbols['sf_ecall'] and
            events[0][2] == 'Environment Call Supervisor Mode' and
            [int(v, 16) for v in re.findall(r'tval: ([0-9a-fA-F]+)', text)] == [0],
            'Exactly one S ECALL cause/PC/tval; no FOF page fault')
    return dict(nontrap_retirements=len(retired), S_ecalls=1, fof_traps=0)


def audit(directory):
    directory = Path(directory).resolve(strict=True)
    require(directory.is_dir(), 'Completed case directory required')
    reference, symbols, pins = reference_contract()
    paths = [directory / n for n in ('commit_trace.csv', 'vector_trace.csv',
                                     'trace_hart_0.log', 'console.log', 'run.vcs.log')]
    require(all(p.is_file() and p.stat().st_size > 0 for p in paths), 'Missing completed evidence')
    local = directory / 'input.elf'
    if local.exists():
        require(life.digest(local) == ELF_SHA, 'Local ELF is not original FOF reproducer')
        paths.append(local)
    paths += [Path(__file__).resolve(), Path(elf_instruction.__code__.co_filename).resolve()]
    paths += [Path(m.__file__).resolve() for m in
              (common, common.spike_trace, control, control.previous, vc, oracle.shared, life)]
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in paths})
    rows = common.read_csv((directory / 'commit_trace.csv').read_bytes(), common.COMMIT_FIELDS)
    vectors = common.read_csv((directory / 'vector_trace.csv').read_bytes(), common.VECTOR_FIELDS)
    trap_contract(rows, symbols)
    lifecycle = control.lifecycle(rows, vectors)
    for name in ('console.log', 'run.vcs.log'):
        path = directory / name
        require(not check_contract_log(path), 'Incomplete/failed simulator contract: ' + name)
        text = path.read_text()
        require(text.count('Core Test *** SUCCESS ***') == 1, 'Unique Core SUCCESS')
        summary = next(parse_contract_summary(line) for line in text.splitlines()
                       if '[ARA_CONTRACT]' in line)
        require(summary['requests'] == summary['responses'] == lifecycle['requests'] and
                summary['exceptions'] == 0, 'No accelerator traps and exact contract counts')
    scalar = common.spike_trace.compare_commit_prefix(
        PRE / 'spike.trace', directory / 'commit_trace.csv', 0x80000000,
        terminal_tohost_address=symbols['tohost'], rvfi_store_data_layout='unshifted')
    scalar_exact(scalar, reference, symbols)
    scalar_memory = scalar_memory_exact(rows, reference)
    footprint = observed(rows, symbols, ORIGINAL_ELF.read_bytes())
    vector = native(directory, reference, symbols)
    tracer = tracer_exact((directory / 'trace_hart_0.log').read_text(), rows, symbols)
    life.check(pins)
    return dict(status='PASS', case=CASE, directory=str(directory), elf_sha256=ELF_SHA,
                scalar=scalar, scalar_memory=scalar_memory, footprint=footprint,
                native=vector, lifecycle=lifecycle, tracer=tracer, input_pins=pins,
                image_provenance_verified=False, process_exit_verified=False,
                campaign_terminal_and_image_checks_required=True,
                coverage_admitted=False, coverage_merged=False, EDA_launched=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), indent=2, sort_keys=True))
