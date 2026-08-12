from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .random_rvv import _elf_entry
from .spike_trace import CommitComparisonError, compare_commit_prefix
from .trace import TraceValidationError, validate_trace
from .vector_commit import (
    VectorCommitComparisonError,
    compare_vector_commits,
    unobservable_vector_scalar_write_indices,
)


@dataclass(frozen=True)
class RvvPostprocessOptions:
    output: Path
    cases: Sequence[str] = ()
    force: bool = False


def _load_command(path: Path) -> List[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    command = payload.get("command", [])
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise ValueError(f"invalid command metadata: {path}")
    return command


def _plusarg(command: Sequence[str], name: str) -> Optional[str]:
    prefix = f"+{name}="
    return next((item[len(prefix):] for item in command if item.startswith(prefix)), None)


def _error(reason: str) -> Dict[str, object]:
    return {"status": "ERROR", "reason": reason}


def postprocess_existing_case(case: Path, readelf: Path) -> Dict[str, object]:
    result_path = case / "result.json"
    try:
        rtl_command = _load_command(case / "rtl.command.json")
        preload = _plusarg(rtl_command, "PRELOAD")
        if preload is None:
            raise ValueError("rtl.command.json has no +PRELOAD argument")
        elf = Path(preload).resolve()
        if not elf.is_file():
            raise ValueError(f"ELF no longer exists: {elf}")
        seed_text = _plusarg(rtl_command, "ntb_random_seed")
        seed = int(seed_text) if seed_text is not None else None
        entry = _elf_entry(elf, readelf)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        result = {
            "name": case.name,
            "status": "ARTIFACT_INCOMPLETE",
            "reason": str(error),
            "artifact_dir": str(case),
            "postprocessed_existing_artifacts": True,
        }
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    spike_log = case / "spike_commit.log"
    ara_trace = case / "ara_commit_trace.csv"
    vector_trace = case / "ara_vector_trace.csv"
    vector_expected = _plusarg(rtl_command, "VECTOR_TRACE") is not None

    rtl_text = ""
    for log in (case / "rtl_console.log", case / "run.vcs.log"):
        if log.is_file():
            rtl_text += log.read_text(encoding="utf-8", errors="replace")
    rtl_success = "Core Test *** SUCCESS ***" in rtl_text

    unobservable_register_values = set()
    if vector_expected:
        try:
            unobservable_register_values = unobservable_vector_scalar_write_indices(
                spike_log, ara_trace, vector_trace, entry
            )
        except (CommitComparisonError, VectorCommitComparisonError, OSError):
            pass
    try:
        comparison: Dict[str, object] = compare_commit_prefix(
            spike_log, ara_trace, entry, unobservable_register_values
        )
    except (CommitComparisonError, OSError) as error:
        comparison = _error(str(error))
    (case / "commit_comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    try:
        trace: Dict[str, object] = {"status": "VALID", **validate_trace(ara_trace)}
    except (TraceValidationError, OSError) as error:
        trace = _error(str(error))
    (case / "trace_summary.json").write_text(
        json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    vector: Dict[str, object] = {"status": "DISABLED"}
    if vector_expected:
        try:
            vector = compare_vector_commits(spike_log, ara_trace, vector_trace, entry)
        except (CommitComparisonError, VectorCommitComparisonError, OSError) as error:
            vector = _error(str(error))
        (case / "vector_commit_comparison.json").write_text(
            json.dumps(vector, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    if not rtl_success:
        status = "RTL_INCOMPLETE"
    elif comparison.get("status") not in {"MATCH", "PREFIX"}:
        status = "MISMATCH"
    elif trace.get("status") != "VALID":
        status = "TRACE_FAIL"
    elif vector_expected and vector.get("status") != "PASS":
        status = "VECTOR_MISMATCH"
    else:
        status = "PASS"

    result = {
        "name": case.name,
        "seed": seed,
        "elf": str(elf),
        "status": status,
        "comparison": comparison,
        "trace": trace,
        "vector_commit_compare": vector_expected,
        "vector_commit": vector,
        "artifact_dir": str(case),
        "postprocessed_existing_artifacts": True,
    }
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def postprocess_existing_run(options: RvvPostprocessOptions, repo_root: Path) -> List[Dict[str, object]]:
    tests_root = options.output / "tests"
    if not tests_root.is_dir():
        raise ValueError(f"test artifact directory does not exist: {tests_root}")
    selected = set(options.cases)
    case_dirs = sorted(path for path in tests_root.iterdir() if path.is_dir())
    if selected:
        missing = selected.difference(path.name for path in case_dirs)
        if missing:
            raise ValueError(f"requested artifact cases do not exist: {sorted(missing)}")
        case_dirs = [path for path in case_dirs if path.name in selected]

    readelf = repo_root / "install/riscv-gcc/bin/riscv64-unknown-elf-readelf"
    for case in case_dirs:
        result_path = case / "result.json"
        if options.force or not result_path.is_file():
            result = postprocess_existing_case(case, readelf)
            print(f"[{result['status']:15}] {case.name}", flush=True)

    results: List[Dict[str, object]] = []
    for case in sorted(path for path in tests_root.iterdir() if path.is_dir()):
        result_path = case / "result.json"
        if result_path.is_file():
            results.append(json.loads(result_path.read_text(encoding="utf-8")))
    (options.output / "summary.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return results


__all__ = [
    "RvvPostprocessOptions",
    "postprocess_existing_case",
    "postprocess_existing_run",
]
