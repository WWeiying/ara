#!/usr/bin/env python3

"""Revalidate an immutable real-model context sweep with current rules."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from context_sweep import (
    SUPPORTED_AKV_D,
    SUPPORTED_AKV_GQA,
    load_json,
    parse_graphs,
    prompt_eval_tokens,
    sha256,
    summarize_graphs,
    validate_akv_disposition,
    validate_decode_expectation,
    validate_reference,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = Path(__file__).with_name("model-generality-manifest.json")
QBS_ABI = ROOT / "config/qbs_abi.json"


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def relative_or_absolute(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def aggregate_row(
    model_id: str,
    effective_kv: int,
    summary: dict[str, object],
    artifact: Path,
) -> dict[str, object]:
    decode = summary["decode"]
    return {
        "model": model_id,
        "effective_kv": effective_kv,
        "prompt_tokens": summary["prompt_tokens"],
        "qbs_candidate_compute_nodes": decode["qbs_candidate_compute_nodes"],
        "qbs_profiles": "/".join(decode["qbs_profiles"]),
        "qbs_operations": "/".join(
            f"{operation}:{count}"
            for operation, count in decode["qbs_operations"].items()
        ),
        "qbs_dot_elements": decode["qbs_dot_elements"],
        "qbs_weight_logical_bytes": decode["qbs_weight_logical_bytes"],
        "qbs_weight_unique_tensor_bytes": decode["qbs_weight_unique_tensor_bytes"],
        "qbs_activation_logical_bytes_without_cross_op_reuse": (
            decode["qbs_activation_logical_bytes_without_cross_op_reuse"]
        ),
        "akv_candidate_compute_nodes": decode["akv_candidate_compute_nodes"],
        "akv_shape_eligible_compute_nodes": decode["akv_shape_eligible_compute_nodes"],
        "akv_shape_fallback_compute_nodes": decode["akv_shape_fallback_compute_nodes"],
        "akv_shape_eligible_groups": decode["akv_shape_eligible_groups"],
        "attention_candidate_query_payload_logical_bytes": (
            decode["attention_candidate_query_payload_logical_bytes"]
        ),
        "attention_candidate_kv_payload_logical_bytes": (
            decode["attention_candidate_kv_payload_logical_bytes"]
        ),
        "attention_candidate_macs": decode["attention_candidate_macs"],
        "akv_shape_eligible_query_payload_logical_bytes": (
            decode["akv_shape_eligible_query_payload_logical_bytes"]
        ),
        "akv_shape_eligible_kv_payload_logical_bytes": (
            decode["akv_shape_eligible_kv_payload_logical_bytes"]
        ),
        "akv_shape_eligible_attention_macs": (
            decode["akv_shape_eligible_attention_macs"]
        ),
        "ordinary_rvv_compute_nodes_if_akv_shape_selected": (
            decode["ordinary_rvv_compute_nodes_if_akv_shape_selected"]
        ),
        "ordinary_rvv_compute_nodes_without_akv": (
            decode["ordinary_rvv_compute_nodes_without_akv"]
        ),
        "status": "PASS",
        "artifact": relative_or_absolute(artifact),
    }


def support_row(
    spec: dict[str, object],
    cases: list[tuple[int, dict[str, object]]],
) -> dict[str, object]:
    shapes: set[tuple[int, int, int, int]] = set()
    candidate_counts: set[int] = set()
    eligible_counts: set[int] = set()
    fallback_counts: set[int] = set()
    observed_dispositions: set[str] = set()

    for _, summary in cases:
        decode = summary["decode"]
        candidate = int(decode["akv_candidate_compute_nodes"])
        eligible = int(decode["akv_shape_eligible_compute_nodes"])
        fallback = int(decode["akv_shape_fallback_compute_nodes"])
        candidate_counts.add(candidate)
        eligible_counts.add(eligible)
        fallback_counts.add(fallback)
        if candidate <= 0 or candidate != eligible + fallback:
            raise ValueError(f"invalid AKV candidate partition for {spec['id']}")
        if eligible == candidate:
            observed_dispositions.add("execute")
        elif fallback == candidate:
            observed_dispositions.add("fallback_shape")
        else:
            observed_dispositions.add("mixed")
        for shape in decode["attention_shapes"]:
            shapes.add((
                int(shape["head_dim"]),
                int(shape["gqa_rows"]),
                int(shape["q_heads"]),
                int(shape["kv_heads"]),
            ))

    if len(observed_dispositions) != 1:
        raise ValueError(
            f"AKV disposition changes across KV lengths for {spec['id']}: "
            f"{sorted(observed_dispositions)}"
        )
    observed = next(iter(observed_dispositions))
    expected = str(spec["akv_disposition"])
    if observed != expected:
        raise ValueError(
            f"AKV support-matrix mismatch for {spec['id']}: "
            f"expected {expected}, observed {observed}"
        )

    return {
        "model": spec["id"],
        "model_name": spec["name"],
        "head_dims": "/".join(str(value) for value in sorted({x[0] for x in shapes})),
        "gqa_rows": "/".join(str(value) for value in sorted({x[1] for x in shapes})),
        "q_heads": "/".join(str(value) for value in sorted({x[2] for x in shapes})),
        "kv_heads": "/".join(str(value) for value in sorted({x[3] for x in shapes})),
        "effective_kv": "/".join(str(value) for value, _ in cases),
        "candidate_nodes_per_decode": "/".join(
            str(value) for value in sorted(candidate_counts)
        ),
        "eligible_nodes_per_decode": "/".join(
            str(value) for value in sorted(eligible_counts)
        ),
        "fallback_nodes_per_decode": "/".join(
            str(value) for value in sorted(fallback_counts)
        ),
        "expected_disposition": expected,
        "observed_disposition": observed,
        "reference_summary": spec.get("reference_summary") or "",
        "host_census_status": "PASS",
    }


def build_summary(
    manifest: dict[str, object],
    rows: list[dict[str, object]],
    support_rows: list[dict[str, object]],
    provenance_path: Path,
    counts_path: Path,
    support_path: Path,
) -> dict[str, object]:
    expected_cases = len(manifest["models"]) * len(manifest["kv_lengths"])
    if len(rows) != expected_cases:
        raise ValueError(
            f"context census has {len(rows)} cases, expected {expected_cases}"
        )
    if len(support_rows) != len(manifest["models"]):
        raise ValueError("support matrix does not contain every manifest model")
    if any(row["status"] != "PASS" for row in rows):
        raise ValueError("context census contains a non-PASS case")
    if any(row["host_census_status"] != "PASS" for row in support_rows):
        raise ValueError("support matrix contains a non-PASS model")

    dispositions = {
        disposition: sum(
            row["observed_disposition"] == disposition for row in support_rows
        )
        for disposition in ("execute", "fallback_shape")
    }
    unknown = sorted(
        {str(row["observed_disposition"]) for row in support_rows}
        - set(dispositions)
    )
    if unknown:
        raise ValueError(f"unsupported observed dispositions: {unknown}")

    return {
        "schema_version": 1,
        "status": "PASS",
        "scope": (
            "offline revalidation of immutable real-model Host Decode graphs; "
            "proves shape selection and logical work accounting, not QEMU "
            "execution, RTL cycles, or physical closure"
        ),
        "support_contract": {
            "head_dims": sorted(SUPPORTED_AKV_D),
            "gqa_rows": sorted(SUPPORTED_AKV_GQA),
        },
        "model_count": len(support_rows),
        "kv_lengths": [int(value) for value in manifest["kv_lengths"]],
        "case_count": len(rows),
        "case_status": {"PASS": len(rows)},
        "model_dispositions": dispositions,
        "candidate_nodes_across_cases": sum(
            int(row["akv_candidate_compute_nodes"]) for row in rows
        ),
        "eligible_nodes_across_cases": sum(
            int(row["akv_shape_eligible_compute_nodes"]) for row in rows
        ),
        "fallback_nodes_across_cases": sum(
            int(row["akv_shape_fallback_compute_nodes"]) for row in rows
        ),
        "models": [
            {
                "id": row["model"],
                "name": row["model_name"],
                "head_dims": row["head_dims"],
                "gqa_rows": row["gqa_rows"],
                "disposition": row["observed_disposition"],
            }
            for row in support_rows
        ],
        "artifacts": {
            "dynamic_counts": {
                "path": relative_or_absolute(counts_path),
                "sha256": sha256(counts_path),
            },
            "support_matrix": {
                "path": relative_or_absolute(support_path),
                "sha256": sha256(support_path),
            },
            "provenance": {
                "path": relative_or_absolute(provenance_path),
                "sha256": sha256(provenance_path),
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    output = args.output.resolve()
    if not (source_root / "complete").is_file():
        raise ValueError(f"source context sweep is not complete: {source_root}")
    if output.exists():
        raise FileExistsError(output)

    manifest = load_json(args.manifest)
    if int(manifest.get("schema_version", 0)) != 1:
        raise ValueError("unsupported model-generality manifest")
    abi = load_json(QBS_ABI)
    output.mkdir(parents=True)

    provenance = {
        "schema_version": 1,
        "mode": "offline_revalidation_of_immutable_host_logs",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest": relative_or_absolute(args.manifest.resolve()),
        "manifest_sha256": sha256(args.manifest),
        "qbs_abi": relative_or_absolute(QBS_ABI),
        "qbs_abi_sha256": sha256(QBS_ABI),
        "source_root": relative_or_absolute(source_root),
        "source_complete_sha256": sha256(source_root / "complete"),
        "source_provenance_sha256": sha256(source_root / "provenance.json"),
        "analyzer": relative_or_absolute(Path(__file__).with_name("context_sweep.py")),
        "analyzer_sha256": sha256(Path(__file__).with_name("context_sweep.py")),
        "tool": relative_or_absolute(Path(__file__).resolve()),
        "tool_sha256": sha256(Path(__file__).resolve()),
        "support_contract": {
            "head_dims": sorted(SUPPORTED_AKV_D),
            "gqa_rows": sorted(SUPPORTED_AKV_GQA),
        },
        "cases": [],
    }
    rows: list[dict[str, object]] = []
    support_rows: list[dict[str, object]] = []

    for spec in manifest["models"]:
        model_id = str(spec["id"])
        model_cases: list[tuple[int, dict[str, object]]] = []
        for effective_kv in manifest["kv_lengths"]:
            effective_kv = int(effective_kv)
            source_case = source_root / model_id / f"kv{effective_kv}"
            log_path = source_case / "host.log"
            prompt_path = source_case / "prompt.txt"
            for required in (log_path, prompt_path):
                if not required.is_file():
                    raise FileNotFoundError(required)

            observed_prompt_tokens = prompt_eval_tokens(log_path)
            if observed_prompt_tokens != effective_kv - 1:
                raise ValueError(
                    f"{model_id}/KV{effective_kv} prompt mismatch: "
                    f"{observed_prompt_tokens}"
                )
            summary = summarize_graphs(parse_graphs(log_path), effective_kv, abi)
            expectation = spec.get("decode_expectation")
            reference_path = spec.get("reference_summary")
            if reference_path:
                reference = load_json(ROOT / str(reference_path))
                validate_reference(summary, reference, expectation)
            elif expectation:
                validate_decode_expectation(summary, expectation)
            validate_akv_disposition(summary, str(spec["akv_disposition"]))

            case_dir = output / model_id / f"kv{effective_kv}"
            case_dir.mkdir(parents=True)
            summary_path = case_dir / "summary.json"
            summary.update({
                "model_id": model_id,
                "model_name": spec["name"],
                "prompt_tokens": observed_prompt_tokens,
                "source_host_log": relative_or_absolute(log_path),
                "source_host_log_sha256": sha256(log_path),
                "source_prompt": relative_or_absolute(prompt_path),
                "source_prompt_sha256": sha256(prompt_path),
            })
            summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            rows.append(aggregate_row(model_id, effective_kv, summary, summary_path))
            model_cases.append((effective_kv, summary))
            provenance["cases"].append({
                "model": model_id,
                "effective_kv": effective_kv,
                "host_log": relative_or_absolute(log_path),
                "host_log_sha256": sha256(log_path),
            })
            print(f"PASS {model_id} KV={effective_kv}")
        support_rows.append(support_row(spec, model_cases))

    counts_path = output / "dynamic_counts.csv"
    support_path = output / "support_matrix.csv"
    provenance_path = output / "provenance.json"
    write_csv(counts_path, rows)
    write_csv(support_path, support_rows)
    provenance_path.write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    summary = build_summary(
        manifest, rows, support_rows, provenance_path, counts_path, support_path
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (output / "complete").write_text("PASS\n", encoding="ascii")
    print(output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
