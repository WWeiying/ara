#!/usr/bin/env python3
"""Build, inspect, and run independently selectable Q4_K_M leaf cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m")
DEFAULT_RUNNER = Path(
    "/home/wangwy/llama/platforms/cva6-qemu/build/llama-q4km-host/bin/llama-q4km-replay"
)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def relative(source: Path, destination_dir: Path) -> str:
    return os.path.relpath(source, destination_dir)


def tensor_meta(root: Path, phase: str, name: str) -> Path:
    return root / phase / "block" / f"{name}-0.json"


def validate_tensors(root: Path) -> list[dict]:
    tensors = []
    for meta_path in sorted(root.rglob("*.json")):
        meta = load_json(meta_path)
        if not {"type", "shape", "nbytes"}.issubset(meta):
            continue
        data_path = meta_path.with_suffix(".bin")
        if not data_path.is_file():
            raise RuntimeError(f"missing tensor data: {data_path}")
        actual = data_path.stat().st_size
        expected = int(meta["nbytes"])
        if actual != expected:
            raise RuntimeError(f"size mismatch: {data_path}: {actual} != {expected}")
        tensors.append(
            {
                "meta": str(meta_path.relative_to(root)),
                "data": str(data_path.relative_to(root)),
                "nbytes": actual,
                "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
            }
        )
    return tensors


def write_leaf(root: Path, level: str, phase: str, name: str, spec: dict) -> Path:
    case_dir = root / "replay" / "cases" / level / phase / name
    case_dir.mkdir(parents=True, exist_ok=True)
    rewritten = {"kind": spec["kind"]}
    for key, value in spec.items():
        if key == "kind":
            continue
        rewritten[key] = relative(value, case_dir) if isinstance(value, Path) else value
    (case_dir / "case.json").write_text(json.dumps(rewritten, indent=2) + "\n", encoding="utf-8")
    return case_dir


def build_manifest(root: Path, strict: bool) -> dict:
    if not (root / "model.json").is_file():
        raise RuntimeError(f"capture is incomplete: missing {root / 'model.json'}")

    replay = root / "replay"
    if replay.exists():
        shutil.rmtree(replay)
    (replay / "cases").mkdir(parents=True)

    cases: list[dict] = []
    micro_ids: list[str] = []
    observed_micro = set()
    for case_dir in sorted((root / "micro" / "cases").glob("*")):
        if case_dir.is_dir() and (case_dir / "microkernel.json").is_file():
            case_id = f"micro/{case_dir.name}"
            observed_micro.add(case_dir.name)
            micro_ids.append(case_id)
            cases.append(
                {
                    "id": case_id,
                    "level": "micro",
                    "kind": load_json(case_dir / "microkernel.json")["case_kind"],
                    "path": str(case_dir.relative_to(root)),
                }
            )
    expected_micro = {
        "q4_k_x_q8_k_dot_n1536_nrc1",
        "q4_k_x_q8_k_dot_n8960_nrc1",
        "q6_k_x_q8_k_dot_n1536_nrc1",
        "q6_k_x_q8_k_dot_n8960_nrc1",
        "quantize_f32_to_q8_k_k1536",
        "quantize_f32_to_q8_k_k8960",
    }
    if strict and observed_micro != expected_micro:
        raise RuntimeError(
            f"micro coverage mismatch: missing={sorted(expected_micro-observed_micro)}, "
            f"extra={sorted(observed_micro-expected_micro)}"
        )
    cases.append(
        {
            "id": "micro/all",
            "level": "suite",
            "kind": "suite",
            "children": micro_ids,
        }
    )

    expected_ops = {
        "blk_0_attn_q_weight",
        "blk_0_attn_k_weight",
        "blk_0_attn_v_weight",
        "blk_0_attn_output_weight",
        "blk_0_ffn_gate_weight",
        "blk_0_ffn_up_weight",
        "blk_0_ffn_down_weight",
    }
    linear_ids: dict[str, dict[str, str]] = {}
    for phase in ("prefill", "decode"):
        observed = set()
        linear_ids[phase] = {}
        for case_dir in sorted((root / phase / "operators").glob("*")):
            if case_dir.is_dir() and (case_dir / "operator.json").is_file():
                observed.add(case_dir.name)
                case_id = f"operator/{phase}/{case_dir.name}"
                linear_ids[phase][case_dir.name] = case_id
                cases.append(
                    {
                        "id": case_id,
                        "level": "operator",
                        "kind": "GGML_OP_MUL_MAT",
                        "path": str(case_dir.relative_to(root)),
                        "weight_type": load_json(case_dir / "operator.json")["weight_type"],
                    }
                )
        if strict and observed != expected_ops:
            raise RuntimeError(
                f"{phase} operator coverage mismatch: missing={sorted(expected_ops-observed)}, "
                f"extra={sorted(observed-expected_ops)}"
            )

    epsilon = 1.0e-6
    model_meta = load_json(root / "model.json").get("metadata", {})
    if "qwen2.attention.layer_norm_rms_epsilon" in model_meta:
        epsilon = float(model_meta["qwen2.attention.layer_norm_rms_epsilon"])

    for phase in ("prefill", "decode"):
        block = root / phase / "block"
        leaves = {
            "attention_norm": {
                "kind": "rms_norm",
                "input_a": tensor_meta(root, phase, "l_in"),
                "weight": block / "attn_norm-0_weight.json",
                "golden": tensor_meta(root, phase, "attn_norm"),
                "epsilon": epsilon,
            },
            "rope_q": {
                "kind": "rope",
                "input_a": tensor_meta(root, phase, "q4km_Qraw"),
                "position": tensor_meta(root, phase, "q4km_position"),
                "golden": tensor_meta(root, phase, "q4km_Qrope"),
                "n_dims": 128,
                "mode": 2,
                "n_ctx_orig": 32768,
                "freq_base": 1000000.0,
                "freq_scale": 1.0,
                "ext_factor": 0.0,
                "attn_factor": 1.0,
                "beta_fast": 32.0,
                "beta_slow": 1.0,
            },
            "rope_k": {
                "kind": "rope",
                "input_a": tensor_meta(root, phase, "q4km_Kraw"),
                "position": tensor_meta(root, phase, "q4km_position"),
                "golden": tensor_meta(root, phase, "q4km_Krope"),
                "n_dims": 128,
                "mode": 2,
                "n_ctx_orig": 32768,
                "freq_base": 1000000.0,
                "freq_scale": 1.0,
                "ext_factor": 0.0,
                "attn_factor": 1.0,
                "beta_fast": 32.0,
                "beta_slow": 1.0,
            },
            "attention_core": {
                "kind": "attention_core",
                "input_a": tensor_meta(root, phase, "attn_q_input"),
                "key": tensor_meta(root, phase, "attn_k_input"),
                "value": tensor_meta(root, phase, "attn_v_input"),
                "mask": tensor_meta(root, phase, "attn_mask_input"),
                "golden": tensor_meta(root, phase, "kqv_out"),
                "scale": 1.0 / (128.0**0.5),
                "max_bias": 0.0,
                "v_transposed": False,
                "atol": 4.0e-3,
                "rtol": 2.0e-3,
            },
            "attention_residual": {
                "kind": "add",
                "input_a": tensor_meta(root, phase, "attn_out"),
                "input_b": tensor_meta(root, phase, "l_in"),
                "golden": tensor_meta(root, phase, "ffn_inp"),
            },
            "ffn_norm": {
                "kind": "rms_norm",
                "input_a": tensor_meta(root, phase, "ffn_inp"),
                "weight": block / "ffn_norm-0_weight.json",
                "golden": tensor_meta(root, phase, "ffn_norm"),
                "epsilon": epsilon,
            },
            "ffn_activation": {
                "kind": "silu_mul",
                "input_a": tensor_meta(root, phase, "ffn_gate"),
                "input_b": tensor_meta(root, phase, "ffn_up"),
                "golden": tensor_meta(root, phase, "ffn_swiglu"),
            },
            "ffn_residual": {
                "kind": "add",
                "input_a": tensor_meta(root, phase, "ffn_out"),
                "input_b": tensor_meta(root, phase, "ffn_inp"),
                "golden": tensor_meta(root, phase, "q4km_l_out"),
            },
        }
        leaf_ids: dict[str, str] = {}
        for name, spec in leaves.items():
            missing = [str(value) for value in spec.values() if isinstance(value, Path) and not value.is_file()]
            if missing:
                if strict:
                    raise RuntimeError(f"block/{phase}/{name} missing files: {missing}")
                continue
            case_dir = write_leaf(root, "operator", phase, name, spec)
            case_id = f"operator/{phase}/{name}"
            leaf_ids[name] = case_id
            cases.append(
                {
                    "id": case_id,
                    "level": "operator-leaf",
                    "kind": spec["kind"],
                    "path": str(case_dir.relative_to(root)),
                }
            )

        def optional_case(mapping: dict[str, str], name: str) -> str | None:
            if name not in mapping and strict:
                raise RuntimeError(f"missing required {phase} case: {name}")
            return mapping.get(name)

        # This is the execution order of one captured layer-0 Transformer block.
        # Every child remains golden-isolated and can also be run by its own ID.
        attention_children = [
            case_id
            for case_id in [
                optional_case(leaf_ids, "attention_norm"),
                optional_case(linear_ids[phase], "blk_0_attn_q_weight"),
                optional_case(linear_ids[phase], "blk_0_attn_k_weight"),
                optional_case(linear_ids[phase], "blk_0_attn_v_weight"),
                optional_case(leaf_ids, "rope_q"),
                optional_case(leaf_ids, "rope_k"),
                optional_case(leaf_ids, "attention_core"),
                optional_case(linear_ids[phase], "blk_0_attn_output_weight"),
                optional_case(leaf_ids, "attention_residual"),
            ]
            if case_id is not None
        ]
        ffn_children = [
            case_id
            for case_id in [
                optional_case(leaf_ids, "ffn_norm"),
                optional_case(linear_ids[phase], "blk_0_ffn_gate_weight"),
                optional_case(linear_ids[phase], "blk_0_ffn_up_weight"),
                optional_case(leaf_ids, "ffn_activation"),
                optional_case(linear_ids[phase], "blk_0_ffn_down_weight"),
                optional_case(leaf_ids, "ffn_residual"),
            ]
            if case_id is not None
        ]
        phase_children = attention_children + ffn_children
        cases.append(
            {
                "id": f"operator/{phase}/all",
                "level": "suite",
                "kind": "suite",
                "children": phase_children,
            }
        )
        cases.append(
            {
                "id": f"block/{phase}/attention",
                "level": "suite",
                "kind": "suite",
                "children": attention_children,
                "execution_model": "ordered golden-isolated operator replay",
            }
        )
        cases.append(
            {
                "id": f"block/{phase}/ffn",
                "level": "suite",
                "kind": "suite",
                "children": ffn_children,
                "execution_model": "ordered golden-isolated operator replay",
            }
        )
        cases.append(
            {
                "id": f"block/{phase}/all",
                "level": "suite",
                "kind": "suite",
                "children": [f"block/{phase}/attention", f"block/{phase}/ffn"],
                "execution_model": "ordered golden-isolated operator replay",
            }
        )

    cases.extend(
        [
            {
                "id": "operator/all",
                "level": "suite",
                "kind": "suite",
                "children": ["operator/prefill/all", "operator/decode/all"],
            },
            {
                "id": "block/all",
                "level": "suite",
                "kind": "suite",
                "children": ["block/prefill/all", "block/decode/all"],
            },
            {
                "id": "all",
                "level": "suite",
                "kind": "suite",
                "children": ["micro/all", "block/all"],
            },
        ]
    )

    case_ids = [case["id"] for case in cases]
    if len(case_ids) != len(set(case_ids)):
        duplicates = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
        raise RuntimeError(f"duplicate case IDs: {duplicates}")
    known_ids = set(case_ids)
    for case in cases:
        missing_children = [child for child in case.get("children", []) if child not in known_ids]
        if missing_children:
            raise RuntimeError(f"{case['id']} references missing children: {missing_children}")

    model = load_json(root / "model.json")
    prefill_q = load_json(tensor_meta(root, "prefill", "attn_q_input"))
    decode_q = load_json(tensor_meta(root, "decode", "attn_q_input"))
    prefill_k = load_json(tensor_meta(root, "prefill", "attn_k_input"))
    manifest = {
        "schema_version": 1,
        "model": "Qwen2.5-1.5B-Instruct-Q4_K_M",
        "source": "real RV64GCV QEMU inference",
        "provenance": {
            key: model[key]
            for key in (
                "llama_commit", "compiler", "build_target", "isa",
                "vlen_bits", "threads", "capture_layer",
            )
            if key in model
        },
        "capture_shape": {
            "prefill_tokens": int(prefill_q["shape"][1]),
            "decode_tokens": int(decode_q["shape"][1]),
            "kv_capacity": int(prefill_k["shape"][1]),
            "hidden_size": int(model["n_embd"]),
            "layers_captured": [int(model.get("capture_layer", 0))],
        },
        "cases": cases,
        "tensor_integrity": validate_tensors(root),
    }
    (replay / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_manifest(root: Path) -> dict:
    path = root / "replay" / "manifest.json"
    if not path.is_file():
        raise RuntimeError(f"missing {path}; run 'cases.py prepare' first")
    return load_json(path)


def by_id(manifest: dict) -> dict[str, dict]:
    return {case["id"]: case for case in manifest["cases"]}


def run_case(root: Path, runner: Path, case_id: str, manifest: dict) -> int:
    cases = by_id(manifest)
    if case_id not in cases:
        raise RuntimeError(f"unknown case {case_id}")
    case = cases[case_id]
    if case["kind"] == "suite":
        status = 0
        for child in case["children"]:
            print(f"== {child} ==", flush=True)
            status |= run_case(root, runner, child, manifest)
        return status
    level = "block-leaf" if case["level"] == "operator-leaf" else case["level"]
    return subprocess.run([str(runner), level, str(root / case["path"])], check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--runner", type=Path, default=DEFAULT_RUNNER)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--strict", action="store_true")
    sub.add_parser("list")
    run = sub.add_parser("run")
    run.add_argument("case_id")
    resolve = sub.add_parser("resolve")
    resolve.add_argument("case_id")
    resolve_all = sub.add_parser("resolve-all")
    resolve_all.add_argument("case_id")
    sub.add_parser("verify-data")
    args = parser.parse_args()

    if args.command == "prepare":
        manifest = build_manifest(args.root, args.strict)
        print(f"wrote {args.root / 'replay/manifest.json'} ({len(manifest['cases'])} cases)")
        return 0
    manifest = load_manifest(args.root)
    if args.command == "list":
        for case in manifest["cases"]:
            print(f"{case['id']:<58} {case['kind']}")
        return 0
    if args.command == "verify-data":
        tensors = validate_tensors(args.root)
        print(f"PASS: {len(tensors)} tensors have matching metadata, size, and SHA-256")
        return 0
    if args.command == "resolve":
        cases = by_id(manifest)
        if args.case_id not in cases:
            raise RuntimeError(f"unknown case {args.case_id}")
        case = cases[args.case_id]
        if case["kind"] == "suite":
            raise RuntimeError("QEMU resolve accepts a leaf case, not a suite")
        level = "block-leaf" if case["level"] == "operator-leaf" else case["level"]
        print(f"{level}\t{case['path']}")
        return 0
    if args.command == "resolve-all":
        cases = by_id(manifest)
        if args.case_id not in cases:
            raise RuntimeError(f"unknown case {args.case_id}")

        def emit(case_id: str) -> None:
            case = cases[case_id]
            if case["kind"] == "suite":
                for child in case["children"]:
                    emit(child)
                return
            level = "block-leaf" if case["level"] == "operator-leaf" else case["level"]
            print(f"{case_id}\t{level}\t{case['path']}")

        emit(args.case_id)
        return 0
    if not args.runner.is_file():
        raise RuntimeError(f"missing replay runner: {args.runner}")
    return run_case(args.root, args.runner, args.case_id, manifest)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
