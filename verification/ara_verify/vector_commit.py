from __future__ import annotations

import csv
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
    arch_mapping: Dict[int, VectorRetire], commits: List[SpikeCommit]
) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    cursor = 0
    for arch_seq, retire in sorted(arch_mapping.items()):
        while cursor < len(commits):
            commit = commits[cursor]
            cursor += 1
            if commit.pc == retire.pc and commit.instruction == retire.instruction:
                mapping[arch_seq] = cursor - 1
                break
        else:
            raise VectorCommitComparisonError(
                f"cannot find Spike commit for architecture request {arch_seq} at "
                f"pc=0x{retire.pc:016x} insn=0x{retire.instruction:08x}"
            )
    return mapping


def _vector_scalar_source_unknown(
    commit: SpikeCommit, unknown_state: Dict[int, int]
) -> bool:
    """Return whether a vector-to-scalar result consumes an unknown element 0."""
    instruction = commit.instruction
    opcode = instruction & 0x7F
    funct3 = (instruction >> 12) & 0x7
    funct6 = (instruction >> 26) & 0x3F
    # vmv.x.s and vfmv.f.s share funct6=010000 and read element 0 of vs2.
    if opcode != 0x57 or funct6 != 0x10 or funct3 not in {0x1, 0x2}:
        return False
    if commit.vector_sew not in {8, 16, 32, 64}:
        return False
    vs2 = (instruction >> 20) & 0x1F
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
    spike_mapping = _map_spike_commits(arch_retires, commits)
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
        if _vector_scalar_source_unknown(commit, unknown_state):
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


def compare_vector_commits(
    spike_log: Path,
    commit_trace: Path,
    vector_trace: Path,
    entry: int,
    selected_index: Optional[int] = None,
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
    spike_mapping = _map_spike_commits(arch_retires, commits)

    all_candidates = [
        arch_seq for arch_seq, activity in sorted(activities.items())
        if activity.use_vd or activity.writes
    ]
    incomplete_requests = [
        arch_seq for arch_seq in all_candidates
        if activities[arch_seq].completions != activities[arch_seq].allocations
    ]
    unretired_requests = [
        arch_seq for arch_seq in all_candidates if arch_seq not in arch_retires
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
        "vector_destination_requests": len(all_candidates),
        "compared_instructions": len(records),
        "compared_bytes": compared_bytes,
        "skipped_unknown_bytes": skipped_bytes,
        "non_bit_exact_instructions": non_bit_exact_instructions,
        "unobservable_instructions": unobservable_instructions,
        "incomplete_requests": incomplete_requests,
        "unretired_requests": unretired_requests,
        "trapped_requests": sorted(trapped_arch_sequences),
        "first_mismatch": first_mismatch,
        "instructions": records,
    }


__all__ = [
    "VectorCommitComparisonError",
    "compare_vector_commits",
    "unobservable_vector_scalar_write_indices",
]
