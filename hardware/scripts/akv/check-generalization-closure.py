#!/usr/bin/env python3

"""Audit the current AKV generalization evidence without inventing closure."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = Path(__file__).with_name("generalization-closure-manifest.json")
DEFAULT_OUTPUT = ROOT / "hardware/akv_generalization_closure_20260901"
OPERATOR_RE = re.compile(r"^LLAMA_OPERATOR (.+) PASS cycles=(\d+) mismatches=(\d+)$", re.MULTILINE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}


def result(name: str, category: str, status: str, detail: str, paths=()) -> dict[str, object]:
    return {
        "name": name,
        "category": category,
        "status": status,
        "detail": detail,
        "artifacts": [artifact(path) for path in paths if path.is_file()],
    }


def path(raw: str) -> Path:
    return ROOT / raw


def parse_operator_log(log: Path, expected_case: str) -> int:
    matches = OPERATOR_RE.findall(log.read_text(encoding="utf-8", errors="replace"))
    selected = [(int(cycles), int(mismatches)) for case, cycles, mismatches in matches if case == expected_case]
    if len(selected) != 1:
        raise ValueError(f"expected one PASS record for {expected_case}, found {len(selected)}")
    cycles, mismatches = selected[0]
    if mismatches != 0 or cycles <= 0:
        raise ValueError(f"invalid result cycles={cycles} mismatches={mismatches}")
    return cycles


def one_csv(csv_path: Path) -> dict[str, str]:
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise ValueError(f"expected one row in {csv_path}, found {len(rows)}")
    return rows[0]


def csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def declared_artifact(spec: dict[str, str], label: str) -> Path:
    artifact_path = path(spec["path"])
    if not artifact_path.is_file():
        raise ValueError(f"{label} artifact is missing: {spec['path']}")
    observed = sha256(artifact_path)
    if observed != spec["sha256"]:
        raise ValueError(f"{label} artifact hash changed: {observed}")
    return artifact_path


def keyed(rows: list[dict[str, object]], field: str, label: str) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for row in rows:
        key = str(row[field])
        if key in indexed:
            raise ValueError(f"duplicate {label} entry: {key}")
        indexed[key] = row
    return indexed


def inspect_simulator(spec: dict[str, object]) -> tuple[Path, Path, list[Path]]:
    simv = path(spec["simv"])
    filelist = path(spec["filelist"])
    if not simv.is_file():
        raise FileNotFoundError(f"simulator is missing: {spec['simv']}")
    if not filelist.is_file():
        raise FileNotFoundError(f"simulator filelist is missing: {spec['filelist']}")
    filelist_text = filelist.read_text(encoding="utf-8", errors="replace")
    filelist_lines = {line.strip() for line in filelist_text.splitlines()}
    missing_defines = [
        define for define in spec.get("required_defines", [])
        if f"+define+{define}" not in filelist_lines
    ]
    if missing_defines:
        raise ValueError(
            "simulator filelist is missing required defines: " +
            ", ".join(missing_defines)
        )

    sources: list[Path] = [filelist]
    missing: list[str] = []
    for raw in filelist_text.splitlines():
        raw = raw.strip()
        if not raw.startswith("/"):
            continue
        source = Path(raw)
        if source.is_file():
            sources.append(source)
        else:
            missing.append(raw)
    for raw in spec.get("metadata_sources", []):
        source = path(raw)
        if source.is_file():
            sources.append(source)
        else:
            missing.append(str(raw))
    if missing:
        raise FileNotFoundError(f"simulator inputs are missing: {', '.join(missing[:3])}")
    if not sources:
        raise ValueError("simulator filelist contains no source files")
    simv_mtime = simv.stat().st_mtime_ns
    stale = sorted(source for source in set(sources) if source.stat().st_mtime_ns > simv_mtime)
    return simv, filelist, stale


def key_value_file(config: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def validate_current_run(
    log: Path, simulator_path: Path, simulator_spec: dict[str, object]
) -> tuple[Path, Path]:
    run_conf = log.parent / "run.conf"
    point_complete = log.parent / "complete"
    if not run_conf.is_file() or not point_complete.is_file():
        raise FileNotFoundError("current result lacks run.conf or completion marker")
    config = key_value_file(run_conf)
    if Path(config["simv"]).resolve() != simulator_path.resolve():
        raise ValueError("result used a different simulator path")
    if config["simv_sha256"] != sha256(simulator_path):
        raise ValueError("result simulator hash differs from the current simulator")
    if Path(config["capture_root"]).resolve() != path(simulator_spec["capture_root"]).resolve():
        # A per-point capture may differ from the legacy suite's frozen capture.
        # Callers that use multiple real-model captures validate it separately.
        raise ValueError("result used a different capture root")
    return run_conf, point_complete


def validate_host_census(host: dict[str, object], manifest: dict[str, object]) -> list[Path]:
    kv_lengths = [16, 128, 512, 1024]
    support_contract = {"head_dims": [64, 96, 128], "gqa_rows": list(range(1, 9))}
    expected_models = keyed(manifest["host_expected_models"], "id", "expected model")
    actual_models = keyed(host["models"], "id", "host model")
    if (
        host.get("schema_version") != 1 or host.get("status") != "PASS" or
        host.get("model_count") != len(expected_models) or
        host.get("case_count") != len(expected_models) * len(kv_lengths) or
        host.get("kv_lengths") != kv_lengths or
        host.get("support_contract") != support_contract or
        set(actual_models) != set(expected_models)
    ):
        raise ValueError("summary fields do not match the frozen support contract")

    dispositions = {"execute": 0, "fallback_shape": 0}
    for model_id, expected in expected_models.items():
        actual = actual_models[model_id]
        observed = {
            "name": actual["name"],
            "head_dims": int(actual["head_dims"]),
            "gqa_rows": int(actual["gqa_rows"]),
            "disposition": actual["disposition"],
        }
        required = {field: expected[field] for field in observed}
        if observed != required:
            raise ValueError(f"{model_id} shape/disposition differs: {observed}")
        dispositions[str(expected["disposition"])] += 1
    if host.get("model_dispositions") != dispositions:
        raise ValueError("model disposition totals do not match the exact model set")

    artifact_specs = host.get("artifacts")
    if not isinstance(artifact_specs, dict) or set(artifact_specs) != {
        "dynamic_counts", "support_matrix", "provenance"
    }:
        raise ValueError("host census artifact set is incomplete")
    dynamic_path = declared_artifact(artifact_specs["dynamic_counts"], "dynamic counts")
    matrix_path = declared_artifact(artifact_specs["support_matrix"], "support matrix")
    provenance_path = declared_artifact(artifact_specs["provenance"], "provenance")

    matrix = keyed(csv_rows(matrix_path), "model", "support-matrix model")
    if set(matrix) != set(expected_models):
        raise ValueError("support matrix model set differs from the frozen model set")
    expected_kv = "/".join(str(value) for value in kv_lengths)
    matrix_counts: dict[str, tuple[int, int, int]] = {}
    for model_id, expected in expected_models.items():
        row = matrix[model_id]
        q_heads, kv_heads = int(row["q_heads"]), int(row["kv_heads"])
        observed = {
            "model_name": row["model_name"],
            "head_dims": int(row["head_dims"]),
            "gqa_rows": int(row["gqa_rows"]),
            "expected_disposition": row["expected_disposition"],
            "observed_disposition": row["observed_disposition"],
            "effective_kv": row["effective_kv"],
            "host_census_status": row["host_census_status"],
        }
        required = {
            "model_name": expected["name"],
            "head_dims": expected["head_dims"],
            "gqa_rows": expected["gqa_rows"],
            "expected_disposition": expected["disposition"],
            "observed_disposition": expected["disposition"],
            "effective_kv": expected_kv,
            "host_census_status": "PASS",
        }
        if observed != required or q_heads <= 0 or kv_heads <= 0 or q_heads != kv_heads * int(expected["gqa_rows"]):
            raise ValueError(f"{model_id} support-matrix row is inconsistent")
        matrix_counts[model_id] = (
            int(row["candidate_nodes_per_decode"]),
            int(row["eligible_nodes_per_decode"]),
            int(row["fallback_nodes_per_decode"]),
        )

    dynamic = csv_rows(dynamic_path)
    expected_cases = {(model_id, kv) for model_id in expected_models for kv in kv_lengths}
    observed_cases: set[tuple[str, int]] = set()
    candidate_total = eligible_total = fallback_total = 0
    for row in dynamic:
        case = (row["model"], int(row["effective_kv"]))
        if case in observed_cases:
            raise ValueError(f"duplicate dynamic census case: {case}")
        observed_cases.add(case)
        if case not in expected_cases or row["status"] != "PASS":
            raise ValueError(f"unexpected or failing dynamic census case: {case}")
        candidate = int(row["akv_candidate_compute_nodes"])
        eligible = int(row["akv_shape_eligible_compute_nodes"])
        fallback = int(row["akv_shape_fallback_compute_nodes"])
        if candidate <= 0 or candidate != eligible + fallback:
            raise ValueError(f"invalid candidate accounting for {case}")
        if (candidate, eligible, fallback) != matrix_counts[case[0]]:
            raise ValueError(f"dynamic/support-matrix count mismatch for {case}")
        if expected_models[case[0]]["disposition"] == "execute":
            if eligible != candidate or fallback != 0:
                raise ValueError(f"execute model contains shape fallback for {case}")
        elif eligible != 0 or fallback != candidate:
            raise ValueError(f"fallback model contains eligible AKV work for {case}")
        case_artifact = path(row["artifact"])
        if not case_artifact.is_file():
            raise ValueError(f"dynamic case artifact is missing: {row['artifact']}")
        candidate_total += candidate
        eligible_total += eligible
        fallback_total += fallback
    if observed_cases != expected_cases:
        raise ValueError("dynamic census does not contain the exact 7-model x 4-KV matrix")
    if (
        candidate_total != host.get("candidate_nodes_across_cases") or
        eligible_total != host.get("eligible_nodes_across_cases") or
        fallback_total != host.get("fallback_nodes_across_cases") or
        candidate_total != eligible_total + fallback_total
    ):
        raise ValueError("dynamic census totals do not match the summary")

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if (
        provenance.get("schema_version") != 1 or
        provenance.get("mode") != "offline_revalidation_of_immutable_host_logs" or
        provenance.get("support_contract") != support_contract
    ):
        raise ValueError("provenance contract is invalid")
    provenance_cases = {(entry["model"], int(entry["effective_kv"])): entry for entry in provenance["cases"]}
    if set(provenance_cases) != expected_cases or len(provenance["cases"]) != len(expected_cases):
        raise ValueError("provenance does not cover the exact case matrix")
    for case, entry in provenance_cases.items():
        log = path(entry["host_log"])
        if not log.is_file() or sha256(log) != entry["host_log_sha256"]:
            raise ValueError(f"source Host log changed for {case}")
    provenance_files = (
        (provenance["manifest"], provenance["manifest_sha256"]),
        (provenance["qbs_abi"], provenance["qbs_abi_sha256"]),
        (provenance["analyzer"], provenance["analyzer_sha256"]),
        (provenance["tool"], provenance["tool_sha256"]),
        (f"{provenance['source_root']}/complete", provenance["source_complete_sha256"]),
        (f"{provenance['source_root']}/provenance.json", provenance["source_provenance_sha256"]),
    )
    for raw, expected_hash in provenance_files:
        source = path(raw)
        if not source.is_file() or sha256(source) != expected_hash:
            raise ValueError(f"provenance source changed: {raw}")
    return [dynamic_path, matrix_path, provenance_path]


def validate_frozen_qemu(summary: dict[str, object], manifest: dict[str, object]) -> tuple[int, int, int]:
    spec = manifest["frozen_full_model_qemu"]
    expected_models = keyed(manifest["host_expected_models"], "id", "expected model")
    models = keyed(summary["models"], "model", "frozen QEMU model")
    if summary.get("schema_version") != 1 or summary.get("status") != "PASS" or set(models) != set(expected_models):
        raise ValueError("frozen full-model QEMU model set is incomplete")
    expected_dispositions = spec["expected_dispositions"]
    if set(expected_dispositions) != set(expected_models):
        raise ValueError("frozen QEMU disposition contract is incomplete")

    native_commands = emulated_commands = executed = fallbacks = 0
    for model_id, expected in expected_models.items():
        row = models[model_id]
        if row["name"] != expected["name"] or row["status"] != "PASS":
            raise ValueError(f"{model_id} frozen QEMU identity/status differs")
        if str(row["qemu_qbs_top1_equal"]) != "1" or str(row["qemu_qbs_token_equal"]) != "1":
            raise ValueError(f"{model_id} frozen QBS numerics are not accepted")
        if str(row["qemu_akv_top1_equal"]) != "1" or str(row["qemu_akv_token_equal"]) != "1":
            raise ValueError(f"{model_id} frozen AKV/fallback numerics are not accepted")
        if float(row["qemu_akv_logits_max_abs"]) > float(row["qemu_akv_logits_tolerance"]):
            raise ValueError(f"{model_id} frozen AKV logits exceed tolerance")
        if int(row["qemu_qbs_dot_elements"]) != int(row["qemu_qbs_command_dot_elements"]):
            raise ValueError(f"{model_id} QBS semantic and command work differ")
        model_native = int(row["qemu_qbs_native_commands"])
        model_emulated = int(row["qemu_qbs_emulated_commands"])
        model_executed = int(row["qemu_akv_executed_ops"])
        model_fallbacks = int(row["qemu_akv_fallback_shape"])
        if model_native <= 0 or model_emulated != 0 or int(row["qemu_model_tokens"]) <= 0:
            raise ValueError(f"{model_id} did not execute native QBS model work")
        disposition = expected_dispositions[model_id]
        if disposition == "execute":
            if model_executed <= 0:
                raise ValueError(f"{model_id} did not execute frozen AKV work")
        elif disposition == "fallback_shape":
            if model_executed != 0 or model_fallbacks <= 0:
                raise ValueError(f"{model_id} did not preserve frozen shape fallback")
        else:
            raise ValueError(f"unknown frozen disposition for {model_id}: {disposition}")
        native_commands += model_native
        emulated_commands += model_emulated
        executed += model_executed
        fallbacks += model_fallbacks

    expected_totals = spec["expected_totals"]
    observed = {
        "qbs_native_commands": native_commands,
        "qbs_emulated_commands": emulated_commands,
        "akv_executed_ops": executed,
        "akv_fallback_ops": fallbacks,
    }
    if observed != expected_totals:
        raise ValueError(f"frozen full-model QEMU totals differ: {observed}")
    return native_commands, executed, fallbacks


def load_qemu_checker():
    script = Path(__file__).with_name("run-model-generality-qemu.py")
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("akv_model_generality_checker", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.qemu_metrics


def load_script_module(filename: str, module_name: str):
    script = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def audit(manifest: dict[str, object]) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []

    host_path = path(manifest["host_census"])
    if not host_path.is_file():
        checks.append(result("seven_model_host_census", "model_coverage", "PENDING", "summary is missing"))
    else:
        try:
            host = json.loads(host_path.read_text(encoding="utf-8"))
            host_artifacts = validate_host_census(host, manifest)
            checks.append(result("seven_model_host_census", "model_coverage", "PASS", "exact seven-model x four-KV matrix, shape dispositions, artifacts, and immutable Host provenance verified", [host_path, *host_artifacts]))
        except Exception as error:
            checks.append(result("seven_model_host_census", "model_coverage", "FAIL", str(error), [host_path]))

    frozen_spec = manifest["frozen_full_model_qemu"]
    frozen_path = path(frozen_spec["summary"])
    frozen_complete = path(frozen_spec["complete"])
    if not frozen_path.is_file() or not frozen_complete.is_file():
        checks.append(result("frozen_seven_model_qemu", "full_model_qemu", "PENDING", "frozen seven-model QEMU result is incomplete", [frozen_path, frozen_complete]))
    else:
        try:
            frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
            native, executed, fallbacks = validate_frozen_qemu(frozen, manifest)
            checks.append(result("frozen_seven_model_qemu", "full_model_qemu", "PASS", f"7/7 models; native QBS={native}; emulated QBS=0; frozen AKV execute/fallback={executed}/{fallbacks}", [frozen_path, frozen_complete]))
        except Exception as error:
            checks.append(result("frozen_seven_model_qemu", "full_model_qemu", "FAIL", str(error), [frozen_path, frozen_complete]))

    simulator_spec = manifest["legacy_simulator"]
    simulator_path = path(simulator_spec["simv"])
    try:
        simulator_path, simulator_filelist, stale_sources = inspect_simulator(simulator_spec)
        if stale_sources:
            names = ", ".join(str(source.relative_to(ROOT)) for source in stale_sources[:3])
            checks.append(result("current_akv_simulator", "provenance", "PENDING", f"simulator rebuild required; newer inputs include {names}", [simulator_path, simulator_filelist]))
        else:
            checks.append(result("current_akv_simulator", "provenance", "PASS", f"all compiled inputs predate simv sha256={sha256(simulator_path)}", [simulator_path, simulator_filelist]))
    except FileNotFoundError as error:
        checks.append(result("current_akv_simulator", "provenance", "PENDING", str(error), [simulator_path]))
    except Exception as error:
        checks.append(result("current_akv_simulator", "provenance", "FAIL", str(error), [simulator_path]))

    legacy_status_path = path(simulator_spec["run_status"])
    legacy_complete_path = path(simulator_spec["run_complete"])
    legacy_status = legacy_status_path.read_text(encoding="ascii", errors="replace").strip() \
        if legacy_status_path.is_file() else ""
    if legacy_status == "PASS" and legacy_complete_path.is_file():
        checks.append(result("legacy_akv_regression_run", "akv_non_regression", "PASS", "worker reached terminal PASS", [legacy_status_path, legacy_complete_path]))
    elif legacy_status in {"FAILED", "INTERRUPTED"}:
        checks.append(result("legacy_akv_regression_run", "akv_non_regression", "FAIL", f"worker terminal status is {legacy_status}", [legacy_status_path]))
    elif legacy_status in {"", "RUNNING"}:
        checks.append(result("legacy_akv_regression_run", "akv_non_regression", "PENDING", "worker has not reached terminal PASS", [legacy_status_path]))
    else:
        checks.append(result("legacy_akv_regression_run", "akv_non_regression", "FAIL", f"unknown worker status {legacy_status}", [legacy_status_path]))

    focused_worker = manifest["focused_simulator_run"]
    focused_status_path = path(focused_worker["status"])
    focused_complete_path = path(focused_worker["complete"])
    focused_status = focused_status_path.read_text(encoding="ascii", errors="replace").strip() \
        if focused_status_path.is_file() else ""
    if focused_status == "PASS" and focused_complete_path.is_file():
        checks.append(result("focused_akv_regression_run", "focused_rtl", "PASS", "worker reached terminal PASS", [focused_status_path, focused_complete_path]))
    elif focused_status in {"FAILED", "INTERRUPTED"}:
        checks.append(result("focused_akv_regression_run", "focused_rtl", "FAIL", f"worker terminal status is {focused_status}", [focused_status_path]))
    elif focused_status in {"", "RUNNING"}:
        checks.append(result("focused_akv_regression_run", "focused_rtl", "PENDING", "worker has not reached terminal PASS", [focused_status_path]))
    else:
        checks.append(result("focused_akv_regression_run", "focused_rtl", "FAIL", f"unknown worker status {focused_status}", [focused_status_path]))

    for category, key in (("akv_directed", "akv_engine_tests"), ("qbs_directed", "qbs_engine_tests")):
        for spec in manifest[key]:
            log = path(spec["log"])
            if not log.is_file():
                checks.append(result(spec["name"], category, "PENDING", "log is missing"))
                continue
            text = log.read_text(encoding="utf-8", errors="replace")
            status = "PASS" if spec["marker"] in text else "FAIL"
            checks.append(result(spec["name"], category, status, "required terminal marker present" if status == "PASS" else "required terminal marker absent", [log]))

    for spec in manifest["qbs_non_regression"]:
        baseline, current = path(spec["baseline"]), path(spec["current"])
        if not current.is_file():
            checks.append(result(spec["name"], "qbs_non_regression", "PENDING", "current result is missing", [baseline]))
            continue
        try:
            before, after = one_csv(baseline), one_csv(current)
            if before["result"] != "PASS" or after["result"] != "PASS" or int(after["mismatches"]) != 0:
                raise ValueError("functional result is not zero-mismatch PASS")
            b, c = int(before["timed_cycles"]), int(after["timed_cycles"])
            regression = c / b - 1.0
            if regression > float(spec["max_regression"]):
                raise ValueError(f"cycle regression {regression:.3%} exceeds gate")
            checks.append(result(spec["name"], "qbs_non_regression", "PASS", f"{b} -> {c} cycles ({regression:+.3%})", [baseline, current]))
        except Exception as error:
            checks.append(result(spec["name"], "qbs_non_regression", "FAIL", str(error), [baseline, current]))

    for spec in manifest["qbs_integrated_points"]:
        directory = path(spec["directory"])
        run_root = directory.parent
        status_path = directory / "status"
        result_path = directory / "result.csv"
        perf_path = directory / "qbs_perf.csv"
        if not status_path.is_file():
            checks.append(result(spec["name"], "qbs_integrated", "PENDING", "terminal status is not available"))
            continue
        try:
            terminal = status_path.read_text(encoding="ascii").strip()
            if terminal != "PASS":
                raise ValueError(f"terminal status is {terminal or 'empty'}")
            row = one_csv(result_path)
            perf = one_csv(perf_path)
            if row["case"] != spec["name"] or row["result"] != "PASS" or int(row["mismatches"]) != 0:
                raise ValueError("benchmark result is not the expected zero-mismatch PASS")
            if perf["case"] != spec["name"] or int(perf["commands"]) <= 0 or int(perf["faults"]) != 0:
                raise ValueError("QBS command summary is missing successful native work")
            run_simv = directory / "simv"
            template_path = run_root / "sim_template"
            template_hash_path = run_root / "simv.sha256"
            template = Path(template_path.read_text(encoding="utf-8").strip()).resolve()
            if template != simulator_path.parent.resolve():
                raise ValueError("QBS run used a different simulator template")
            declared_hash = template_hash_path.read_text(encoding="ascii").split()[0]
            current_hash = sha256(simulator_path)
            if declared_hash != current_hash or sha256(run_simv) != current_hash:
                raise ValueError("QBS run simulator hash differs from the current simulator")
            checks.append(result(
                spec["name"], "qbs_integrated", "PASS",
                f"cycles={row['timed_cycles']}; commands={perf['commands']}; faults=0; current simv hash verified",
                [status_path, result_path, perf_path, template_path, template_hash_path],
            ))
        except FileNotFoundError:
            checks.append(result(spec["name"], "qbs_integrated", "FAIL", "PASS status lacks required result artifacts", [status_path]))
        except Exception as error:
            checks.append(result(spec["name"], "qbs_integrated", "FAIL", str(error), [status_path, result_path, perf_path]))

    rvv = manifest["ordinary_rvv"]
    baseline, current = path(rvv["baseline"]), path(rvv["current"])
    try:
        b = parse_operator_log(baseline, rvv["case"])
        c = parse_operator_log(current, rvv["case"])
        regression = c / b - 1.0
        if regression > float(rvv["max_regression"]):
            raise ValueError(f"cycle regression {regression:.3%} exceeds gate")
        checks.append(result("ordinary_rvv_fallback", "fallback", "PASS", f"{b} -> {c} cycles ({regression:+.3%})", [baseline, current]))
    except FileNotFoundError:
        checks.append(result("ordinary_rvv_fallback", "fallback", "PENDING", "baseline or current log is missing", [baseline, current]))
    except Exception as error:
        checks.append(result("ordinary_rvv_fallback", "fallback", "FAIL", str(error), [baseline, current]))

    for spec in manifest["focused_akv"]:
        baseline, current = path(spec["baseline"]), path(spec["current"])
        if not current.is_file() or not (current.parent / "complete").is_file():
            checks.append(result(spec["name"], "focused_rtl", "PENDING", "current rerun is not complete", [baseline]))
            continue
        try:
            before = parse_operator_log(baseline, spec["case"])
            after = parse_operator_log(current, spec["case"])
            run_conf = current.parent / "run.conf"
            point_complete = current.parent / "complete"
            config = key_value_file(run_conf)
            if Path(config["simv"]).resolve() != simulator_path.resolve() or \
                    config["simv_sha256"] != sha256(simulator_path):
                raise ValueError("focused result did not use the current simulator")
            if Path(config["capture_root"]).resolve() != Path(spec["capture_root"]).resolve():
                raise ValueError("focused result used a different real-model capture")
            regression = after / before - 1.0
            if regression > float(spec["max_regression"]):
                raise ValueError(f"cycle regression {regression:.3%} exceeds gate")
            checks.append(result(spec["name"], "focused_rtl", "PASS", f"{before} -> {after} cycles ({regression:+.3%}); zero mismatches and current simv hash verified", [baseline, current, run_conf, point_complete]))
        except Exception as error:
            checks.append(result(spec["name"], "focused_rtl", "FAIL", str(error), [baseline, current]))

    gate = manifest["d256_gate"]
    akv_log, rvv_log = path(gate["current_akv_log"]), path(gate["current_rvv_log"])
    if not akv_log.is_file() or not rvv_log.is_file() or \
            not (akv_log.parent / "complete").is_file() or \
            not (rvv_log.parent / "complete").is_file():
        checks.append(result("Gemma_D256_admission", "performance_gate", "PENDING", "current AKV/RVV gate rerun is incomplete", [akv_log, rvv_log]))
    else:
        try:
            for log in (akv_log, rvv_log):
                config = key_value_file(log.parent / "run.conf")
                if Path(config["simv"]).resolve() != simulator_path.resolve() or \
                        config["simv_sha256"] != sha256(simulator_path):
                    raise ValueError("D256 gate result did not use the current simulator")
                if Path(config["capture_root"]).resolve() != Path(gate["capture_root"]).resolve():
                    raise ValueError("D256 gate used a different real-model capture")
            akv_cycles = parse_operator_log(akv_log, gate["akv_case"])
            rvv_cycles = parse_operator_log(rvv_log, gate["rvv_case"])
            speedup = rvv_cycles / akv_cycles
            observed = "execute" if speedup >= float(gate["minimum_speedup"]) else "fallback_shape"
            if observed != gate["expected_disposition"]:
                raise ValueError(f"observed disposition {observed} differs from expected")
            checks.append(result("Gemma_D256_admission", "performance_gate", "PASS", f"AKV={akv_cycles}, tiled-RVV={rvv_cycles}, speedup={speedup:.3f}x, disposition={observed}; current simv hash verified", [akv_log, rvv_log]))
        except Exception as error:
            checks.append(result("Gemma_D256_admission", "performance_gate", "FAIL", str(error), [akv_log, rvv_log]))

    for spec in manifest["legacy_akv_non_regression"]:
        baseline, current = path(spec["baseline"]), path(spec["current"])
        point_complete = current.parent / "complete"
        if not current.is_file() or not point_complete.is_file():
            checks.append(result(spec["name"], "akv_non_regression", "PENDING", "current rerun is not complete", [baseline]))
            continue
        try:
            b = parse_operator_log(baseline, spec["case"])
            c = parse_operator_log(current, spec["case"])
            run_conf, point_complete = validate_current_run(current, simulator_path, simulator_spec)
            regression = c / b - 1.0
            if regression > float(spec["max_regression"]):
                raise ValueError(f"cycle regression {regression:.3%} exceeds gate")
            checks.append(result(spec["name"], "akv_non_regression", "PASS", f"{b} -> {c} cycles ({regression:+.3%}); current simv hash verified", [baseline, current, run_conf, point_complete]))
        except Exception as error:
            checks.append(result(spec["name"], "akv_non_regression", "FAIL", str(error), [baseline, current]))

    qemu_metrics = load_qemu_checker()
    for spec in manifest["generalized_qemu"]:
        summary_path = path(spec["summary"])
        if not summary_path.is_file():
            checks.append(result(spec["name"], "full_model_qemu", "PENDING", "dynamic summary is not complete"))
            continue
        try:
            metrics = qemu_metrics(json.loads(summary_path.read_text(encoding="utf-8")), spec["disposition"])
            checks.append(result(spec["name"], "full_model_qemu", "PASS", f"native AKV executed={metrics['akv_executed_ops']}; candidates={metrics['akv_candidate_ops']}; top1/text/numerics pass", [summary_path]))
        except Exception as error:
            checks.append(result(spec["name"], "full_model_qemu", "FAIL", str(error), [summary_path]))

    physical = manifest["physical_closure"]
    preflight = physical["preflight"]
    filelist_path = path(preflight["filelist"])
    integrated_sdc_path = path(preflight["integrated_sdc"])
    standalone_sdc_path = path(preflight["standalone_sdc"])
    setup_path = path(preflight["setup"])
    flow_paths = {name: path(item) for name, item in preflight["flow"].items()}
    preflight_paths = [
        filelist_path,
        integrated_sdc_path,
        standalone_sdc_path,
        setup_path,
        *flow_paths.values(),
        *(path(item) for item in preflight["other_flow_inputs"]),
    ]
    if not all(item.is_file() for item in preflight_paths):
        checks.append(result(
            "synthesis_preflight",
            "physical_preflight",
            "PENDING",
            "run make -C hardware dc_preflight mc=1 qbs=1 akv_v2=1",
            preflight_paths,
        ))
    else:
        try:
            checker = load_script_module(
                "check-synthesis-preflight.py", "akv_synthesis_preflight_checker"
            )
            common = {
                "filelist": filelist_path,
                "setup": setup_path,
                "sram_db": Path(preflight["sram_db"]),
                **flow_paths,
                "require_qbs": True,
                "require_akv": True,
                "require_akv_v2": True,
                "require_macro_sram": True,
                "nr_lanes": int(preflight["nr_lanes"]),
                "vlen": int(preflight["vlen"]),
            }
            checker.audit(checker.Options(sdc=integrated_sdc_path, **common))
            checker.audit(checker.Options(sdc=standalone_sdc_path, **common))
            checks.append(result(
                "synthesis_preflight",
                "physical_preflight",
                "PASS",
                "integrated and standalone QBS+AKV-v2 filelist, flow setup, macro SRAM, DB, and 1 GHz/0.15 ns constraints verified",
                preflight_paths,
            ))
        except Exception as error:
            checks.append(result(
                "synthesis_preflight",
                "physical_preflight",
                "FAIL",
                str(error),
                preflight_paths,
            ))

    standalone_summary = path(physical["standalone_summary"])
    integrated_summary = path(physical["integrated_summary"])
    if not standalone_summary.is_file() or not integrated_summary.is_file():
        missing = [
            relative for relative, summary_path in (
                (physical["standalone_summary"], standalone_summary),
                (physical["integrated_summary"], integrated_summary),
            ) if not summary_path.is_file()
        ]
        checks.append(result(
            "physical_closure",
            "physical",
            "PENDING",
            f"{physical['status']}: missing {', '.join(missing)}; corner={physical['required_corner']}",
            [standalone_summary, integrated_summary],
        ))
    else:
        try:
            collector = load_script_module(
                "collect-synthesis-results.py", "akv_synthesis_result_collector"
            )
            standalone = collector.validate_summary(standalone_summary, "standalone", ROOT)
            integrated = collector.validate_summary(integrated_summary, "integrated", ROOT)
            standalone_metrics = standalone["metrics"]
            integrated_metrics = integrated["metrics"]
            checks.append(result(
                "physical_closure",
                "physical",
                "PASS",
                "standalone area={:.3f} um^2, reg2reg slack={:.3f} ns; integrated area={:.3f} um^2, reg2reg slack={:.3f} ns; AKV SRAM=20 (4+16)".format(
                    standalone_metrics["design_total_area_um2"],
                    standalone_metrics["worst_reg_to_reg_setup_slack_ns"],
                    integrated_metrics["design_total_area_um2"],
                    integrated_metrics["worst_reg_to_reg_setup_slack_ns"],
                ),
                [standalone_summary, integrated_summary],
            ))
        except Exception as error:
            checks.append(result(
                "physical_closure",
                "physical",
                "FAIL",
                str(error),
                [standalone_summary, integrated_summary],
            ))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema")
    checks = audit(manifest)
    counts = {status: sum(check["status"] == status for check in checks) for status in ("PASS", "PENDING", "FAIL")}
    overall = "FAIL" if counts["FAIL"] else ("PENDING" if counts["PENDING"] else "PASS")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": 1,
        "status": overall,
        "counts": counts,
        "scope": "AKV area-controlled generalization functional/performance/physical completion audit",
        "manifest": artifact(args.manifest.resolve()),
        "checks": checks,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"{overall}: PASS={counts['PASS']} PENDING={counts['PENDING']} FAIL={counts['FAIL']}")
    if counts["FAIL"]:
        return 1
    if counts["PENDING"] and not args.allow_pending:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
