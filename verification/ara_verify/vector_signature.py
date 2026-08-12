from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class VectorSignatureError(ValueError):
    pass


@dataclass(frozen=True)
class VectorSignatureRewrite:
    source: Path
    policy_rewrites: int
    dynamic_policy_rewrites: int
    vector_registers: int
    bytes_per_register: int
    checkpoints: int = 0
    checkpoint_instructions: tuple[str, ...] = ()
    checkpoint_source_indices: tuple[int, ...] = ()
    scratch_stack_register: str | None = None
    checkpoint_memory_regions: tuple[str, ...] = ()
    checkpoint_memory_sites: tuple[int, ...] = ()
    checkpoint_mask_register: int | None = None

    @property
    def signature_bytes(self) -> int:
        return self.vector_registers * self.bytes_per_register

    @property
    def scalar_check_loads(self) -> int:
        return self.signature_bytes // 8


_BEGIN_MARKER = "# ARA_DSA_VECTOR_SIGNATURE_BEGIN"
_END_MARKER = "# ARA_DSA_VECTOR_SIGNATURE_END"
_POLICY_RE = re.compile(
    r"(?P<prefix>\b(?:vsetvli|vsetivli)\b.*?,\s*)"
    r"(?:ta|tu)(?P<separator>\s*,\s*)(?:ma|mu)"
    r"(?P<suffix>\s*(?:#.*)?)$"
)
_DYNAMIC_VSETVL_RE = re.compile(
    r"\bvsetvl\s+(?P<rd>[a-zA-Z0-9]+)\s*,\s*(?P<rs1>[a-zA-Z0-9]+)\s*,\s*"
    r"(?P<rs2>[a-zA-Z0-9]+)"
)
_LOAD_IMMEDIATE_RE = re.compile(
    r"^(?P<prefix>\s*li\s+)(?P<rd>[a-zA-Z0-9]+)(?P<separator>\s*,\s*)"
    r"(?P<value>[-+]?(?:0[xX][0-9a-fA-F]+|[0-9]+))(?P<suffix>\s*(?:#.*)?)$"
)
_GPR_ALIASES = {
    "zero": "x0", "ra": "x1", "sp": "x2", "gp": "x3", "tp": "x4",
    "t0": "x5", "t1": "x6", "t2": "x7", "s0": "x8", "fp": "x8",
    "s1": "x9", "a0": "x10", "a1": "x11", "a2": "x12", "a3": "x13",
    "a4": "x14", "a5": "x15", "a6": "x16", "a7": "x17", "s2": "x18",
    "s3": "x19", "s4": "x20", "s5": "x21", "s6": "x22", "s7": "x23",
    "s8": "x24", "s9": "x25", "s10": "x26", "s11": "x27", "t3": "x28",
    "t4": "x29", "t5": "x30", "t6": "x31",
}
_NO_GPR_DEST_MNEMONICS = {
    "sb", "sh", "sw", "sd", "fsw", "fsd", "fence", "fence.i",
    "ecall", "ebreak", "mret", "sret", "wfi", "j", "jr", "ret", "nop",
    "csrw", "csrs", "csrc", "csrwi", "csrsi", "csrci",
}
_TEST_DONE_RE = re.compile(r"^(?P<label>\s*test_done:\s*(?:#.*)?\n)", re.MULTILINE)
_USER_STACK_RE = re.compile(
    r"^\s*la\s+(?P<register>x(?:[1-9]|[12][0-9]|3[01]))\s*,\s*"
    r"(?:h\d+_)?user_stack_end\s*(?:#.*)?$",
    re.MULTILINE,
)
_LABEL_RE = re.compile(
    r"^(?P<label>(?:[.$a-zA-Z_][.$a-zA-Z0-9_]*|[0-9]+)):(?P<body>.*)$"
)
_SECTION_RE = re.compile(r"^\s*\.section\s+(?P<section>[^,;\s]+)")
_MEMORY_REGION_SECTION_RE = re.compile(r"^\.region_[0-9]+$")
_VECTOR_STORE_RE = re.compile(
    r"^(?:"
    r"vse(?:8|16|32|64)\.v|"
    r"vsse(?:8|16|32|64)\.v|"
    r"vs(?:u|o)xei(?:8|16|32|64)\.v|"
    r"vsseg[2-8]e(?:8|16|32|64)\.v|"
    r"vssseg[2-8]e(?:8|16|32|64)\.v|"
    r"vs(?:u|o)xseg[2-8]ei(?:8|16|32|64)\.v|"
    r"vs[1248]r\.v|"
    r"vsm\.v"
    r")$"
)
_CHECKPOINT_TEMP_REGISTERS = (
    "x5", "x6", "x7", "x28", "x29", "x30", "x31", "x10", "x11", "x12",
)


def _signature_routine(bytes_per_register: int, stack_register: str) -> str:
    signature_bytes = 32 * bytes_per_register
    scalar_loads = signature_bytes // 8
    temporary_registers = [
        register for register in _CHECKPOINT_TEMP_REGISTERS if register != stack_register
    ][:3]
    if len(temporary_registers) != 3:
        raise VectorSignatureError("cannot select signature temporary registers")
    address, count, value = temporary_registers
    lines = [
        f"                  {_BEGIN_MARKER}",
        f"                  addi {stack_register}, {stack_register}, -32",
        f"                  sd {address}, 0({stack_register})",
        f"                  sd {count}, 8({stack_register})",
        f"                  sd {value}, 16({stack_register})",
        f"                  la {address}, __ara_vector_signature",
    ]
    for register in range(32):
        lines.append(f"                  vs1r.v v{register}, ({address})")
        lines.append(f"                  csrr {value}, vl")
        if register != 31:
            lines.append(f"                  addi {address}, {address}, {bytes_per_register}")
    lines.extend([
        "                  fence rw, rw",
        f"                  la {address}, __ara_vector_signature",
        f"                  li {count}, {scalar_loads}",
        "__ara_vector_signature_read_loop:",
        f"                  ld {value}, 0({address})",
        f"                  addi {address}, {address}, 8",
        f"                  addi {count}, {count}, -1",
        f"                  bnez {count}, __ara_vector_signature_read_loop",
        "__ara_vector_signature_read_done:",
        f"                  ld {address}, 0({stack_register})",
        f"                  ld {count}, 8({stack_register})",
        f"                  ld {value}, 16({stack_register})",
        f"                  addi {stack_register}, {stack_register}, 32",
        f"                  {_END_MARKER}",
    ])
    return "\n".join(lines) + "\n"


def _signature_storage(signature_bytes: int) -> str:
    return (
        "\n.section .data\n"
        ".balign 4096\n"
        ".global __ara_vector_signature\n"
        "__ara_vector_signature:\n"
        f"                  .zero {signature_bytes}\n"
    )


def _instruction_on_line(line: str) -> tuple[str | None, str | None]:
    body = line.split("#", 1)[0].strip()
    label = None
    label_match = _LABEL_RE.match(body)
    if label_match is not None:
        label = label_match.group("label")
        body = label_match.group("body").strip()
    if not body:
        return label, None
    return label, body.split(None, 1)[0].lower()


def _instruction_text_on_line(line: str) -> str | None:
    body = line.split("#", 1)[0].strip()
    label_match = _LABEL_RE.match(body)
    if label_match is not None:
        body = label_match.group("body").strip()
    return body or None


def _normalize_gpr(register: str) -> str | None:
    lowered = register.strip().lower()
    if re.fullmatch(r"x(?:[0-9]|[12][0-9]|3[01])", lowered):
        return lowered
    return _GPR_ALIASES.get(lowered)


def _find_reaching_immediate(
    lines: list[str], instruction_index: int, register: str, source: Path
) -> int:
    target = _normalize_gpr(register)
    if target is None:
        raise VectorSignatureError(f"vsetvl in {source} uses unknown GPR {register}")

    for line in reversed(lines[:instruction_index]):
        instruction = _instruction_text_on_line(line)
        if instruction is None or instruction.startswith("."):
            continue
        parts = instruction.split(None, 1)
        mnemonic = parts[0].lower()
        operands = [] if len(parts) == 1 else [item.strip() for item in parts[1].split(",")]

        if mnemonic in {"jal", "jalr"} or mnemonic.startswith("b"):
            raise VectorSignatureError(
                f"cannot prove a straight-line constant definition of {register} "
                f"before vsetvl in {source}"
            )
        if not operands or _normalize_gpr(operands[0]) != target:
            continue
        if mnemonic in _NO_GPR_DEST_MNEMONICS:
            continue
        if mnemonic != "li" or len(operands) != 2:
            raise VectorSignatureError(
                f"reaching definition of {register} before vsetvl in {source} "
                f"is not a constant li: {instruction}"
            )
        try:
            return int(operands[1], 0) & ((1 << 64) - 1)
        except ValueError as error:
            raise VectorSignatureError(
                f"cannot parse constant definition of {register} before vsetvl "
                f"in {source}: {instruction}"
            ) from error

    raise VectorSignatureError(
        f"cannot find a reaching constant definition of {register} before vsetvl in {source}"
    )


def _is_vector_store_instruction(instruction_text: str) -> bool:
    mnemonic = instruction_text.split(None, 1)[0].lower()
    return _VECTOR_STORE_RE.fullmatch(mnemonic) is not None


def _annotate_memory_regions(lines: list[str]) -> tuple[list[str], tuple[str, ...]]:
    rewritten: list[str] = []
    regions: list[str] = []
    region_labels: set[str] = set()
    active_region: str | None = None

    def close_active_region() -> None:
        nonlocal active_region
        if active_region is not None:
            rewritten.append(f"__ara_{active_region}_end:\n")
            active_region = None

    for line in lines:
        section_match = _SECTION_RE.match(line)
        if section_match is not None:
            close_active_region()
            section = section_match.group("section")
            if _MEMORY_REGION_SECTION_RE.match(section) is not None:
                active_region = section[1:]
                if active_region in regions:
                    raise VectorSignatureError(
                        f"memory section {section} is emitted more than once"
                    )
                regions.append(active_region)
        label, _ = _instruction_on_line(line)
        if label is not None:
            region_labels.add(label)
        rewritten.append(line)
    close_active_region()

    missing = [region for region in regions if region not in region_labels]
    if missing:
        raise VectorSignatureError(
            "memory sections have no matching start labels: " + ", ".join(missing)
        )
    return rewritten, tuple(regions)


def _checkpoint_routine(
    bytes_per_register: int,
    checkpoint: int,
    instruction: str,
    stack_register: str,
    memory_regions: tuple[str, ...],
    mask_register: int | None = None,
) -> str:
    temporary_registers = [
        register for register in _CHECKPOINT_TEMP_REGISTERS if register != stack_register
    ][:3]
    if len(temporary_registers) != 3:
        raise VectorSignatureError("cannot select checkpoint temporary registers")
    address, count, value = temporary_registers
    scalar_loads = 32 * bytes_per_register // 8
    prefix = f"__ara_vector_checkpoint_{checkpoint:03d}"
    if mask_register is not None:
        operation = (
            f"addi {value}, zero, 0" if instruction == "initial_state"
            else f"vcpop.m {value}, v{mask_register}"
        )
        return "\n".join([
            f"                  # ARA_DSA_VECTOR_CHECKPOINT_{checkpoint:03d} after {instruction}",
            f"{prefix}_start:",
            f"                  addi {stack_register}, {stack_register}, -16",
            f"                  sd {value}, 0({stack_register})",
            f"{prefix}_read_loop:",
            f"                  {operation}",
            f"{prefix}_read_done:",
            f"                  ld {value}, 0({stack_register})",
            f"                  addi {stack_register}, {stack_register}, 16",
        ]) + "\n"
    lines = [
        f"                  # ARA_DSA_VECTOR_CHECKPOINT_{checkpoint:03d} after {instruction}",
        f"{prefix}_start:",
        f"                  addi {stack_register}, {stack_register}, -32",
        f"                  sd {address}, 0({stack_register})",
        f"                  sd {count}, 8({stack_register})",
        f"                  sd {value}, 16({stack_register})",
        f"                  la {address}, __ara_vector_signature",
    ]
    for register in range(32):
        lines.append(f"                  vs1r.v v{register}, ({address})")
        lines.append(f"                  csrr {value}, vl")
        if register != 31:
            lines.append(f"                  addi {address}, {address}, {bytes_per_register}")
    lines.extend([
        "                  fence rw, rw",
        f"                  csrr {value}, vl",
        f"                  csrr {value}, vtype",
        f"                  csrr {value}, vstart",
        f"                  csrr {value}, vcsr",
        f"                  csrr {value}, fcsr",
        f"                  la {address}, __ara_vector_signature",
        f"                  li {count}, {scalar_loads}",
        f"{prefix}_read_loop:",
        f"                  ld {value}, 0({address})",
        f"                  addi {address}, {address}, 8",
        f"                  addi {count}, {count}, -1",
        f"                  bnez {count}, {prefix}_read_loop",
        f"{prefix}_read_done:",
    ])
    for region in memory_regions:
        lines.extend([
            f"                  la {address}, {region}",
            f"                  la {count}, __ara_{region}_end",
            f"                  sub {count}, {count}, {address}",
            f"                  beqz {count}, {prefix}_{region}_read_done",
            f"{prefix}_{region}_read_loop:",
            f"                  lbu {value}, 0({address})",
            f"                  addi {address}, {address}, 1",
            f"                  addi {count}, {count}, -1",
            f"                  bnez {count}, {prefix}_{region}_read_loop",
            f"{prefix}_{region}_read_done:",
        ])
    lines.extend([
        f"                  ld {address}, 0({stack_register})",
        f"                  ld {count}, 8({stack_register})",
        f"                  ld {value}, 16({stack_register})",
        f"                  addi {stack_register}, {stack_register}, 32",
    ])
    return "\n".join(lines) + "\n"


def _insert_vector_checkpoints(
    lines: list[str], bytes_per_register: int, stack_register: str,
    memory_regions: tuple[str, ...], checkpoint_indices: set[int] | None = None,
    mask_register: int | None = None,
) -> tuple[list[str], tuple[str, ...], tuple[int, ...], tuple[int, ...]]:
    rewritten: list[str] = []
    checkpoint_instructions: list[str] = []
    checkpoint_source_indices: list[int] = []
    checkpoint_memory_sites: list[int] = []
    source_vector_index = 0
    saw_main = False
    saw_test_done = False
    for line in lines:
        label, instruction = _instruction_on_line(line)
        if label == "main":
            saw_main = True
            if instruction is not None:
                colon = line.index(":")
                instruction_line = "                  " + line[colon + 1:].lstrip()
                if not instruction_line.endswith("\n"):
                    instruction_line += "\n"
                rewritten.append(line[:colon + 1] + "\n")
            else:
                instruction_line = None
                rewritten.append(line)
            checkpoint_instructions.append("initial_state")
            checkpoint_source_indices.append(0)
            rewritten.append(_checkpoint_routine(
                bytes_per_register,
                0,
                "initial_state",
                stack_register,
                (),
                mask_register,
            ))
            if instruction_line is None:
                continue
            line = instruction_line
        if label == "test_done":
            saw_test_done = True

        is_vector_instruction = (
            saw_main and instruction is not None and instruction.startswith("v")
        )
        if is_vector_instruction:
            source_vector_index += 1
            if checkpoint_indices is not None and source_vector_index not in checkpoint_indices:
                rewritten.append(line)
                continue
            checkpoint = len(checkpoint_instructions)
            instruction_text = _instruction_text_on_line(line)
            if instruction_text is None:
                raise VectorSignatureError(
                    f"cannot extract vector instruction text from: {line.strip()}"
                )
            checkpoint_instructions.append(instruction_text)
            checkpoint_source_indices.append(source_vector_index)
            checkpoint_regions = ()
            if mask_register is None and _is_vector_store_instruction(instruction_text):
                checkpoint_regions = memory_regions
                checkpoint_memory_sites.append(checkpoint)
            rewritten.append(f"__ara_vector_checkpoint_{checkpoint:03d}_instruction:\n")
            rewritten.append(line if line.endswith("\n") else line + "\n")
            rewritten.append(_checkpoint_routine(
                bytes_per_register,
                checkpoint,
                instruction_text,
                stack_register,
                checkpoint_regions,
                mask_register,
            ))
        elif label != "main" or instruction is not None:
            rewritten.append(line)
    if not saw_main:
        raise VectorSignatureError("cannot find main label for vector checkpoints")
    if not saw_test_done:
        raise VectorSignatureError("cannot find test_done label for vector checkpoints")
    if len(checkpoint_instructions) == 1:
        if checkpoint_indices is None:
            raise VectorSignatureError("no vector instruction found in main")
        raise VectorSignatureError("selected checkpoint indices match no vector instruction")
    if checkpoint_indices is not None:
        missing = sorted(checkpoint_indices.difference(checkpoint_source_indices))
        if missing:
            raise VectorSignatureError(
                "checkpoint indices exceed generated vector stream: " +
                ", ".join(str(index) for index in missing)
            )
    return (
        rewritten,
        tuple(checkpoint_instructions),
        tuple(checkpoint_source_indices),
        tuple(checkpoint_memory_sites),
    )


def _label_test_exit_ecall(lines: list[str]) -> list[str]:
    rewritten: list[str] = []
    saw_test_done = False
    for line in lines:
        label, instruction = _instruction_on_line(line)
        saw_test_done |= label == "test_done"
        if saw_test_done and instruction == "ecall":
            rewritten.append("__ara_vector_signature_exit_ecall:\n")
            saw_test_done = False
        rewritten.append(line)
    return rewritten


def _normalize_vector_policies(
    lines: list[str], source: Path
) -> tuple[list[str], int, int]:
    rewritten_lines = []
    policy_rewrites = 0
    dynamic_policy_rewrites = 0
    static_vset_count = 0
    for line in lines:
        if re.search(r"\b(?:vsetvli|vsetivli)\b", line):
            static_vset_count += 1
            newline = "\n" if line.endswith("\n") else ""
            body = line[:-1] if newline else line
            body, count = _POLICY_RE.subn(
                lambda match: (
                    f"{match.group('prefix')}tu{match.group('separator')}mu"
                    f"{match.group('suffix')}"
                ),
                body,
                count=1,
            )
            if count != 1:
                raise VectorSignatureError(
                    f"cannot identify tail/mask policy in generated instruction: {line.strip()}"
                )
            policy_rewrites += 1
            line = body + newline
        rewritten_lines.append(line)

    dynamic_lines: list[str] = []
    for index, line in enumerate(rewritten_lines):
        dynamic_match = _DYNAMIC_VSETVL_RE.search(line)
        if dynamic_match is None:
            dynamic_lines.append(line)
            continue
        rs2 = dynamic_match.group("rs2")
        if _normalize_gpr(rs2) == "x0":
            dynamic_policy_rewrites += 1
            dynamic_lines.append(line)
            continue
        vtype = _find_reaching_immediate(rewritten_lines, index, rs2, source)
        deterministic_vtype = vtype & ~0xC0
        rs1 = dynamic_match.group("rs1")
        rd = dynamic_match.group("rd")
        if deterministic_vtype != vtype and _normalize_gpr(rs1) == _normalize_gpr(rs2):
            raise VectorSignatureError(
                f"vsetvl in {source} uses {rs2} as both AVL and vtype; "
                "cannot force deterministic policy without changing AVL"
            )
        indent = line[: len(line) - len(line.lstrip())]
        if deterministic_vtype != vtype:
            dynamic_lines.append(f"{indent}li {rs2}, 0x{deterministic_vtype:x}\n")
        dynamic_lines.append(line)
        if deterministic_vtype != vtype and _normalize_gpr(rd) != _normalize_gpr(rs2):
            dynamic_lines.append(f"{indent}li {rs2}, 0x{vtype:x}\n")
        dynamic_policy_rewrites += 1

    if static_vset_count + dynamic_policy_rewrites == 0:
        raise VectorSignatureError(f"no vector configuration instruction found in {source}")
    return dynamic_lines, policy_rewrites, dynamic_policy_rewrites


def rewrite_deterministic_vector_policies(source: Path) -> tuple[int, int]:
    lines, policy_rewrites, dynamic_policy_rewrites = _normalize_vector_policies(
        source.read_text(encoding="utf-8").splitlines(keepends=True), source
    )
    source.write_text("".join(lines), encoding="utf-8")
    return policy_rewrites, dynamic_policy_rewrites


def rewrite_vector_signature(
    source: Path, vlen_bits: int = 1024, vector_checkpoints: bool = False,
    checkpoint_indices: tuple[int, ...] = (),
    checkpoint_mask_register: int | None = None,
) -> VectorSignatureRewrite:
    if vlen_bits <= 0 or vlen_bits % 64:
        raise VectorSignatureError("VLEN must be a positive multiple of 64 bits")
    bytes_per_register = vlen_bits // 8
    if bytes_per_register > 2047:
        raise VectorSignatureError("VLEN is too large for the signature addi sequence")

    text = source.read_text(encoding="utf-8")
    if _BEGIN_MARKER in text or "__ara_vector_signature:" in text:
        raise VectorSignatureError(f"vector signature is already present in {source}")
    rewritten_lines, policy_rewrites, dynamic_policy_rewrites = _normalize_vector_policies(
        text.splitlines(keepends=True), source
    )

    rewritten_lines, checkpoint_memory_regions = _annotate_memory_regions(rewritten_lines)

    stack_matches = list(_USER_STACK_RE.finditer("".join(rewritten_lines)))
    if len(stack_matches) != 1:
        raise VectorSignatureError(
            "cannot identify a unique riscv-dv user stack register for vector signatures"
        )
    scratch_stack_register = stack_matches[0].group("register")

    if checkpoint_indices and not vector_checkpoints:
        raise VectorSignatureError("checkpoint indices require vector checkpoints")
    if checkpoint_mask_register is not None:
        if not vector_checkpoints:
            raise VectorSignatureError("mask checkpoint register requires vector checkpoints")
        if checkpoint_mask_register < 0 or checkpoint_mask_register >= 32:
            raise VectorSignatureError("mask checkpoint register must be in v0-v31")
    selected_checkpoint_indices = set(checkpoint_indices) if checkpoint_indices else None
    if selected_checkpoint_indices is not None and any(index <= 0 for index in checkpoint_indices):
        raise VectorSignatureError("checkpoint indices are one-based and must be positive")

    checkpoint_instructions: tuple[str, ...] = ()
    checkpoint_source_indices: tuple[int, ...] = ()
    checkpoint_memory_sites: tuple[int, ...] = ()
    if vector_checkpoints:
        (rewritten_lines, checkpoint_instructions, checkpoint_source_indices,
         checkpoint_memory_sites) = (
            _insert_vector_checkpoints(
                rewritten_lines,
                bytes_per_register,
                scratch_stack_register,
                checkpoint_memory_regions,
                selected_checkpoint_indices,
                checkpoint_mask_register,
            )
        )

    rewritten_lines = _label_test_exit_ecall(rewritten_lines)

    rewritten = "".join(rewritten_lines)
    rewritten, label_count = _TEST_DONE_RE.subn(
        lambda match: match.group("label") + _signature_routine(
            bytes_per_register, scratch_stack_register
        ),
        rewritten,
        count=1,
    )
    if label_count != 1:
        raise VectorSignatureError(f"cannot find a unique test_done label in {source}")

    signature_bytes = 32 * bytes_per_register
    source.write_text(rewritten + _signature_storage(signature_bytes), encoding="utf-8")
    return VectorSignatureRewrite(
        source=source,
        policy_rewrites=policy_rewrites,
        dynamic_policy_rewrites=dynamic_policy_rewrites,
        vector_registers=32,
        bytes_per_register=bytes_per_register,
        checkpoints=len(checkpoint_instructions),
        checkpoint_instructions=checkpoint_instructions,
        checkpoint_source_indices=checkpoint_source_indices,
        scratch_stack_register=scratch_stack_register,
        checkpoint_memory_regions=checkpoint_memory_regions,
        checkpoint_memory_sites=checkpoint_memory_sites,
        checkpoint_mask_register=checkpoint_mask_register,
    )
