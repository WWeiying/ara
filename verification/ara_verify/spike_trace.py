from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from .trace import is_vector_instruction


class CommitComparisonError(ValueError):
    pass


@dataclass(frozen=True)
class SpikeCommit:
    pc: int
    instruction: int
    gpr_writes: Dict[int, int]
    fpr_writes: Dict[int, int]
    vector_writes: Dict[int, int]
    csr_writes: Dict[int, int]
    memory_accesses: Tuple[Tuple[int, Optional[int]], ...]
    vector_sew: Optional[int] = None
    vector_lmul: Optional[str] = None
    vector_vl: Optional[int] = None
    vector_vstart: Optional[int] = None
    vector_vtype: Optional[int] = None
    vector_tail_agnostic: Optional[bool] = None
    vector_mask_agnostic: Optional[bool] = None


@dataclass(frozen=True)
class AraRetire:
    order: int
    pc: int
    instruction: int
    rd: int
    rd_value: Optional[int]
    rd_value_raw: str
    mem_addr: Optional[int]
    mem_rmask: Optional[int]
    mem_wmask: Optional[int]
    mem_wdata: Optional[int]
    trap: bool


_SPIKE_COMMIT_RE = re.compile(
    r"^core\s+\d+:\s+\d+\s+(0x[0-9a-fA-F]+)\s+\((0x[0-9a-fA-F]+)\)(.*)$"
)
_GPR_WRITE_RE = re.compile(r"(?:^|\s)x(\d+)\s+(0x[0-9a-fA-F]+)")
_FPR_WRITE_RE = re.compile(r"(?:^|\s)f(\d+)\s+(0x[0-9a-fA-F]+)")
_VECTOR_WRITE_RE = re.compile(r"(?:^|\s)v(\d+)\s+(0x[0-9a-fA-F]+)")
_CSR_WRITE_RE = re.compile(r"(?:^|\s)c(\d+)_\S+\s+(0x[0-9a-fA-F]+)")
_MEMORY_RE = re.compile(
    r"(?:^|\s)mem\s+(0x[0-9a-fA-F]+)(?:\s+(0x[0-9a-fA-F]+))?"
)
_VECTOR_CONTEXT_RE = re.compile(
    r"^\s+e(8|16|32|64)\s+(mf8|mf4|mf2|m1|m2|m4|m8)\s+l(\d+)(?:\s|$)"
)


def _optional_hex(value: str) -> Optional[int]:
    if not value or re.search(r"[xz]", value, re.IGNORECASE):
        return None
    return int(value, 16)


def _iter_spike_commits(path: Path) -> Iterator[SpikeCommit]:
    try:
        file = path.open(encoding="utf-8", errors="replace")
    except OSError as error:
        raise CommitComparisonError(f"cannot read Spike log: {error}") from error

    vector_vstart = 0
    vector_vtype: Optional[int] = None
    with file:
        for line in file:
            match = _SPIKE_COMMIT_RE.match(line)
            if match is None:
                continue
            suffix = match.group(3)
            csr_writes = {
                int(csr): int(value, 16) for csr, value in _CSR_WRITE_RE.findall(suffix)
            }
            vector_context = _VECTOR_CONTEXT_RE.match(suffix)
            commit = SpikeCommit(
                pc=int(match.group(1), 16),
                instruction=int(match.group(2), 16),
                gpr_writes={
                    int(reg): int(value, 16) for reg, value in _GPR_WRITE_RE.findall(suffix)
                },
                fpr_writes={
                    int(reg): int(value, 16) for reg, value in _FPR_WRITE_RE.findall(suffix)
                },
                vector_writes={
                    int(reg): int(value, 16)
                    for reg, value in _VECTOR_WRITE_RE.findall(suffix)
                },
                csr_writes=csr_writes,
                memory_accesses=tuple(
                    (int(address, 16), int(value, 16) if value else None)
                    for address, value in _MEMORY_RE.findall(suffix)
                ),
                vector_sew=int(vector_context.group(1)) if vector_context else None,
                vector_lmul=vector_context.group(2) if vector_context else None,
                vector_vl=int(vector_context.group(3)) if vector_context else None,
                vector_vstart=vector_vstart if vector_context else None,
                vector_vtype=vector_vtype if vector_context else None,
                vector_tail_agnostic=(
                    bool((vector_vtype >> 6) & 1)
                    if vector_context and vector_vtype is not None else None
                ),
                vector_mask_agnostic=(
                    bool((vector_vtype >> 7) & 1)
                    if vector_context and vector_vtype is not None else None
                ),
            )
            if 0x008 in csr_writes:
                vector_vstart = csr_writes[0x008]
            if 0xC21 in csr_writes:
                vector_vtype = csr_writes[0xC21]
            yield commit


def parse_spike_commits(path: Path) -> List[SpikeCommit]:
    commits = list(_iter_spike_commits(path))
    if not commits:
        raise CommitComparisonError("Spike log contains no commit records")
    return commits


def _iter_ara_retire(path: Path) -> Iterator[AraRetire]:
    required = {"event", "order", "pc", "insn", "rd", "rd_wdata", "trap"}
    try:
        file = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise CommitComparisonError(f"cannot read Ara commit trace: {error}") from error

    with file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            missing = sorted(required.difference(reader.fieldnames or []))
            raise CommitComparisonError(f"Ara trace is missing columns: {', '.join(missing)}")
        for row in reader:
            if row["event"] != "retire":
                continue
            try:
                yield AraRetire(
                    order=int(row["order"]),
                    pc=int(row["pc"], 16),
                    instruction=int(row["insn"], 16),
                    rd=int(row["rd"]),
                    rd_value=(
                        None if re.search(r"[xz]", row["rd_wdata"], re.IGNORECASE)
                        else int(row["rd_wdata"], 16)
                    ),
                    rd_value_raw=row["rd_wdata"],
                    mem_addr=_optional_hex(row.get("mem_addr", "")),
                    mem_rmask=_optional_hex(row.get("mem_rmask", "")),
                    mem_wmask=_optional_hex(row.get("mem_wmask", "")),
                    mem_wdata=_optional_hex(row.get("mem_wdata", "")),
                    trap=bool(int(row["trap"])),
                )
            except ValueError as error:
                raise CommitComparisonError(f"invalid Ara retire record: {row}") from error


def parse_ara_retire(path: Path) -> List[AraRetire]:
    retires = list(_iter_ara_retire(path))
    if not retires:
        raise CommitComparisonError("Ara trace contains no retire records")
    return retires


def _commit_dict(commit: Optional[SpikeCommit]) -> Optional[Dict[str, object]]:
    if commit is None:
        return None
    return {
        "pc": f"0x{commit.pc:016x}",
        "instruction": f"0x{commit.instruction:08x}",
        "gpr_writes": {f"x{reg}": f"0x{value:016x}" for reg, value in commit.gpr_writes.items()},
        "fpr_writes": {f"f{reg}": f"0x{value:016x}" for reg, value in commit.fpr_writes.items()},
        "vector_write_registers": [f"v{reg}" for reg in commit.vector_writes],
        "csr_writes": {f"0x{csr:03x}": f"0x{value:016x}" for csr, value in commit.csr_writes.items()},
        "vector_context": (
            {
                "sew": commit.vector_sew,
                "lmul": commit.vector_lmul,
                "vl": commit.vector_vl,
                "vstart": commit.vector_vstart,
                "vtype": (
                    f"0x{commit.vector_vtype:016x}"
                    if commit.vector_vtype is not None else None
                ),
                "tail_agnostic": commit.vector_tail_agnostic,
                "mask_agnostic": commit.vector_mask_agnostic,
            }
            if commit.vector_vl is not None else None
        ),
        "memory_accesses": [
            {
                "address": f"0x{address:016x}",
                "write_value": f"0x{value:x}" if value is not None else None,
            }
            for address, value in commit.memory_accesses
        ],
    }


def _retire_dict(retire: Optional[AraRetire]) -> Optional[Dict[str, object]]:
    if retire is None:
        return None
    return {
        "order": retire.order,
        "pc": f"0x{retire.pc:016x}",
        "instruction": f"0x{retire.instruction:08x}",
        "rd": retire.rd,
        "rd_value": (
            f"0x{retire.rd_value:016x}" if retire.rd_value is not None
            else retire.rd_value_raw
        ),
        "trap": retire.trap,
        "memory": {
            "address": f"0x{retire.mem_addr:016x}" if retire.mem_addr is not None else None,
            "rmask": f"0x{retire.mem_rmask:02x}" if retire.mem_rmask is not None else None,
            "wmask": f"0x{retire.mem_wmask:02x}" if retire.mem_wmask is not None else None,
            "wdata": f"0x{retire.mem_wdata:016x}" if retire.mem_wdata is not None else None,
        },
    }


def _packed_store_value(mask: int, data: int) -> int:
    packed = 0
    packed_byte = 0
    for byte in range(8):
        if mask & (1 << byte):
            packed |= ((data >> (8 * byte)) & 0xFF) << (8 * packed_byte)
            packed_byte += 1
    return packed


def _set_bit_count(value: int) -> int:
    return bin(value).count("1")


def _scalar_memory_access(instruction: int) -> Optional[Tuple[str, int]]:
    if instruction & 0x3 != 0x3 or is_vector_instruction(instruction):
        return None
    opcode = instruction & 0x7F
    funct3 = (instruction >> 12) & 0x7
    if opcode == 0x03:
        widths = {0: 1, 1: 2, 2: 4, 3: 8, 4: 1, 5: 2, 6: 4}
        return ("read", widths[funct3]) if funct3 in widths else None
    if opcode == 0x23:
        widths = {0: 1, 1: 2, 2: 4, 3: 8}
        return ("write", widths[funct3]) if funct3 in widths else None
    if opcode == 0x07 and funct3 in {2, 3}:
        return "read", 4 if funct3 == 2 else 8
    if opcode == 0x27 and funct3 in {2, 3}:
        return "write", 4 if funct3 == 2 else 8
    if opcode == 0x2F and funct3 in {2, 3}:
        return "amo", 4 if funct3 == 2 else 8
    return None


def compare_commit_prefix(
    spike_log: Path,
    ara_trace: Path,
    entry: int,
    unobservable_register_value_indices: Optional[Set[int]] = None,
) -> Dict[str, object]:
    spike_source = _iter_spike_commits(spike_log)
    saw_spike_commit = False
    first_spike: Optional[SpikeCommit] = None
    for commit in spike_source:
        saw_spike_commit = True
        if commit.pc == entry:
            first_spike = commit
            break
    if first_spike is None:
        if not saw_spike_commit:
            raise CommitComparisonError("Spike log contains no commit records")
        raise CommitComparisonError(f"Spike did not execute ELF entry 0x{entry:016x}")

    def spike_from_entry() -> Iterator[SpikeCommit]:
        yield first_spike
        yield from spike_source

    spike_iter = spike_from_entry()
    ara_iter = _iter_ara_retire(ara_trace)
    spike_count = 0
    spike_vector_writes = 0
    ara_retired = 0
    ara_committed = 0
    ara_traps = 0

    def take_spike() -> Optional[SpikeCommit]:
        nonlocal spike_count, spike_vector_writes
        try:
            item = next(spike_iter)
        except StopIteration:
            return None
        spike_count += 1
        spike_vector_writes += bool(item.vector_writes)
        return item

    def take_ara_commit() -> Optional[AraRetire]:
        nonlocal ara_retired, ara_committed, ara_traps
        for item in ara_iter:
            ara_retired += 1
            if item.trap:
                ara_traps += 1
                continue
            ara_committed += 1
            return item
        return None

    matched = 0
    scalar_writes = 0
    floating_writes = 0
    scalar_memory_accesses = 0
    scalar_state = [0] * 32
    floating_state = [0] * 32
    unobservable_register_value_indices = unobservable_register_value_indices or set()
    skipped_unobservable_register_values = 0
    stopped_at_unobservable: Optional[Dict[str, object]] = None
    mismatch: Optional[Dict[str, object]] = None
    last_matched: Optional[SpikeCommit] = None
    expected = take_spike()
    actual = take_ara_commit()
    if ara_retired == 0 and actual is None:
        raise CommitComparisonError("Ara trace contains no retire records")

    while expected is not None and actual is not None:
        index = matched
        if expected.pc != actual.pc or expected.instruction != actual.instruction:
            mismatch = {
                "index": index,
                "reason": "pc_or_instruction",
                "spike": _commit_dict(expected),
                "ara": _retire_dict(actual),
            }
            break
        expected_writes = {
            register: value for register, value in expected.gpr_writes.items() if register != 0
        }
        expected_fpr_writes = expected.fpr_writes
        expects_register_write = bool(expected_writes or expected_fpr_writes)
        value_is_unobservable = index in unobservable_register_value_indices
        if (expects_register_write and not actual.trap and actual.rd_value is None
                and not value_is_unobservable):
            mismatch = {
                "index": index,
                "reason": "unknown_register_value",
                "spike": _commit_dict(expected),
                "ara": _retire_dict(actual),
            }
            break
        actual_writes = ({actual.rd: actual.rd_value}
                         if not expected_fpr_writes and actual.rd != 0 and not actual.trap
                         else {})
        actual_fpr_writes = ({actual.rd: actual.rd_value}
                             if expected_fpr_writes and not actual.trap else {})
        if expected_writes.keys() != actual_writes.keys():
            mismatch = {
                "index": index,
                "reason": "gpr_write_set",
                "spike": _commit_dict(expected),
                "ara": _retire_dict(actual),
            }
            break
        if expected_writes != actual_writes and not value_is_unobservable:
            mismatch = {
                "index": index,
                "reason": "gpr_value",
                "spike": _commit_dict(expected),
                "ara": _retire_dict(actual),
            }
            break
        if expected_fpr_writes.keys() != actual_fpr_writes.keys():
            mismatch = {
                "index": index,
                "reason": "fpr_write_set",
                "spike": _commit_dict(expected),
                "ara": _retire_dict(actual),
            }
            break
        if expected_fpr_writes != actual_fpr_writes and not value_is_unobservable:
            mismatch = {
                "index": index,
                "reason": "fpr_value",
                "spike": _commit_dict(expected),
                "ara": _retire_dict(actual),
            }
            break
        state_writes = expected_writes if value_is_unobservable else actual_writes
        state_fpr_writes = (
            expected_fpr_writes if value_is_unobservable else actual_fpr_writes
        )
        for register, value in state_writes.items():
            scalar_state[register] = value
            scalar_writes += 1
        for register, value in state_fpr_writes.items():
            floating_state[register] = value
            floating_writes += 1
        skipped_unobservable_register_values += int(
            value_is_unobservable and expects_register_write
        )

        memory_access = _scalar_memory_access(expected.instruction)
        if memory_access is not None and expected.memory_accesses:
            kind, width = memory_access
            expected_address, expected_store_value = expected.memory_accesses[0]
            actual_mask = actual.mem_wmask if kind in {"write", "amo"} else actual.mem_rmask
            if (actual.mem_addr != expected_address or actual_mask is None or
                    _set_bit_count(actual_mask) != width):
                mismatch = {
                    "index": index,
                    "reason": "scalar_memory_address_or_mask",
                    "spike": _commit_dict(expected),
                    "ara": _retire_dict(actual),
                }
                break
            if kind in {"write", "amo"} and expected_store_value is not None:
                if actual.mem_wdata is None or _packed_store_value(
                    actual_mask, actual.mem_wdata
                ) != (expected_store_value & ((1 << (8 * width)) - 1)):
                    mismatch = {
                        "index": index,
                        "reason": "scalar_memory_write_value",
                        "spike": _commit_dict(expected),
                        "ara": _retire_dict(actual),
                    }
                    break
            scalar_memory_accesses += 1
        matched += 1
        last_matched = expected
        expected = take_spike()
        actual = take_ara_commit()
        if value_is_unobservable and expects_register_write and (
            expected is not None or actual is not None
        ):
            stopped_at_unobservable = {
                "index": index,
                "pc": f"0x{last_matched.pc:016x}",
                "instruction": f"0x{last_matched.instruction:08x}",
                "reason": "downstream scalar state depends on an architecturally "
                          "unobservable vector-to-scalar result",
            }
            break

    if mismatch is not None:
        status = "MISMATCH"
    elif stopped_at_unobservable is not None:
        status = "PREFIX"
    elif expected is None and actual is not None:
        status = "MISMATCH"
        mismatch = {
            "index": matched,
            "reason": "ara_retired_beyond_spike",
            "spike": None,
            "ara": _retire_dict(actual),
        }
    elif expected is not None:
        status = "PREFIX"
    else:
        status = "MATCH"

    next_spike = expected
    # Drain both streams to retain the existing total-count fields without
    # retaining millions of commit objects in memory.
    while take_spike() is not None:
        pass
    while take_ara_commit() is not None:
        pass
    scalar_state_bytes = b"".join(value.to_bytes(8, "little") for value in scalar_state)
    floating_state_bytes = b"".join(value.to_bytes(8, "little") for value in floating_state)
    return {
        "status": status,
        "entry": f"0x{entry:016x}",
        "matched_instructions": matched,
        "matched_scalar_writes": scalar_writes,
        "matched_floating_writes": floating_writes,
        "skipped_unobservable_register_values": skipped_unobservable_register_values,
        "stopped_at_unobservable": stopped_at_unobservable,
        "matched_scalar_memory_accesses": scalar_memory_accesses,
        "ara_retired_instructions": ara_retired,
        "ara_committed_instructions": ara_committed,
        "ara_trap_events": ara_traps,
        "spike_instructions_from_entry": spike_count,
        "spike_vector_write_instructions": spike_vector_writes,
        "last_matched": _commit_dict(last_matched),
        "next_spike": _commit_dict(next_spike),
        "mismatch": mismatch,
        "matched_prefix_scalar_state": {
            "sha256": hashlib.sha256(scalar_state_bytes).hexdigest(),
            "nonzero_registers": {
                f"x{register}": f"0x{value:016x}"
                for register, value in enumerate(scalar_state) if value != 0
            },
        },
        "matched_prefix_floating_state": {
            "sha256": hashlib.sha256(floating_state_bytes).hexdigest(),
            "nonzero_registers": {
                f"f{register}": f"0x{value:016x}"
                for register, value in enumerate(floating_state) if value != 0
            },
        },
        "scope": (
            "pc, instruction encoding, exact GPR/FPR write set and value, reconstructed "
            "GPR/FPR state, uncompressed scalar memory address/mask/write data, and "
            "explicit accounting for trap-marked RVFI rows omitted by Spike commit logs"
        ),
        "vector_state_compared": False,
    }
