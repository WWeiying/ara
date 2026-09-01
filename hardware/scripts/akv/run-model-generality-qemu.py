#!/usr/bin/env python3

"""Run the manifest-defined RVV/QBS/AKV model generality checks."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from context_sweep import load_json, sha256


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = Path(__file__).with_name("model-generality-manifest.json")
CREATE_DISK = Path(__file__).with_name("create-model-disk.sh")
RUN_QEMU = Path(__file__).with_name("run-qemu-model-check.sh")
MODEL_SUMMARIZER = Path(__file__).with_name("summarize-model-closure.py")
QBS_FALLBACK_FIELDS = {
    "fallback_runtime", "fallback_format_filter", "fallback_capability",
    "fallback_dimensions", "fallback_shape", "fallback_layout",
    "fallback_profile", "fallback_dispatch",
}
AKV_FALLBACK_FIELDS = {
    "fallback_runtime", "fallback_capability", "fallback_threading",
    "fallback_feature", "fallback_shape", "fallback_layout", "fallback_mask",
}
RESULT_FIELDS = (
    "model", "architecture", "mode", "akv_disposition", "qemu_memory",
    "status", "return_code", "qbs_profiles", "qbs_operations", "qbs_nodes",
    "qbs_gemv_calls", "qbs_gemm_calls", "qbs_dot_elements",
    "qbs_command_dot_elements", "qbs_native_commands", "qbs_emulated_commands",
    "qbs_top1_equal", "qbs_token_output_equal", "qbs_logits_max_abs", "akv_candidate_ops",
    "akv_executed_ops", "akv_fallback_shape", "akv_top1_equal",
    "akv_token_output_equal", "akv_logits_max_abs", "llama_revision",
    "llama_binary_sha256", "qemu_binary_sha256", "qemu_cpu", "model_prompt",
    "model_tokens", "qbs_activation_accounting", "qbs_activation_unresolved_nodes",
    "qbs_abi_sha256", "qbs_architecture_version", "akv_logits_tolerance",
    "artifact", "dynamic_summary",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def selection(raw: str, models: dict[str, dict[str, object]]) -> list[str]:
    if raw == "all":
        return list(models)
    selected = raw.split(",")
    unknown = sorted(set(selected) - set(models))
    if unknown:
        raise ValueError(f"unknown models: {', '.join(unknown)}")
    return selected


def read_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key:
            raise ValueError(f"invalid key/value manifest line in {path}: {line}")
        values[key] = value
    return values


def ensure_model_disk(spec: dict[str, object]) -> tuple[Path, str, str]:
    model = Path(str(spec["model"]))
    expected_model_sha = str(spec["expected_sha256"])
    observed_model_sha = sha256(model)
    if observed_model_sha != expected_model_sha:
        raise ValueError(f"{spec['id']} model SHA-256 mismatch")

    qemu = spec["qemu"]
    disk = Path(str(qemu["disk"]))
    guest_path = str(qemu["guest_path"])
    expected_disk_sha = str(qemu.get("disk_sha256", ""))
    disk_manifest = Path(f"{disk}.manifest")
    rebuild = not disk.is_file()

    if not rebuild and expected_disk_sha:
        if sha256(disk) != expected_disk_sha:
            raise ValueError(f"{spec['id']} prebuilt model disk SHA-256 mismatch")
    elif not rebuild:
        if not disk_manifest.is_file():
            rebuild = True
        else:
            values = read_key_values(disk_manifest)
            rebuild = (
                values.get("MODEL_SOURCE_SHA256") != expected_model_sha
                or values.get("MODEL_GUEST_PATH") != guest_path
            )

    if rebuild:
        disk.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [str(CREATE_DISK), str(model), str(disk), Path(guest_path).name],
            cwd=ROOT,
            check=True,
        )
        values = read_key_values(disk_manifest)
        if (
            values.get("MODEL_SOURCE_SHA256") != expected_model_sha
            or values.get("MODEL_GUEST_PATH") != guest_path
        ):
            raise ValueError(f"{spec['id']} generated model disk failed provenance checks")

    return disk, guest_path, observed_model_sha


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def artifact_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def fallback_total(coverage: dict[str, object], required: set[str]) -> int:
    missing = sorted(required - set(coverage))
    if missing:
        raise ValueError(f"coverage lacks fallback fields: {missing}")
    return sum(int(coverage[key]) for key in required)


def qemu_metrics(
    summary: dict[str, object], disposition: str
) -> dict[str, object]:
    provenance = summary.get("provenance", {})
    summary_tool = provenance.get("tool", {})
    expected_summary_tool_sha = sha256(MODEL_SUMMARIZER)
    if summary_tool.get("sha256") != expected_summary_tool_sha:
        raise ValueError(
            "QEMU summary was produced by a different model-closure summarizer"
        )
    run_manifest = provenance.get("run_manifest", {})
    required_provenance = (
        "LLAMA_REVISION", "LLAMA_BINARY_SHA256", "QEMU_BINARY_SHA256",
        "QEMU_CPU", "MODEL_PROMPT", "MODEL_TOKENS", "LOGITS_MAX_ABS_TOLERANCE",
    )
    missing_provenance = [key for key in required_provenance if not run_manifest.get(key)]
    if missing_provenance:
        raise ValueError(
            "QEMU run manifest lacks execution provenance: "
            + ", ".join(missing_provenance)
        )
    qbs_abi = provenance.get("qbs_abi", {})
    if not qbs_abi.get("sha256") or int(qbs_abi.get("architecture_version", 0)) <= 0:
        raise ValueError("QEMU summary lacks QBS ABI provenance")
    functional = summary["functional"]
    qbs = summary["qbs"]
    akv = summary["akv_v2"]
    qbs_rvv = functional["qbs_rvv"]
    akv_logits_max_abs = float(functional["logits_max_abs"])
    akv_logits_tolerance = float(run_manifest["LOGITS_MAX_ABS_TOLERANCE"])
    if akv_logits_tolerance < 0:
        raise ValueError("QEMU AKV logits tolerance is negative")
    if (
        int(functional["guest_exit"]) != 0
        or functional["output_equal"] is not True
        or str(functional["logits_top1_equal"]) != "1"
        or akv_logits_max_abs > akv_logits_tolerance
        or str(qbs_rvv["QBS_RVV_LOGITS_TOP1_EQUAL"]) != "1"
        or str(qbs_rvv["QBS_RVV_TOKEN_OUTPUT_EQUAL"]) != "1"
    ):
        raise ValueError("QEMU functional or numerical closure failed")

    native_commands = 0
    emulated_commands = 0
    gemv_calls = 0
    gemm_calls = 0
    dot_elements = 0
    command_dot_elements = 0
    operations = qbs.get("operations", {})
    if not operations:
        raise ValueError("QEMU summary lacks QBS operation accounting")
    profiles = sorted(qbs["coverage"])
    if not profiles or int(qbs["nodes"]) <= 0:
        raise ValueError("QEMU run contains no QBS model work")
    if sum(int(count) for count in operations.values()) != int(qbs["nodes"]):
        raise ValueError("QBS operation accounting does not equal model-node count")
    for profile in profiles:
        coverage = qbs["coverage"][profile]
        execution = qbs["execution"][profile]
        if (
            int(coverage["candidate_tensors"]) <= 0
            or int(coverage["candidate_tensors"]) != int(coverage["selected_tensors"])
            or int(coverage["candidate_elements"]) != int(coverage["selected_elements"])
            or fallback_total(coverage, QBS_FALLBACK_FIELDS) != 0
        ):
            raise ValueError(f"QBS coverage is incomplete for {profile}")
        if int(execution["dot_elements"]) != int(execution["command_dot_elements"]):
            raise ValueError(f"QBS command work differs from operator work for {profile}")
        gemv_calls += int(execution["gemv_calls"])
        gemm_calls += int(execution["gemm_calls"])
        dot_elements += int(execution["dot_elements"])
        command_dot_elements += int(execution["command_dot_elements"])
        native_commands += int(execution["native_qbexec"])
        emulated_commands += int(execution["emulated_commands"])
    if gemv_calls + gemm_calls <= 0 or dot_elements <= 0:
        raise ValueError("QBS selected model work but executed no matrix kernel")
    if dot_elements != command_dot_elements:
        raise ValueError("aggregate QBS command work differs from operator work")
    if native_commands <= 0 or emulated_commands != 0:
        raise ValueError("QBS did not execute exclusively through native commands")

    akv_coverage = akv["coverage"]
    candidates = int(akv_coverage["candidate_ops"])
    executed = int(akv_coverage["executed_ops"])
    fallback_shape = int(akv_coverage["fallback_shape"])
    accounted = executed + fallback_total(akv_coverage, AKV_FALLBACK_FIELDS)
    if candidates <= 0 or candidates != accounted:
        raise ValueError("AKV candidates are not completely accounted")
    if disposition == "execute":
        if executed <= 0:
            raise ValueError("AKV execute model has no executed operation")
    elif disposition == "fallback_shape":
        if executed != 0 or fallback_shape != candidates:
            raise ValueError("AKV fallback model did not fall back exclusively by shape")
    else:
        raise ValueError(f"unknown AKV disposition: {disposition}")

    activation_accounting = qbs.get("activation_accounting")
    if "MUL_MAT_ID" in operations:
        if not isinstance(activation_accounting, dict):
            raise ValueError("MUL_MAT_ID QEMU summary lacks activation-accounting status")
        unresolved_nodes = int(activation_accounting.get("unresolved_nodes", 0))
        if bool(activation_accounting.get("complete")):
            activation_status = "complete"
            if unresolved_nodes != 0:
                raise ValueError("complete activation accounting reports unresolved nodes")
        else:
            unresolved = activation_accounting.get("unresolved_operations", {})
            if (
                set(unresolved) != {"MUL_MAT_ID"}
                or int(unresolved["MUL_MAT_ID"]) != unresolved_nodes
                or unresolved_nodes <= 0
            ):
                raise ValueError("incomplete MUL_MAT_ID activation accounting is ambiguous")
            activation_status = "unavailable_legacy_source_shape"
    else:
        activation_status = "not_required_no_mul_mat_id"
        unresolved_nodes = 0
    return {
        "qbs_profiles": "/".join(profiles),
        "qbs_operations": "/".join(
            f"{operation}:{count}" for operation, count in sorted(operations.items())
        ),
        "qbs_nodes": int(qbs["nodes"]),
        "qbs_gemv_calls": gemv_calls,
        "qbs_gemm_calls": gemm_calls,
        "qbs_dot_elements": dot_elements,
        "qbs_command_dot_elements": command_dot_elements,
        "qbs_native_commands": native_commands,
        "qbs_emulated_commands": emulated_commands,
        "qbs_top1_equal": qbs_rvv["QBS_RVV_LOGITS_TOP1_EQUAL"],
        "qbs_token_output_equal": qbs_rvv["QBS_RVV_TOKEN_OUTPUT_EQUAL"],
        "qbs_logits_max_abs": qbs_rvv["QBS_RVV_LOGITS_MAX_ABS"],
        "akv_candidate_ops": candidates,
        "akv_executed_ops": executed,
        "akv_fallback_shape": fallback_shape,
        "akv_top1_equal": functional["logits_top1_equal"],
        "akv_token_output_equal": int(bool(functional["output_equal"])),
        "akv_logits_max_abs": functional["logits_max_abs"],
        "akv_logits_tolerance": akv_logits_tolerance,
        "llama_revision": str(run_manifest["LLAMA_REVISION"]),
        "llama_binary_sha256": str(run_manifest["LLAMA_BINARY_SHA256"]),
        "qemu_binary_sha256": str(run_manifest["QEMU_BINARY_SHA256"]),
        "qemu_cpu": str(run_manifest["QEMU_CPU"]),
        "model_prompt": str(run_manifest["MODEL_PROMPT"]),
        "model_tokens": str(run_manifest["MODEL_TOKENS"]),
        "qbs_activation_accounting": activation_status,
        "qbs_activation_unresolved_nodes": unresolved_nodes,
        "qbs_abi_sha256": str(qbs_abi["sha256"]),
        "qbs_architecture_version": int(qbs_abi["architecture_version"]),
    }


def empty_metrics() -> dict[str, object]:
    return {field: "" for field in RESULT_FIELDS[7:-2]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--models", default="all")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--reuse-existing-log",
        action="store_true",
        help="revalidate complete QEMU logs already present under --output without rerunning QEMU",
    )
    parser.add_argument("--tokens", type=int, default=2)
    parser.add_argument(
        "--prompt",
        default="Explain why low-bit vector inference benefits from packed arithmetic and data reuse.",
    )
    args = parser.parse_args()
    if args.tokens <= 0:
        raise ValueError("tokens must be positive")
    if args.prepare_only and args.reuse_existing_log:
        raise ValueError("--prepare-only and --reuse-existing-log are mutually exclusive")
    if args.reuse_existing_log and args.output is None:
        raise ValueError("--reuse-existing-log requires --output")

    manifest = load_json(args.manifest)
    if int(manifest.get("schema_version", 0)) != 1:
        raise ValueError("unsupported model-generality manifest")
    models = {str(spec["id"]): spec for spec in manifest["models"]}
    selected = selection(args.models, models)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = (args.output or ROOT / f"hardware/akv_jobs/qemu_model_generality_{stamp}").resolve()
    output.mkdir(parents=True, exist_ok=args.reuse_existing_log)

    provenance = {
        "schema_version": 1,
        "started_at": now(),
        "ara_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "manifest": str(args.manifest.resolve()),
        "manifest_sha256": sha256(args.manifest),
        "model_summary_tool": {
            "path": str(MODEL_SUMMARIZER.resolve()),
            "sha256": sha256(MODEL_SUMMARIZER),
        },
        "models": {},
    }
    rows: list[dict[str, object]] = []
    failed = False

    for model_id in selected:
        spec = models[model_id]
        case_dir = output / model_id
        case_dir.mkdir(exist_ok=args.reuse_existing_log)
        status = {
            "model": model_id,
            "name": spec["name"],
            "started_at": now(),
            "status": "PREPARING",
        }
        status_path = case_dir / "status.json"
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        try:
            disk, guest_path, model_sha = ensure_model_disk(spec)
            qemu = spec["qemu"]
            mode = "combined" if spec["akv_disposition"] == "execute" else "combined-fallback"
            provenance["models"][model_id] = {
                "name": spec["name"],
                "architecture": spec["architecture"],
                "model": str(Path(str(spec["model"])).resolve()),
                "model_sha256": model_sha,
                "model_disk": str(disk.resolve()),
                "model_disk_sha256": sha256(disk),
                "guest_path": guest_path,
                "qemu_memory": qemu["memory"],
                "mode": mode,
            }
            if args.prepare_only:
                status.update(status="PREPARED", finished_at=now())
                return_code = 0
                metrics = empty_metrics()
                dynamic_summary = ""
            else:
                environment = os.environ.copy()
                environment.update({
                    "AKV_MODEL_MODE": mode,
                    "AKV_MODEL_DISK": str(disk),
                    "AKV_MODEL_GUEST_PATH": guest_path,
                    "AKV_QEMU_MEMORY": str(qemu["memory"]),
                    "AKV_MODEL_TOKENS": str(args.tokens),
                    "AKV_MODEL_PROMPT": args.prompt,
                    "AKV_RUN_DIR": str(case_dir / "run"),
                })
                status.update(
                    status="CHECKING_EXISTING" if args.reuse_existing_log else "RUNNING",
                    mode=mode,
                    model_disk=str(disk),
                )
                status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
                command = [str(RUN_QEMU)]
                driver_log = case_dir / "driver.log"
                if args.reuse_existing_log:
                    qemu_log = case_dir / "run" / "qemu.log"
                    if not qemu_log.is_file():
                        raise FileNotFoundError(qemu_log)
                    command.extend(["--check-log", str(qemu_log)])
                    driver_log = case_dir / "recheck.log"
                with driver_log.open("w", encoding="utf-8") as stream:
                    result = subprocess.run(
                        command,
                        cwd=ROOT,
                        env=environment,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                return_code = result.returncode
                if return_code:
                    raise RuntimeError(f"QEMU model check exited {return_code}")
                summary_path = case_dir / "run" / "model_closure" / "dynamic_summary.json"
                if not summary_path.is_file():
                    raise FileNotFoundError(summary_path)
                metrics = qemu_metrics(load_json(summary_path), str(spec["akv_disposition"]))
                dynamic_summary = artifact_path(summary_path)
                status.update(
                    status="PASS",
                    finished_at=now(),
                    dynamic_summary=dynamic_summary,
                    metrics=metrics,
                )
            rows.append({
                "model": model_id,
                "architecture": spec["architecture"],
                "mode": mode,
                "akv_disposition": spec["akv_disposition"],
                "qemu_memory": qemu["memory"],
                "status": status["status"],
                "return_code": return_code,
                **metrics,
                "artifact": artifact_path(case_dir),
                "dynamic_summary": dynamic_summary,
            })
        except Exception as error:
            failed = True
            status.update(status="FAIL", finished_at=now(), error=str(error))
            rows.append({
                "model": model_id,
                "architecture": spec["architecture"],
                "mode": "",
                "akv_disposition": spec["akv_disposition"],
                "qemu_memory": spec["qemu"]["memory"],
                "status": "FAIL",
                "return_code": 1,
                **empty_metrics(),
                "artifact": artifact_path(case_dir),
                "dynamic_summary": "",
            })
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        write_rows(output / "results.csv", rows)

    provenance["finished_at"] = now()
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    write_rows(output / "results.csv", rows)
    if not failed:
        (output / "complete").write_text("PASS\n", encoding="ascii")
    print(output)
    return int(failed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
