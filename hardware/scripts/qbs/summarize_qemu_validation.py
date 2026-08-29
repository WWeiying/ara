#!/usr/bin/env python3
"""Close a native-QEMU QBS validation run into auditable paper artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


PROFILE_RUNS = {
    "Q2_K": (
        "q2_k",
        Path("/home/wangwy/llama/models/qbs-format-closure/"
             "Qwen2.5-0.5B-Instruct-Q2_K-pure.gguf"),
    ),
    "Q3_K": (
        "q3_k",
        Path("/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q3_k_m.gguf"),
    ),
    "Q4_K": (
        "q4_k",
        Path("/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"),
    ),
    "Q5_K": (
        "q5_k",
        Path("/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q5_k_m.gguf"),
    ),
    "Q6_K": (
        "q6_k",
        Path("/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q6_k.gguf"),
    ),
    "Q8_0": (
        "q8_0",
        Path("/home/wangwy/llama/models/Qwen2.5-0.5B-Instruct-Q8_0.gguf"),
    ),
    "IQ4_NL": (
        "iq4_nl",
        Path("/home/wangwy/llama/models/qbs-format-closure/"
             "Qwen2.5-0.5B-Instruct-IQ4_NL-pure.gguf"),
    ),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256_manifest(path: Path) -> int:
    entries = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        digest, filename = line.split(maxsplit=1)
        filename = filename.lstrip("* ")
        artifact = Path(filename)
        require(artifact.is_file(), f"manifest artifact is missing: {artifact}")
        require(sha256(artifact) == digest,
                f"manifest hash no longer matches: {artifact}")
        entries += 1
    require(entries > 0, f"empty SHA-256 manifest: {path}")
    return entries


def parse_key_values(line: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in line.split():
        if "=" in token:
            key, value = token.split("=", 1)
            result[key] = value
    return result


def last_marker(text: str, marker: str) -> dict[str, str]:
    matches = [line for line in text.splitlines() if marker in line]
    require(bool(matches), f"missing marker: {marker}")
    return parse_key_values(matches[-1].split(marker, 1)[1])


def finite_number(values: dict[str, str], key: str) -> float:
    require(key in values, f"missing metric field: {key}")
    value = float(values[key])
    require(math.isfinite(value), f"non-finite metric field: {key}={value}")
    return value


def read_executable_hashes(path: Path) -> tuple[str, Path, str, Path]:
    qemu_hash = ""
    qemu_path: Path | None = None
    guest_hash = ""
    guest_path: Path | None = None
    for line in path.read_text().splitlines():
        digest, filename = line.split(maxsplit=1)
        filename = filename.lstrip("* ")
        if filename.endswith("qemu-system-riscv64"):
            qemu_hash = digest
            qemu_path = Path(filename)
        elif filename.endswith("llama-simple"):
            guest_hash = digest
            guest_path = Path(filename)
    require(bool(qemu_hash), "executables.sha256 has no QEMU hash")
    require(bool(guest_hash), "executables.sha256 has no llama-simple hash")
    require(qemu_path is not None and qemu_path.is_file(), "recorded QEMU is missing")
    require(guest_path is not None and guest_path.is_file(), "recorded guest is missing")
    require(sha256(qemu_path) == qemu_hash, "recorded QEMU hash no longer matches")
    require(sha256(guest_path) == guest_hash, "recorded guest hash no longer matches")
    return qemu_hash, qemu_path, guest_hash, guest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--expected-git-head")
    parser.add_argument(
        "--skip-model-hash",
        action="store_true",
        help="Skip hashing the source GGUF files (not suitable for final closure).",
    )
    args = parser.parse_args()

    root = args.run_root.resolve()
    require((root / "DONE").is_file(), f"run is incomplete: {root / 'DONE'}")
    require((root / "full_model.status").read_text().strip() == "PASS",
            "full-model validation did not pass")

    git_head = (root / "ara_git_head").read_text().strip()
    if args.expected_git_head:
        require(git_head == args.expected_git_head,
                f"source revision mismatch: {git_head}")
    ara_diff_hash = sha256(root / "ara_git_diff.patch")
    llama_head = (root / "llama_git_head").read_text().strip()
    llama_diff_hash = sha256(root / "llama_git_diff.patch")
    qbs_sources_manifest = root / "qbs_sources.sha256"
    qbs_sources_manifest_entries = verify_sha256_manifest(qbs_sources_manifest)
    qbs_sources_manifest_hash = sha256(qbs_sources_manifest)
    qemu_hash, qemu_path, guest_hash, guest_path = read_executable_hashes(
        root / "executables.sha256"
    )

    full_log_path = root / "full_model" / "qwen-native-check.log"
    full_log = full_log_path.read_text(errors="replace")
    require("QBS_TOKEN_RUN_EXIT=QBS_NATIVE:0" in full_log,
            "full-model native QBS execution failed")
    require("QBS_TOKEN_OUTPUT_EQUAL=1" in full_log,
            "full-model RVV/QBS token output differs")
    full_records = last_marker(full_log, "QBS_LOGITS_RECORDS")
    require(full_records.get("status") == "OK", "full-model logits status is not OK")
    full_metrics = last_marker(full_log, "QBS_MODEL_METRICS")
    require(int(full_metrics["records"]) >= 1, "full-model run has no logit records")
    full_exec: dict[str, dict[str, int]] = {}
    full_coverage: dict[str, dict[str, int]] = {}
    for profile in ("Q4_K", "Q6_K"):
        coverage_metrics = last_marker(
            full_log, f"GGML_RISCV_QBS_COVERAGE type={profile}"
        )
        coverage = {
            key: int(coverage_metrics.get(key, "-1"))
            for key in (
                "candidate_tensors",
                "selected_tensors",
                "segmented_tensors",
                "candidate_elements",
                "selected_elements",
                "fallback_runtime",
                "fallback_format_filter",
                "fallback_capability",
                "fallback_dimensions",
                "fallback_shape",
                "fallback_layout",
                "fallback_profile",
                "fallback_dispatch",
            )
        }
        require(coverage["candidate_tensors"] > 0,
                f"full-model run has no {profile} candidate tensors")
        require(coverage["selected_tensors"] == coverage["candidate_tensors"],
                f"full-model run does not select every {profile} candidate tensor")
        require(coverage["selected_elements"] == coverage["candidate_elements"],
                f"full-model run does not select every {profile} candidate element")
        require(
            all(value == 0 for key, value in coverage.items()
                if key.startswith("fallback_")),
            f"full-model run has an unexpected {profile} fallback: {coverage}",
        )
        full_coverage[profile] = coverage

        exec_metrics = last_marker(full_log, f"GGML_RISCV_QBS_EXEC type={profile}")
        parsed = {
            key: int(exec_metrics.get(key, "-1"))
            for key in (
                "gemv_calls",
                "gemm_calls",
                "native_qbexec",
                "emulated_commands",
                "command_dot_elements",
            )
        }
        require(parsed["gemv_calls"] > 0,
                f"full-model run has no {profile} GEMV calls")
        require(parsed["gemm_calls"] > 0,
                f"full-model run has no {profile} GEMM calls")
        require(parsed["native_qbexec"] > 0,
                f"full-model run has no native {profile} qbexec")
        require(parsed["emulated_commands"] == 0,
                f"full-model run emulated {profile} commands")
        full_exec[profile] = parsed

    full_initrd = root / "full_model" / "qbs-token-initramfs.cpio"
    require(full_initrd.is_file(), "full-model initramfs is missing")

    rows: list[dict[str, object]] = []
    model_hashes: dict[str, str] = {}
    for profile, (directory, model_path) in PROFILE_RUNS.items():
        work = root / "quality" / directory
        require((work / "status").read_text().strip() == "PASS",
                f"quality run failed: {profile}")
        require((work / "exit_code").read_text().strip() == "0",
                f"quality run returned nonzero: {profile}")
        log_path = work / "qwen-precision.log"
        text = log_path.read_text(errors="replace")
        require("QBS_TOKEN_RUN_EXIT=QBS_NATIVE:0" in text,
                f"native QBS execution failed: {profile}")
        records = last_marker(text, "QBS_LOGITS_RECORDS")
        require(records.get("status") == "OK", f"bad logits status: {profile}")
        metrics = last_marker(text, "QBS_MODEL_METRICS")
        require(int(metrics["records"]) == 68, f"wrong record count: {profile}")
        require(int(metrics["target_records"]) == 68,
                f"wrong teacher-forced target count: {profile}")

        exec_metrics = last_marker(text, f"GGML_RISCV_QBS_EXEC type={profile}")
        require(int(exec_metrics.get("native_qbexec", "0")) > 0,
                f"no native qbexec commands: {profile}")
        require(int(exec_metrics.get("emulated_commands", "-1")) == 0,
                f"emulated QBS command observed: {profile}")

        values = {
            key: finite_number(metrics, key)
            for key in (
                "rvv_ppl",
                "qbs_ppl",
                "ppl_ratio",
                "mean_kl",
                "top1_agreement",
                "top5_overlap",
                "mean_rmse",
                "max_abs",
            )
        }
        require(0.0 <= values["top1_agreement"] <= 1.0,
                f"invalid Top-1 agreement: {profile}")
        require(0.0 <= values["top5_overlap"] <= 1.0,
                f"invalid Top-5 overlap: {profile}")
        require(model_path.is_file(), f"missing source model: {model_path}")
        model_hash = "SKIPPED" if args.skip_model_hash else sha256(model_path)
        model_hashes[profile] = model_hash
        initrd_path = work / "qbs-token-initramfs.cpio"
        require(initrd_path.is_file(), f"missing quality initramfs: {profile}")

        rows.append({
            "profile": profile,
            "steps": 68,
            **values,
            "native_qbexec": int(exec_metrics["native_qbexec"]),
            "command_dot_elements": int(exec_metrics["command_dot_elements"]),
            "model_path": str(model_path),
            "model_sha256": model_hash,
            "initramfs_sha256": sha256(initrd_path),
            "log_sha256": sha256(log_path),
            "ara_git_head": git_head,
            "ara_diff_sha256": ara_diff_hash,
            "llama_git_head": llama_head,
            "llama_diff_sha256": llama_diff_hash,
            "qemu_sha256": qemu_hash,
            "guest_sha256": guest_hash,
        })

    fieldnames = list(rows[0])
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "run_root": str(root),
        "ara_git_head": git_head,
        "ara_diff_sha256": ara_diff_hash,
        "llama_git_head": llama_head,
        "llama_diff_sha256": llama_diff_hash,
        "qbs_sources_manifest_sha256": qbs_sources_manifest_hash,
        "qbs_sources_manifest_entries": qbs_sources_manifest_entries,
        "runner_sha256": sha256(root / "run_validation.sh"),
        "qemu_sha256": qemu_hash,
        "qemu_path": str(qemu_path),
        "guest_sha256": guest_hash,
        "guest_path": str(guest_path),
        "full_model_log_sha256": sha256(full_log_path),
        "full_model_initramfs_sha256": sha256(full_initrd),
        "full_model_records": int(full_metrics["records"]),
        "full_model_output_equal": True,
        "full_model_coverage": full_coverage,
        "full_model_execution": full_exec,
        "profile_model_sha256": model_hashes,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {args.output_csv} and {args.output_json}")


if __name__ == "__main__":
    main()
