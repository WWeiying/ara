"""Re-audit a completed random RVV terminal exit without rerunning VCS."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .artifacts import check_inputs
from .plan import _full_vector_match
from .random_rvv import _elf_entry, _elf_symbol, _vector_exit_pc
from .spike_trace import compare_commit_prefix
from .trace import validate_trace
from .vector_commit import (compare_vector_commits,
                            unobservable_vector_scalar_write_indices)


ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def command_value(command: list[str], name: str) -> str:
    values = [item.split("=", 1)[1] for item in command
              if isinstance(item, str) and item.startswith(f"+{name}=")]
    if len(values) != 1:
        raise ValueError(f"expected exactly one +{name} argument")
    return values[0]


def simulator_image(simv: Path) -> dict[str, str]:
    library_dir = Path(str(simv) + ".daidir")
    libraries = sorted(library_dir.rglob("*.so"))
    if not simv.is_file() or not libraries:
        raise ValueError("VCS executable or generated libraries are missing")
    return {str(path.relative_to(simv.parent)): digest(path)
            for path in (simv, *libraries)}


def spike_image(command: object, case: Path, elf: Path) -> Path:
    if (not isinstance(command, list) or len(command) < 2 or
            not all(isinstance(arg, str) for arg in command) or
            Path(command[-1]).resolve() != elf or
            command.count(f"--log={case / 'spike_commit.log'}") != 1):
        raise ValueError("Spike command does not identify the audited ELF and commit log")
    binary = Path(command[0]).resolve()
    if not binary.is_file():
        raise ValueError("Spike executable is missing")
    return binary


def audit(case: Path, readelf: Path, *, require_frozen_inputs: bool = False) -> dict[str, object]:
    case = case.resolve()
    command_path = case / "rtl.command.json"
    command = json.loads(command_path.read_text(encoding="utf-8"))["command"]
    if not isinstance(command, list) or not command or not all(
            isinstance(arg, str) for arg in command):
        raise ValueError("invalid RTL command metadata")
    simv = Path(command[0]).resolve()
    elf = Path(command_value(command, "PRELOAD")).resolve()
    spike_command_path = case / "spike.command.json"
    spike_command = json.loads(spike_command_path.read_text(encoding="utf-8"))["command"]
    spike_binary = spike_image(spike_command, case, elf)
    inputs_path = case / "inputs.json"
    if require_frozen_inputs and (not inputs_path.is_file() or elf != case / "input.elf"):
        raise ValueError("frozen per-case ELF and inputs.json are required")
    if inputs_path.is_file():
        inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
        if Path(inputs["simv"]["path"]).resolve() != simv or \
                Path(inputs["spike"]["path"]).resolve() != spike_binary:
            raise ValueError("recorded simulator or Spike differs from executed command")
        input_errors = check_inputs(inputs, elf)
        if input_errors:
            raise ValueError(f"frozen inputs changed: {input_errors}")
    spike = case / "spike_commit.log"
    ara = case / "ara_commit_trace.csv"
    vector = case / "ara_vector_trace.csv"
    console = case / "rtl_console.log"
    for key, expected in (("COMMIT_TRACE", ara), ("VECTOR_TRACE", vector)):
        if Path(command_value(command, key)).resolve() != expected:
            raise ValueError(f"+{key} points outside the audited case")
    tohost = int(command_value(command, "COMMIT_TOHOST"), 16)
    if _elf_symbol(elf, readelf, "tohost") != tohost:
        raise ValueError("configured tohost differs from the frozen ELF symbol")
    exit_args = [arg for arg in command if arg.startswith("+COMMIT_EXIT_PC=")]
    exit_pc = None
    if exit_args:
        if len(exit_args) != 1:
            raise ValueError("expected at most one +COMMIT_EXIT_PC argument")
        exit_pc = int(command_value(command, "COMMIT_EXIT_PC"), 16)
        objdump = ROOT / "install/riscv-llvm/bin/llvm-objdump"
        if _vector_exit_pc(elf, readelf, objdump) != exit_pc:
            raise ValueError("configured exit PC differs from the ELF vector-signature exit")
    if json.loads((case / "result.json").read_text(encoding="utf-8")).get("status") != "PASS":
        raise ValueError("original run did not pass")
    log = console.read_text(encoding="utf-8", errors="replace")
    if log.count("Core Test *** SUCCESS ***") != 1 or "Fatal:" in log:
        raise ValueError("RTL success marker is absent, duplicated or accompanied by fatal")

    entry = _elf_entry(elf, readelf)
    unobservable = unobservable_vector_scalar_write_indices(spike, ara, vector, entry)
    comparison = compare_commit_prefix(
        spike, ara, entry, unobservable, terminal_ecall_pc=exit_pc,
        terminal_tohost_address=tohost,
        rtl_exception_log=(case / "trace_hart_0.log") if (case / "trace_hart_0.log").is_file() else None)
    vector_result = compare_vector_commits(
        spike, ara, vector, entry,
        aligned_vector_faults=comparison.get("aligned_vector_faults"),
    )
    trace_result = {"status": "VALID", **validate_trace(ara)}
    issues = []
    if comparison["status"] not in {"TERMINAL_MATCH", "TERMINAL_TOHOST_MATCH"}:
        issues.append("full architectural comparison did not end at a verified terminal exit")
    if not _full_vector_match(vector_result):
        issues.append("full vector destination comparison is incomplete")
    if trace_result["status"] != "VALID":
        issues.append("RTL retirement trace is invalid")
    files = {name: path for name, path in (
        ("elf", elf), ("simv", simv), ("spike_binary", spike_binary),
        ("spike_command", spike_command_path), ("rtl_command", command_path),
        ("rtl_console", console), ("spike_commit", spike),
        ("ara_commit", ara), ("ara_vector", vector),
    )}
    if inputs_path.is_file():
        files["inputs"] = inputs_path
    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "scope": "one completed random RVV program; verified ecall/tohost terminal exit, complete vector destination request accounting and comparison of architecturally known bytes",
        "case": str(case),
        "tohost": f"0x{tohost:016x}",
        "terminal_ecall_pc": f"0x{exit_pc:016x}" if exit_pc is not None else None,
        "input_sha256": {name: digest(path) for name, path in files.items()},
        "simv_image_sha256": simulator_image(simv),
        "comparison": comparison,
        "vector_comparison": vector_result,
        "trace_validation": trace_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-frozen-inputs", action="store_true")
    parser.add_argument("--readelf", type=Path, default=ROOT /
                        "install/riscv-gcc/bin/riscv64-unknown-elf-readelf")
    args = parser.parse_args()
    try:
        result = audit(args.case, args.readelf,
                       require_frozen_inputs=args.require_frozen_inputs)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        result = {"status": "FAIL", "issues": [str(error)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"RVV terminal re-audit: {result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
