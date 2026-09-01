#!/usr/bin/env python3

"""Capture real llama.cpp Decode graphs at controlled effective KV lengths."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from context_sweep import (
    exact_prompt,
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
DEFAULT_MANIFEST = Path(__file__).with_name("context-sweep-manifest.json")
DEFAULT_LLAMA_ROOT = Path("/home/wangwy/llama/llama.cpp")
DEFAULT_BINARY = DEFAULT_LLAMA_ROOT / "build-prof/bin/llama-completion"
DEFAULT_TOKENIZER = DEFAULT_LLAMA_ROOT / "build-prof/bin/llama-tokenize"
QBS_ABI = ROOT / "config/qbs_abi.json"


def git_output(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def next_power_of_two(value: int) -> int:
    return 1 << (max(value, 64) - 1).bit_length()


def parse_selection(raw: str | None, available: list[str], label: str) -> list[str]:
    if raw is None or raw == "all":
        return available
    selected = raw.split(",")
    unknown = sorted(set(selected) - set(available))
    if unknown:
        raise ValueError(f"unknown {label}: {', '.join(unknown)}")
    return selected


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--models", default="all")
    parser.add_argument("--kv", default="all")
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--tokenizer", type=Path, default=DEFAULT_TOKENIZER)
    parser.add_argument("--llama-root", type=Path, default=DEFAULT_LLAMA_ROOT)
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="append non-overlapping model/KV cases to an existing compatible sweep",
    )
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    if int(manifest.get("schema_version", 0)) != 1:
        raise ValueError("unsupported context-sweep manifest")
    baseline = str(manifest["baseline_commit"])
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    for required in (args.binary, args.tokenizer, args.llama_root, QBS_ABI):
        if not required.exists():
            raise FileNotFoundError(required)
    llama_dirty = git_output(args.llama_root, "status", "--porcelain", "--untracked-files=no")
    if llama_dirty:
        raise ValueError("llama.cpp has tracked modifications; commit the trace instrumentation first")

    model_specs = {str(item["id"]): item for item in manifest["models"]}
    model_ids = parse_selection(args.models, list(model_specs), "model")
    available_kv = [str(value) for value in manifest["kv_lengths"]]
    kv_lengths = [int(value) for value in parse_selection(args.kv, available_kv, "KV length")]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = (args.output or ROOT / f"hardware/qbs_akv_context_sweep_{stamp}").resolve()
    if args.resume and not output.is_dir():
        raise FileNotFoundError(output)
    output.mkdir(parents=True, exist_ok=args.resume)

    abi = load_json(QBS_ABI)
    current_provenance = {
        "schema_version": 1,
        "baseline_commit": baseline,
        "ara_revision": git_output(ROOT, "rev-parse", "HEAD"),
        "manifest": str(args.manifest.resolve()),
        "manifest_sha256": sha256(args.manifest),
        "llama_revision": git_output(args.llama_root, "rev-parse", "HEAD"),
        "llama_binary": str(args.binary.resolve()),
        "llama_binary_sha256": sha256(args.binary),
        "tokenizer": str(args.tokenizer.resolve()),
        "tokenizer_sha256": sha256(args.tokenizer),
        "qbs_abi_sha256": sha256(QBS_ABI),
        "models": {},
    }
    aggregate: list[dict[str, object]] = []
    provenance = current_provenance
    if args.resume:
        aggregate_path = output / "dynamic_counts.csv"
        provenance_path = output / "provenance.json"
        if not aggregate_path.is_file() or not provenance_path.is_file():
            raise ValueError("resumed context sweep lacks dynamic_counts.csv or provenance.json")
        with aggregate_path.open(newline="", encoding="utf-8") as stream:
            aggregate = list(csv.DictReader(stream))
        provenance = load_json(provenance_path)
        for key, value in current_provenance.items():
            if key == "models":
                continue
            existing = provenance.get(key)
            if existing is not None and existing != value:
                raise ValueError(f"resumed context sweep provenance mismatch in {key}")
            provenance[key] = value
        (output / "complete").unlink(missing_ok=True)
    existing_cases = {
        (str(row["model"]), int(row["effective_kv"])) for row in aggregate
    }
    requested_cases = {(model, kv) for model in model_ids for kv in kv_lengths}
    overlap = sorted(existing_cases & requested_cases)
    if overlap:
        raise ValueError(f"context sweep already contains requested cases: {overlap}")

    for model_id in model_ids:
        spec = model_specs[model_id]
        model = Path(str(spec["model"]))
        if not model.is_file():
            raise FileNotFoundError(model)
        model_sha256 = sha256(model)
        expected_sha256 = str(spec.get("expected_sha256", ""))
        if expected_sha256 and model_sha256 != expected_sha256:
            raise ValueError(f"{model_id} model SHA-256 mismatch")
        reference_path = None
        reference = None
        if spec.get("reference_summary"):
            reference_path = ROOT / str(spec["reference_summary"])
            if not reference_path.is_file():
                raise FileNotFoundError(reference_path)
            reference = load_json(reference_path)
        provenance["models"][model_id] = {
            "name": spec["name"],
            "path": str(model.resolve()),
            "sha256": model_sha256,
            "source": spec.get("source"),
            "reference_summary": (
                str(reference_path.relative_to(ROOT)) if reference_path else None
            ),
            "reference_summary_sha256": sha256(reference_path) if reference_path else None,
        }
        for effective_kv in kv_lengths:
            case_dir = output / model_id / f"kv{effective_kv}"
            case_dir.mkdir(parents=True)
            prompt = exact_prompt(args.tokenizer, model, effective_kv - 1)
            prompt_path = case_dir / "prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            context_size = next_power_of_two(effective_kv + 1)
            command = [
                str(args.binary), "-m", str(model), "-f", str(prompt_path),
                "-n", "2", "-c", str(context_size),
                "-t", str(args.threads), "-tb", str(args.threads),
                "-no-cnv", "--load-mode", "mmap", "--no-warmup",
                "--no-display-prompt", "--seed", "1", "--temp", "0",
            ]
            log_path = case_dir / "host.log"
            environment = os.environ.copy()
            environment["GGML_RISCV_MODEL_TRACE"] = "1"
            with log_path.open("w", encoding="utf-8") as stream:
                result = subprocess.run(
                    command,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    timeout=args.timeout,
                    check=False,
                )
            if result.returncode != 0:
                raise RuntimeError(f"host llama failed for {model_id}/KV{effective_kv}: {result.returncode}")
            observed_prompt_tokens = prompt_eval_tokens(log_path)
            if observed_prompt_tokens != effective_kv - 1:
                raise ValueError(
                    f"{model_id}/KV{effective_kv} prompt mismatch: {observed_prompt_tokens}"
                )
            graphs = parse_graphs(log_path)
            summary = summarize_graphs(graphs, effective_kv, abi)
            decode_expectation = spec.get("decode_expectation")
            if reference is not None:
                if decode_expectation is None:
                    raise ValueError(f"{model_id} reference requires decode_expectation")
                validate_reference(summary, reference, decode_expectation)
            elif decode_expectation is not None:
                validate_decode_expectation(summary, decode_expectation)
            else:
                decode = summary["decode"]
                if int(decode["qbs_candidate_compute_nodes"]) <= 0:
                    raise ValueError(f"{model_id} Decode graph has no QBS candidates")
            if spec.get("akv_disposition"):
                validate_akv_disposition(summary, str(spec["akv_disposition"]))
            summary["model_id"] = model_id
            summary["model_name"] = spec["name"]
            summary["prompt_tokens"] = observed_prompt_tokens
            summary["context_size"] = context_size
            summary["prompt_sha256"] = sha256(prompt_path)
            summary["host_log_sha256"] = sha256(log_path)
            (case_dir / "summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
            decode = summary["decode"]
            aggregate.append({
                "model": model_id,
                "effective_kv": effective_kv,
                "prompt_tokens": observed_prompt_tokens,
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
                "artifact": str((case_dir / "summary.json").relative_to(ROOT)),
            })
            write_csv(output / "dynamic_counts.csv", aggregate)
            (output / "provenance.json").write_text(
                json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
            )
            print(f"PASS {model_id} KV={effective_kv}")

    write_csv(output / "dynamic_counts.csv", aggregate)
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
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
