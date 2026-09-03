#!/usr/bin/env python3

"""Cross-check host graph coverage and RISC-V QEMU model closure."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from context_sweep import (
    load_json,
    sha256,
    validate_akv_disposition,
    validate_decode_expectation,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = Path(__file__).with_name("model-generality-manifest.json")
DEFAULT_RTL_CLOSURE = ROOT / "hardware/qbs_akv_model_closure_20260831/summary.json"
DEFAULT_QBS_CALIBRATION = Path(__file__).with_name("qbs-cycle-calibration.json")
QEMU_RUNNER = Path(__file__).with_name("run-model-generality-qemu.py")
SPEC = importlib.util.spec_from_file_location("model_generality_qemu", QEMU_RUNNER)
QEMU_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = QEMU_MODULE
SPEC.loader.exec_module(QEMU_MODULE)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_qemu_sources(values: list[str]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for value in values:
        model, separator, raw_path = value.partition("=")
        if not separator or not model or not raw_path:
            raise ValueError(f"invalid --qemu-summary value: {value}")
        if model in sources:
            raise ValueError(f"duplicate QEMU summary for {model}")
        sources[model] = Path(raw_path).resolve()
    return sources


def verify_host_sweep(
    host_root: Path,
    models: dict[str, dict[str, object]],
    kv_lengths: list[int],
    baseline_commit: str,
) -> dict[str, object]:
    dynamic_path = host_root / "dynamic_counts.csv"
    provenance_path = host_root / "provenance.json"
    if not (host_root / "complete").is_file():
        raise ValueError(f"host sweep is incomplete: {host_root}")
    if not dynamic_path.is_file() or not provenance_path.is_file():
        raise ValueError("host sweep lacks aggregate counts or provenance")

    rows = read_csv(dynamic_path)
    expected = {(model_id, kv) for model_id in models for kv in kv_lengths}
    observed: set[tuple[str, int]] = set()
    for row in rows:
        case = (row["model"], int(row["effective_kv"]))
        if case in observed:
            raise ValueError(f"duplicate host sweep case: {case}")
        observed.add(case)
        if row.get("status") != "PASS":
            raise ValueError(f"host sweep case is not PASS: {case}")
    if observed != expected:
        raise ValueError(
            f"host sweep matrix mismatch: missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )

    provenance = load_json(provenance_path)
    for key in ("llama_revision", "llama_binary_sha256", "tokenizer_sha256", "qbs_abi_sha256"):
        if not provenance.get(key):
            raise ValueError(f"host sweep provenance lacks {key}")
    if provenance.get("baseline_commit") != baseline_commit:
        raise ValueError("host sweep baseline revision differs from model manifest")
    recorded_models = provenance.get("models", {})
    if set(recorded_models) != set(models):
        raise ValueError("host sweep provenance model set is incomplete")
    for model_id, spec in models.items():
        if recorded_models[model_id].get("sha256") != spec.get("expected_sha256"):
            raise ValueError(f"host sweep model SHA-256 mismatch for {model_id}")
    return provenance


def verify_representative_selection(
    root: Path, host_root: Path, models: dict[str, dict[str, object]], kv_lengths: list[int]
) -> tuple[dict[str, object], list[dict[str, str]]]:
    selection_path = root / "selection.json"
    selected_path = root / "selected_shapes.csv"
    if (root / "complete").read_text(encoding="ascii").strip() != "PASS":
        raise ValueError("QBS representative selection is incomplete")
    selection = load_json(selection_path)
    if set(selection["models"]) != set(models):
        raise ValueError("QBS representative selection model set mismatch")
    if [int(value) for value in selection["validated_kv_lengths"]] != kv_lengths:
        raise ValueError("QBS representative selection KV matrix mismatch")
    if selection["input_dynamic_counts_sha256"] != sha256(host_root / "dynamic_counts.csv"):
        raise ValueError("QBS representative selection does not derive from this host sweep")
    selected = read_csv(selected_path)
    if len(selected) != int(selection["selected_shape_count"]):
        raise ValueError("QBS representative shape count mismatch")
    if float(selection["nominal_coverage"]) < float(selection["coverage_target"]):
        raise ValueError("QBS representative selection misses its coverage target")
    represented_models: set[str] = set()
    represented_profiles: set[str] = set()
    represented_operations: set[str] = set()
    for row in selected:
        row_models = {model for model in row["models"].split("/") if model}
        unknown_models = row_models - set(models)
        if unknown_models:
            raise ValueError(
                f"QBS representative selection names unknown models: {sorted(unknown_models)}"
            )
        represented_models.update(row_models)
        represented_profiles.add(row["profile"])
        represented_operations.add(row["operation"])
    represented_architectures = {
        str(models[model]["architecture"]) for model in represented_models
    }
    represented_topologies = {
        str(models[model]["topology"]) for model in represented_models
    }
    expected_architectures = {str(spec["architecture"]) for spec in models.values()}
    expected_topologies = {str(spec["topology"]) for spec in models.values()}
    expected_profiles = {
        str(profile)
        for spec in models.values()
        for profile in spec["decode_expectation"]["qbs_profiles"]
    }
    expected_operations = {
        str(operation)
        for spec in models.values()
        for operation in spec["decode_expectation"]["qbs_operations"]
    }
    for label, represented, expected in (
        ("architecture", represented_architectures, expected_architectures),
        ("topology", represented_topologies, expected_topologies),
        ("profile", represented_profiles, expected_profiles),
        ("operation", represented_operations, expected_operations),
    ):
        if represented != expected:
            raise ValueError(
                f"QBS representative {label} coverage mismatch: "
                f"missing={sorted(expected - represented)}, "
                f"extra={sorted(represented - expected)}"
            )
    selection["represented_model_count"] = len(represented_models)
    selection["represented_architecture_count"] = len(represented_architectures)
    selection["represented_topology_count"] = len(represented_topologies)
    return selection, selected


def verify_rtl_closure(path: Path) -> dict[str, object]:
    closure = load_json(path)
    if closure.get("status") != "PASS":
        raise ValueError("QBS/AKV RTL closure is not PASS")
    if not closure.get("qbs_rtl_tests") or any(
        row.get("status") != "PASS" for row in closure["qbs_rtl_tests"]
    ):
        raise ValueError("QBS RTL test suite is incomplete")
    shape_matrix = closure.get("akv_shape_matrix", {})
    if shape_matrix.get("status") != "PASS" or int(shape_matrix.get("results", 0)) <= 0:
        raise ValueError("AKV RTL shape matrix is incomplete")
    for field in ("qbs_representative_points", "akv_rtl_points"):
        if not closure.get(field) or any(row.get("status") != "PASS" for row in closure[field]):
            raise ValueError(f"RTL closure lacks passing {field}")
    if closure.get("ordinary_rvv", {}).get("status") != "PASS":
        raise ValueError("ordinary RVV fallback RTL point is not PASS")
    return closure


def qbs_static_signature(summary: dict[str, object]) -> tuple[object, ...]:
    decode = summary["decode"]
    return (
        int(decode["qbs_candidate_compute_nodes"]),
        json.dumps(decode["qbs_profiles"], sort_keys=True),
        json.dumps(decode["qbs_operations"], sort_keys=True),
        int(decode["qbs_dot_elements"]),
        int(decode["qbs_weight_logical_bytes"]),
        int(decode["qbs_weight_unique_tensor_bytes"]),
        int(decode["qbs_activation_logical_bytes_without_cross_op_reuse"]),
    )


def attention_static_signature(summary: dict[str, object]) -> tuple[tuple[int, ...], ...]:
    return tuple(sorted(
        (
            int(shape["head_dim"]), int(shape["q_heads"]),
            int(shape["kv_heads"]), int(shape["gqa_rows"]),
            int(bool(shape["shape_eligible"])),
        )
        for shape in summary["decode"]["attention_shapes"]
    ))


def attention_work(decode: dict[str, object]) -> dict[str, int]:
    shapes = decode["attention_shapes"]
    candidate = {
        "query_payload_logical_bytes": sum(
            int(shape["query_payload_logical_bytes"]) for shape in shapes
        ),
        "kv_payload_logical_bytes": sum(
            int(shape["kv_payload_logical_bytes"]) for shape in shapes
        ),
        "attention_macs": sum(int(shape["attention_macs"]) for shape in shapes),
    }
    eligible_shapes = [shape for shape in shapes if bool(shape["shape_eligible"])]
    eligible = {
        "query_payload_logical_bytes": sum(
            int(shape["query_payload_logical_bytes"]) for shape in eligible_shapes
        ),
        "kv_payload_logical_bytes": sum(
            int(shape["kv_payload_logical_bytes"]) for shape in eligible_shapes
        ),
        "attention_macs": sum(int(shape["attention_macs"]) for shape in eligible_shapes),
    }
    for suffix, value in candidate.items():
        key = f"attention_candidate_{suffix}"
        if key in decode and int(decode[key]) != value:
            raise ValueError(f"host summary {key} disagrees with its attention-shape census")
    for suffix, value in eligible.items():
        key = f"akv_shape_eligible_{suffix}"
        if key in decode and int(decode[key]) != value:
            raise ValueError(f"host summary {key} disagrees with its attention-shape census")
    legacy_keys = {
        "akv_query_payload_logical_bytes": eligible["query_payload_logical_bytes"],
        "akv_kv_payload_logical_bytes": eligible["kv_payload_logical_bytes"],
        "akv_attention_macs": eligible["attention_macs"],
    }
    for key, value in legacy_keys.items():
        if key in decode and int(decode[key]) != value:
            raise ValueError(f"legacy host summary {key} has inconsistent eligible-shape semantics")
    return {
        **{f"candidate_{key}": value for key, value in candidate.items()},
        **{f"eligible_{key}": value for key, value in eligible.items()},
    }


def host_model_summary(
    host_root: Path, model_id: str, kv_lengths: list[int]
) -> tuple[dict[str, object], list[dict[str, object]]]:
    summaries = []
    context_rows = []
    for kv in kv_lengths:
        path = host_root / model_id / f"kv{kv}" / "summary.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        summary = load_json(path)
        if str(summary.get("model_id")) != model_id:
            raise ValueError(f"host summary model mismatch in {path}")
        if int(summary["decode"]["effective_kv"]) != kv:
            raise ValueError(f"host summary KV mismatch in {path}")
        summaries.append((path, summary))
        decode = summary["decode"]
        work = attention_work(decode)
        context_rows.append({
            "model": model_id,
            "effective_kv": kv,
            "qbs_nodes": decode["qbs_candidate_compute_nodes"],
            "qbs_dot_elements": decode["qbs_dot_elements"],
            "qbs_weight_logical_bytes": decode["qbs_weight_logical_bytes"],
            "qbs_weight_unique_tensor_bytes": decode["qbs_weight_unique_tensor_bytes"],
            "qbs_activation_logical_bytes": (
                decode["qbs_activation_logical_bytes_without_cross_op_reuse"]
            ),
            "akv_candidate_nodes": decode["akv_candidate_compute_nodes"],
            "akv_eligible_nodes": decode["akv_shape_eligible_compute_nodes"],
            "akv_fallback_nodes": decode["akv_shape_fallback_compute_nodes"],
            "attention_candidate_query_payload_logical_bytes": (
                work["candidate_query_payload_logical_bytes"]
            ),
            "attention_candidate_macs": work["candidate_attention_macs"],
            "attention_candidate_kv_payload_logical_bytes": (
                work["candidate_kv_payload_logical_bytes"]
            ),
            "akv_shape_eligible_query_payload_logical_bytes": (
                work["eligible_query_payload_logical_bytes"]
            ),
            "akv_shape_eligible_attention_macs": (
                work["eligible_attention_macs"]
            ),
            "akv_shape_eligible_kv_payload_logical_bytes": (
                work["eligible_kv_payload_logical_bytes"]
            ),
            "summary_sha256": sha256(path),
        })

    qbs_signatures = {qbs_static_signature(summary) for _, summary in summaries}
    attention_signatures = {attention_static_signature(summary) for _, summary in summaries}
    if len(qbs_signatures) != 1:
        raise ValueError(f"{model_id} QBS Decode graph changes with KV length")
    if len(attention_signatures) != 1:
        raise ValueError(f"{model_id} attention topology changes with KV length")
    return summaries[0][1], context_rows


def verify_qemu_against_host(
    spec: dict[str, object],
    host: dict[str, object],
    qemu: dict[str, object],
    prefill_census: bool = False,
) -> dict[str, object]:
    disposition = str(spec["akv_disposition"])
    metrics = QEMU_MODULE.qemu_metrics(qemu, disposition, prefill_census)
    decode = host["decode"]
    expectation = spec.get("decode_expectation")
    if expectation is None:
        raise ValueError(f"{spec['id']} manifest lacks frozen Decode expectation")
    validate_decode_expectation(host, expectation)
    validate_akv_disposition(host, disposition)
    if qemu.get("graphs") != {"prefill": 1, "decode": 1}:
        raise ValueError(f"{spec['id']} QEMU run is not one Prefill plus one Decode graph")
    if int(qemu["qbs"]["nodes"]) != 2 * int(decode["qbs_candidate_compute_nodes"]):
        raise ValueError(f"{spec['id']} host/QEMU QBS node count mismatch")
    expected_operations = {
        operation: 2 * int(count)
        for operation, count in decode["qbs_operations"].items()
    }
    if qemu["qbs"]["operations"] != expected_operations:
        raise ValueError(f"{spec['id']} host/QEMU QBS operation mismatch")
    if set(qemu["qbs"]["coverage"]) != set(decode["qbs_profiles"]):
        raise ValueError(f"{spec['id']} host/QEMU QBS profile mismatch")

    candidates = int(decode["akv_candidate_compute_nodes"])
    if int(metrics["akv_candidate_ops"]) != 2 * candidates:
        raise ValueError(f"{spec['id']} host/QEMU attention candidate mismatch")
    if disposition == "execute":
        if prefill_census:
            if (
                int(metrics["akv_executed_ops"]) != 2 * candidates
                or int(metrics["akv_executed_decode"]) != candidates
                or int(metrics["akv_executed_prefill"]) != candidates
                or int(metrics["akv_fallback_ops"]) != 0
            ):
                raise ValueError(f"{spec['id']} QEMU Prefill/Decode AKV partition mismatch")
        elif (
            int(metrics["akv_executed_ops"]) != candidates
            or int(metrics["akv_fallback_shape"]) != candidates
        ):
            raise ValueError(f"{spec['id']} QEMU Prefill/Decode AKV partition mismatch")
    elif (
        int(metrics["akv_executed_ops"]) != 0
        or int(metrics["akv_fallback_shape"]) != 2 * candidates
    ):
        raise ValueError(f"{spec['id']} QEMU AKV shape fallback mismatch")

    run_manifest = qemu["provenance"]["run_manifest"]
    if run_manifest.get("MODEL_GUEST_PATH") != spec["qemu"]["guest_path"]:
        raise ValueError(f"{spec['id']} QEMU guest model path mismatch")
    if "vlen=1024" not in run_manifest.get("QEMU_CPU", "") or \
       "xaraqbs=true" not in run_manifest.get("QEMU_CPU", ""):
        raise ValueError(f"{spec['id']} QEMU CPU does not expose VLEN=1024 native QBS")
    observed_memory = run_manifest.get("QEMU_MEMORY")
    # Runs predating the configurable-memory field used the runner's fixed 4G
    # command line. Treat only that exact legacy case as recorded implicitly.
    if observed_memory is None:
        observed_memory = "4G"
    if observed_memory != spec["qemu"]["memory"]:
        raise ValueError(f"{spec['id']} QEMU memory differs from the model manifest")
    expected_disk_sha = spec["qemu"].get("disk_sha256")
    if expected_disk_sha and run_manifest.get("MODEL_DISK_SHA256") != expected_disk_sha:
        raise ValueError(f"{spec['id']} QEMU model-disk SHA-256 mismatch")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--host-root", type=Path, required=True)
    parser.add_argument("--qemu-summary", action="append", default=[], metavar="MODEL=JSON")
    parser.add_argument("--qbs-representatives", type=Path, required=True)
    parser.add_argument("--qbs-calibration", type=Path, default=DEFAULT_QBS_CALIBRATION)
    parser.add_argument("--rtl-closure", type=Path, default=DEFAULT_RTL_CLOSURE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--prefill-census",
        action="store_true",
        help="require supported QEMU models to execute both Prefill and Decode",
    )
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    if int(manifest.get("schema_version", 0)) != 1:
        raise ValueError("unsupported model-generality manifest")
    models = {str(spec["id"]): spec for spec in manifest["models"]}
    kv_lengths = [int(value) for value in manifest["kv_lengths"]]
    qemu_sources = parse_qemu_sources(args.qemu_summary)
    if set(qemu_sources) != set(models):
        missing = sorted(set(models) - set(qemu_sources))
        extra = sorted(set(qemu_sources) - set(models))
        raise ValueError(f"QEMU source set mismatch: missing={missing}, extra={extra}")
    host_root = args.host_root.resolve()
    host_provenance = verify_host_sweep(
        host_root, models, kv_lengths, str(manifest["baseline_commit"])
    )
    qbs_abi_path = ROOT / "config/qbs_abi.json"
    if sha256(qbs_abi_path) != host_provenance["qbs_abi_sha256"]:
        raise ValueError("current QBS ABI differs from the checked Host graph contract")
    selection_root = args.qbs_representatives.resolve()
    selection, representative_rows = verify_representative_selection(
        selection_root, host_root, models, kv_lengths
    )
    calibration_path = args.qbs_calibration.resolve()
    if not calibration_path.is_file():
        raise FileNotFoundError(calibration_path)
    if sha256(calibration_path) != selection["calibration_sha256"]:
        raise ValueError("QBS representative selection calibration hash mismatch")
    rtl_closure_path = args.rtl_closure.resolve()
    rtl_closure = verify_rtl_closure(rtl_closure_path)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    evidence_root = output / "evidence"
    host_evidence_root = evidence_root / "host_decode"
    qemu_evidence_root = evidence_root / "qemu_dynamic"
    tool_evidence_root = evidence_root / "verification_tools"
    host_evidence_root.mkdir(parents=True)
    qemu_evidence_root.mkdir(parents=True)
    tool_evidence_root.mkdir(parents=True)
    shutil.copyfile(args.manifest, evidence_root / "model-generality-manifest.json")
    shutil.copyfile(host_root / "dynamic_counts.csv", evidence_root / "host-dynamic-counts.csv")
    shutil.copyfile(host_root / "provenance.json", evidence_root / "host-provenance.json")
    shutil.copyfile(selection_root / "selection.json", evidence_root / "qbs-selection.json")
    shutil.copyfile(calibration_path, evidence_root / "qbs-cycle-calibration.json")
    shutil.copyfile(rtl_closure_path, evidence_root / "rtl-closure.json")
    shutil.copyfile(qbs_abi_path, evidence_root / "qbs_abi.json")
    verification_tools = {
        "summarizer": Path(__file__).resolve(),
        "context_parser": Path(__file__).with_name("context_sweep.py").resolve(),
        "qemu_verifier": QEMU_RUNNER.resolve(),
    }
    archived_tools = {}
    for name, source in verification_tools.items():
        archive = tool_evidence_root / source.name
        shutil.copyfile(source, archive)
        archived_tools[name] = {
            "source_path": str(source),
            "archived_path": str(archive.relative_to(output)),
            "sha256": sha256(archive),
        }

    model_rows = []
    context_rows = []
    provenance = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prefill_census": args.prefill_census,
        "verification_tools": archived_tools,
        "manifest": {"path": str(args.manifest.resolve()), "sha256": sha256(args.manifest)},
        "qbs_abi": {
            "path": str(qbs_abi_path),
            "sha256": sha256(qbs_abi_path),
            "archived_path": "evidence/qbs_abi.json",
        },
        "host": {
            "root": str(host_root),
            "dynamic_counts_sha256": sha256(host_root / "dynamic_counts.csv"),
            "provenance_sha256": sha256(host_root / "provenance.json"),
            "archived_dynamic_counts": "evidence/host-dynamic-counts.csv",
            "archived_provenance": "evidence/host-provenance.json",
            "capture_manifest_sha256": host_provenance.get("manifest_sha256"),
            "llama_revision": host_provenance["llama_revision"],
            "llama_binary_sha256": host_provenance["llama_binary_sha256"],
            "archived_decode_summaries": {},
        },
        "qemu_summaries": {},
        "qbs_representative_selection": {
            "path": str(selection_root),
            "selection_sha256": sha256(selection_root / "selection.json"),
            "selected_shapes_sha256": sha256(selection_root / "selected_shapes.csv"),
            "calibration_path": str(calibration_path),
            "calibration_sha256": sha256(calibration_path),
            "archived_calibration": "evidence/qbs-cycle-calibration.json",
        },
        "rtl_closure": {"path": str(rtl_closure_path), "sha256": sha256(rtl_closure_path)},
    }
    for model_id, spec in models.items():
        host, rows = host_model_summary(host_root, model_id, kv_lengths)
        context_rows.extend(rows)
        host_model_archive = host_evidence_root / model_id
        host_model_archive.mkdir()
        provenance["host"]["archived_decode_summaries"][model_id] = {}
        for kv in kv_lengths:
            host_source = host_root / model_id / f"kv{kv}" / "summary.json"
            host_archive = host_model_archive / f"kv{kv}.json"
            shutil.copyfile(host_source, host_archive)
            provenance["host"]["archived_decode_summaries"][model_id][str(kv)] = {
                "path": str(host_archive.relative_to(output)),
                "sha256": sha256(host_archive),
            }
        qemu_path = qemu_sources[model_id]
        if not qemu_path.is_file():
            raise FileNotFoundError(qemu_path)
        qemu = load_json(qemu_path)
        qemu_archive = qemu_evidence_root / f"{model_id}.json"
        shutil.copyfile(qemu_path, qemu_archive)
        metrics = verify_qemu_against_host(spec, host, qemu, args.prefill_census)
        provenance["qemu_summaries"][model_id] = {
            "source_path": str(qemu_path),
            "archived_path": str(qemu_archive.relative_to(output)),
            "sha256": sha256(qemu_path),
        }
        decode = host["decode"]
        shapes = attention_static_signature(host)
        shape_text = "/".join(
            f"D{d}:Hq{qh}:Hkv{kvh}:G{gqa}" for d, qh, kvh, gqa, _ in sorted(set(shapes))
        )
        model_rows.append({
            "model": model_id,
            "name": spec["name"],
            "architecture": spec["architecture"],
            "topology": spec["topology"],
            "quantization": spec["quantization"],
            "source_repo": spec["source"]["repo"],
            "source_revision": spec["source"]["revision"],
            "source_file": spec["source"]["file"],
            "model_sha256": spec["expected_sha256"],
            "model_disk_sha256": spec["qemu"].get("disk_sha256", ""),
            "qbs_operations": "/".join(
                f"{operation}:{count}"
                for operation, count in sorted(decode["qbs_operations"].items())
            ),
            "qbs_profiles": "/".join(sorted(decode["qbs_profiles"])),
            "decode_qbs_nodes": decode["qbs_candidate_compute_nodes"],
            "decode_qbs_dot_elements": decode["qbs_dot_elements"],
            "attention_shape": shape_text,
            "akv_disposition": spec["akv_disposition"],
            "qemu_qbs_gemv_calls": metrics["qbs_gemv_calls"],
            "qemu_qbs_gemm_calls": metrics["qbs_gemm_calls"],
            "qemu_qbs_dot_elements": metrics["qbs_dot_elements"],
            "qemu_qbs_command_dot_elements": metrics["qbs_command_dot_elements"],
            "qemu_qbs_native_commands": metrics["qbs_native_commands"],
            "qemu_qbs_emulated_commands": metrics["qbs_emulated_commands"],
            **{
                f"qemu_qbs_commands_m{m}": metrics[f"qbs_commands_m{m}"]
                for m in range(1, 9)
            },
            "qemu_qbs_top1_equal": metrics["qbs_top1_equal"],
            "qemu_qbs_token_equal": metrics["qbs_token_output_equal"],
            "qemu_qbs_logits_records": metrics["qbs_logits_records"],
            "qemu_qbs_logits_comparable_records": metrics[
                "qbs_logits_comparable_records"
            ],
            "qemu_qbs_logits_max_abs": metrics["qbs_logits_max_abs"],
            "qemu_qbs_logits_max_rel": metrics["qbs_logits_max_rel"],
            "qemu_qbs_logits_mean_abs": metrics["qbs_logits_mean_abs"],
            "qemu_qbs_logits_mean_rmse": metrics["qbs_logits_mean_rmse"],
            "qemu_qbs_logits_mean_kl": metrics["qbs_logits_mean_kl"],
            "qemu_qbs_logits_mean_cosine": metrics["qbs_logits_mean_cosine"],
            "qemu_qbs_logits_top5_overlap": metrics["qbs_logits_top5_overlap"],
            "qemu_qbs_logits_max_kl": metrics["qbs_logits_max_kl"],
            "qemu_qbs_logits_min_cosine": metrics["qbs_logits_min_cosine"],
            "qemu_qbs_logits_min_top5_overlap": metrics[
                "qbs_logits_min_top5_overlap"
            ],
            "qemu_akv_executed_ops": metrics["akv_executed_ops"],
            "qemu_akv_executed_decode": metrics["akv_executed_decode"],
            "qemu_akv_executed_prefill": metrics["akv_executed_prefill"],
            "qemu_akv_prefill_query_tokens": metrics["akv_prefill_query_tokens"],
            "qemu_akv_prefill_attention_pairs": metrics["akv_prefill_attention_pairs"],
            "qemu_akv_fallback_ops": metrics["akv_fallback_ops"],
            "qemu_akv_fallback_shape": metrics["akv_fallback_shape"],
            "qemu_akv_fastpath_status": metrics["akv_fastpath_status"],
            "qemu_akv_performance_evidence": metrics["akv_performance_evidence"],
            "qemu_akv_top1_equal": metrics["akv_top1_equal"],
            "qemu_akv_token_equal": metrics["akv_token_output_equal"],
            "qemu_akv_logits_records": metrics["akv_logits_records"],
            "qemu_akv_logits_comparable_records": metrics[
                "akv_logits_comparable_records"
            ],
            "qemu_akv_logits_max_abs": metrics["akv_logits_max_abs"],
            "qemu_akv_logits_max_rel": metrics["akv_logits_max_rel"],
            "qemu_akv_logits_mean_abs": metrics["akv_logits_mean_abs"],
            "qemu_akv_logits_mean_rmse": metrics["akv_logits_mean_rmse"],
            "qemu_akv_logits_mean_kl": metrics["akv_logits_mean_kl"],
            "qemu_akv_logits_mean_cosine": metrics["akv_logits_mean_cosine"],
            "qemu_akv_logits_top5_overlap": metrics["akv_logits_top5_overlap"],
            "qemu_akv_logits_max_kl": metrics["akv_logits_max_kl"],
            "qemu_akv_logits_min_cosine": metrics["akv_logits_min_cosine"],
            "qemu_akv_logits_min_top5_overlap": metrics[
                "akv_logits_min_top5_overlap"
            ],
            "qemu_akv_logits_tolerance": metrics["akv_logits_tolerance"],
            "qemu_model_numerical_contract": metrics["model_numerical_contract"],
            "qemu_model_logits_max_kl_tolerance": metrics[
                "model_logits_max_kl_tolerance"
            ],
            "qemu_model_logits_min_cosine_tolerance": metrics[
                "model_logits_min_cosine_tolerance"
            ],
            "qemu_model_logits_min_top5_overlap_tolerance": metrics[
                "model_logits_min_top5_overlap_tolerance"
            ],
            "qemu_llama_revision": metrics["llama_revision"],
            "qemu_llama_binary_sha256": metrics["llama_binary_sha256"],
            "qemu_binary_sha256": metrics["qemu_binary_sha256"],
            "qemu_cpu": metrics["qemu_cpu"],
            "qemu_prompt": metrics["model_prompt"],
            "qemu_model_tokens": metrics["model_tokens"],
            "qemu_qbs_activation_accounting": metrics["qbs_activation_accounting"],
            "qemu_qbs_activation_unresolved_nodes": (
                metrics["qbs_activation_unresolved_nodes"]
            ),
            "qemu_qbs_abi_sha256": metrics["qbs_abi_sha256"],
            "qemu_qbs_architecture_version": metrics["qbs_architecture_version"],
            "status": "PASS",
        })

    qemu_llama_binaries = {str(row["qemu_llama_binary_sha256"]) for row in model_rows}
    qemu_binaries = {str(row["qemu_binary_sha256"]) for row in model_rows}
    qemu_cpus = {str(row["qemu_cpu"]) for row in model_rows}
    qemu_model_tokens = {str(row["qemu_model_tokens"]) for row in model_rows}
    qemu_qbs_abi_hashes = {str(row["qemu_qbs_abi_sha256"]) for row in model_rows}
    qemu_qbs_architecture_versions = {
        int(row["qemu_qbs_architecture_version"]) for row in model_rows
    }
    qemu_akv_logits_tolerances = {
        float(row["qemu_akv_logits_tolerance"]) for row in model_rows
    }
    qemu_model_contracts = {
        str(row["qemu_model_numerical_contract"]) for row in model_rows
    }
    qemu_model_max_kl_tolerances = {
        float(row["qemu_model_logits_max_kl_tolerance"]) for row in model_rows
    }
    qemu_model_min_cosine_tolerances = {
        float(row["qemu_model_logits_min_cosine_tolerance"]) for row in model_rows
    }
    qemu_model_min_top5_tolerances = {
        float(row["qemu_model_logits_min_top5_overlap_tolerance"])
        for row in model_rows
    }
    if "" in qemu_llama_binaries or len(qemu_llama_binaries) != 1:
        raise ValueError("QEMU model runs do not share one recorded llama binary")
    if "" in qemu_binaries or len(qemu_binaries) != 1:
        raise ValueError("QEMU model runs do not share one recorded QEMU binary")
    if "" in qemu_cpus or len(qemu_cpus) != 1:
        raise ValueError("QEMU model runs do not share one recorded CPU contract")
    if "" in qemu_model_tokens or len(qemu_model_tokens) != 1:
        raise ValueError("QEMU model runs do not share one generated-token count")
    if qemu_qbs_abi_hashes != {str(host_provenance["qbs_abi_sha256"])}:
        raise ValueError("Host and QEMU model runs do not share one QBS ABI")
    if len(qemu_qbs_architecture_versions) != 1:
        raise ValueError("QEMU model runs do not share one QBS architecture version")
    if len(qemu_akv_logits_tolerances) != 1:
        raise ValueError("QEMU model runs do not share one AKV logits tolerance")
    if qemu_model_contracts != {"decision-preserving-v1"}:
        raise ValueError("QEMU model runs do not share the expected numerical contract")
    if len(qemu_model_max_kl_tolerances) != 1 or \
            len(qemu_model_min_cosine_tolerances) != 1 or \
            len(qemu_model_min_top5_tolerances) != 1:
        raise ValueError("QEMU model runs do not share model-quality thresholds")

    aggregate = {
        "model_count": len(model_rows),
        "architecture_count": len({row["architecture"] for row in model_rows}),
        "dense_model_count": sum(row["topology"] == "dense" for row in model_rows),
        "moe_model_count": sum(row["topology"] == "moe" for row in model_rows),
        "host_case_count": len(context_rows),
        "qemu_case_count": len(model_rows),
        "qbs_profiles": sorted({
            profile
            for row in model_rows
            for profile in str(row["qbs_profiles"]).split("/")
        }),
        "qbs_operations": sorted({
            operation.split(":", 1)[0]
            for row in model_rows
            for operation in str(row["qbs_operations"]).split("/")
        }),
        "qbs_native_commands": sum(int(row["qemu_qbs_native_commands"]) for row in model_rows),
        "qbs_emulated_commands": sum(int(row["qemu_qbs_emulated_commands"]) for row in model_rows),
        "qbs_commands_by_m": {
            str(m): sum(int(row[f"qemu_qbs_commands_m{m}"]) for row in model_rows)
            for m in range(1, 9)
        },
        "qbs_gemv_calls": sum(int(row["qemu_qbs_gemv_calls"]) for row in model_rows),
        "qbs_gemm_calls": sum(int(row["qemu_qbs_gemm_calls"]) for row in model_rows),
        "qbs_dot_elements": sum(int(row["qemu_qbs_dot_elements"]) for row in model_rows),
        "akv_execute_models": sum(row["akv_disposition"] == "execute" for row in model_rows),
        "akv_shape_fallback_models": sum(
            row["akv_disposition"] == "fallback_shape" for row in model_rows
        ),
        "akv_executed_decode": sum(
            int(row["qemu_akv_executed_decode"]) for row in model_rows
        ),
        "akv_executed_prefill": sum(
            int(row["qemu_akv_executed_prefill"]) for row in model_rows
        ),
        "akv_prefill_query_tokens": sum(
            int(row["qemu_akv_prefill_query_tokens"]) for row in model_rows
        ),
        "akv_prefill_attention_pairs": sum(
            int(row["qemu_akv_prefill_attention_pairs"]) for row in model_rows
        ),
        "prefill_census": args.prefill_census,
        "qemu_llama_binary_sha256": next(iter(qemu_llama_binaries)),
        "qemu_binary_sha256": next(iter(qemu_binaries)),
        "qemu_cpu": next(iter(qemu_cpus)),
        "qemu_model_tokens": int(next(iter(qemu_model_tokens))),
        "qbs_abi_sha256": next(iter(qemu_qbs_abi_hashes)),
        "qbs_architecture_version": next(iter(qemu_qbs_architecture_versions)),
        "akv_logits_tolerance": next(iter(qemu_akv_logits_tolerances)),
        "model_numerical_contract": next(iter(qemu_model_contracts)),
        "model_logits_max_kl_tolerance": next(iter(qemu_model_max_kl_tolerances)),
        "model_logits_min_cosine_tolerance": next(
            iter(qemu_model_min_cosine_tolerances)
        ),
        "model_logits_min_top5_overlap_tolerance": next(
            iter(qemu_model_min_top5_tolerances)
        ),
        "qemu_llama_revisions": sorted({
            str(row["qemu_llama_revision"]) for row in model_rows
        }),
        "qemu_prompt_count": len({str(row["qemu_prompt"]) for row in model_rows}),
        "qemu_qbs_activation_unresolved_nodes": sum(
            int(row["qemu_qbs_activation_unresolved_nodes"]) for row in model_rows
        ),
        "qbs_representative_shape_count": int(selection["selected_shape_count"]),
        "qbs_representative_model_count": int(selection["represented_model_count"]),
        "qbs_representative_architecture_count": int(
            selection["represented_architecture_count"]
        ),
        "qbs_representative_projected_coverage": float(selection["nominal_coverage"]),
        "qbs_rtl_suite_count": len(rtl_closure["qbs_rtl_tests"]),
        "akv_rtl_shape_results": int(rtl_closure["akv_shape_matrix"]["results"]),
    }
    write_csv(output / "models.csv", model_rows)
    write_csv(output / "contexts.csv", context_rows)
    write_csv(output / "qbs_representatives.csv", representative_rows)
    (output / "summary.json").write_text(
        json.dumps({"schema_version": 1, "status": "PASS", "aggregate": aggregate,
                    "models": model_rows, "contexts": context_rows,
                    "qbs_representatives": representative_rows,
                    "rtl_evidence": {
                        "qbs_rtl_tests": rtl_closure["qbs_rtl_tests"],
                        "qbs_representative_points": rtl_closure["qbs_representative_points"],
                        "akv_shape_matrix": rtl_closure["akv_shape_matrix"],
                        "akv_rtl_points": rtl_closure["akv_rtl_points"],
                        "ordinary_rvv": rtl_closure["ordinary_rvv"],
                    },
                    "provenance": provenance}, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# QBS + AKV Model Generality Closure", "",
        "The closure uses the same published GGUF quantization class across multiple dense and MoE model",
        "architectures. Host graph traces cover four Decode KV lengths; full-system QEMU",
        "runs cover one Prefill and one Decode graph with native QBS, explicit AKV",
        "functional execution/fallback accounting, and RVV/QBS/AKV numerical checks.", "",
        "## Coverage", "",
        f"- Models: {aggregate['model_count']} ({aggregate['dense_model_count']} dense, "
        f"{aggregate['moe_model_count']} MoE) across {aggregate['architecture_count']} GGML architectures.",
        f"- Host graph matrix: {aggregate['host_case_count']} PASS cases "
        f"({len(model_rows)} models x {len(kv_lengths)} KV lengths).",
        f"- QEMU model runs: {aggregate['qemu_case_count']} PASS cases; "
        f"{aggregate['qbs_native_commands']} native QBS commands and "
        f"{aggregate['qbs_emulated_commands']} emulated commands; "
        f"{aggregate['qemu_model_tokens']} generated tokens per run.",
        f"- QEMU matrix execution: {aggregate['qbs_gemv_calls']} GEMV calls, "
        f"{aggregate['qbs_gemm_calls']} GEMM calls, and "
        f"{aggregate['qbs_dot_elements']} checked dot elements.",
        f"- AKV phase execution: {aggregate['akv_executed_decode']} Decode calls and "
        f"{aggregate['akv_executed_prefill']} Prefill calls; Prefill accounts for "
        f"{aggregate['akv_prefill_query_tokens']} query tokens and "
        f"{aggregate['akv_prefill_attention_pairs']} causal attention pairs.",
        f"- All QEMU runs use one guest llama binary (`{aggregate['qemu_llama_binary_sha256'][:12]}...`), "
        f"one QEMU binary (`{aggregate['qemu_binary_sha256'][:12]}...`), and one CPU contract.",
        f"- Host and QEMU use QBS ABI v{aggregate['qbs_architecture_version']} "
        f"(`{aggregate['qbs_abi_sha256'][:12]}...`).",
        f"- Legacy QEMU graph records with unavailable source-activation shape: "
        f"{aggregate['qemu_qbs_activation_unresolved_nodes']} nodes; Host graph accounting remains exact.",
        f"- Observed QBS operators: {', '.join(aggregate['qbs_operations'])}; profiles: "
        f"{', '.join(aggregate['qbs_profiles'])}.", "",
        "## Model Inputs", "",
        "All rows use the published `Q4_K_M` quantization label, so the primary GGUF format",
        "class is held constant. This does not imply identical quantizer versions, importance",
        "matrices, or calibration data across publishers. Exact file hashes and immutable source",
        "revisions are part of the machine-readable manifest.", "",
        "| Model | Topology | Source repository | Revision | Model SHA-256 |",
        "|---|---|---|---|---|",
    ]
    for row in model_rows:
        lines.append(
            f"| {row['name']} | {row['topology']} | {row['source_repo']} | "
            f"`{str(row['source_revision'])[:12]}` | `{str(row['model_sha256'])[:12]}...` |"
        )
    lines.extend([
        "",
        "## Evidence Layers", "",
        "| Layer | Coverage | What it establishes |",
        "|---|---|---|",
        f"| Real host graphs | {aggregate['host_case_count']} model/KV cases | Exact GGML operator, profile, shape, routing and logical-work census |",
        f"| Full-system QEMU | {aggregate['qemu_case_count']} models | Native QBS custom-instruction execution, AKV functional dispatch/fallback, and numerical checks |",
        f"| Timing RTL | {aggregate['qbs_rtl_suite_count']} QBS suites; {aggregate['akv_rtl_shape_results']} AKV case/mode results | Datapath, command, memory, commit, fault and supported-shape contracts |",
        f"| Representative ranking | {aggregate['qbs_representative_shape_count']} shapes across {aggregate['qbs_representative_architecture_count']} architectures; {aggregate['qbs_representative_projected_coverage']:.3%} pooled projected work | Which real shapes dominate; projection is not measured full-model timing |",
        "",
        "## Model Results", "",
        "| Model | Topology | GGML arch. | QBS op | Profiles | Decode nodes | Attention | AKV | AKV D/P/F | GEMV/GEMM | Native cmds | Numerical |",
        "|---|---|---|---|---|---:|---|---|---:|---:|---:|---|",
    ])
    for row in model_rows:
        lines.append(
            f"| {row['name']} | {row['topology']} | {row['architecture']} | "
            f"{row['qbs_operations']} | "
            f"{row['qbs_profiles']} | {row['decode_qbs_nodes']} | {row['attention_shape']} | "
            f"{row['akv_disposition']} | {row['qemu_akv_executed_decode']}/"
            f"{row['qemu_akv_executed_prefill']}/{row['qemu_akv_fallback_ops']} | "
            f"{row['qemu_qbs_gemv_calls']}/"
            f"{row['qemu_qbs_gemm_calls']} | {row['qemu_qbs_native_commands']} | "
            f"top1/token PASS; AKV max/RMSE/KL/cos/top5 "
            f"{row['qemu_akv_logits_max_abs']}/{row['qemu_akv_logits_mean_rmse']}/"
            f"{row['qemu_akv_logits_mean_kl']}/{row['qemu_akv_logits_mean_cosine']}/"
            f"{row['qemu_akv_logits_top5_overlap']} |"
        )
    lines.extend([
        "", "## Context-Length Checks", "",
        "QBS Decode graph structure is invariant across the tested KV lengths. AKV topology",
        "is invariant while attention MACs and KV payload scale with effective context.", "",
        "| Model | KV range | QBS nodes | QBS dot elements | Attention candidates | Candidate MACs (min -> max KV) | AKV disposition |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in model_rows:
        model_contexts = [item for item in context_rows if item["model"] == row["model"]]
        first, last = model_contexts[0], model_contexts[-1]
        lines.append(
            f"| {row['name']} | {first['effective_kv']} -> {last['effective_kv']} | "
            f"{first['qbs_nodes']} | {first['qbs_dot_elements']} | "
            f"{first['akv_candidate_nodes']} | {first['attention_candidate_macs']} -> "
            f"{last['attention_candidate_macs']} | {row['akv_disposition']} |"
        )
    lines.extend([
        "", "## Interpretation and Boundary", "",
        "- QBS closure requires every eligible quantized tensor to select native commands with zero emulated commands.",
        (
            "- `execute` means both Decode and eligible Prefill attention use AKV with zero fallback."
            if args.prefill_census else
            "- `execute` means Decode attention uses AKV; its Prefill attention intentionally follows the RVV fallback."
        ),
        "- `fallback_shape` is a positive compatibility result: all attention candidates remain correct on RVV.",
        "- Equal greedy tokens/top-1 establish the fixed-run decision result; nonzero QBS logit deltas reflect the documented accumulation-order difference and are not bitwise equivalence.",
        "- QEMU establishes functional and numerical behavior, not RTL cycle performance.",
        "- AKV executes through its GGML functional-emulation path in full-model QEMU; native AKV timing evidence comes from the representative RTL leaves.",
        "- The common guest-binary hash is the QEMU execution identity; checkout revision labels remain recorded because later source changes only extended graph-trace metadata.",
        "- Prompts are provenance-recorded but are not identical across every model; cross-model command counts are coverage evidence, not comparable timing samples.",
        "- Directed/timing RTL establishes mechanism contracts; it does not claim cycle-accurate simulation of every full-model matrix.",
        "- `MUL_MAT_ID` traffic counts dynamically routed expert matrices separately from resident expert-tensor capacity.",
        "- Legacy `MUL_MAT_ID` QEMU traces without source-tensor shape are not used to infer activation-quantization work; the newer Host trace supplies that quantity.",
    ])
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "complete").write_text("PASS\n", encoding="ascii")
    print(output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
