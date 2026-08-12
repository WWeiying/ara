from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List


class TraceValidationError(ValueError):
    pass


def is_vector_instruction(instruction: int) -> bool:
    opcode = instruction & 0x7F
    funct3 = (instruction >> 12) & 0x7
    if opcode == 0x57:
        return True
    # Opcodes 0x07 and 0x27 are shared with scalar FP loads/stores.
    if opcode in {0x07, 0x27} and funct3 not in {0x2, 0x3}:
        return True
    # CVA6 also offloads accesses to the architected vector CSRs over CVXIF.
    # These participate in the same request/retire ordering check even though
    # their opcode is SYSTEM rather than a vector opcode.
    vector_csrs = {0x008, 0x009, 0x00A, 0x00F, 0xC20, 0xC21, 0xC22}
    csr = (instruction >> 20) & 0xFFF
    return opcode == 0x73 and funct3 != 0 and csr in vector_csrs


def _is_side_effect_free_vector_csr_read(instruction: int) -> bool:
    opcode = instruction & 0x7F
    funct3 = (instruction >> 12) & 0x7
    rs1 = (instruction >> 15) & 0x1F
    csr = (instruction >> 20) & 0xFFF
    vector_csrs = {0x008, 0x009, 0x00A, 0x00F, 0xC20, 0xC21, 0xC22}
    return opcode == 0x73 and funct3 in {2, 3} and rs1 == 0 and csr in vector_csrs


def _is_transport_replay(instruction: int, previous_request: int | None) -> bool:
    if not _is_side_effect_free_vector_csr_read(instruction):
        return False
    rd = (instruction >> 7) & 0x1F
    return rd == 0 or instruction == previous_request


def _validate_retired_request_sequence(
    retired: List[int], requested: List[int]
) -> int:
    """Match architectural retirement while accounting for harmless CSR-read replay.

    CVA6 can present a zero-destination vector CSR read more than once around a
    serialization boundary. These reads have no architectural destination and
    allocate no Ara backend uop. Keep them visible as transport replays, but do
    not require an extra RVFI retirement. No data-processing or memory request
    is eligible for this exception.
    """
    retire_index = 0
    request_index = 0
    replay_count = 0
    while retire_index < len(retired) and request_index < len(requested):
        if retired[retire_index] == requested[request_index]:
            retire_index += 1
            request_index += 1
        elif _is_transport_replay(
            requested[request_index],
            requested[request_index - 1] if request_index else None,
        ):
            replay_count += 1
            request_index += 1
        else:
            raise TraceValidationError(
                "retired-vector/CVX-request sequence mismatch at index "
                f"{retire_index} ({len(retired)} retired, {len(requested)} requested)"
            )

    while request_index < len(requested) and _is_transport_replay(
        requested[request_index],
        requested[request_index - 1] if request_index else None,
    ):
        replay_count += 1
        request_index += 1

    if retire_index != len(retired) or request_index != len(requested):
        raise TraceValidationError(
            "retired-vector/CVX-request sequence length mismatch after CSR replay filtering "
            f"({len(retired)} retired, {len(requested)} requested)"
        )
    return replay_count


def _integer(row: Dict[str, str], field: str, base: int = 10) -> int:
    value = row.get(field, "")
    try:
        return int(value, base)
    except ValueError as error:
        raise TraceValidationError(f"invalid {field}: {value!r}") from error


def validate_trace(path: Path) -> Dict[str, int]:
    required = {"cycle", "event", "order", "trans_id", "insn"}
    retired_vector: List[int] = []
    requested_vector: List[int] = []
    pending: Dict[int, tuple[int, int]] = {}
    expected_order = 0
    retire_count = 0
    response_count = 0
    trapped_request_indices: set[int] = set()
    row_count = 0
    max_inflight = 0
    next_arch_order = 0
    arch_instructions: List[int] = []
    pending_uops: Dict[int, tuple[int, int]] = {}
    uop_alloc_count = 0
    uop_done_count = 0
    uop_max_inflight = 0
    first_cycle = -1
    last_cycle = -1

    try:
        file = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise TraceValidationError(f"cannot read trace: {error}") from error

    with file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            missing = sorted(required.difference(reader.fieldnames or []))
            raise TraceValidationError(f"trace is missing columns: {', '.join(missing)}")

        for row in reader:
            row_count += 1
            cycle = _integer(row, "cycle")
            if first_cycle < 0:
                first_cycle = cycle
            if cycle < last_cycle:
                raise TraceValidationError(f"cycle moved backwards at row {row_count}")
            last_cycle = cycle

            event = row["event"]
            instruction = _integer(row, "insn", 16)
            if event == "retire":
                order = _integer(row, "order")
                if order != expected_order:
                    raise TraceValidationError(
                        f"retire order discontinuity: expected {expected_order}, found {order}"
                    )
                expected_order += 1
                retire_count += 1
                if is_vector_instruction(instruction):
                    retired_vector.append(instruction)
            elif event == "cvx_req":
                trans_id = _integer(row, "trans_id")
                if not is_vector_instruction(instruction):
                    raise TraceValidationError(
                        f"CVX request {trans_id} is not a vector instruction: {instruction:08x}"
                    )
                if trans_id in pending:
                    raise TraceValidationError(f"duplicate in-flight transaction ID {trans_id}")
                pending[trans_id] = (instruction, len(requested_vector))
                requested_vector.append(instruction)
                max_inflight = max(max_inflight, len(pending))
            elif event == "cvx_resp":
                trans_id = _integer(row, "trans_id")
                if trans_id not in pending:
                    raise TraceValidationError(f"response for unknown transaction ID {trans_id}")
                _, request_index = pending[trans_id]
                trap_text = row.get("trap", "0") or "0"
                try:
                    response_trap = int(trap_text, 10)
                except ValueError as error:
                    raise TraceValidationError(f"invalid trap: {trap_text!r}") from error
                if response_trap:
                    trapped_request_indices.add(request_index)
                del pending[trans_id]
                response_count += 1
            elif event == "arch_start":
                arch_order = _integer(row, "order")
                if arch_order != next_arch_order:
                    raise TraceValidationError(
                        f"architecture request order discontinuity: expected "
                        f"{next_arch_order}, found {arch_order}"
                    )
                next_arch_order += 1
                arch_instructions.append(instruction)
            elif event == "uop_alloc":
                arch_order = _integer(row, "order")
                vid = _integer(row, "port")
                if arch_order < 0 or arch_order >= len(arch_instructions):
                    raise TraceValidationError(
                        f"uop allocation references unknown architecture request {arch_order}"
                    )
                if arch_instructions[arch_order] != instruction:
                    raise TraceValidationError(
                        f"uop allocation instruction differs from architecture request {arch_order}"
                    )
                if vid in pending_uops:
                    raise TraceValidationError(f"backend vid {vid} reused before completion")
                pending_uops[vid] = (arch_order, instruction)
                uop_alloc_count += 1
                uop_max_inflight = max(uop_max_inflight, len(pending_uops))
            elif event == "uop_done":
                arch_order = _integer(row, "order")
                vid = _integer(row, "port")
                expected_uop = pending_uops.get(vid)
                if expected_uop is None:
                    raise TraceValidationError(f"completion for unknown backend vid {vid}")
                if expected_uop != (arch_order, instruction):
                    raise TraceValidationError(
                        f"completion metadata differs for backend vid {vid}"
                    )
                del pending_uops[vid]
                uop_done_count += 1
            else:
                raise TraceValidationError(f"unknown trace event: {event!r}")

    if row_count == 0:
        raise TraceValidationError("trace contains no events")
    if pending:
        details = ", ".join(
            f"trans_id={trans_id} insn={metadata[0]:08x}"
            for trans_id, metadata in sorted(pending.items())
        )
        raise TraceValidationError(
            f"trace ends with {len(pending)} CVX requests in flight: {details}"
        )
    if pending_uops:
        details = ", ".join(
            f"vid={vid} arch={metadata[0]} insn={metadata[1]:08x}"
            for vid, metadata in sorted(pending_uops.items())
        )
        raise TraceValidationError(
            f"trace ends with {len(pending_uops)} backend uops in flight: {details}"
        )
    retirable_requests = [
        instruction for index, instruction in enumerate(requested_vector)
        if index not in trapped_request_indices
    ]
    cvx_replay_count = _validate_retired_request_sequence(
        retired_vector, retirable_requests
    )
    arch_request_replay_count = 0
    if arch_instructions:
        arch_request_replay_count = _validate_retired_request_sequence(
            arch_instructions, requested_vector
        )

    return {
        "rows": row_count,
        "first_cycle": first_cycle,
        "last_cycle": last_cycle,
        "retire_count": retire_count,
        "vector_retire_count": len(retired_vector),
        "cvx_request_count": len(requested_vector),
        "cvx_response_count": response_count,
        "cvx_max_inflight": max_inflight,
        "cvx_replay_count": cvx_replay_count,
        "arch_request_replay_count": arch_request_replay_count,
        "cvx_exception_count": len(trapped_request_indices),
        "architecture_request_count": len(arch_instructions),
        "backend_uop_alloc_count": uop_alloc_count,
        "backend_uop_done_count": uop_done_count,
        "backend_uop_max_inflight": uop_max_inflight,
    }
