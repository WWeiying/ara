from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .spike_trace import SpikeCommit, parse_spike_commits
from .trace import is_vector_instruction


class VectorCommitComparisonError(ValueError):
    pass


@dataclass(frozen=True)
class VectorRetire:
    pc: int
    instruction: int


@dataclass(frozen=True)
class VectorWrite:
    row: int
    cycle: int
    arch_seq: int
    vid: int
    lane: int
    source: int
    instruction: int
    eew: int
    addr: int
    be: int
    data: int
    known_be: int


@dataclass
class ArchActivity:
    instruction: int
    allocations: int = 0
    completions: int = 0
    use_vd: bool = False
    vd: int = 0
    eew: Optional[int] = None
    vl: Optional[int] = None
    vstart: Optional[int] = None
    writes: List[VectorWrite] = field(default_factory=list)


def _integer(row: Dict[str, str], field: str, base: int = 10) -> int:
    value = row.get(field, "")
    try:
        return int(value, base)
    except ValueError as error:
        raise VectorCommitComparisonError(f"invalid {field}: {value!r}") from error


def _write_data(value: str) -> Tuple[int, int]:
    text = value.strip().lower()
    if len(text) > 16:
        raise VectorCommitComparisonError(f"invalid 64-bit write data: {value!r}")
    text = text.rjust(16, "0")
    data = 0
    known_be = 0
    for byte in range(8):
        pair = text[14 - 2 * byte:16 - 2 * byte]
        if any(character in "xz" for character in pair):
            continue
        try:
            byte_value = int(pair, 16)
        except ValueError as error:
            raise VectorCommitComparisonError(
                f"invalid 64-bit write data: {value!r}"
            ) from error
        data |= byte_value << (8 * byte)
        known_be |= 1 << byte
    return data, known_be


def _is_side_effect_free_vector_csr_read(instruction: int) -> bool:
    opcode = instruction & 0x7F
    funct3 = (instruction >> 12) & 0x7
    rs1 = (instruction >> 15) & 0x1F
    csr = (instruction >> 20) & 0xFFF
    return (
        opcode == 0x73
        and funct3 in {2, 3}
        and rs1 == 0
        and csr in {0x008, 0x009, 0x00A, 0x00F, 0xC20, 0xC21, 0xC22}
    )


def _transport_replay(instruction: int, previous: Optional[int]) -> bool:
    if not _is_side_effect_free_vector_csr_read(instruction):
        return False
    rd = (instruction >> 7) & 0x1F
    return rd == 0 or instruction == previous


def _is_non_bit_exact_vector_result(instruction: int) -> bool:
    """Return true for reductions whose result order is implementation-defined."""
    opcode = instruction & 0x7F
    funct3 = (instruction >> 12) & 0x7
    funct6 = (instruction >> 26) & 0x3F
    # vfredusum.vs and vfwredusum.vs may use any deterministic reduction tree.
    # Their ordered counterparts (funct6 0x03/0x33) remain bit-exact checks.
    return opcode == 0x57 and funct3 == 0x1 and funct6 in {0x01, 0x31}


def _parse_vector_trace(
    path: Path,
) -> Tuple[int, int, Dict[int, ArchActivity]]:
    required = {
        "cycle", "event", "arch_seq", "vid", "lane", "source", "insn",
        "use_vd", "vd", "eew", "addr", "be", "wdata", "nr_lanes", "vlen_bits",
    }
    activities: Dict[int, ArchActivity] = {}
    nr_lanes = 0
    vlen_bits = 0
    try:
        file = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise VectorCommitComparisonError(f"cannot read vector trace: {error}") from error

    with file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            missing = sorted(required.difference(reader.fieldnames or []))
            raise VectorCommitComparisonError(
                f"vector trace is missing columns: {', '.join(missing)}"
            )
        for row_index, row in enumerate(reader, start=2):
            event = row["event"]
            row_lanes = _integer(row, "nr_lanes")
            row_vlen = _integer(row, "vlen_bits")
            if event == "config":
                nr_lanes = row_lanes
                vlen_bits = row_vlen
                continue
            if row_lanes != nr_lanes or row_vlen != vlen_bits:
                raise VectorCommitComparisonError(
                    f"vector configuration changed at row {row_index}"
                )
            arch_seq = _integer(row, "arch_seq")
            instruction = _integer(row, "insn", 16)
            activity = activities.setdefault(arch_seq, ArchActivity(instruction=instruction))
            if activity.instruction != instruction:
                raise VectorCommitComparisonError(
                    f"architecture request {arch_seq} has inconsistent instruction encodings"
                )
            if event == "alloc":
                activity.allocations += 1
                activity.use_vd |= bool(_integer(row, "use_vd"))
                alloc_vd = _integer(row, "vd")
                activity.vd = (instruction >> 7) & 0x1F
                if alloc_vd == activity.vd:
                    activity.eew = _integer(row, "eew")
                    activity.vl = _integer(row, "vl")
                    activity.vstart = _integer(row, "vstart")
            elif event == "done":
                activity.completions += 1
            elif event == "write":
                data, known_be = _write_data(row.get("wdata", ""))
                activity.writes.append(VectorWrite(
                    row=row_index,
                    cycle=_integer(row, "cycle"),
                    arch_seq=arch_seq,
                    vid=_integer(row, "vid"),
                    lane=_integer(row, "lane"),
                    source=_integer(row, "source"),
                    instruction=instruction,
                    eew=_integer(row, "eew"),
                    addr=_integer(row, "addr"),
                    be=_integer(row, "be", 16),
                    data=data,
                    known_be=known_be,
                ))
            else:
                raise VectorCommitComparisonError(f"unknown vector trace event: {event!r}")

    if nr_lanes <= 0 or vlen_bits <= 0:
        raise VectorCommitComparisonError("vector trace has no valid configuration record")
    if vlen_bits % (nr_lanes * 64) != 0:
        raise VectorCommitComparisonError(
            f"VLEN={vlen_bits} is not divisible by {nr_lanes} lanes x 64 bits"
        )
    return nr_lanes, vlen_bits, activities


def _parse_architecture_mapping(
    path: Path,
) -> Tuple[List[Tuple[int, int]], List[VectorRetire], Set[int]]:
    starts: List[Tuple[int, int]] = []
    retires: List[VectorRetire] = []
    pending_arch_by_trans_id: Dict[int, int] = {}
    trapped_arch_sequences: Set[int] = set()
    try:
        file = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise VectorCommitComparisonError(f"cannot read commit trace: {error}") from error
    with file:
        reader = csv.DictReader(file)
        required = {"event", "order", "pc", "insn", "trap"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            missing = sorted(required.difference(reader.fieldnames or []))
            raise VectorCommitComparisonError(
                f"commit trace is missing columns: {', '.join(missing)}"
            )
        for row in reader:
            instruction = _integer(row, "insn", 16)
            if row["event"] == "arch_start":
                arch_seq = _integer(row, "order")
                trans_id = _integer(row, "trans_id")
                starts.append((arch_seq, instruction))
                pending_arch_by_trans_id[trans_id] = arch_seq
            elif row["event"] == "cvx_resp":
                trans_id = _integer(row, "trans_id")
                arch_seq = pending_arch_by_trans_id.pop(trans_id, None)
                if arch_seq is not None and bool(_integer(row, "trap")):
                    trapped_arch_sequences.add(arch_seq)
            elif (
                row["event"] == "retire"
                and not bool(_integer(row, "trap"))
                and is_vector_instruction(instruction)
            ):
                retires.append(VectorRetire(
                    pc=_integer(row, "pc", 16), instruction=instruction
                ))
    return starts, retires, trapped_arch_sequences


def _map_architecture_retires(
    starts: Iterable[Tuple[int, int]], retires: List[VectorRetire],
    trapped_arch_sequences: Set[int],
    allow_incomplete_tail: bool = False,
) -> Dict[int, VectorRetire]:
    mapping: Dict[int, VectorRetire] = {}
    retire_index = 0
    previous: Optional[int] = None
    for arch_seq, instruction in starts:
        if arch_seq in trapped_arch_sequences:
            previous = instruction
            continue
        if retire_index < len(retires) and retires[retire_index].instruction == instruction:
            mapping[arch_seq] = retires[retire_index]
            retire_index += 1
        elif allow_incomplete_tail and retire_index >= len(retires):
            break
        elif not _transport_replay(instruction, previous):
            found = retires[retire_index].instruction if retire_index < len(retires) else None
            found_text = "end of trace" if found is None else f"0x{found:08x}"
            raise VectorCommitComparisonError(
                f"cannot map architecture request {arch_seq} instruction 0x{instruction:08x} "
                f"to vector retirement {found_text}"
            )
        previous = instruction
    return mapping


def _spike_from_entry(path: Path, entry: int) -> List[SpikeCommit]:
    commits = parse_spike_commits(path)
    for index, commit in enumerate(commits):
        if commit.pc == entry:
            return commits[index:]
    raise VectorCommitComparisonError(f"Spike did not execute ELF entry 0x{entry:016x}")


def _map_spike_commits(
    arch_mapping: Dict[int, VectorRetire],
    commits: List[SpikeCommit],
    *,
    allow_incomplete_tail: bool = False,
    stop_spike_index: Optional[int] = None,
) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    cursor = 0
    limit = len(commits)
    if stop_spike_index is not None:
        limit = min(limit, stop_spike_index + 1)
    for arch_seq, retire in sorted(arch_mapping.items()):
        while cursor < limit:
            commit = commits[cursor]
            cursor += 1
            if commit.pc == retire.pc and commit.instruction == retire.instruction:
                mapping[arch_seq] = cursor - 1
                break
        else:
            if allow_incomplete_tail:
                break
            raise VectorCommitComparisonError(
                f"cannot find Spike commit for architecture request {arch_seq} at "
                f"pc=0x{retire.pc:016x} insn=0x{retire.instruction:08x}"
            )
    return mapping


def _vector_scalar_source_unknown(
    commit: SpikeCommit,
    unknown_state: Dict[int, int],
    expected_state: Optional[Dict[int, int]] = None,
) -> bool:
    """Return whether a vector-to-scalar result consumes unknown vector bits."""
    instruction = commit.instruction
    opcode = instruction & 0x7F
    funct3 = (instruction >> 12) & 0x7
    funct6 = (instruction >> 26) & 0x3F
    # These scalar-result operations share funct6=010000. The vs1 field
    # distinguishes element-zero moves from mask population/first-set scans.
    if opcode != 0x57 or funct6 != 0x10 or funct3 not in {0x1, 0x2}:
        return False
    vs2 = (instruction >> 20) & 0x1F
    vs1 = (instruction >> 15) & 0x1F
    if vs1 in {0x10, 0x11} and funct3 == 0x2:  # vcpop.m / vfirst.m
        if commit.vector_vl is None:
            return bool(unknown_state.get(vs2, 0) or unknown_state.get(0, 0))
        active_mask = (1 << commit.vector_vl) - 1
        source_unknown = unknown_state.get(vs2, 0) & active_mask
        masked = ((instruction >> 25) & 1) == 0
        predicate_unknown = (
            unknown_state.get(0, 0) & active_mask if masked else 0
        )
        if expected_state is None:
            return bool(source_unknown or predicate_unknown)

        source_value = expected_state.get(vs2, 0) & active_mask
        source_known_one = source_value & ~source_unknown
        source_may_be_one = source_value | source_unknown
        if masked:
            predicate_value = expected_state.get(0, 0) & active_mask
            predicate_known_one = predicate_value & ~predicate_unknown
            predicate_may_be_one = predicate_value | predicate_unknown
        else:
            predicate_known_one = active_mask
            predicate_may_be_one = active_mask

        definite_one = source_known_one & predicate_known_one
        possible_one = source_may_be_one & predicate_may_be_one
        uncertain_effective_bits = possible_one & ~definite_one
        if vs1 == 0x10:  # vcpop.m: every active effective bit contributes.
            return bool(uncertain_effective_bits)

        # vfirst.m only depends on bits through the first definite one. Unknown
        # effective bits after that position cannot change the scalar result.
        if definite_one:
            first_definite = (definite_one & -definite_one).bit_length() - 1
            relevant_mask = (1 << first_definite) - 1
            return bool(uncertain_effective_bits & relevant_mask)
        return bool(uncertain_effective_bits)
    if vs1 != 0 or commit.vector_sew not in {8, 16, 32, 64}:
        return False
    element_mask = (1 << commit.vector_sew) - 1
    return bool(unknown_state.get(vs2, 0) & element_mask)


def unobservable_vector_scalar_write_indices(
    spike_log: Path, commit_trace: Path, vector_trace: Path, entry: int
) -> Set[int]:
    """Find dynamic vector-to-scalar writes sourced from unknown element 0 bits."""
    _, vlen_bits, activities = _parse_vector_trace(vector_trace)
    starts, retires, trapped_arch_sequences = _parse_architecture_mapping(commit_trace)
    arch_retires = _map_architecture_retires(
        starts, retires, trapped_arch_sequences, allow_incomplete_tail=True
    )
    commits = _spike_from_entry(spike_log, entry)
    # An architecturally unknown vector-to-scalar result may legitimately make
    # RTL and Spike follow different control flow. Preserve the strict mapped
    # prefix instead of discarding all observability information at that point.
    spike_mapping = _map_spike_commits(
        arch_retires, commits, allow_incomplete_tail=True
    )
    activity_by_spike = {
        spike_mapping[arch_seq]: activities[arch_seq]
        for arch_seq in activities
        if arch_seq in spike_mapping
    }

    expected_state: Dict[int, int] = {}
    unknown_state: Dict[int, int] = {}
    unobservable: Set[int] = set()
    for index, commit in enumerate(commits):
        activity = activity_by_spike.get(index)
        # Vector-to-scalar moves have no VRF destination activity. Their source
        # observability still depends on the vector state produced by preceding
        # requests, so do not gate this check on a writeback activity record.
        if _vector_scalar_source_unknown(commit, unknown_state, expected_state):
            unobservable.add(index)
        pre_state = dict(expected_state)
        for register, value in commit.vector_writes.items():
            expected_state[register] = value
        if activity is not None:
            _advance_unknown_state(
                unknown_state, activity, commit, pre_state, vlen_bits
            )
    return unobservable


def _deshuffle_byte(physical_byte: int, nr_lanes: int, eew: int) -> int:
    if eew < 0 or eew > 3:
        raise VectorCommitComparisonError(f"unsupported destination EEW encoding {eew}")
    element_bytes = 1 << eew
    chunk_bytes = nr_lanes * 8
    if physical_byte < 0 or physical_byte >= chunk_bytes:
        raise VectorCommitComparisonError(
            f"physical byte {physical_byte} is outside a {chunk_bytes}-byte VRF word"
        )
    elements_per_lane = 8 // element_bytes
    lane = physical_byte // 8
    lane_byte = physical_byte % 8
    lane_element = lane_byte // element_bytes
    index_bits = elements_per_lane.bit_length() - 1
    natural_lane_element = 0
    for bit in range(index_bits):
        natural_lane_element |= ((lane_element >> bit) & 1) << (index_bits - 1 - bit)
    natural_element = natural_lane_element * nr_lanes + lane
    return natural_element * element_bytes + physical_byte % element_bytes


def _architectural_bytes(
    writes: Iterable[VectorWrite], nr_lanes: int, vlen_bits: int
) -> Dict[Tuple[int, int], Tuple[Optional[int], VectorWrite]]:
    words_per_register = vlen_bits // nr_lanes // 64
    physical: Dict[Tuple[int, int, int, int], Tuple[Optional[int], VectorWrite]] = {}
    final_eew: Dict[int, int] = {}
    for write in sorted(writes, key=lambda item: (item.cycle, item.row)):
        register = write.addr // words_per_register
        word = write.addr % words_per_register
        if register < 0 or register >= 32:
            raise VectorCommitComparisonError(
                f"VRF write address {write.addr} decodes to invalid v{register}"
            )
        final_eew[register] = write.eew
        for byte in range(8):
            if write.be & (1 << byte):
                value = (
                    (write.data >> (8 * byte)) & 0xFF
                    if write.known_be & (1 << byte) else None
                )
                physical[(register, word, write.lane, byte)] = (value, write)

    result: Dict[Tuple[int, int], Tuple[Optional[int], VectorWrite]] = {}
    for (register, word, lane, byte), (value, write) in physical.items():
        physical_byte = lane * 8 + byte
        natural_byte = _deshuffle_byte(physical_byte, nr_lanes, final_eew[register])
        register_byte = word * nr_lanes * 8 + natural_byte
        result[(register, register_byte)] = (value, write)
    return result


def _is_mask_destination(instruction: int) -> bool:
    if (instruction & 0x7F) != 0x57:
        return False
    funct3 = (instruction >> 12) & 0x7
    rs1 = (instruction >> 15) & 0x1F
    funct6 = (instruction >> 26) & 0x3F
    if 0x18 <= funct6 <= 0x1F:
        return True
    if funct6 in {0x11, 0x13} and funct3 != 0x1:
        return True
    return funct3 == 0x2 and funct6 == 0x14 and rs1 in {1, 2, 3}


def _vmsx_unknown_result_bits(
    instruction: int,
    pre_state: Dict[int, int],
    pre_unknown: Dict[int, int],
    vl: int,
    vstart: int,
) -> int:
    """Propagate uncertainty through vmsbf/vmsof/vmsif's prefix scan."""
    opcode = instruction & 0x7F
    funct3 = (instruction >> 12) & 0x7
    rs1 = (instruction >> 15) & 0x1F
    funct6 = (instruction >> 26) & 0x3F
    if opcode != 0x57 or funct3 != 0x2 or funct6 != 0x14 or rs1 not in {1, 2, 3}:
        return 0

    vs2 = (instruction >> 20) & 0x1F
    source = pre_state.get(vs2)
    source_unknown = pre_unknown.get(vs2, 0)
    predicate = pre_state.get(0)
    predicate_unknown = pre_unknown.get(0, 0)
    unmasked = bool((instruction >> 25) & 1)
    found_states = {False}
    unknown_result = 0

    for element in range(vl):
        if element < vstart:
            continue
        if unmasked:
            predicate_states = {True}
        elif predicate is None or ((predicate_unknown >> element) & 1):
            predicate_states = {False, True}
        else:
            predicate_states = {bool((predicate >> element) & 1)}

        if source is None or ((source_unknown >> element) & 1):
            source_states = {False, True}
        else:
            source_states = {bool((source >> element) & 1)}

        output_states = set()
        next_found_states = set()
        for found in found_states:
            for enabled in predicate_states:
                if not enabled:
                    next_found_states.add(found)
                    continue
                for source_bit in source_states:
                    if rs1 == 1:       # vmsbf.m: bits before the first set bit
                        output_states.add(not found and not source_bit)
                    elif rs1 == 2:     # vmsof.m: only the first set bit
                        output_states.add(not found and source_bit)
                    else:              # vmsif.m: bits through the first set bit
                        output_states.add(not found)
                    next_found_states.add(found or source_bit)

        # Predicate uncertainty is handled locally by mask policy, but it also
        # branches the scan state and can affect later active result bits.
        if len(output_states) > 1:
            unknown_result |= 1 << element
        found_states = next_found_states

    return unknown_result


def _mask_result_source_unknown_bits(
    instruction: int,
    pre_state: Dict[int, int],
    pre_unknown: Dict[int, int],
    vl: int,
    vstart: int,
    vlen_bits: int,
    source_element_bytes: int,
) -> int:
    """Return mask-result bits tainted by uncertain vector source values."""
    if not _is_mask_destination(instruction):
        return 0
    funct3 = (instruction >> 12) & 0x7
    funct6 = (instruction >> 26) & 0x3F
    vs2 = (instruction >> 20) & 0x1F
    vs1 = (instruction >> 15) & 0x1F
    unmasked = bool((instruction >> 25) & 1)
    predicate = pre_state.get(0)
    predicate_unknown = pre_unknown.get(0, 0)
    bytes_per_register = vlen_bits // 8
    unknown_result = 0

    is_vmsx = funct3 == 0x2 and funct6 == 0x14 and vs1 in {1, 2, 3}
    if is_vmsx:
        return 0
    mask_logical = funct3 == 0x2 and 0x18 <= funct6 <= 0x1F
    carry_mask_result = funct6 in {0x11, 0x13} and funct3 != 0x1

    for element in range(vstart, vl):
        # For ordinary predicated comparisons an inactive element cannot
        # consume uncertain data. An uncertain predicate is already marked
        # unknown by the destination policy machinery.
        if not unmasked and not carry_mask_result:
            if predicate is None or ((predicate_unknown >> element) & 1):
                continue
            if not ((predicate >> element) & 1):
                continue

        source_unknown = False
        if mask_logical:
            source_unknown = bool(
                ((pre_unknown.get(vs2, 0) | pre_unknown.get(vs1, 0)) >> element) & 1
            )
        elif source_element_bytes:
            source_bases = [vs2]
            if funct3 in {0x0, 0x2} or (
                funct3 == 0x1 and funct6 not in {0x12, 0x13}
            ):
                source_bases.append(vs1)
            for source_base in source_bases:
                for source_byte_in_element in range(source_element_bytes):
                    source_global_byte = (
                        element * source_element_bytes + source_byte_in_element
                    )
                    source_register = (
                        source_base + source_global_byte // bytes_per_register
                    )
                    source_byte = source_global_byte % bytes_per_register
                    source_unknown |= bool(
                        (pre_unknown.get(source_register, 0) >> (8 * source_byte)) & 0xFF
                    )
        if carry_mask_result and not unmasked:
            source_unknown |= bool((pre_unknown.get(0, 0) >> element) & 1)
        if source_unknown:
            unknown_result |= 1 << element

    return unknown_result


def _uses_mask_predicate(instruction: int) -> bool:
    funct6 = (instruction >> 26) & 0x3F
    funct3 = (instruction >> 12) & 0x7
    if funct6 in {0x11, 0x13} and funct3 != 0x1:
        return False
    return not bool((instruction >> 25) & 1)


def _architectural_compare_mask(
    activity: ArchActivity,
    register: int,
    byte: int,
    vlen_bits: int,
    pre_state: Dict[int, int],
    destination_registers: Iterable[int],
    architectural_vl: Optional[int] = None,
    architectural_vstart: Optional[int] = None,
    tail_agnostic: Optional[bool] = None,
    mask_agnostic: Optional[bool] = None,
) -> int:
    if register not in destination_registers:
        # Internal reshuffle uops share the architectural request tag but may
        # write source or preservation registers.  They are transport state,
        # not architectural destinations of this instruction.
        return 0
    vl = architectural_vl if architectural_vl is not None else activity.vl
    vstart = (
        architectural_vstart
        if architectural_vstart is not None
        else activity.vstart
    )
    if activity.eew is None or vl is None or vstart is None:
        return 0xFF

    mask_destination = _is_mask_destination(activity.instruction)
    # RVV mask-producing instructions always treat destination tail bits as
    # agnostic, independently of vtype.vta.
    tail_is_agnostic = mask_destination or tail_agnostic is not False
    mask_is_agnostic = mask_agnostic is not False
    masked = _uses_mask_predicate(activity.instruction)
    predicate = pre_state.get(0)

    def compare_element(element: int) -> bool:
        if element < vstart:
            return True
        if element >= vl:
            return not tail_is_agnostic
        if not masked:
            return True
        if predicate is None:
            return not mask_is_agnostic
        if (predicate >> element) & 1:
            return True
        return not mask_is_agnostic

    if mask_destination:
        result = 0
        first_element = (register - activity.vd) * vlen_bits + byte * 8
        for bit in range(8):
            element = first_element + bit
            if not compare_element(element):
                continue
            result |= 1 << bit
        return result

    element_bytes = 1 << activity.eew
    elements_per_register = vlen_bits // (8 * element_bytes)
    element = (
        (register - activity.vd) * elements_per_register + byte // element_bytes
    )
    return 0xFF if compare_element(element) else 0


def _architectural_byte_effect_masks(
    activity: ArchActivity,
    register: int,
    byte: int,
    vlen_bits: int,
    pre_state: Dict[int, int],
    pre_unknown: Dict[int, int],
    destination_registers: Iterable[int],
    architectural_vl: Optional[int] = None,
    architectural_vstart: Optional[int] = None,
    tail_agnostic: Optional[bool] = None,
    mask_agnostic: Optional[bool] = None,
) -> Tuple[int, int]:
    """Return bit masks for defined writes and architecturally unknown writes.

    Bits in neither mask are undisturbed and retain their previous definedness.
    An unknown predicate bit also makes the corresponding result unknown: the
    implementation may either preserve or update that element.
    """
    if register not in destination_registers or activity.eew is None:
        return 0, 0
    vl = architectural_vl if architectural_vl is not None else activity.vl
    vstart = (
        architectural_vstart
        if architectural_vstart is not None
        else activity.vstart
    )
    if vl is None or vstart is None:
        return 0, 0xFF

    mask_destination = _is_mask_destination(activity.instruction)
    # Mask result tail bits are architecturally agnostic even under `tu`.
    tail_is_agnostic = mask_destination or tail_agnostic is not False
    mask_is_agnostic = mask_agnostic is not False
    masked = _uses_mask_predicate(activity.instruction)
    predicate = pre_state.get(0)
    predicate_unknown = pre_unknown.get(0, 0)

    def element_effect(element: int) -> str:
        if element < vstart:
            return "preserve"
        if element >= vl:
            return "unknown" if tail_is_agnostic else "preserve"
        if not masked:
            return "write"
        if predicate is None or ((predicate_unknown >> element) & 1):
            return "unknown"
        if (predicate >> element) & 1:
            return "write"
        return "unknown" if mask_is_agnostic else "preserve"

    write_mask = 0
    unknown_mask = 0
    if mask_destination:
        first_element = (register - activity.vd) * vlen_bits + byte * 8
        for bit in range(8):
            effect = element_effect(first_element + bit)
            if effect == "write":
                write_mask |= 1 << bit
            elif effect == "unknown":
                unknown_mask |= 1 << bit
        return write_mask, unknown_mask

    element_bytes = 1 << activity.eew
    elements_per_register = vlen_bits // (8 * element_bytes)
    element = (
        (register - activity.vd) * elements_per_register + byte // element_bytes
    )
    effect = element_effect(element)
    if effect == "write":
        write_mask = 0xFF
    elif effect == "unknown":
        unknown_mask = 0xFF
    return write_mask, unknown_mask


def _advance_unknown_state(
    unknown_state: Dict[int, int],
    activity: ArchActivity,
    commit: SpikeCommit,
    pre_state: Dict[int, int],
    vlen_bits: int,
) -> None:
    destination_registers = commit.vector_writes.keys()
    pre_unknown = dict(unknown_state)
    non_bit_exact = _is_non_bit_exact_vector_result(activity.instruction)
    funct6 = (activity.instruction >> 26) & 0x3F
    funct3 = (activity.instruction >> 12) & 0x7
    vs2 = (activity.instruction >> 20) & 0x1F
    vs1 = (activity.instruction >> 15) & 0x1F
    element_bytes = 1 << activity.eew if activity.eew is not None else 0
    source_element_bytes = (
        commit.vector_sew // 8 if commit.vector_sew is not None else 0
    )
    vmsx_unknown_bits = _vmsx_unknown_result_bits(
        activity.instruction,
        pre_state,
        pre_unknown,
        commit.vector_vl if commit.vector_vl is not None else (activity.vl or 0),
        commit.vector_vstart
        if commit.vector_vstart is not None else (activity.vstart or 0),
    )
    mask_source_unknown_bits = _mask_result_source_unknown_bits(
        activity.instruction,
        pre_state,
        pre_unknown,
        commit.vector_vl if commit.vector_vl is not None else (activity.vl or 0),
        commit.vector_vstart
        if commit.vector_vstart is not None else (activity.vstart or 0),
        vlen_bits,
        source_element_bytes,
    )
    vector_sources = [vs2]
    if funct3 in {0x0, 0x2} or (
        funct3 == 0x1 and funct6 not in {0x12, 0x13}
    ):
        vector_sources.append(vs1)
    for register in destination_registers:
        register_unknown = pre_unknown.get(register, 0)
        for byte in range(vlen_bits // 8):
            write_mask, new_unknown_mask = _architectural_byte_effect_masks(
                activity, register, byte, vlen_bits, pre_state, pre_unknown,
                destination_registers, commit.vector_vl, commit.vector_vstart,
                commit.vector_tail_agnostic, commit.vector_mask_agnostic,
            )
            # Unordered FP sums are legal but not bit-exact. Only their scalar
            # result element is nondeterministic; the rest of vd is governed by
            # the normal tail policy.
            if (non_bit_exact and register == activity.vd and
                    byte < element_bytes):
                # A reduction always writes vd[0] from its scalar seed, even
                # when every vs2 element is masked off. The source predicate
                # therefore does not gate this destination element.
                new_unknown_mask |= 0xFF
                write_mask = 0

            if register == activity.vd:
                new_unknown_mask |= (
                    (vmsx_unknown_bits | mask_source_unknown_bits) >> (8 * byte)
                ) & 0xFF

            # Propagate source uncertainty by element. This keeps unrelated
            # elements observable and also handles widening destinations: any
            # unknown byte in a source element taints that element's result.
            if ((activity.instruction & 0x7F) == 0x57 and
                    not _is_mask_destination(activity.instruction) and
                    register >= activity.vd and element_bytes and
                    source_element_bytes):
                bytes_per_register = vlen_bits // 8
                destination_global_byte = (
                    (register - activity.vd) * bytes_per_register + byte
                )
                element = destination_global_byte // element_bytes
                source_is_unknown = False
                for source_base in vector_sources:
                    for source_byte_in_element in range(source_element_bytes):
                        source_global_byte = (
                            element * source_element_bytes +
                            source_byte_in_element
                        )
                        source_register = (
                            source_base + source_global_byte // bytes_per_register
                        )
                        source_byte = source_global_byte % bytes_per_register
                        source_is_unknown |= bool(
                            (pre_unknown.get(source_register, 0) >>
                             (8 * source_byte)) & 0xFF
                        )
                if source_is_unknown:
                    new_unknown_mask |= write_mask
                    write_mask = 0
            shift = 8 * byte
            old_unknown_mask = (register_unknown >> shift) & 0xFF
            result_unknown_mask = (
                (old_unknown_mask & ~(write_mask | new_unknown_mask))
                | new_unknown_mask
            ) & 0xFF
            register_unknown &= ~(0xFF << shift)
            register_unknown |= result_unknown_mask << shift
        unknown_state[register] = register_unknown


def _identity_trap_write_bytes(
    activity: ArchActivity,
    pre_state: Dict[int, int],
    pre_unknown: Dict[int, int],
    nr_lanes: int,
    vlen_bits: int,
    *,
    allow_load: bool = False,
) -> int:
    """Count fully known SLDU maintenance bytes that preserve pre-trap VRF state."""
    opcode = activity.instruction & 0x7F
    if (opcode != 0x27 and not (allow_load and opcode == 0x07)) or not activity.writes:
        return 0
    sources = {3, 4} if allow_load and opcode == 0x07 else {3}
    if any(write.source not in sources for write in activity.writes):
        return 0
    actual = _architectural_bytes(activity.writes, nr_lanes, vlen_bits)
    accepted_bytes = sum(bin(write.be & 0xFF).count("1") for write in activity.writes)
    if not actual or len(actual) != accepted_bytes:
        return 0
    for (register, byte), (value, _) in actual.items():
        if (value is None or register not in pre_state or
                (pre_unknown.get(register, 0) >> (8 * byte)) & 0xFF or
                value != (pre_state[register] >> (8 * byte)) & 0xFF):
            return 0
    return len(actual)


def _known_identity_load_fault(activity: ArchActivity, commit: SpikeCommit,
                               fault: Dict[str, object]) -> bool:
    """Narrow first-element misaligned load, never a partial-effect fault."""
    csrs = fault.get("matched_fault_csrs", {})
    return (
        activity.instruction & 0x7f == 0x07 and
        activity.allocations > 0 and activity.allocations == activity.completions and
        isinstance(commit.vector_vl, int) and commit.vector_vl > 0 and
        commit.vector_vstart == 0 and
        not commit.vector_writes and not commit.memory_accesses and
        not commit.gpr_writes and not commit.fpr_writes and commit.csr_writes == {8: 0} and
        csrs.get("0x342") == 4 and csrs.get("0x341") == commit.pc and
        isinstance(csrs.get("0x343"), int)
    )


def _fault_require(condition: bool, message: str) -> None:
    if not condition:
        raise VectorCommitComparisonError("load fault proof: " + message)


def _fault_probe_pair(path: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    records = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.startswith("[ARA_FAULT_VSTART] "):
                continue
            record = {}
            for token in line.split()[1:]:
                key, value = token.split("=", 1)
                _fault_require(key not in record, "duplicate probe field")
                record[key] = value
            records.append(record)
    _fault_require(len(records) == 2, "requires exactly one RESP/NEXT pair")
    response, following = records
    _fault_require(response.get("phase") == "RESP" and following.get("phase") == "NEXT",
                   "missing or reordered probe phase")
    for key in ("req_valid", "req_ready", "resp_valid", "resp_ready", "fire",
                "backend_valid", "backend_exception"):
        _fault_require(response.get(key) == "1", "probe handshake/exception " + key)
    for key in ("rst_n", "match"):
        _fault_require(following.get(key) == "1", "probe NEXT " + key)
    for key in ("inst", "event", "trans_id"):
        _fault_require(response.get(key) is not None and response[key] == following.get(key),
                       "probe pair identity " + key)
    _fault_require(response["trans_id"] == response.get("req_trans_id"), "request/response ID")
    _fault_require(int(following["resp_cycle"]) == int(response["cycle"]) and
                   int(following["cycle"]) == int(response["cycle"]) + 1 and
                   int(following["time"]) > int(response["time"]), "probe NEXT timing")
    result = int(response["exception_vstart"], 16)
    _fault_require(all(int(value, 16) == result for value in (
        response["csr_vstart_d"], following["expected_d"], following["actual_q"])),
        "exception vstart did not become architectural CSR")
    return response, following


def _fault_uop_writes(path: Path, arch_seq: int, instruction: int,
                      activity: ArchActivity, response_cycle: int) -> List[List[VectorWrite]]:
    pending = {}
    completed = {}
    groups = []
    writes = {write.row: write for write in activity.writes}
    fields = ("insn", "use_vd", "vd", "eew", "vl", "vstart")
    with path.open(newline="", encoding="utf-8") as stream:
        for row_number, row in enumerate(csv.DictReader(stream), 2):
            if row["event"] == "config" or int(row["arch_seq"]) != arch_seq:
                continue
            _fault_require(int(row["cycle"]) <= response_cycle, "uop event after fault response")
            _fault_require(int(row["insn"], 16) == instruction, "uop instruction")
            vid = int(row["vid"])
            metadata = tuple(row[field] for field in fields)
            if row["event"] == "alloc":
                _fault_require(vid not in pending, "overlapping uop ID")
                group = []
                pending[vid] = (metadata, group)
                groups.append(group)
            else:
                if row["event"] == "write":
                    owner = pending.get(vid)
                    if owner is None or owner[0] != metadata:
                        old = completed.get(vid)
                        # The monitor retains metadata after done. BE=0 grants
                        # carry no bytes; accepted final writes may share done's edge.
                        _fault_require(old is not None and old[0] == metadata and
                                       (int(row["be"], 16) == 0 or old[2] == int(row["cycle"])),
                                       "write outside uop lifetime")
                        owner = old
                    owner[1].append(writes[row_number])
                elif row["event"] == "done":
                    _fault_require(vid in pending and pending[vid][0] == metadata,
                                   "unallocated uop or changed uop metadata")
                    completed[vid] = (*pending[vid], int(row["cycle"]))
                    del pending[vid]
                else:
                    _fault_require(False, "unexpected uop event")
    _fault_require(not pending and len(groups) == activity.allocations == activity.completions
                   and bool(groups), "incomplete uop lifecycle")
    return groups


def _prove_load_fault_bytes(activity: ArchActivity, commit: SpikeCommit,
                          pre_state: Dict[int, int], pre_unknown: Dict[int, int],
                          concrete_pre: Dict[Tuple[int, int], Tuple[Optional[int], VectorWrite]],
                          groups: List[List[VectorWrite]], exception_vstart: int,
                          nr_lanes: int, vlen_bits: int) -> Dict[str, object]:
    """Prove maintenance separately from actual load results; never clear taint."""
    reg_bytes = vlen_bits // 8
    width = commit.vector_sew // 8
    nf = (commit.instruction >> 29) + 1
    vd = (commit.instruction >> 7) & 31
    stride = {"mf8": 1, "mf4": 1, "mf2": 1, "m1": 1, "m2": 2,
              "m4": 4, "m8": 8}[commit.vector_lmul]
    required = set()
    for element in range(commit.vector_vstart, exception_vstart):
        for field in range(nf):
            for byte in range(width):
                offset = element * width + byte
                required.add((vd + field * stride + offset // reg_bytes, offset % reg_bytes))
    post_state = dict(pre_state)
    post_state.update(commit.vector_writes)
    partial = bool(required)
    _fault_require(set(commit.vector_writes) == {reg for reg, _ in required},
                   "unsupported partial field effects/reference destinations")
    loaded = set()
    maintained = set()
    accepted = 0
    concrete_only = set()
    maintenance_cycles = {}
    load_cycles = {}
    for group in groups:
        seen = set()
        source = None
        for write in group:
            _fault_require(write.source in (3, 4) and 0 <= write.be <= 255 and
                           0 <= write.lane < nr_lanes and write.be & ~write.known_be == 0,
                           "unknown accepted data or invalid write source/BE/lane")
            source = write.source if source is None else source
            _fault_require(source == write.source, "mixed producer in a uop")
            for key, (value, _) in _architectural_bytes([write], nr_lanes, vlen_bits).items():
                _fault_require(key not in seen, "duplicate accepted byte within uop")
                seen.add(key)
                accepted += 1
                reg, byte = key
                unknown = (pre_unknown.get(reg, 0) >> (8 * byte)) & 255
                prior = concrete_pre.get(key, (None, None))[0]
                _fault_require(prior is not None and reg in pre_state,
                               "missing concrete/reference prestate")
                if source == 3:
                    _fault_require(key not in maintained and key not in loaded,
                                   "duplicate/out-of-order maintenance byte")
                    _fault_require(value == prior, "maintenance changed concrete prestate")
                    expected = (pre_state[reg] >> (8 * byte)) & 255
                    _fault_require(((value ^ expected) & ~unknown & 255) == 0,
                                   "maintenance differs from known reference prestate")
                    _fault_require(not (partial and unknown), "partial fault has unknown prestate")
                    if unknown:
                        concrete_only.add(key)
                    maintained.add(key)
                    maintenance_cycles[key] = write.cycle
                else:
                    _fault_require(key in required and key not in loaded,
                                   "unexpected/duplicate accepted load byte")
                    _fault_require(write.eew == (width.bit_length() - 1), "load data EEW")
                    _fault_require(not unknown, "partial load has unknown reference state")
                    _fault_require(value == ((post_state[reg] >> (8 * byte)) & 255),
                                   "load byte differs from Spike partial poststate")
                    loaded.add(key)
                    load_cycles[key] = write.cycle
        if source == 3:
            registers = {reg for reg, _ in seen}
            _fault_require(len(registers) == 1 and len(seen) == reg_bytes,
                           "incomplete maintenance register")
    _fault_require(loaded == required, "missing required accepted load bytes")
    _fault_require(all(maintenance_cycles[key] < load_cycles[key] for key in maintained & loaded),
                   "maintenance/load accepted-cycle order or simultaneous byte collision")
    final = _architectural_bytes(activity.writes, nr_lanes, vlen_bits)
    for key, (value, _) in final.items():
        reg, byte = key
        unknown = (pre_unknown.get(reg, 0) >> (8 * byte)) & 255
        _fault_require(value is not None and reg in post_state, "unknown final poststate")
        expected = (post_state[reg] >> (8 * byte)) & 255
        _fault_require(((value ^ expected) & ~unknown & 255) == 0, "final poststate mismatch")
        if unknown:
            _fault_require(not partial and value == concrete_pre[key][0],
                           "unknown byte not concretely preserved")
    # Also check untouched bytes in every Spike destination, not just changed bytes.
    for reg, expected in commit.vector_writes.items():
        for byte in range(reg_bytes):
            key = (reg, byte)
            value = final.get(key, concrete_pre.get(key, (None, None)))[0]
            _fault_require(not ((pre_unknown.get(reg, 0) >> (8 * byte)) & 255) and
                           value is not None and value == ((expected >> (8 * byte)) & 255),
                           "missing/incorrect full destination poststate")
    return {"accepted_byte_events": accepted, "final_written_bytes": len(final),
            "required_load_bytes": len(required), "verified_load_bytes": len(loaded),
            "maintenance_bytes": len(maintained), "preserved_unknown_bytes": len(concrete_only),
            "duplicate_bytes": len(maintained & loaded),
            "full_destination_bytes": len(commit.vector_writes) * reg_bytes}


def prove_load_faults(spike_log: Path, commit_trace: Path, vector_trace: Path,
                      probe_log: Path, entry: int) -> List[Dict[str, object]]:
    try:
        return _prove_load_faults(spike_log, commit_trace, vector_trace, probe_log, entry)
    except VectorCommitComparisonError:
        raise
    except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError) as error:
        raise VectorCommitComparisonError(f"load fault proof: malformed/missing evidence: {error}") from error


def _prove_load_faults(spike_log: Path, commit_trace: Path, vector_trace: Path,
                       probe_log: Path, entry: int) -> List[Dict[str, object]]:
    """Fail-closed opt-in proof for one unmasked indexed segment load fault.

    The supported fault is misalignment before the first field of an element.
    Masked, mid-segment, multi-fault and unknown-index cases require other proofs.
    This checks fault effects only, not the scalar or normal vector stream.
    """
    response, following = _fault_probe_pair(probe_log)
    nr_lanes, vlen_bits, activities = _parse_vector_trace(vector_trace)
    starts, retires, trapped = _parse_architecture_mapping(commit_trace)
    arch_seq = int(response["arch_seq"])
    _fault_require(trapped == {arch_seq}, "probe/trapped request identity")
    activity = activities[arch_seq]
    insn = activity.instruction
    _fault_require(int(response["current_insn"], 16) == insn == int(response["req_insn"], 16),
                   "probe instruction identity")
    _fault_require(insn & 127 == 7 and (insn >> 26) & 3 in (1, 3) and
                   (insn >> 25) & 1 == 1 and (insn >> 29) > 0 and (insn >> 28) & 1 == 0,
                   "unsupported load encoding")
    pending = {}
    trap_row = None
    with commit_trace.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["event"] == "arch_start":
                tid = int(row["trans_id"])
                _fault_require(tid not in pending, "overlapping architectural transaction ID")
                pending[tid] = row
            elif row["event"] == "cvx_resp":
                start = pending.pop(int(row["trans_id"]), None)
                if int(row["trap"]):
                    _fault_require(start is not None and int(start["order"]) == arch_seq and
                                   int(start["insn"], 16) == insn and
                                   int(row["trans_id"]) == int(response["trans_id"], 16),
                                   "trap response lifecycle")
                    trap_row = row
    _fault_require(trap_row is not None, "missing trap response")
    commits = _spike_from_entry(spike_log, entry)
    arch_retires = _map_architecture_retires(starts, retires, trapped, allow_incomplete_tail=True)
    mapping = _map_spike_commits(arch_retires, commits)
    lower = max((index for arch, index in mapping.items() if arch < arch_seq), default=-1)
    upper = min((index for arch, index in mapping.items() if arch > arch_seq), default=len(commits))
    matches = [index for index in range(lower + 1, upper) if commits[index].instruction == insn]
    _fault_require(len(matches) == 1, "ambiguous dynamic Spike fault row")
    index = matches[0]
    commit = commits[index]
    start = commit.vector_vstart
    end = int(response["exception_vstart"], 16)
    _fault_require(isinstance(start, int) and isinstance(commit.vector_vl, int) and
                   0 <= start <= end < commit.vector_vl and
                   commit.vector_sew in (8, 16, 32, 64) and
                   commit.vector_lmul in ("mf8", "mf4", "mf2", "m1", "m2", "m4", "m8") and
                   commit.vector_tail_agnostic is False and commit.vector_mask_agnostic is False,
                   "unsupported vector configuration")
    _fault_require(commit.csr_writes == {8: end} and not commit.gpr_writes and
                   not commit.fpr_writes and int(response["csr_vstart_q"], 16) == start and
                   int(response["cause"], 16) == 4, "fault CSR/pre-vstart mismatch")
    pre_state = {}
    pre_unknown = {}
    gprs = {0: 0}
    activity_by_spike = {i: activities[a] for a, i in mapping.items() if a in activities}
    for i, prior in enumerate(commits[:index]):
        before = dict(pre_state)
        pre_state.update(prior.vector_writes)
        gprs.update(prior.gpr_writes)
        if i in activity_by_spike:
            _advance_unknown_state(pre_unknown, activity_by_spike[i], prior, before, vlen_bits)
    index_width = {0: 1, 5: 2, 6: 4, 7: 8}.get((insn >> 12) & 7)
    _fault_require(index_width is not None, "unsupported index EEW")
    reg_bytes = vlen_bits // 8
    base = gprs.get((insn >> 15) & 31)
    _fault_require(base is not None, "missing scalar base")

    def address(element: int) -> int:
        offset = element * index_width
        reg = ((insn >> 20) & 31) + offset // reg_bytes
        shift = 8 * (offset % reg_bytes)
        mask = (1 << (8 * index_width)) - 1
        _fault_require(reg < 32 and reg in pre_state and
                       (pre_unknown.get(reg, 0) >> shift) & mask == 0, "unknown index")
        return (base + ((pre_state[reg] >> shift) & mask)) & ((1 << 64) - 1)

    width = commit.vector_sew // 8
    tval = address(end)
    _fault_require(tval == int(response["tval"], 16) and tval % width != 0,
                   "fault address/cause inconsistent with base/index/SEW")
    nf = (insn >> 29) + 1
    memory = tuple((address(element) + field * width, None)
                   for element in range(start, end) for field in range(nf))
    _fault_require(commit.memory_accesses == memory, "unsupported partial memory effects")
    groups = _fault_uop_writes(vector_trace, arch_seq, insn, activity, int(trap_row["cycle"]))
    first_cycle = min(write.cycle for write in activity.writes)
    _fault_require(all(write.cycle <= int(trap_row["cycle"]) for write in activity.writes),
                   "writes after fault response")
    prior_writes = [write for a in activities.values() for write in a.writes
                    if write.cycle < first_cycle and write.arch_seq != arch_seq and write.be]
    _fault_require(not any(write.arch_seq != arch_seq and
                           first_cycle <= write.cycle <= int(trap_row["cycle"])
                           for a in activities.values() for write in a.writes),
                   "overlapping architecture writes require a separate proof")
    concrete_pre = _architectural_bytes(prior_writes, nr_lanes, vlen_bits)
    counts = _prove_load_fault_bytes(activity, commit, pre_state, pre_unknown, concrete_pre,
                                     groups, end, nr_lanes, vlen_bits)
    inputs = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (spike_log, commit_trace, vector_trace, probe_log)}
    return [{"arch_seq": arch_seq, "index": index, "pc": f"0x{commit.pc:016x}",
             "instruction": f"0x{insn:08x}", "vstart_before": start, "vstart_after": end,
             "expected_fault_csrs": {"0x341": commit.pc, "0x342": 4, "0x343": tval},
             "probe_next_time": int(following["time"]), "inputs": inputs, **counts}]


def compare_vector_commits(
    spike_log: Path,
    commit_trace: Path,
    vector_trace: Path,
    entry: int,
    selected_index: Optional[int] = None,
    stop_spike_index: Optional[int] = None,
    aligned_vector_faults: Optional[List[Dict[str, object]]] = None,
    fault_probe_log: Optional[Path] = None,
) -> Dict[str, object]:
    """Compare non-intrusively observed VRF writebacks with Spike post-state.

    The optional index is one-based among dynamic architectural vector requests that
    declare a vector destination or generate an accepted VRF write. Every byte accepted
    by Ara is compared; no diagnostic instruction is inserted into the program.
    """
    if selected_index is not None and selected_index <= 0:
        raise VectorCommitComparisonError("vector commit index must be positive")
    nr_lanes, vlen_bits, activities = _parse_vector_trace(vector_trace)
    starts, retires, trapped_arch_sequences = _parse_architecture_mapping(commit_trace)
    arch_retires = _map_architecture_retires(
        starts, retires, trapped_arch_sequences, allow_incomplete_tail=True
    )
    commits = _spike_from_entry(spike_log, entry)
    spike_mapping = _map_spike_commits(
        arch_retires,
        commits,
        allow_incomplete_tail=stop_spike_index is not None,
        stop_spike_index=stop_spike_index,
    )

    verified_zero_write_traps: List[int] = []
    verified_identity_write_traps: List[Dict[str, int]] = []
    faults = aligned_vector_faults or []
    proven_loads = (prove_load_faults(spike_log, commit_trace, vector_trace, fault_probe_log, entry)
                    if fault_probe_log is not None else [])
    for proof in proven_loads:
        aligned = [fault for fault in faults if fault.get("index") == proof["index"] and
                   fault.get("pc") == proof["pc"] and fault.get("instruction") == proof["instruction"]]
        _fault_require(len(aligned) == 1 and aligned[0].get("load_fault_proof") == proof and
                       aligned[0].get("matched_fault_csrs") == proof["expected_fault_csrs"],
                       "scalar fault CSR comparison/proof missing or changed")
    proven_arches = {proof["arch_seq"] for proof in proven_loads}
    trapped_in_order = sorted(trapped_arch_sequences)
    if len(faults) == len(trapped_in_order):
        activity_by_spike = {
            spike_index: activities[arch_seq]
            for arch_seq, spike_index in spike_mapping.items()
            if arch_seq in activities
        }
        for arch_seq, fault in zip(trapped_in_order, faults):
            if arch_seq in proven_arches:
                continue
            activity = activities.get(arch_seq)
            if (activity is None or
                    activity.instruction != int(str(fault["instruction"]), 16) or
                    activity.allocations != activity.completions):
                continue
            fault_index = fault.get("index")
            if (not isinstance(fault_index, int) or
                    not 0 <= fault_index < len(commits) or
                    commits[fault_index].pc != int(str(fault.get("pc", "-1")), 16) or
                    commits[fault_index].instruction != activity.instruction):
                continue
            fault_commit = commits[fault_index]
            if (all(write.be == 0 for write in activity.writes) and
                    not fault_commit.vector_writes and not fault_commit.memory_accesses and
                    not fault_commit.gpr_writes and not fault_commit.fpr_writes):
                verified_zero_write_traps.append(arch_seq)
                continue
            pre_state: Dict[int, int] = {}
            pre_unknown: Dict[int, int] = {}
            for index, commit in enumerate(commits[:fault_index]):
                before = dict(pre_state)
                pre_state.update(commit.vector_writes)
                prior_activity = activity_by_spike.get(index)
                if prior_activity is not None:
                    _advance_unknown_state(
                        pre_unknown, prior_activity, commit, before, vlen_bits
                    )
            byte_count = _identity_trap_write_bytes(
                activity, pre_state, pre_unknown, nr_lanes, vlen_bits,
                allow_load=_known_identity_load_fault(activity, commits[fault_index], fault),
            )
            if byte_count:
                verified_identity_write_traps.append({
                    "arch_seq": arch_seq, "compared_bytes": byte_count
                })

    complete_stream_candidates = [
        arch_seq for arch_seq, activity in sorted(activities.items())
        if activity.use_vd or activity.writes
    ]
    all_candidates = [
        arch_seq for arch_seq in complete_stream_candidates
        if stop_spike_index is None or arch_seq in spike_mapping
    ]
    verified_identity_arch_seqs = {
        item["arch_seq"] for item in verified_identity_write_traps
    } | proven_arches
    verified_trap_candidates = sorted(
        arch_seq for arch_seq in all_candidates
        if arch_seq in verified_zero_write_traps or arch_seq in verified_identity_arch_seqs
    )
    incomplete_requests = [
        arch_seq for arch_seq in all_candidates
        if activities[arch_seq].completions != activities[arch_seq].allocations
    ]
    unretired_requests = [
        arch_seq for arch_seq in all_candidates
        if arch_seq not in arch_retires and
        arch_seq not in verified_zero_write_traps and
        arch_seq not in verified_identity_arch_seqs
    ]
    candidates = [
        arch_seq for arch_seq in all_candidates
        if arch_seq not in incomplete_requests and arch_seq in arch_retires
    ]
    if selected_index is not None:
        if selected_index > len(all_candidates):
            raise VectorCommitComparisonError(
                f"selected vector commit {selected_index} exceeds {len(all_candidates)} vector-destination requests"
            )
        selected_arch_seq = all_candidates[selected_index - 1]
        if selected_arch_seq not in candidates:
            raise VectorCommitComparisonError(
                f"selected vector commit {selected_index} is incomplete or has not retired"
            )
        candidates = [selected_arch_seq]

    expected_state: Dict[int, int] = {}
    unknown_state: Dict[int, int] = {}
    activity_by_spike = {
        spike_mapping[arch_seq]: activities[arch_seq]
        for arch_seq in activities
        if arch_seq in spike_mapping
    }
    commit_cursor = 0
    records: List[Dict[str, object]] = []
    first_mismatch: Optional[Dict[str, object]] = None
    compared_bytes = 0
    skipped_bytes = 0
    source_names = {0: "ALU", 1: "MFPU", 2: "MASKU", 3: "SLDU", 4: "VLDU"}
    non_bit_exact_instructions = 0
    unobservable_instructions = 0

    for arch_seq in candidates:
        activity = activities[arch_seq]
        spike_index = spike_mapping.get(arch_seq)
        retire = arch_retires.get(arch_seq)
        if spike_index is None or retire is None:
            raise VectorCommitComparisonError(
                f"write-producing architecture request {arch_seq} has no architectural retirement"
            )
        # Advance through every instruction preceding this vector request, then
        # snapshot the exact predicate/old-destination state seen by it.
        while commit_cursor < spike_index:
            pre_commit_state = dict(expected_state)
            for register, value in commits[commit_cursor].vector_writes.items():
                expected_state[register] = value
            prior_activity = activity_by_spike.get(commit_cursor)
            if prior_activity is not None:
                _advance_unknown_state(
                    unknown_state, prior_activity, commits[commit_cursor],
                    pre_commit_state, vlen_bits,
                )
            commit_cursor += 1
        pre_state = dict(expected_state)
        for register, value in commits[spike_index].vector_writes.items():
            expected_state[register] = value
        _advance_unknown_state(
            unknown_state, activity, commits[spike_index], pre_state, vlen_bits
        )
        commit_cursor = spike_index + 1

        actual = _architectural_bytes(activity.writes, nr_lanes, vlen_bits)
        non_bit_exact = _is_non_bit_exact_vector_result(activity.instruction)
        unknown_write_bytes = sum(
            bin(write.be & ~write.known_be & 0xFF).count("1") for write in activity.writes
        )
        mismatches: List[Dict[str, object]] = []
        checked = 0
        skipped = 0
        destination_registers = commits[spike_index].vector_writes.keys()
        for register in destination_registers:
            before = pre_state.get(register)
            after = expected_state.get(register)
            if before is None or after is None:
                continue
            for byte in range(vlen_bits // 8):
                if (register, byte) in actual:
                    continue
                compare_mask = _architectural_compare_mask(
                    activity, register, byte, vlen_bits, pre_state,
                    destination_registers,
                    commits[spike_index].vector_vl,
                    commits[spike_index].vector_vstart,
                    commits[spike_index].vector_tail_agnostic,
                    commits[spike_index].vector_mask_agnostic,
                )
                compare_mask &= ~(
                    (unknown_state.get(register, 0) >> (8 * byte)) & 0xFF
                )
                changed = ((before ^ after) >> (8 * byte)) & compare_mask
                if changed:
                    mismatches.append({
                        "reason": "missing_changed_vrf_write",
                        "register": f"v{register}",
                        "byte": byte,
                        "expected": f"0x{(after >> (8 * byte)) & 0xFF:02x}",
                        "pre_state": f"0x{(before >> (8 * byte)) & 0xFF:02x}",
                        "compare_mask": f"0x{compare_mask:02x}",
                    })
        for (register, byte), (value, write) in sorted(actual.items()):
            if non_bit_exact:
                skipped += 1
                continue
            if value is None:
                skipped += 1
                continue
            expected_register = expected_state.get(register)
            if expected_register is None:
                skipped += 1
                continue
            expected = (expected_register >> (8 * byte)) & 0xFF
            compare_mask = _architectural_compare_mask(
                activity, register, byte, vlen_bits, pre_state,
                commits[spike_index].vector_writes.keys(),
                commits[spike_index].vector_vl,
                commits[spike_index].vector_vstart,
                commits[spike_index].vector_tail_agnostic,
                commits[spike_index].vector_mask_agnostic,
            )
            compare_mask &= ~((unknown_state.get(register, 0) >> (8 * byte)) & 0xFF)
            if not compare_mask:
                skipped += 1
                continue
            checked += 1
            if ((value ^ expected) & compare_mask) != 0:
                mismatches.append({
                    "register": f"v{register}",
                    "byte": byte,
                    "expected": f"0x{expected:02x}",
                    "actual": f"0x{value:02x}",
                    "compare_mask": f"0x{compare_mask:02x}",
                    "cycle": write.cycle,
                    "vid": write.vid,
                    "lane": write.lane,
                    "source": source_names.get(write.source, str(write.source)),
                    "vrf_addr": write.addr,
                    "eew_bits": 8 << write.eew,
                })
        status = "PASS" if not mismatches and checked else "MISMATCH"
        if non_bit_exact and not mismatches:
            status = "NON_BIT_EXACT"
            non_bit_exact_instructions += 1
        elif not checked and not mismatches:
            status = "UNOBSERVABLE"
            unobservable_instructions += 1
        record = {
            "dynamic_index": selected_index if selected_index is not None else len(records) + 1,
            "arch_seq": arch_seq,
            "pc": f"0x{retire.pc:016x}",
            "instruction": f"0x{activity.instruction:08x}",
            "status": status,
            "uops": activity.allocations,
            "write_events": len(activity.writes),
            "compared_bytes": checked,
            "skipped_unknown_bytes": skipped,
            "unknown_write_bytes": unknown_write_bytes,
            "mismatch_count": len(mismatches),
            "first_mismatch": mismatches[0] if mismatches else None,
        }
        records.append(record)
        compared_bytes += checked
        skipped_bytes += skipped
        if mismatches and first_mismatch is None:
            first_mismatch = {**record, "first_mismatch": mismatches[0]}

    status = "PASS"
    if first_mismatch is not None:
        status = "MISMATCH"
    elif stop_spike_index is not None:
        status = "PREFIX"
    elif incomplete_requests or unretired_requests:
        status = "PREFIX"
    elif not records or compared_bytes == 0:
        status = "UNOBSERVABLE"
    return {
        "status": status,
        "method": (
            "non-intrusive accepted VRF writeback comparison, grouped by architectural "
            "request and deshuffled by destination EEW"
        ),
        "nr_lanes": nr_lanes,
        "vlen_bits": vlen_bits,
        "selected_index": selected_index,
        "vector_destination_requests": len(complete_stream_candidates),
        "prefix_vector_destination_requests": len(all_candidates),
        "stopped_at_spike_index": stop_spike_index,
        "compared_instructions": len(records),
        "compared_bytes": compared_bytes,
        "skipped_unknown_bytes": skipped_bytes,
        "non_bit_exact_instructions": non_bit_exact_instructions,
        "unobservable_instructions": unobservable_instructions,
        "incomplete_requests": incomplete_requests,
        "unretired_requests": unretired_requests,
        "trapped_requests": sorted(trapped_arch_sequences),
        "verified_zero_write_traps": verified_zero_write_traps,
        "verified_identity_write_traps": verified_identity_write_traps,
        "verified_probed_load_faults": proven_loads,
        "verified_trapped_destination_requests": verified_trap_candidates,
        "first_mismatch": first_mismatch,
        "instructions": records,
    }


__all__ = [
    "VectorCommitComparisonError",
    "compare_vector_commits",
    "unobservable_vector_scalar_write_indices",
]
