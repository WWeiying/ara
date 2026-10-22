from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .artifacts import check_inputs, sha256, simulation_image
from .random_rvv import (
    _elf_entry,
    _elf_symbol,
    _git_snapshot,
    _vector_exit_pc,
    _run_logged,
    _run_rtl,
    _require_completed_reference,
    _write_command,
)
from .spike_trace import CommitComparisonError, compare_commit_prefix
from .spike_probe import check_spike_vstart, probe_paths
from .trace import TraceValidationError, validate_trace
from .vector_commit import (
    VectorCommitComparisonError,
    compare_vector_commits,
    unobservable_vector_scalar_write_indices,
)


def _rtl_setup_error(log: str) -> bool:
    return "UVM_FATAL" in log and "[NOCOMP]" in log


def _replay_comparison_status(comparison: dict, vector: dict) -> str:
    match = comparison.get("status")
    if match == "PREFIX":
        return "INCOMPLETE_PREFIX"
    if match not in {"MATCH", "TERMINAL_MATCH", "TERMINAL_TOHOST_MATCH"}:
        return "MISMATCH"
    if vector.get("status") == "PASS":
        return "PASS"
    return "VECTOR_INCOMPLETE" if vector.get("status") == "PREFIX" else "VECTOR_MISMATCH"


def _freeze_replay_inputs(options: RvvReplayOptions, replay: RvvReplayCase,
                          case: Path) -> tuple[Path, dict]:
    frozen_elf = case / "input.elf"
    source_hash = sha256(replay.elf)
    shutil.copy2(replay.elf, frozen_elf)
    if sha256(frozen_elf) != source_hash:
        raise RuntimeError(f"replay ELF changed while freezing: {replay.elf}")
    inputs = {
        "binary": {"source": str(replay.elf), "path": str(frozen_elf),
                   "sha256": source_hash},
        "simv": {"path": str(options.simv),
                  "image_sha256": simulation_image(options.simv)},
        "spike": {"path": str(options.spike), "sha256": sha256(options.spike)},
    }
    (case / "inputs.json").write_text(
        json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return frozen_elf, inputs


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
    spike_isa: str = "rv64gcv_zvl1024b"
    fault_vstart_probe: bool = False


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
    summary: Path, names: Optional[Sequence[str]] = None,
    include_passed: bool = False,
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
                (row.get("status") == "PASS" and not include_passed):
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
        raise ValueError(f"requested cases not found among selected random tests: {sorted(missing_names)}")
    if not cases:
        raise ValueError("no replayable random cases selected")
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

    frozen_elf, inputs = _freeze_replay_inputs(options, replay, case)
    readelf = Path(__file__).resolve().parents[2] / "install/riscv-gcc/bin/riscv64-unknown-elf-readelf"
    entry = _elf_entry(frozen_elf, readelf)
    tohost = _elf_symbol(frozen_elf, readelf, "tohost")
    objdump = Path(__file__).resolve().parents[2] / "install/riscv-llvm/bin/llvm-objdump"
    exit_pc = _optional_vector_exit_pc(frozen_elf, readelf, objdump)
    spike_log = case / "spike_commit.log"
    spike_command = [
        str(options.spike), f"--isa={options.spike_isa}", "--log-commits",
        f"--log={spike_log}", str(frozen_elf),
    ]
    _write_command(case / "spike.command.json", spike_command, case)
    spike_rc, spike_elapsed, spike_timeout = _run_logged(
        spike_command, case, case / "spike_console.log", timeout_s=options.spike_timeout_s
    )

    ara_trace = case / "ara_commit_trace.csv"
    vector_trace = case / "ara_vector_trace.csv"
    rtl_command = [
        str(options.simv), "-l", "run.vcs.log",
        f"+ntb_random_seed={replay.seed}", f"+PRELOAD={frozen_elf}",
        f"+TESTCASE={replay.name}", "+NO_FSDB", f"+COMMIT_TRACE={ara_trace}",
        f"+VECTOR_TRACE={vector_trace}",
        f"+COMMIT_WATCHDOG={options.watchdog_cycles}",
        f"+COMMIT_TOHOST={tohost:016x}",
    ]
    if exit_pc is not None:
        rtl_command.append(f"+COMMIT_EXIT_PC={exit_pc:016x}")
    if options.fault_vstart_probe:
        rtl_command.append("+ARA_FAULT_VSTART_PROBE")
    _write_command(case / "rtl.command.json", rtl_command, case)
    rtl_rc, rtl_elapsed, rtl_timeout = _run_rtl(
        rtl_command, case, case / "rtl_console.log", options.timeout_s
    )

    rtl_text = ""
    for log in (case / "rtl_console.log", case / "run.vcs.log"):
        if log.is_file():
            rtl_text += log.read_text(encoding="utf-8", errors="replace")
    rtl_success = "Core Test *** SUCCESS ***" in rtl_text

    reference_valid = spike_rc == 0 and not spike_timeout
    unobservable_register_values = set()
    try:
        _require_completed_reference(spike_rc, spike_timeout)
        unobservable_register_values = unobservable_vector_scalar_write_indices(
            spike_log, ara_trace, vector_trace, entry
        )
    except (CommitComparisonError, VectorCommitComparisonError):
        pass
    try:
        _require_completed_reference(spike_rc, spike_timeout)
        comparison: Dict[str, object] = compare_commit_prefix(
            spike_log, ara_trace, entry, unobservable_register_values,
            terminal_ecall_pc=exit_pc,
            terminal_tohost_address=tohost,
            rtl_exception_log=(case / "trace_hart_0.log") if (case / "trace_hart_0.log").is_file() else None,
            fault_vector_trace=vector_trace if options.fault_vstart_probe else None,
            fault_probe_log=(case / "run.vcs.log") if options.fault_vstart_probe else None,
        )
    except (CommitComparisonError, VectorCommitComparisonError) as error:
        comparison = {"status": "ERROR" if reference_valid else "SKIPPED_REFERENCE_FAILURE",
                      "reason": str(error), "vector_state_compared": False}
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
        _require_completed_reference(spike_rc, spike_timeout)
        vector_stop_index = (
            min(unobservable_register_values)
            if comparison.get("status") == "PREFIX" and
            unobservable_register_values else None
        )
        vector = compare_vector_commits(
            spike_log, ara_trace, vector_trace, entry,
            stop_spike_index=vector_stop_index,
            aligned_vector_faults=comparison.get("aligned_vector_faults"),
            fault_probe_log=(case / "run.vcs.log") if options.fault_vstart_probe else None,
        )
    except (CommitComparisonError, VectorCommitComparisonError) as error:
        vector = {"status": "ERROR" if reference_valid else "SKIPPED_REFERENCE_FAILURE",
                  "reason": str(error)}
    (case / "vector_commit_comparison.json").write_text(
        json.dumps(vector, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    input_errors = check_inputs(inputs, frozen_elf)
    if input_errors:
        status = "INPUT_CHANGED"
    elif spike_rc != 0 or spike_timeout:
        status = "SPIKE_FAIL"
    elif _rtl_setup_error(rtl_text):
        status = "RTL_SETUP_FAIL"
    elif rtl_timeout:
        status = "RTL_TIMEOUT"
    elif "commit watchdog" in rtl_text:
        status = "RTL_STALL"
    elif rtl_rc != 0 or not rtl_success:
        status = "RTL_FAIL"
    elif trace.get("status") != "VALID":
        status = "TRACE_FAIL"
    else:
        status = _replay_comparison_status(comparison, vector)

    result: Dict[str, object] = {
        "name": replay.name,
        "profile": replay.profile,
        "seed": replay.seed,
        "previous_status": replay.previous_status,
        "status": status,
        "elf": str(frozen_elf),
        "source_elf": str(replay.elf),
        "input_errors": input_errors,
        "spike_returncode": spike_rc,
        "spike_elapsed_s": round(spike_elapsed, 3),
        "spike_timed_out": spike_timeout,
        "rtl_returncode": rtl_rc,
        "rtl_elapsed_s": round(rtl_elapsed, 3),
        "rtl_timed_out": rtl_timeout,
        "rtl_success": rtl_success,
        "rtl_failure_lines": [line for line in rtl_text.splitlines()
                              if any(word in line.lower() for word in
                                     ("fatal", "failed", "watchdog", "exceeds"))][:16],
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
    repo_root = Path(__file__).resolve().parents[2]
    probe_gcc, probe_source = probe_paths(repo_root)
    probe = check_spike_vstart(options.spike, probe_gcc,
                               options.output / "spike_probe", probe_source)
    if probe["status"] != "PASS":
        raise ValueError(f"Spike lacks nonzero-vstart ALU support: "
                         f"{options.output / 'spike_probe/spike_probe.json'}")
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
    run_metadata = {
        "schema_version": 1,
        "status": "RUNNING",
        "created_at": datetime.now().astimezone().isoformat(),
        "invocation": ["verification/verify.py", "replay-failed-rvv"],
        "git": _git_snapshot(repo_root),
        "input_snapshots": True,
        "fault_vstart_probe": options.fault_vstart_probe,
        "spike_isa": options.spike_isa,
        "simv_image_sha256": simulation_image(options.simv),
        "spike_sha256": sha256(options.spike),
        "timeouts": {
            "rtl_s": options.timeout_s,
            "spike_s": options.spike_timeout_s,
            "watchdog_cycles": options.watchdog_cycles,
        },
    }
    (options.output / "run.json").write_text(
        json.dumps(run_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
    run_metadata.update({
        "status": "COMPLETE",
        "verdict": "PASS" if all(result["status"] == "PASS" for result in results) else "FAIL",
        "completed_at": datetime.now().astimezone().isoformat(),
        "status_counts": {
            status: sum(result["status"] == status for result in results)
            for status in sorted({str(result["status"]) for result in results})
        },
    })
    (options.output / "run.json").write_text(
        json.dumps(run_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return results


__all__ = [
    "RvvReplayCase",
    "RvvReplayOptions",
    "failed_random_cases",
    "replay_failed_cases",
]
