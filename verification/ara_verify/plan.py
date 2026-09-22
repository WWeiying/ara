from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .catalog import Catalog, ManifestError


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
        })
    dimensions = plan.get("coverage_dimensions", {})
    if not isinstance(dimensions, dict) or not dimensions:
        raise PlanError("coverage_dimensions must be a non-empty object")
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


def _audit_case(
    run_root: Path,
    row: Mapping[str, Any],
    require_trace: bool,
    require_vector: bool,
    require_coverage: bool,
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
    if require_trace:
        if trace is None or _status(trace.get("status")) not in {"VALID", "PASS"}:
            errors.append("valid trace evidence is missing")
        if comparison is not None and _status(comparison.get("status")) not in {"MATCH", "PREFIX"}:
            errors.append("architectural comparison is not MATCH/PREFIX")
    if require_vector:
        vector_ok = False
        if checkpoint is not None and _status(checkpoint.get("status")) == "PASS":
            vector_ok = True
        if vector is not None and _status(vector.get("status")) in {"PASS", "PREFIX"}:
            vector_ok = True
        if result is not None and bool(result.get("vector_signature")) and comparison is not None:
            vector_ok = vector_ok or _status(comparison.get("status")) in {"MATCH", "PREFIX"}
        if not vector_ok:
            errors.append("vector-state evidence is missing or unresolved")
    if require_coverage:
        coverage = _read_json(run_root / "stimulus_coverage.json")
        if coverage is None:
            errors.append("stimulus_coverage.json is missing")
    return {
        "name": name,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "artifact_dir": str(artifact),
    }


def audit_run(
    run_root: Path,
    *,
    require_complete: bool = True,
    require_trace: bool = False,
    require_vector: bool = False,
    require_coverage: bool = False,
) -> Dict[str, Any]:
    run_root = run_root.resolve()
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
        coverage_paths = (
            run_root / "stimulus_coverage.json",
            run_root / "random_stimulus_coverage.json",
        )
        coverage = next((
            _read_json(path) for path in coverage_paths if path.is_file()
        ), None)
        if coverage is None:
            errors.append("stimulus coverage report is missing")
        elif _status(coverage.get("status")) not in {"PASS", "VALID", "COMPLETE"}:
            errors.append("stimulus coverage report is not PASS")
    cases = [
        _audit_case(run_root, row, require_trace, require_vector, False)
        for row in rows if isinstance(row, dict)
    ]
    failed_cases = [case for case in cases if case["status"] != "PASS"]
    errors.extend(f"{case['name']}: {error}" for case in failed_cases for error in case["errors"])
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
        },
        "errors": errors,
        "cases": cases,
    }


def write_audit(payload: Mapping[str, Any], output: Path) -> None:
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
