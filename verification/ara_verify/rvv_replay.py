from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .random_rvv import (
    _elf_entry,
    _elf_symbol,
    _vector_exit_pc,
    _run_logged,
    _run_rtl,
    _write_command,
)
from .spike_trace import CommitComparisonError, compare_commit_prefix
from .trace import TraceValidationError, validate_trace
from .vector_commit import (
    VectorCommitComparisonError,
    compare_vector_commits,
    unobservable_vector_scalar_write_indices,
)


@dataclass(frozen=True)
class RvvReplayCase:
    name: str
    profile: str
    seed: int
    previous_status: str
    elf: Path


@dataclass(frozen=True)
class RvvReplayOptions:
    output: Path
    simv: Path
    spike: Path
    timeout_s: int
    spike_timeout_s: int
    watchdog_cycles: int
    jobs: int = 1


def _optional_vector_exit_pc(elf: Path, readelf: Path, objdump: Path) -> Optional[int]:
    try:
        return _vector_exit_pc(elf, readelf, objdump)
    except RuntimeError as error:
        if "has no vector-signature exit symbol" in str(error):
            return None
        raise


def _profile_root(row: Dict[str, object]) -> Path:
    artifact = str(row.get("artifact_dir", ""))
    if artifact:
        return Path(artifact).resolve().parents[1]
    source = Path(str(row.get("summary_source", ""))).resolve()
    return source.parent if source.suffix == ".json" else source


def failed_random_cases(
    summary: Path, names: Optional[Sequence[str]] = None
) -> List[RvvReplayCase]:
    payload = json.loads(summary.read_text(encoding="utf-8"))
    selected = set(names or ())
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("results", [])
    else:
        rows = []
    cases: List[RvvReplayCase] = []
    for row in rows:
        # Per-profile and replay summaries predate the campaign-level ``class``
        # field. Profile/ELF plus seed still identifies a replayable random case.
        if row.get("class") not in (None, "random") or \
                ("profile" not in row and "elf" not in row) or \
                "seed" not in row or \
                row.get("status") == "PASS":
            continue
        name = str(row["name"])
        if selected and name not in selected:
            continue
        root = _profile_root(row)
        elf = (Path(str(row["elf"])).resolve() if row.get("elf") else
               root / "asm_test" / f"{name}.o")
        cases.append(RvvReplayCase(
            name=name,
            profile=str(row.get("profile", "")),
            seed=int(row["seed"]),
            previous_status=str(row["status"]),
            elf=elf,
        ))
    missing_names = selected.difference(case.name for case in cases)
    if missing_names:
        raise ValueError(f"requested cases not found among failed random tests: {sorted(missing_names)}")
    return cases


def _run_case(options: RvvReplayOptions, replay: RvvReplayCase) -> Dict[str, object]:
    case = options.output / "tests" / replay.name
    case.mkdir(parents=True, exist_ok=True)
    if not replay.elf.is_file():
        return {
            "name": replay.name,
            "profile": replay.profile,
            "seed": replay.seed,
            "previous_status": replay.previous_status,
            "status": "MISSING_ELF",
            "elf": str(replay.elf),
            "artifact_dir": str(case),
        }

    readelf = Path(__file__).resolve().parents[2] / "install/riscv-gcc/bin/riscv64-unknown-elf-readelf"
    entry = _elf_entry(replay.elf, readelf)
    tohost = _elf_symbol(replay.elf, readelf, "tohost")
    objdump = Path(__file__).resolve().parents[2] / "install/riscv-llvm/bin/llvm-objdump"
    exit_pc = _optional_vector_exit_pc(replay.elf, readelf, objdump)
    spike_log = case / "spike_commit.log"
    spike_command = [
        str(options.spike), "--isa=rv64gcv_zvl1024b", "--log-commits",
        f"--log={spike_log}", str(replay.elf),
    ]
    _write_command(case / "spike.command.json", spike_command, case)
    spike_rc, spike_elapsed, spike_timeout = _run_logged(
        spike_command, case, case / "spike_console.log", timeout_s=options.spike_timeout_s
    )

    ara_trace = case / "ara_commit_trace.csv"
    vector_trace = case / "ara_vector_trace.csv"
    rtl_command = [
        str(options.simv), "-l", "run.vcs.log",
        f"+ntb_random_seed={replay.seed}", f"+PRELOAD={replay.elf}",
        f"+TESTCASE={replay.name}", "+NO_FSDB", f"+COMMIT_TRACE={ara_trace}",
        f"+VECTOR_TRACE={vector_trace}",
        f"+COMMIT_WATCHDOG={options.watchdog_cycles}",
        f"+COMMIT_TOHOST={tohost:016x}",
    ]
    if exit_pc is not None:
        rtl_command.append(f"+COMMIT_EXIT_PC={exit_pc:016x}")
    _write_command(case / "rtl.command.json", rtl_command, case)
    rtl_rc, rtl_elapsed, rtl_timeout = _run_rtl(
        rtl_command, case, case / "rtl_console.log", options.timeout_s
    )

    rtl_text = ""
    for log in (case / "rtl_console.log", case / "run.vcs.log"):
        if log.is_file():
            rtl_text += log.read_text(encoding="utf-8", errors="replace")
    rtl_success = "Core Test *** SUCCESS ***" in rtl_text

    unobservable_register_values = set()
    try:
        unobservable_register_values = unobservable_vector_scalar_write_indices(
            spike_log, ara_trace, vector_trace, entry
        )
    except (CommitComparisonError, VectorCommitComparisonError):
        pass
    try:
        comparison: Dict[str, object] = compare_commit_prefix(
            spike_log, ara_trace, entry, unobservable_register_values
        )
    except CommitComparisonError as error:
        comparison = {"status": "ERROR", "reason": str(error)}
    (case / "commit_comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    try:
        trace: Dict[str, object] = {"status": "VALID", **validate_trace(ara_trace)}
    except TraceValidationError as error:
        trace = {"status": "ERROR", "reason": str(error)}
    (case / "trace_summary.json").write_text(
        json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    try:
        vector_stop_index = (
            min(unobservable_register_values)
            if comparison.get("status") == "PREFIX" and
            unobservable_register_values else None
        )
        vector = compare_vector_commits(
            spike_log, ara_trace, vector_trace, entry,
            stop_spike_index=vector_stop_index,
        )
    except (CommitComparisonError, VectorCommitComparisonError) as error:
        vector = {"status": "ERROR", "reason": str(error)}
    (case / "vector_commit_comparison.json").write_text(
        json.dumps(vector, indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
    elif trace.get("status") != "VALID":
        status = "TRACE_FAIL"
    elif vector.get("status") != "PASS" and not (
        comparison.get("status") == "PREFIX" and
        vector.get("status") == "PREFIX"
    ):
        status = "VECTOR_MISMATCH"
    else:
        status = "PASS"

    result: Dict[str, object] = {
        "name": replay.name,
        "profile": replay.profile,
        "seed": replay.seed,
        "previous_status": replay.previous_status,
        "status": status,
        "elf": str(replay.elf),
        "spike_returncode": spike_rc,
        "spike_elapsed_s": round(spike_elapsed, 3),
        "spike_timed_out": spike_timeout,
        "rtl_returncode": rtl_rc,
        "rtl_elapsed_s": round(rtl_elapsed, 3),
        "rtl_timed_out": rtl_timeout,
        "comparison": comparison,
        "trace": trace,
        "vector_commit": vector,
        "artifact_dir": str(case),
    }
    (case / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def replay_failed_cases(
    options: RvvReplayOptions, cases: Iterable[RvvReplayCase]
) -> List[Dict[str, object]]:
    selected = list(cases)
    if options.jobs <= 0:
        raise ValueError("jobs must be positive")
    options.output.mkdir(parents=True, exist_ok=True)
    manifest = [
        {
            "name": case.name,
            "profile": case.profile,
            "seed": case.seed,
            "previous_status": case.previous_status,
            "elf": str(case.elf),
        }
        for case in selected
    ]
    (options.output / "replay_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    results: List[Dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=options.jobs) as executor:
        futures = {executor.submit(_run_case, options, case): case for case in selected}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            vector = result.get("vector_commit", {})
            print(
                f"[{result['status']:15}] {result['name']} seed={result['seed']} "
                f"rtl={result.get('rtl_elapsed_s', 0):.2f}s "
                f"vector={vector.get('status', 'N/A')}",
                flush=True,
            )
    results.sort(key=lambda item: (str(item["profile"]), int(item["seed"])))
    (options.output / "summary.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return results


__all__ = [
    "RvvReplayCase",
    "RvvReplayOptions",
    "failed_random_cases",
    "replay_failed_cases",
]
