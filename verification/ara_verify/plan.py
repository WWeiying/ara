from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .catalog import Catalog, ManifestError
from .contract import check_contract_log
from .artifacts import check_inputs, sha256
from .probes import check_probe_capture
from .stimulus_coverage import collect_stimulus_coverage


class PlanError(ValueError):
    """Raised when the verification plan or an audit result is not signoff-safe."""


def load_plan(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanError(f"cannot load verification plan {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise PlanError("verification plan must be an object with schema_version=1")
    if not isinstance(payload.get("requirements"), list) or not payload["requirements"]:
        raise PlanError("verification plan has no requirements")
    return payload


def _names(values: object) -> List[str]:
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise PlanError("plan references must be a list of strings")
    return list(values)


def validate_plan(catalog: Catalog, plan: Mapping[str, Any]) -> Dict[str, Any]:
    requirements = plan.get("requirements")
    if not isinstance(requirements, list):
        raise PlanError("requirements must be a list")
    seen: set[str] = set()
    records: List[Dict[str, Any]] = []
    for item in requirements:
        if not isinstance(item, dict):
            raise PlanError("each requirement must be an object")
        requirement_id = item.get("id")
        if not isinstance(requirement_id, str) or not requirement_id:
            raise PlanError("each requirement needs a non-empty id")
        if requirement_id in seen:
            raise PlanError(f"duplicate requirement id: {requirement_id}")
        seen.add(requirement_id)
        suite_names = _names(item.get("suites", []))
        missing_suites = [name for name in suite_names if name not in catalog.suites]
        if missing_suites:
            raise ManifestError(
                f"requirement {requirement_id} references unknown suites: {missing_suites}"
            )
        selected = []
        for suite_name in suite_names:
            selected.extend(test.name for test in catalog.resolve_suite(suite_name))
        records.append({
            "id": requirement_id,
            "title": item.get("title", ""),
            "risk": item.get("risk", "unspecified"),
            "suites": suite_names,
            "test_count": len(set(selected)),
            "evidence": _names(item.get("evidence", [])),
            "random_profiles": _names(item.get("random_profiles", [])),
            "linux_levels": _names(item.get("linux_levels", [])),
        })
    dimensions = plan.get("coverage_dimensions", {})
    if not isinstance(dimensions, dict) or not dimensions:
        raise PlanError("coverage_dimensions must be a non-empty object")
    constraints = plan.get("coverage_constraints", {})
    if not isinstance(constraints, dict) or type(constraints.get("elen_bits")) is not int or (
            constraints["elen_bits"] <= 0 or constraints["elen_bits"] &
            (constraints["elen_bits"] - 1)):
        raise PlanError("coverage_constraints.elen_bits must be a positive power of two")
    random_profiles = sorted({
        profile
        for record in records
        for profile in record["random_profiles"]
    })
    linux_levels = sorted({
        level
        for item in requirements
        if isinstance(item, dict)
        for level in _names(item.get("linux_levels", []))
    })
    return {
        "status": "VALID",
        "requirements": records,
        "requirement_count": len(records),
        "random_profile_count": len(random_profiles),
        "random_profiles": random_profiles,
        "linux_level_count": len(linux_levels),
        "linux_levels": linux_levels,
        "coverage_dimensions": {
            str(name): _names(values) for name, values in dimensions.items()
        },
        "coverage_constraints": {"elen_bits": constraints["elen_bits"]},
    }


def _artifact_dir(run_root: Path, row: Mapping[str, Any]) -> Optional[Path]:
    raw = row.get("artifact_dir")
    if not raw:
        return None
    path = Path(str(raw))
    return path if path.is_absolute() else run_root / path


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _status(value: object) -> str:
    return str(value or "").upper()


def _full_architecture_match(comparison: Optional[Mapping[str, Any]]) -> bool:
    if comparison is None or comparison.get("mismatch") is not None:
        return False
    matched = comparison.get("matched_instructions")
    committed = comparison.get("ara_committed_instructions")
    if not isinstance(matched, int) or matched <= 0 or matched != committed:
        return False
    if _status(comparison.get("status")) == "MATCH":
        return True
    if _status(comparison.get("status")) == "TERMINAL_TOHOST_MATCH":
        terminal = comparison.get("terminal_tohost")
        last = comparison.get("last_matched")
        return (isinstance(terminal, dict) and isinstance(last, dict)
                and terminal.get("write_value") == "0x1"
                and terminal.get("pc") == last.get("pc")
                and terminal.get("instruction") == last.get("instruction")
                and last.get("memory_accesses") == [{
                    "address": terminal.get("address"), "write_value": "0x1"}]
                and comparison.get("stopped_at_unobservable") is None)
    return (
        _status(comparison.get("status")) == "TERMINAL_MATCH"
        and isinstance(comparison.get("terminal_ecall"), dict)
        and comparison["terminal_ecall"].get("instruction") == "0x00000073"
        and comparison["terminal_ecall"].get("trap") is True
        and comparison.get("stopped_at_unobservable") is None
    )


def _terminal_exit_matches_command(artifact: Path, comparison: Mapping[str, Any]) -> bool:
    command = _read_json(artifact / "rtl.command.json")
    arguments = command.get("command") if command is not None else None
    terminal = comparison.get("terminal_ecall")
    if not isinstance(arguments, list) or not isinstance(terminal, dict):
        return False
    exit_args = [arg.split("=", 1)[1] for arg in arguments
                 if isinstance(arg, str) and arg.startswith("+COMMIT_EXIT_PC=")]
    if len(exit_args) != 1:
        return False
    try:
        return int(exit_args[0], 16) == int(str(terminal.get("pc")), 16)
    except (TypeError, ValueError):
        return False


def _terminal_tohost_matches_command(artifact: Path, comparison: Mapping[str, Any]) -> bool:
    command = _read_json(artifact / "rtl.command.json")
    arguments = command.get("command") if command is not None else None
    terminal = comparison.get("terminal_tohost")
    if not isinstance(arguments, list) or not isinstance(terminal, dict):
        return False
    addresses = [arg.split("=", 1)[1] for arg in arguments
                 if isinstance(arg, str) and arg.startswith("+COMMIT_TOHOST=")]
    if len(addresses) != 1 or terminal.get("write_value") != "0x1":
        return False
    try:
        if int(addresses[0], 16) != int(str(terminal.get("address")), 16):
            return False
    except (TypeError, ValueError):
        return False
    log = artifact / "rtl_console.log"
    return log.is_file() and "Core Test *** SUCCESS ***" in log.read_text(
        encoding="utf-8", errors="replace")


def _valid_load_fault_proof(proof: Any) -> bool:
    if not isinstance(proof, dict):
        return False
    counts = ("arch_seq", "index", "vstart_before", "vstart_after", "probe_next_time",
              "accepted_byte_events", "final_written_bytes", "required_load_bytes",
              "verified_load_bytes", "maintenance_bytes", "preserved_unknown_bytes",
              "duplicate_bytes", "full_destination_bytes")
    if not all(type(proof.get(key)) is int and proof[key] >= 0 for key in counts):
        return False
    try:
        pc = int(proof["pc"], 16)
        instruction = int(proof["instruction"], 16)
    except (KeyError, ValueError, TypeError):
        return False
    csrs = proof.get("expected_fault_csrs")
    inputs = proof.get("inputs")
    elements = proof["vstart_after"] - proof["vstart_before"]
    fields = (instruction >> 29) + 1
    partial_bytes_valid = (
        proof["required_load_bytes"] == 0 if elements == 0 else
        proof["required_load_bytes"] in {elements * fields * width for width in (1, 2, 4, 8)}
    )
    return (
        0 <= instruction < (1 << 32) and instruction & 127 == 7
        and (instruction >> 26) & 3 in (1, 3) and (instruction >> 25) & 1 == 1
        and (instruction >> 28) & 1 == 0 and 2 <= fields <= 8
        and (instruction >> 12) & 7 in (0, 5, 6, 7)
        and elements >= 0 and partial_bytes_valid
        and isinstance(csrs, dict) and set(csrs) == {"0x341", "0x342", "0x343"}
        and csrs["0x341"] == pc and csrs["0x342"] == 4
        and type(csrs["0x343"]) is int
        and isinstance(inputs, dict) and len(inputs) == 4
        and all(isinstance(path, str) and isinstance(digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", digest) for path, digest in inputs.items())
        and proof["required_load_bytes"] == proof["verified_load_bytes"]
        and (proof["vstart_after"] > proof["vstart_before"]) == (proof["verified_load_bytes"] > 0)
        and proof["accepted_byte_events"] == proof["maintenance_bytes"] + proof["verified_load_bytes"]
        and proof["final_written_bytes"] > 0
        and proof["final_written_bytes"] + proof["duplicate_bytes"] == proof["accepted_byte_events"]
        and proof["duplicate_bytes"] <= min(proof["maintenance_bytes"], proof["verified_load_bytes"])
        and proof["preserved_unknown_bytes"] <= proof["maintenance_bytes"]
        and (proof["verified_load_bytes"] == 0 or
             (proof["preserved_unknown_bytes"] == 0 and
              proof["full_destination_bytes"] >= proof["verified_load_bytes"]))
    )


def _load_fault_evidence_errors(artifact: Path, comparison: Optional[Mapping[str, Any]],
                                vector: Optional[Mapping[str, Any]]) -> List[str]:
    proofs = (vector or {}).get("verified_probed_load_faults", [])
    aligned = (comparison or {}).get("aligned_vector_faults", [])
    if not isinstance(proofs, list) or not isinstance(aligned, list):
        return ["invalid load-fault evidence containers"]
    scalar_proofs = [row.get("load_fault_proof") for row in aligned
                     if isinstance(row, dict) and "load_fault_proof" in row]
    if not proofs and not scalar_proofs:
        return []
    if not isinstance(proofs, list) or not all(_valid_load_fault_proof(p) for p in proofs):
        return ["invalid probed load-fault proof"]
    if proofs != scalar_proofs or any(
        row.get("matched_fault_csrs") != row["load_fault_proof"].get("expected_fault_csrs")
        or any(row.get(key) != row["load_fault_proof"][key]
               for key in ("index", "pc", "instruction"))
        for row in aligned if isinstance(row, dict) and "load_fault_proof" in row
    ):
        return ["scalar/vector load-fault evidence differs"]
    expected_paths = {str((artifact / name).resolve()) for name in
                      ("spike_commit.log", "ara_commit_trace.csv", "ara_vector_trace.csv", "run.vcs.log")}
    for proof in proofs:
        if set(proof["inputs"]) != expected_paths:
            return ["load-fault proof belongs to different trace files"]
        for path, digest in proof["inputs"].items():
            source = Path(path)
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                return ["load-fault trace hash missing or changed"]
    return []


def _full_vector_match(vector: Optional[Mapping[str, Any]]) -> bool:
    if vector is None or _status(vector.get("status")) != "PASS":
        return False
    if vector.get("selected_index") is not None or vector.get("stopped_at_spike_index") is not None:
        return False
    if vector.get("incomplete_requests") or vector.get("unretired_requests"):
        return False
    total = vector.get("vector_destination_requests")
    prefix = vector.get("prefix_vector_destination_requests")
    compared = vector.get("compared_instructions")
    verified_traps = vector.get("verified_trapped_destination_requests", [])
    trapped = vector.get("trapped_requests", [])
    zero_write = vector.get("verified_zero_write_traps", [])
    identity_write = vector.get("verified_identity_write_traps", [])
    probed_loads = vector.get("verified_probed_load_faults", [])
    if (not isinstance(verified_traps, list) or not isinstance(trapped, list)
            or not isinstance(zero_write, list) or not isinstance(identity_write, list)
            or not isinstance(probed_loads, list)
            or not all(_valid_load_fault_proof(item) for item in probed_loads)
            or not all(type(item) is int for item in zero_write + trapped)
            or not all(isinstance(item, dict)
                       and isinstance(item.get("arch_seq"), int)
                       and isinstance(item.get("compared_bytes"), int)
                       and item["compared_bytes"] > 0 for item in identity_write)):
        return False
    evidence_list = zero_write + [item["arch_seq"] for item in identity_write + probed_loads]
    if len(evidence_list) != len(set(evidence_list)):
        return False
    evidence = set(evidence_list)
    return (
        isinstance(total, int) and total > 0
        and prefix == total
        and all(isinstance(arch_seq, int) for arch_seq in verified_traps)
        and len(verified_traps) == len(set(verified_traps))
        and set(verified_traps) <= set(trapped) & evidence
        and isinstance(compared, int) and compared + len(verified_traps) == total
    )


def _profile_coverage_errors(
    run_root: Path, coverage: Mapping[str, Any], case_count: int,
) -> List[str]:
    test = coverage.get("test")
    if not isinstance(test, str) or re.fullmatch(r"[A-Za-z0-9_]+", test) is None:
        return ["stimulus coverage has an invalid profile name"]
    sources = sorted((run_root / "asm_test").glob(f"{test}_*.S"))
    if not sources or len(sources) != case_count:
        return ["stimulus coverage source count differs from completed cases"]
    expected = collect_stimulus_coverage(sources, test)
    if expected["vector_instruction_count"] <= 0:
        return ["stimulus coverage has no generated vector instructions"]
    if coverage != expected:
        return ["stimulus coverage differs from the generated assembly"]
    return []


def _audit_case(
    run_root: Path,
    row: Mapping[str, Any],
    require_trace: bool,
    require_vector: bool,
    require_coverage: bool,
    require_contract: bool = False,
    require_inputs: bool = False,
    probe_kinds: Sequence[str] = (),
    require_full_match: bool = False,
    recompute_terminal_tohost: bool = False,
) -> Dict[str, Any]:
    name = str(row.get("name", "<unnamed>"))
    status = _status(row.get("status"))
    artifact = _artifact_dir(run_root, row)
    errors: List[str] = []
    if status != "PASS":
        errors.append(f"result status is {status or 'MISSING'}")
    if artifact is None or not artifact.is_dir():
        errors.append("artifact directory is missing")
        return {"name": name, "status": "FAIL", "errors": errors}
    if not (artifact / "command.json").is_file() and not (artifact / "rtl.command.json").is_file():
        errors.append("replay command metadata is missing")
    result = _read_json(artifact / "result.json")
    trace = _read_json(artifact / "trace_summary.json")
    comparison = _read_json(artifact / "commit_comparison.json")
    vector = _read_json(artifact / "vector_commit_comparison.json")
    checkpoint = _read_json(artifact / "vector_checkpoints.json")
    recomputed = None
    if recompute_terminal_tohost and require_full_match and not _full_architecture_match(comparison):
        from .terminal_reaudit import ROOT, audit as terminal_audit

        try:
            recomputed = terminal_audit(
                artifact, ROOT / "install/riscv-gcc/bin/riscv64-unknown-elf-readelf"
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"terminal tohost re-audit failed: {error}")
        else:
            if recomputed.get("status") == "PASS":
                comparison = recomputed["comparison"]
                vector = recomputed["vector_comparison"]
                trace = recomputed["trace_validation"]
            else:
                errors.extend(f"terminal tohost re-audit: {issue}"
                              for issue in recomputed.get("issues", []))
    if require_trace:
        if trace is None or _status(trace.get("status")) not in {"VALID", "PASS"}:
            errors.append("valid trace evidence is missing")
        if comparison is not None and _status(comparison.get("status")) not in {
            "MATCH", "TERMINAL_MATCH", "TERMINAL_TOHOST_MATCH", "PREFIX"
        }:
            errors.append("architectural comparison has an invalid status")
    if require_full_match and not _full_architecture_match(comparison):
        errors.append("architectural comparison stops before all RTL commits are matched")
    if require_full_match:
        errors.extend(_load_fault_evidence_errors(artifact, comparison, vector))
    if (require_full_match and comparison is not None
            and _status(comparison.get("status")) == "TERMINAL_MATCH"
            and not _terminal_exit_matches_command(artifact, comparison)):
        errors.append("terminal ecall does not match the configured RTL exit PC")
    if (require_full_match and comparison is not None
            and _status(comparison.get("status")) == "TERMINAL_TOHOST_MATCH"
            and not _terminal_tohost_matches_command(artifact, comparison)):
        errors.append("terminal tohost store lacks matching RTL exit evidence")
    if require_vector:
        vector_ok = False
        if checkpoint is not None and _status(checkpoint.get("status")) == "PASS":
            vector_ok = True
        if vector is not None and _status(vector.get("status")) in {"PASS", "PREFIX"}:
            vector_ok = True
        if result is not None and bool(result.get("vector_signature")) and comparison is not None:
            vector_ok = vector_ok or _status(comparison.get("status")) in {
                "MATCH", "TERMINAL_MATCH", "TERMINAL_TOHOST_MATCH", "PREFIX"}
        if not vector_ok:
            errors.append("vector-state evidence is missing or unresolved")
    if require_full_match and not (
        (checkpoint is not None and _status(checkpoint.get("status")) == "PASS")
        or _full_vector_match(vector)
        or (result is not None and bool(result.get("vector_signature"))
            and _full_architecture_match(comparison)
            and comparison is not None and comparison.get("vector_state_compared") is True)
    ):
        errors.append("full vector-state evidence is missing or unresolved")
    if require_coverage:
        coverage = _read_json(run_root / "stimulus_coverage.json")
        if coverage is None:
            errors.append("stimulus_coverage.json is missing")
    if require_contract:
        contract = _read_json(artifact / "contract_summary.json")
        if contract is None or contract.get("status") != "PASS":
            errors.append("requested protocol monitor evidence is missing or not PASS")
        recorded_logs = contract.get("logs", {}) if contract else {}
        if not isinstance(recorded_logs, dict):
            recorded_logs = {}
        for path in (artifact / "console.log", artifact / "work/run.vcs.log"):
            # Recheck source logs: a stale JSON PASS must not mask a changed log.
            errors.extend(f"{path.name}: {issue}" for issue in check_contract_log(path))
            recorded = recorded_logs.get(str(path), {})
            if not isinstance(recorded, dict):
                recorded = {}
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != recorded.get("sha256"):
                errors.append(f"protocol log hash missing or changed: {path.name}")
    if probe_kinds:
        observed = check_probe_capture(artifact / "work", probe_kinds)
        recorded = _read_json(artifact / "probe_capture.json")
        errors.extend(f"probe capture: {issue}" for issue in observed["issues"])
        if recorded != observed:
            errors.append("probe capture evidence missing or changed since run")
    if require_inputs:
        inputs = _read_json(artifact / "inputs.json")
        if inputs is None:
            errors.append("simulation input identity is missing")
        else:
            errors.extend(check_inputs(inputs, artifact / "input.elf"))
    audited = {
        "name": name,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "artifact_dir": str(artifact),
    }
    if recomputed is not None:
        audited["terminal_reaudit"] = recomputed
    return audited


def _audit_reference_recomparison(run_root: Path, metadata: Mapping[str, Any],
                                  cases: Sequence[Mapping[str, Any]]) -> List[str]:
    errors: List[str] = []
    spike = metadata.get("spike")
    if not isinstance(spike, dict):
        return ["reference Spike identity is missing"]
    try:
        if sha256(Path(spike["path"])) != spike["sha256"]:
            errors.append("reference Spike executable changed")
    except (OSError, KeyError, TypeError, ValueError) as error:
        errors.append(f"reference Spike identity unavailable: {error}")
    for row in cases:
        case = Path(str(row["artifact_dir"]))
        evidence = _read_json(case / "source_evidence.json")
        output = _read_json(case / "reference_output.json")
        command = _read_json(case / "spike.command.json")
        if evidence is None or output is None or command is None:
            errors.append(f"{case.name}: reference comparison provenance is missing")
            continue
        if evidence.get("source_case") != str(Path(metadata["source_run"]) / "tests" / case.name):
            errors.append(f"{case.name}: source-case path does not match run metadata")
        sources = evidence.get("copied_sha256")
        if not isinstance(sources, dict) or not sources:
            errors.append(f"{case.name}: frozen source-file hashes are missing")
            continue
        for source_name, digest in sources.items():
            source = Path(source_name)
            frozen = case / ("input.elf" if source.suffix == ".o" else source.name)
            try:
                if sha256(source) != digest or sha256(frozen) != digest:
                    errors.append(f"{case.name}: source or frozen copy changed: {source.name}")
            except OSError as error:
                errors.append(f"{case.name}: cannot rehash {source.name}: {error}")
        try:
            if output["spike_sha256"] != spike["sha256"] or \
                    sha256(case / "spike_commit.log") != output["spike_commit_sha256"] or \
                    sha256(case / "spike_console.log") != output["spike_console_sha256"]:
                errors.append(f"{case.name}: Spike output identity changed")
            args = command["command"]
            if args[0] != spike["path"] or args[-1] != str(case / "input.elf"):
                errors.append(f"{case.name}: Spike command does not use frozen inputs")
        except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
            errors.append(f"{case.name}: Spike output identity unavailable: {error}")
    return errors


def audit_run(
    run_root: Path,
    *,
    require_complete: bool = True,
    require_trace: bool = False,
    require_vector: bool = False,
    require_coverage: bool = False,
    require_full_match: bool = False,
    recompute_terminal_tohost: bool = False,
) -> Dict[str, Any]:
    if recompute_terminal_tohost and not require_full_match:
        raise PlanError("terminal tohost recomputation requires full-match auditing")
    run_root = run_root.resolve()
    require_trace = require_trace or require_full_match
    require_vector = require_vector or require_full_match
    errors: List[str] = []
    metadata = _read_json(run_root / "run.json")
    if metadata is None:
        errors.append("run.json is missing or invalid")
    else:
        if require_complete and _status(metadata.get("status")) != "COMPLETE":
            errors.append(f"run status is {_status(metadata.get('status')) or 'MISSING'}")
        if not metadata.get("invocation") and not metadata.get("command"):
            errors.append("reproducibility invocation metadata is missing")
        provenance = metadata.get("git") or metadata.get("source_snapshot")
        if not isinstance(provenance, dict) or not (
            provenance.get("commit") or provenance.get("sha256")
        ):
            errors.append("source commit metadata is missing")
    summary_path = run_root / "summary.json"
    try:
        rows = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanError(f"cannot read run summary {summary_path}: {error}") from error
    if not isinstance(rows, list) or not rows:
        errors.append("summary.json has no test results")
        rows = []
    if require_coverage:
        profile = _read_json(run_root / "stimulus_coverage.json")
        campaign = _read_json(run_root / "random_stimulus_coverage.json")
        if profile is not None:
            errors.extend(_profile_coverage_errors(run_root, profile, len(rows)))
        elif campaign is not None:
            if _status(campaign.get("status")) not in {"PASS", "VALID", "COMPLETE"}:
                errors.append("random stimulus coverage report is not PASS")
        else:
            errors.append("stimulus coverage report is missing")
    cases = [
        _audit_case(run_root, row, require_trace, require_vector, False,
                    bool(metadata and metadata.get("contract_monitor")),
                    bool(metadata and metadata.get("input_snapshots")),
                    metadata.get("probe_kinds", ()) if metadata else (),
                    require_full_match=require_full_match,
                    recompute_terminal_tohost=recompute_terminal_tohost)
        for row in rows if isinstance(row, dict)
    ]
    failed_cases = [case for case in cases if case["status"] != "PASS"]
    errors.extend(f"{case['name']}: {error}" for case in failed_cases for error in case["errors"])
    if metadata and metadata.get("source_run"):
        errors.extend(_audit_reference_recomparison(run_root, metadata, cases))
    return {
        "status": "PASS" if not errors and cases else "FAIL",
        "run": str(run_root),
        "case_count": len(cases),
        "passed_cases": len(cases) - len(failed_cases),
        "failed_cases": len(failed_cases),
        "policy": {
            "require_complete": require_complete,
            "require_trace": require_trace,
            "require_vector": require_vector,
            "require_coverage": require_coverage,
            "require_full_match": require_full_match,
            "recompute_terminal_tohost": recompute_terminal_tohost,
            "require_contract": bool(metadata and metadata.get("contract_monitor")),
        },
        "errors": errors,
        "cases": cases,
    }


def write_audit(payload: Mapping[str, Any], output: Path) -> None:
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
