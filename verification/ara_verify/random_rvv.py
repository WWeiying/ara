from __future__ import annotations

import shlex
import json
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .dependencies import DependencyError, locked_tools
from .spike_trace import CommitComparisonError, compare_commit_prefix
from .stimulus_coverage import write_stimulus_coverage
from .trace import TraceValidationError, validate_trace
from .vector_commit import (
    VectorCommitComparisonError,
    compare_vector_commits,
    unobservable_vector_scalar_write_indices,
)
from .vector_signature import (
    VectorSignatureError,
    _find_reaching_immediate,
    rewrite_deterministic_vector_policies,
    rewrite_vector_signature,
)


@dataclass(frozen=True)
class RandomRvvOptions:
    repo_root: Path
    test: str
    iterations: Optional[int]
    seed: int
    output: Path
    simulator: str = "vcs"
    dry_run: bool = False


@dataclass(frozen=True)
class RandomRvvRunOptions:
    generation: RandomRvvOptions
    simv: Path
    spike: Path
    generator_simv: Optional[Path] = None
    timeout_s: int = 120
    watchdog_cycles: int = 10000
    spike_timeout_s: int = 30
    vector_signature: bool = False
    vector_checkpoints: bool = False
    checkpoint_indices: Tuple[int, ...] = ()
    checkpoint_mask_register: Optional[int] = None
    vector_commit_compare: bool = False
    vector_commit_index: Optional[int] = None


def _profile_iterations(repo_root: Path, test: str) -> int:
    testlist = repo_root / "verification" / "riscv_dv" / "testlist.yaml"
    current_test: Optional[str] = None
    for line in testlist.read_text(encoding="utf-8").splitlines():
        test_match = re.match(r"\s*-\s+test:\s*(\S+)\s*$", line)
        if test_match is not None:
            current_test = test_match.group(1)
            continue
        if current_test == test:
            iteration_match = re.match(r"\s+iterations:\s*(\d+)\s*$", line)
            if iteration_match is not None:
                iterations = int(iteration_match.group(1))
                if iterations <= 0:
                    raise ValueError(f"profile {test} has no positive iteration count")
                return iterations
    raise ValueError(f"cannot find profile iteration count for {test}")


def effective_iterations(options: RandomRvvOptions) -> int:
    if options.iterations is not None:
        return options.iterations
    return _profile_iterations(options.repo_root, options.test)


def _generated_case_sort_key(path: Path) -> int:
    match = re.search(r"_(\d+)\.(?:S|o)$", path.name)
    if match is None:
        raise ValueError(f"generated RVV case has no numeric suffix: {path}")
    return int(match.group(1))


def _rewrite_ordered_fp_reductions(source: Path) -> Dict[str, int]:
    """Make strict random differential tests bit-exact across legal implementations.

    RVV permits vfredusum/vfwredusum to use an implementation-defined reduction
    tree.  Once their result feeds later vector or scalar control, waiving only
    the reduction write is insufficient: two legal results can make the rest of
    the program diverge.  Directed tests retain the unordered instructions; the
    strict random stream uses their ordered counterparts instead.
    """
    text = source.read_text(encoding="utf-8")
    rewrites: Dict[str, int] = {}
    for unordered, ordered in (
        ("vfredusum.vs", "vfredosum.vs"),
        ("vfwredusum.vs", "vfwredosum.vs"),
    ):
        pattern = re.compile(rf"(?m)^(\s*){re.escape(unordered)}(?=\s)")
        text, count = pattern.subn(rf"\1{ordered}", text)
        rewrites[unordered] = count
    source.write_text(text, encoding="utf-8")
    return rewrites


def _rewrite_ordered_indexed_stores(source: Path) -> Dict[str, int]:
    """Make duplicate-address indexed stores deterministic in strict streams.

    Unordered indexed stores may write one address from several active elements
    in an implementation-dependent order. A later load can therefore observe
    different, architecturally legal values on Spike and Ara. Directed ISA
    tests retain the unordered forms; full-state random differential programs
    use their ordered counterparts.
    """
    text = source.read_text(encoding="utf-8")
    rewrites: Dict[str, int] = {}
    for name, suffix in (
        ("vsuxei", r"ei(?:8|16|32|64)\.v"),
        ("vsuxseg", r"seg[2-8]ei(?:8|16|32|64)\.v"),
    ):
        pattern = re.compile(rf"(?m)^(\s*)vsux({suffix})(?=\s)")
        text, count = pattern.subn(r"\1vsox\2", text)
        rewrites[name] = count
    source.write_text(text, encoding="utf-8")
    return rewrites


def _rewrite_reserved_narrowing_source_overlaps(source: Path) -> Dict[str, int]:
    """Repair RVV-reserved dual-source EEW overlaps in strict random streams.

    The `.wv` narrowing forms read `vs2` at 2*SEW and `vs1` at SEW.  RVV 1.0
    reserves an encoding when the two source groups share any physical vector
    register because that register would be read with two EEWs.  Some versions
    of the RVV riscv-dv fork do not constrain this cross-source case.
    """
    vset_pattern = re.compile(
        r"\bvset(?:i)?vli\s+[^,]+,\s*[^,]+,\s*e(?:8|16|32|64),\s*"
        r"(mf8|mf4|mf2|m1|m2|m4|m8)\b"
    )
    vsetvl_pattern = re.compile(
        r"\bvsetvl\s+[^,]+,\s*[^,]+,\s*(?P<vtype>[a-zA-Z0-9]+)\b"
    )
    narrow_pattern = re.compile(
        r"^(?P<prefix>\s*)(?P<op>vnsrl\.wv|vnsra\.wv|vnclipu\.wv|vnclip\.wv)"
        r"(?P<gap>\s+)(?P<vd>v\d+)\s*,\s*(?P<vs2>v\d+)\s*,\s*"
        r"(?P<vs1>v\d+)(?P<suffix>\s*(?:,\s*v0\.t)?\s*(?:#.*)?)$"
    )
    lmul_registers = {
        "mf8": 1,
        "mf4": 1,
        "mf2": 1,
        "m1": 1,
        "m2": 2,
        "m4": 4,
        "m8": 8,
    }
    wide_registers = {
        "mf8": 1,
        "mf4": 1,
        "mf2": 1,
        "m1": 2,
        "m2": 4,
        "m4": 8,
    }

    rewrites = {name: 0 for name in ("vnsrl.wv", "vnsra.wv", "vnclipu.wv", "vnclip.wv")}
    current_lmul: Optional[str] = None
    output_lines: List[str] = []
    source_lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    encoded_lmul = {
        0b000: "m1",
        0b001: "m2",
        0b010: "m4",
        0b011: "m8",
        0b101: "mf8",
        0b110: "mf4",
        0b111: "mf2",
    }

    for line_index, line in enumerate(source_lines):
        vset_match = vset_pattern.search(line)
        if vset_match is not None:
            current_lmul = vset_match.group(1)
        else:
            vsetvl_match = vsetvl_pattern.search(line)
            if vsetvl_match is not None:
                try:
                    vtype = _find_reaching_immediate(
                        source_lines, line_index, vsetvl_match.group("vtype"), source
                    )
                except VectorSignatureError as error:
                    raise RuntimeError(
                        f"cannot prove vsetvl vtype before narrowing overlap in {source}: "
                        f"{line.strip()}"
                    ) from error
                vlmul = vtype & 0b111
                if (vtype >> 63) or vlmul not in encoded_lmul:
                    raise RuntimeError(
                        f"vsetvl has an illegal static vtype 0x{vtype:x} in {source}: "
                        f"{line.strip()}"
                    )
                current_lmul = encoded_lmul[vlmul]

        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        narrow_match = narrow_pattern.match(body)
        if narrow_match is None:
            output_lines.append(line)
            continue
        if current_lmul is None or current_lmul not in wide_registers:
            raise RuntimeError(
                f"cannot validate narrowing source overlap without legal LMUL in {source}: {body}"
            )

        vs2 = int(narrow_match.group("vs2")[1:])
        vs1 = int(narrow_match.group("vs1")[1:])
        narrow_count = lmul_registers[current_lmul]
        wide_count = wide_registers[current_lmul]
        wide_group = set(range(vs2, vs2 + wide_count))
        shift_group = set(range(vs1, vs1 + narrow_count))
        if wide_group.isdisjoint(shift_group):
            output_lines.append(line)
            continue

        masked = "v0.t" in narrow_match.group("suffix")
        replacement: Optional[int] = None
        for candidate in range(0, 32, narrow_count):
            candidate_group = set(range(candidate, candidate + narrow_count))
            if candidate + narrow_count > 32 or not wide_group.isdisjoint(candidate_group):
                continue
            if masked and 0 in candidate_group:
                continue
            replacement = candidate
            break
        if replacement is None:
            raise RuntimeError(f"cannot repair reserved narrowing overlap in {source}: {body}")

        op = narrow_match.group("op")
        output_lines.append(
            f'{narrow_match.group("prefix")}{op}{narrow_match.group("gap")}'
            f'{narrow_match.group("vd")}, {narrow_match.group("vs2")}, v{replacement}'
            f'{narrow_match.group("suffix")}{newline}'
        )
        rewrites[op] += 1

    source.write_text("".join(output_lines), encoding="utf-8")
    return rewrites


def _rewrite_reserved_indexed_store_source_overlaps(source: Path) -> Dict[str, int]:
    """Remove indexed stores whose data and index operands form a reserved encoding.

    RVV 1.0 reserves instructions that read one physical vector register at
    different EEWs. Indexed stores read the data group at SEW and the offset
    group at the EEW encoded in the mnemonic. Some RVV riscv-dv streams let
    those groups overlap. There is no architectural behavior to preserve for
    such an instruction, so replace only that instruction with a NOP. Choosing
    an unrelated index group could generate an out-of-range address, while
    copying the index group would clobber otherwise-live vector state.
    """
    vset_pattern = re.compile(
        r"\bvset(?:i)?vli\s+[^,]+,\s*[^,]+,\s*e(?P<sew>8|16|32|64),\s*"
        r"(?P<lmul>mf8|mf4|mf2|m1|m2|m4|m8)\b"
    )
    vsetvl_pattern = re.compile(
        r"\bvsetvl\s+[^,]+,\s*[^,]+,\s*(?P<vtype>[a-zA-Z0-9]+)\b"
    )
    store_pattern = re.compile(
        r"^(?P<prefix>\s*)(?P<op>vsox(?:seg(?P<nf>[2-8]))?ei(?P<eew>8|16|32|64)\.v)"
        r"(?P<gap>\s+)(?P<data>v\d+)\s*,\s*(?P<base>\([^)]*\))\s*,\s*"
        r"(?P<index>v\d+)(?P<suffix>\s*(?:,\s*v0\.t)?\s*(?:#.*)?)$"
    )
    lmul_ratio = {
        "mf8": (1, 8), "mf4": (1, 4), "mf2": (1, 2),
        "m1": (1, 1), "m2": (2, 1), "m4": (4, 1), "m8": (8, 1),
    }
    encoded_lmul = {
        0b000: "m1", 0b001: "m2", 0b010: "m4", 0b011: "m8",
        0b101: "mf8", 0b110: "mf4", 0b111: "mf2",
    }

    rewrites = {"indexed_store_source_overlap": 0}
    current_sew: Optional[int] = None
    current_lmul: Optional[str] = None
    output_lines: List[str] = []
    source_lines = source.read_text(encoding="utf-8").splitlines(keepends=True)

    for line_index, line in enumerate(source_lines):
        vset_match = vset_pattern.search(line)
        if vset_match is not None:
            current_sew = int(vset_match.group("sew"))
            current_lmul = vset_match.group("lmul")
        else:
            vsetvl_match = vsetvl_pattern.search(line)
            if vsetvl_match is not None:
                try:
                    vtype = _find_reaching_immediate(
                        source_lines, line_index, vsetvl_match.group("vtype"), source
                    )
                except VectorSignatureError as error:
                    raise RuntimeError(
                        f"cannot prove vsetvl vtype before indexed store in {source}: "
                        f"{line.strip()}"
                    ) from error
                vlmul = vtype & 0b111
                vsew = (vtype >> 3) & 0b111
                if (vtype >> 63) or vlmul not in encoded_lmul or vsew > 3:
                    raise RuntimeError(
                        f"vsetvl has an illegal static vtype 0x{vtype:x} in {source}: "
                        f"{line.strip()}"
                    )
                current_lmul = encoded_lmul[vlmul]
                current_sew = 8 << vsew

        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        match = store_pattern.match(body)
        if match is None:
            output_lines.append(line)
            continue
        if current_sew is None or current_lmul is None:
            raise RuntimeError(
                f"cannot validate indexed-store overlap without vtype in {source}: {body}"
            )

        index_eew = int(match.group("eew"))
        if index_eew == current_sew:
            output_lines.append(line)
            continue
        numerator, denominator = lmul_ratio[current_lmul]
        fields = int(match.group("nf") or "1")
        data_count = fields * max(1, numerator // denominator)
        index_numerator = numerator * index_eew
        index_denominator = denominator * current_sew
        index_count = max(1, index_numerator // index_denominator)
        data_base = int(match.group("data")[1:])
        index_base = int(match.group("index")[1:])
        data_group = set(range(data_base, data_base + data_count))
        index_group = set(range(index_base, index_base + index_count))
        if data_group.isdisjoint(index_group):
            output_lines.append(line)
            continue

        output_lines.append(
            f'{match.group("prefix")}nop'
            f'  # removed reserved dual-EEW indexed store: {body.strip()}{newline}'
        )
        rewrites["indexed_store_source_overlap"] += 1

    source.write_text("".join(output_lines), encoding="utf-8")
    return rewrites


def random_rvv_command(
    options: RandomRvvOptions, steps: str = "gen", simulate_only: bool = False
) -> List[str]:
    tools = {tool.name: tool for tool in locked_tools(
        options.repo_root / "verification" / "toolchain.lock.json"
    )}
    try:
        tool = tools["riscv-dv-rvv1"]
    except KeyError as error:
        raise DependencyError("riscv-dv-rvv1 is not present in toolchain.lock.json") from error

    tool_root = options.repo_root / tool.path
    run_py = tool_root / "run.py"
    if not run_py.is_file():
        raise DependencyError(
            f"missing RVV 1.0 generator at {run_py}; run verification/verify.py deps"
        )
    actual = subprocess.run(
        ["git", "-C", str(tool_root), "rev-parse", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if actual.returncode != 0 or actual.stdout.strip().lower() != tool.revision:
        raise DependencyError(
            f"RVV 1.0 generator must be at {tool.revision}; run verification/verify.py deps"
        )

    command = [
        "python3",
        str(run_py),
        "--target",
        "rv64gcv",
        "--testlist",
        str(options.repo_root / "verification" / "riscv_dv" / "testlist.yaml"),
        "--test",
        options.test,
        "--simulator",
        options.simulator,
        "--steps",
        steps,
        "--output",
        str(options.output),
        "--gen_timeout",
        "900",
        "--batch_size",
        "5",
    ]
    if options.iterations is None:
        command.extend(["--start_seed", str(options.seed)])
    elif options.iterations == 1:
        command.extend(["--seed", str(options.seed)])
    else:
        command.extend(["--iterations", str(options.iterations), "--start_seed", str(options.seed)])
    if simulate_only:
        command.append("--so")
    return command


def _link_generator_simv(output: Path, generator_simv: Path) -> None:
    """Expose a precompiled VCS generator and its runtime database to a profile."""
    source = generator_simv.resolve()
    if not source.is_file():
        raise DependencyError(f"missing precompiled riscv-dv generator: {source}")
    runtime_database = source.parent / f"{source.name}.daidir"
    if not runtime_database.is_dir():
        raise DependencyError(
            f"missing precompiled riscv-dv generator runtime database: {runtime_database}"
        )

    for destination, artifact in (
        (output / "vcs_simv", source),
        (output / "vcs_simv.daidir", runtime_database),
    ):
        if destination.exists() or destination.is_symlink():
            try:
                if destination.resolve(strict=True).samefile(artifact):
                    continue
            except (FileNotFoundError, OSError):
                pass
            raise RuntimeError(
                f"generator destination already exists and does not match "
                f"{artifact}: {destination}"
            )
        destination.symlink_to(artifact, target_is_directory=artifact.is_dir())


def generate_random_rvv(options: RandomRvvOptions) -> int:
    if effective_iterations(options) <= 0:
        raise ValueError("iterations must be positive")
    if options.seed < 0:
        raise ValueError("seed must be non-negative")
    command = random_rvv_command(options)
    print(shlex.join(command), flush=True)
    if options.dry_run:
        return 0
    options.output.mkdir(parents=True, exist_ok=True)
    tool_root = Path(command[1]).parent
    returncode = subprocess.run(command, cwd=tool_root, check=False).returncode
    if returncode == 0:
        write_stimulus_coverage(options.output, options.test)
    return returncode


def _command_text(command: Sequence[object]) -> str:
    return shlex.join(str(item) for item in command)


def _write_command(path: Path, command: Sequence[object], cwd: Path) -> None:
    path.write_text(
        json.dumps({"command": [str(item) for item in command], "cwd": str(cwd)}, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_logged(
    command: Sequence[object], cwd: Path, log_path: Path, env: Optional[Dict[str, str]] = None,
    timeout_s: Optional[int] = None,
) -> Tuple[int, float, bool]:
    start = time.monotonic()
    timed_out = False
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {_command_text(command)}\n")
        log.flush()
        try:
            process = subprocess.run(
                [str(item) for item in command], cwd=cwd, env=env,
                stdout=log, stderr=subprocess.STDOUT, check=False, timeout=timeout_s,
            )
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            returncode = -signal.SIGTERM
            timed_out = True
    return returncode, time.monotonic() - start, timed_out


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def _run_rtl(
    command: Sequence[object], cwd: Path, console_path: Path, timeout_s: int
) -> Tuple[int, float, bool]:
    start = time.monotonic()
    timed_out = False
    with console_path.open("wb") as console:
        process = subprocess.Popen(
            [str(item) for item in command], cwd=cwd,
            stdout=console, stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _stop_process_group(process)
    return process.returncode, time.monotonic() - start, timed_out


def _elf_entry(elf: Path, readelf: Path) -> int:
    result = subprocess.run(
        [str(readelf), "-h", str(elf)], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"readelf failed for {elf}: {result.stderr.strip()}")
    match = re.search(r"Entry point address:\s*(0x[0-9a-fA-F]+)", result.stdout)
    if match is None:
        raise RuntimeError(f"cannot determine ELF entry for {elf}")
    return int(match.group(1), 16)


def _elf_symbol(elf: Path, readelf: Path, symbol: str) -> int:
    symbols = _elf_symbols(elf, readelf)
    try:
        return symbols[symbol]
    except KeyError as error:
        raise RuntimeError(f"ELF {elf} has no {symbol} symbol") from error


def _elf_symbols(elf: Path, readelf: Path) -> Dict[str, int]:
    result = subprocess.run(
        [str(readelf), "-sW", str(elf)], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"readelf failed for {elf}: {result.stderr.strip()}")
    pattern = re.compile(
        r"^\s*\d+:\s+([0-9a-fA-F]+)\s+\d+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\S+)$"
    )
    symbols: Dict[str, int] = {}
    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if match is not None:
            symbols[match.group(2)] = int(match.group(1), 16)
    return symbols


def _vector_exit_pc(elf: Path, readelf: Path, objdump: Path) -> int:
    symbols = _elf_symbols(elf, readelf)
    direct = symbols.get("__ara_vector_signature_exit_ecall")
    if direct is not None:
        return direct
    start = symbols.get("__ara_vector_signature_read_done")
    if start is None:
        raise RuntimeError(f"ELF {elf} has no vector-signature exit symbol")
    result = subprocess.run(
        [str(objdump), "-d", "--no-show-raw-insn", str(elf)], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"objdump failed for {elf}: {result.stderr.strip()}")
    instruction = re.compile(r"^\s*([0-9a-fA-F]+):\s+ecall(?:\s|$)")
    for line in result.stdout.splitlines():
        match = instruction.match(line)
        if match is not None:
            pc = int(match.group(1), 16)
            if start <= pc < start + 128:
                return pc
    raise RuntimeError(f"cannot find vector-signature exit ecall in {elf}")


def _vector_checkpoint_locations(
    elf: Path, readelf: Path, instructions: Sequence[object],
    memory_regions: Sequence[object] = (),
    memory_sites: Sequence[object] = (),
    source_indices: Sequence[object] = (),
) -> List[Dict[str, object]]:
    symbols = _elf_symbols(elf, readelf)
    memory_site_indices = {int(index) for index in memory_sites}
    locations: List[Dict[str, object]] = []
    for index, instruction in enumerate(instructions):
        prefix = f"__ara_vector_checkpoint_{index:03d}"
        try:
            checkpoint_pc = symbols[f"{prefix}_start"]
            read_loop_pc = symbols[f"{prefix}_read_loop"]
            read_done_pc = symbols[f"{prefix}_read_done"]
        except KeyError as error:
            raise RuntimeError(f"ELF {elf} has incomplete symbols for {prefix}") from error
        location: Dict[str, object] = {
            "index": index,
            "source_index": int(source_indices[index]) if source_indices else index,
            "site": str(instruction),
            "checkpoint_pc": f"0x{checkpoint_pc:016x}",
            "read_loop_pc": f"0x{read_loop_pc:016x}",
            "read_done_pc": f"0x{read_done_pc:016x}",
        }
        instruction_symbol = f"{prefix}_instruction"
        if instruction_symbol in symbols:
            location["instruction_pc"] = f"0x{symbols[instruction_symbol]:016x}"
        memory_read_loop_pcs = []
        if index in memory_site_indices:
            for region in memory_regions:
                symbol = f"{prefix}_{region}_read_loop"
                try:
                    pc = symbols[symbol]
                except KeyError as error:
                    raise RuntimeError(f"ELF {elf} has no symbol {symbol}") from error
                memory_read_loop_pcs.append(f"0x{pc:016x}")
        location["memory_signature"] = index in memory_site_indices
        location["memory_read_loop_pcs"] = memory_read_loop_pcs
        locations.append(location)
    return locations


def _comparison_vector_checkpoint(
    comparison: Dict[str, object], locations: Sequence[Dict[str, object]]
) -> Optional[Dict[str, object]]:
    mismatch = comparison.get("mismatch")
    if not isinstance(mismatch, dict):
        return None
    for side in ("ara", "spike"):
        record = mismatch.get(side)
        if not isinstance(record, dict) or not isinstance(record.get("pc"), str):
            continue
        pc = record["pc"].lower()
        for location in locations:
            if pc in {
                str(location.get("instruction_pc", "")).lower(),
                str(location.get("checkpoint_pc", "")).lower(),
                str(location.get("read_loop_pc", "")).lower(),
                str(location.get("read_done_pc", "")).lower(),
                *(
                    str(memory_pc).lower()
                    for memory_pc in location.get("memory_read_loop_pcs", [])
                ),
            }:
                return dict(location)
    return None


def _vector_checkpoint_report(
    comparison: Dict[str, object], locations: Sequence[Dict[str, object]],
    completed: bool = False,
) -> Dict[str, object]:
    records = [dict(location) for location in locations]
    first_failure = _comparison_vector_checkpoint(comparison, locations)

    if comparison.get("status") == "MATCH" or (
        comparison.get("status") == "PREFIX" and completed
    ):
        for record in records:
            record["status"] = "PASS"
        status = "PASS"
    elif first_failure is not None:
        failed_index = int(first_failure["index"])
        for record in records:
            index = int(record["index"])
            record["status"] = (
                "PASS" if index < failed_index
                else "FAIL" if index == failed_index
                else "NOT_RUN"
            )
        status = "FAIL"
    else:
        for record in records:
            record["status"] = "UNKNOWN"
        status = "UNRESOLVED"

    counts = {
        name: sum(record["status"] == name for record in records)
        for name in ("PASS", "FAIL", "NOT_RUN", "UNKNOWN")
    }
    return {
        "status": status,
        "scope": (
            "full v0-v31 state and vl/vtype/vstart/vcsr/fcsr after each generated "
            "RVV instruction, every byte in generated .region_N data sections after each "
            "vector store, plus exact scalar retirement comparison"
        ),
        "total": len(records),
        "passed": counts["PASS"],
        "failed": counts["FAIL"],
        "not_run": counts["NOT_RUN"],
        "unknown": counts["UNKNOWN"],
        "first_failure": first_failure,
        "checkpoints": records,
    }


def run_random_rvv(options: RandomRvvRunOptions) -> int:
    generation = options.generation
    iterations = effective_iterations(generation)
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if generation.seed < 0:
        raise ValueError("seed must be non-negative")
    if options.timeout_s <= 0 or options.spike_timeout_s <= 0:
        raise ValueError("timeouts must be positive")
    if options.watchdog_cycles <= 0:
        raise ValueError("watchdog_cycles must be positive")
    if options.checkpoint_indices and not options.vector_checkpoints:
        raise ValueError("checkpoint indices require --vector-checkpoints")
    if options.checkpoint_mask_register is not None and not options.vector_checkpoints:
        raise ValueError("mask checkpoint register requires --vector-checkpoints")
    if options.vector_commit_index is not None and not options.vector_commit_compare:
        raise ValueError("vector commit index requires --vector-commit-compare")
    if options.vector_commit_index is not None and options.vector_commit_index <= 0:
        raise ValueError("vector commit index must be positive")
    if not options.simv.is_file():
        raise DependencyError(f"missing Ara simulator: {options.simv}")
    if not options.spike.is_file():
        raise DependencyError(f"missing Spike executable: {options.spike}")

    output = generation.output
    output.mkdir(parents=True, exist_ok=True)
    strict_vector_state = options.vector_signature or options.vector_checkpoints
    deterministic_stream = strict_vector_state or options.vector_commit_compare
    if options.generator_simv is not None:
        if generation.simulator != "vcs":
            raise ValueError("--generator-simv currently requires the VCS generator")
        _link_generator_simv(output, options.generator_simv)
    generation_command = random_rvv_command(
        generation, steps="gen" if deterministic_stream else "gen,gcc_compile",
        simulate_only=options.generator_simv is not None,
    )
    tool_root = Path(generation_command[1]).parent
    gcc_root = generation.repo_root / "install" / "riscv-gcc" / "bin"
    gcc = gcc_root / "riscv64-unknown-elf-gcc"
    objcopy = gcc_root / "riscv64-unknown-elf-objcopy"
    readelf = gcc_root / "riscv64-unknown-elf-readelf"
    objdump = options.generation.repo_root / "install/riscv-llvm/bin/llvm-objdump"
    for tool in (gcc, objcopy, readelf, objdump):
        if not tool.is_file():
            raise DependencyError(f"missing RISC-V tool: {tool}")

    first_step_name = "generate" if deterministic_stream else "generate_compile"
    _write_command(output / f"{first_step_name}.command.json", generation_command, tool_root)
    print(_command_text(generation_command), flush=True)
    if generation.dry_run:
        return 0
    compile_env = os.environ.copy()
    compile_env.update({"RISCV_GCC": str(gcc), "RISCV_OBJCOPY": str(objcopy)})
    compile_rc, _, compile_timeout = _run_logged(
        generation_command, tool_root, output / f"{first_step_name}.log", compile_env,
    )
    if compile_rc != 0 or compile_timeout:
        raise RuntimeError(
            f"RVV generation/compile failed; see {output / f'{first_step_name}.log'}"
        )

    write_stimulus_coverage(output, generation.test)

    signature_manifest: List[Dict[str, object]] = []
    deterministic_rewrite_manifest: List[Dict[str, object]] = []
    if deterministic_stream:
        sources = sorted(
            (output / "asm_test").glob(f"{generation.test}_*.S"),
            key=_generated_case_sort_key,
        )
        if len(sources) != iterations:
            raise RuntimeError(
                f"expected {iterations} generated assembly files, found {len(sources)} "
                f"in {output / 'asm_test'}"
            )
        try:
            for source in sources:
                ordered_reduction_rewrites = _rewrite_ordered_fp_reductions(source)
                ordered_indexed_store_rewrites = _rewrite_ordered_indexed_stores(source)
                indexed_store_overlap_rewrites = (
                    _rewrite_reserved_indexed_store_source_overlaps(source)
                )
                narrowing_overlap_rewrites = _rewrite_reserved_narrowing_source_overlaps(source)
                rewrite_record: Dict[str, object] = {
                    "source": str(source),
                    "ordered_fp_reduction_rewrites": ordered_reduction_rewrites,
                    "ordered_indexed_store_rewrites": ordered_indexed_store_rewrites,
                    "reserved_indexed_store_overlap_rewrites":
                        indexed_store_overlap_rewrites,
                    "reserved_narrowing_overlap_rewrites": narrowing_overlap_rewrites,
                }
                if options.vector_commit_compare and not strict_vector_state:
                    policy_rewrites, dynamic_policy_rewrites = (
                        rewrite_deterministic_vector_policies(source)
                    )
                    rewrite_record.update({
                        "policy_rewrites": policy_rewrites,
                        "dynamic_policy_rewrites": dynamic_policy_rewrites,
                    })
                deterministic_rewrite_manifest.append(rewrite_record)
                if strict_vector_state:
                    rewrite = rewrite_vector_signature(
                        source, vector_checkpoints=options.vector_checkpoints,
                        checkpoint_indices=options.checkpoint_indices,
                        checkpoint_mask_register=options.checkpoint_mask_register,
                    )
                    signature_manifest.append({
                        **rewrite_record,
                        "source": str(rewrite.source),
                        "policy_rewrites": rewrite.policy_rewrites,
                        "dynamic_policy_rewrites": rewrite.dynamic_policy_rewrites,
                        "vector_registers": rewrite.vector_registers,
                        "bytes_per_register": rewrite.bytes_per_register,
                        "signature_bytes": rewrite.signature_bytes,
                        "scalar_check_loads": rewrite.scalar_check_loads,
                        "checkpoints": rewrite.checkpoints,
                        "checkpoint_instructions": list(rewrite.checkpoint_instructions),
                        "checkpoint_source_indices": list(rewrite.checkpoint_source_indices),
                        "scratch_stack_register": rewrite.scratch_stack_register,
                        "checkpoint_memory_regions": list(rewrite.checkpoint_memory_regions),
                        "checkpoint_memory_sites": list(rewrite.checkpoint_memory_sites),
                        "checkpoint_mask_register": rewrite.checkpoint_mask_register,
                    })
        except (OSError, VectorSignatureError) as error:
            raise RuntimeError(f"vector signature rewrite failed: {error}") from error
        (output / "deterministic_rewrite_manifest.json").write_text(
            json.dumps(deterministic_rewrite_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if strict_vector_state:
            (output / "vector_signature_manifest.json").write_text(
                json.dumps(signature_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        compile_command = random_rvv_command(generation, steps="gcc_compile")
        _write_command(output / "compile.command.json", compile_command, tool_root)
        print(_command_text(compile_command), flush=True)
        compile_rc, _, compile_timeout = _run_logged(
            compile_command, tool_root, output / "compile.log", compile_env,
        )
        if compile_rc != 0 or compile_timeout:
            raise RuntimeError(f"RVV compile failed; see {output / 'compile.log'}")

    elfs = sorted(
        (output / "asm_test").glob(f"{generation.test}_*.o"),
        key=_generated_case_sort_key,
    )
    if len(elfs) != iterations:
        raise RuntimeError(
            f"expected {iterations} generated ELF files, found {len(elfs)} in "
            f"{output / 'asm_test'}"
        )

    if strict_vector_state:
        for index, elf in enumerate(elfs):
            manifest = signature_manifest[index]
            manifest["elf"] = str(elf)
            if options.vector_checkpoints:
                manifest["checkpoint_locations"] = _vector_checkpoint_locations(
                    elf, readelf, manifest["checkpoint_instructions"],
                    manifest["checkpoint_memory_regions"],
                    manifest["checkpoint_memory_sites"],
                    manifest["checkpoint_source_indices"],
                )
        (output / "vector_signature_manifest.json").write_text(
            json.dumps(signature_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    results: List[Dict[str, object]] = []
    for index, elf in enumerate(elfs):
        case = output / "tests" / elf.stem
        case.mkdir(parents=True, exist_ok=True)
        entry = _elf_entry(elf, readelf)
        tohost = _elf_symbol(elf, readelf, "tohost")
        exit_pc = _vector_exit_pc(elf, readelf, objdump) if strict_vector_state else None
        spike_log = case / "spike_commit.log"
        spike_command = [
            str(options.spike), "--isa=rv64gcv_zvl1024b", "--log-commits",
            f"--log={spike_log}", str(elf),
        ]
        _write_command(case / "spike.command.json", spike_command, case)
        spike_rc, spike_elapsed, spike_timeout = _run_logged(
            spike_command, case, case / "spike_console.log", timeout_s=options.spike_timeout_s,
        )

        ara_trace = case / "ara_commit_trace.csv"
        vector_trace = case / "ara_vector_trace.csv"
        rtl_command = [
            str(options.simv), "-l", "run.vcs.log",
            f"+ntb_random_seed={generation.seed + index}", f"+PRELOAD={elf}",
            f"+TESTCASE={elf.stem}", "+NO_FSDB", f"+COMMIT_TRACE={ara_trace}",
            f"+COMMIT_WATCHDOG={options.watchdog_cycles}", f"+COMMIT_TOHOST={tohost:016x}",
        ]
        if exit_pc is not None:
            rtl_command.append(f"+COMMIT_EXIT_PC={exit_pc:016x}")
        if options.vector_commit_compare:
            rtl_command.append(f"+VECTOR_TRACE={vector_trace}")
        _write_command(case / "rtl.command.json", rtl_command, case)
        rtl_rc, rtl_elapsed, rtl_timeout = _run_rtl(
            rtl_command, case, case / "rtl_console.log", options.timeout_s,
        )

        rtl_text = ""
        for log in (case / "rtl_console.log", case / "run.vcs.log"):
            if log.is_file():
                rtl_text += log.read_text(encoding="utf-8", errors="replace")
        rtl_success = "Core Test *** SUCCESS ***" in rtl_text

        unobservable_register_values = set()
        if options.vector_commit_compare:
            try:
                unobservable_register_values = unobservable_vector_scalar_write_indices(
                    spike_log, ara_trace, vector_trace, entry
                )
            except (CommitComparisonError, VectorCommitComparisonError):
                pass
        comparison: Dict[str, object]
        try:
            comparison = compare_commit_prefix(
                spike_log, ara_trace, entry, unobservable_register_values
            )
        except CommitComparisonError as error:
            comparison = {"status": "ERROR", "reason": str(error), "vector_state_compared": False}
        if strict_vector_state:
            comparison["vector_state_compared"] = (
                comparison.get("status") == "MATCH" or
                (comparison.get("status") == "PREFIX" and rtl_success)
            )
            if options.vector_checkpoints:
                if options.checkpoint_mask_register is None:
                    comparison["vector_state_method"] = (
                        "full v0-v31 checkpoints and vl/vtype/vstart/vcsr/fcsr reads after "
                        "each generated RVV instruction, byte-exact reads of generated data "
                        "regions after vector stores, plus a full exit signature under "
                        "deterministic tu/mu policy"
                    )
                else:
                    comparison["vector_state_method"] = (
                        f"non-destructive vcpop.m checkpoints for v"
                        f"{options.checkpoint_mask_register} after selected generated RVV "
                        "instructions, plus a full exit signature under deterministic tu/mu policy"
                    )
            else:
                comparison["vector_state_method"] = (
                    "full 32-register exit signature under deterministic tu/mu policy, checked "
                    "as 512 exact scalar load results"
                )
            comparison["vector_signature_bytes"] = 4096
            if options.vector_checkpoints:
                checkpoint_locations = signature_manifest[index]["checkpoint_locations"]
                checkpoint = _comparison_vector_checkpoint(
                    comparison,
                    checkpoint_locations,
                )
                if checkpoint is not None:
                    comparison["vector_checkpoint"] = checkpoint
                checkpoint_report = _vector_checkpoint_report(
                    comparison, checkpoint_locations, completed=rtl_success
                )
                comparison["vector_checkpoint_summary"] = {
                    key: checkpoint_report[key]
                    for key in ("status", "total", "passed", "failed", "not_run", "unknown")
                }
                (case / "vector_checkpoints.json").write_text(
                    json.dumps(checkpoint_report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
        (case / "commit_comparison.json").write_text(
            json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        trace_summary: Dict[str, object]
        try:
            trace_summary = validate_trace(ara_trace)
        except TraceValidationError as error:
            trace_summary = {"status": "ERROR", "reason": str(error)}
        else:
            trace_summary = {"status": "VALID", **trace_summary}
        (case / "trace_summary.json").write_text(
            json.dumps(trace_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        vector_commit: Dict[str, object] = {"status": "DISABLED"}
        if options.vector_commit_compare:
            try:
                vector_commit = compare_vector_commits(
                    spike_log, ara_trace, vector_trace, entry,
                    selected_index=options.vector_commit_index,
                )
            except (CommitComparisonError, VectorCommitComparisonError) as error:
                vector_commit = {"status": "ERROR", "reason": str(error)}
            (case / "vector_commit_comparison.json").write_text(
                json.dumps(vector_commit, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        if spike_rc != 0 or spike_timeout:
            status = "SPIKE_FAIL"
        elif rtl_timeout:
            status = "RTL_TIMEOUT"
        elif "commit watchdog" in rtl_text:
            status = "RTL_STALL"
        elif rtl_rc != 0 or not rtl_success:
            status = "RTL_FAIL"
        elif comparison.get("status") not in {"MATCH", "PREFIX"}:
            status = "MISMATCH"
        elif trace_summary.get("status") != "VALID":
            status = "TRACE_FAIL"
        elif options.vector_commit_compare and vector_commit.get("status") != "PASS":
            status = "VECTOR_MISMATCH"
        else:
            status = "PASS"

        result: Dict[str, object] = {
            "name": elf.stem,
            "seed": generation.seed + index,
            "elf": str(elf),
            "status": status,
            "spike_returncode": spike_rc,
            "spike_elapsed_s": round(spike_elapsed, 3),
            "spike_timed_out": spike_timeout,
            "rtl_returncode": rtl_rc,
            "rtl_elapsed_s": round(rtl_elapsed, 3),
            "rtl_timed_out": rtl_timeout,
            "comparison": comparison,
            "trace": trace_summary,
            "vector_signature": strict_vector_state,
            "vector_checkpoints": options.vector_checkpoints,
            "vector_commit_compare": options.vector_commit_compare,
            "vector_commit": vector_commit,
            "artifact_dir": str(case),
        }
        (case / "result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        results.append(result)
        checkpoint_text = ""
        checkpoint = comparison.get("vector_checkpoint")
        if isinstance(checkpoint, dict):
            checkpoint_text = (
                f" checkpoint={checkpoint.get('index')}:{checkpoint.get('site')}"
            )
        print(
            f"[{status:11}] {elf.stem} "
            f"matched={comparison.get('matched_instructions', 0)} "
            f"spike={spike_elapsed:.2f}s rtl={rtl_elapsed:.2f}s{checkpoint_text}" +
            (f" vector={vector_commit.get('status')}"
             if options.vector_commit_compare else ""),
            flush=True,
        )

    (output / "summary.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if all(result["status"] == "PASS" for result in results) else 1
