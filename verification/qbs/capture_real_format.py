#!/usr/bin/env python3
"""Capture and audit one real-model decode MUL_MAT input for QBS closure."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


FORMATS = {
    "q2_K": (256, 84),
    "q4_0": (32, 18),
    "q5_0": (32, 22),
    "iq4_nl": (32, 18),
}
PROMPT = "Explain why quantized matrix multiplication benefits from data reuse."


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_tensor(directory: Path, role: str, kind: str, shape: list[int],
                 strides: list[int], size: int) -> dict[str, object]:
    metadata_path = directory / f"{role}.json"
    data_path = directory / f"{role}.bin"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if (metadata.get("role") != role or metadata.get("type") != kind or
            metadata.get("shape") != shape or metadata.get("strides") != strides or
            metadata.get("nbytes") != size or data_path.stat().st_size != size):
        raise ValueError(f"{role}: type, shape, stride, or byte count differs from format contract")
    return {
        "data": str(data_path), "data_sha256": sha256(data_path),
        "metadata": str(metadata_path), "metadata_sha256": sha256(metadata_path),
        "bytes": size,
    }


def audit_capture(root: Path, operator: str, weight_type: str) -> dict[str, object]:
    if weight_type not in FORMATS or not re.fullmatch(r"blk_0_[A-Za-z0-9_]+_weight", operator):
        raise ValueError("unsupported format or unsafe layer-zero operator name")
    block_elements, block_bytes = FORMATS[weight_type]
    directory = root / "decode" / "operators" / operator
    info_path = directory / "operator.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    model_path = root / "model.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if (info.get("op") != "GGML_OP_MUL_MAT" or info.get("phase") != "decode" or
            info.get("weight_type") != weight_type or info.get("result_type") != "F32" or
            info.get("weight", "").replace(".", "_") != operator or
            model.get("capture_layer") != 0 or not model.get("llama_commit")):
        raise ValueError("operator or model metadata does not identify the requested decode capture")
    weight_meta = json.loads((directory / f"weight_{weight_type}.json").read_text(encoding="utf-8"))
    shape = weight_meta.get("shape")
    if (not isinstance(shape, list) or len(shape) != 4 or
            any(not isinstance(value, int) or value <= 0 for value in shape) or
            shape[2:] != [1, 1]):
        raise ValueError("invalid weight shape")
    k, n = shape[:2]
    if k % block_elements:
        raise ValueError("K is not aligned to the quantization block")
    row_bytes = k // block_elements * block_bytes
    weight_bytes = n * row_bytes
    tensors = {
        "weight": check_tensor(directory, f"weight_{weight_type}", weight_type,
                               [k, n, 1, 1],
                               [block_bytes, row_bytes, weight_bytes, weight_bytes],
                               weight_bytes),
        "activation": check_tensor(directory, "activation_f32", "f32",
                                   [k, 1, 1, 1], [4, k * 4, k * 4, k * 4], k * 4),
        "golden": check_tensor(directory, "output_f32", "f32",
                               [n, 1, 1, 1], [4, n * 4, n * 4, n * 4], n * 4),
    }
    return {
        "status": "PASS", "scope": "real-model F32/quantized tensor capture; not RTL or RVV comparison",
        "format": weight_type, "operator": operator, "k": k, "n": n, "m": 1,
        "llama_commit": model["llama_commit"],
        "operator_sha256": sha256(info_path), "model_metadata_sha256": sha256(model_path),
        "tensors": tensors,
        "note": "capture operator.json activation_quantization is not a measured activation tensor type; raw activation is F32",
    }


def audit_existing(output: Path) -> dict[str, object]:
    try:
        inputs_path = output / "inputs.json"
        inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
        recorded = json.loads((output / "result.json").read_text(encoding="utf-8"))
        if recorded.get("status") != "PASS" or recorded.get("returncode") != 0:
            raise ValueError("original capture did not pass")
        if recorded.get("inputs_sha256") != sha256(inputs_path):
            raise ValueError("input manifest changed")
        for name in ("model", "binary"):
            if (recorded.get(f"{name}_sha256") != inputs.get(f"{name}_sha256") or
                    sha256(Path(inputs[name])) != inputs[f"{name}_sha256"]):
                raise ValueError(f"{name} identity changed")
        if recorded.get("console_sha256") != sha256(output / "console.log"):
            raise ValueError("capture console changed")
        expected_command = [inputs["binary"], "-m", inputs["model"],
                            "-p", inputs["prompt"], "-n", "2", "-t", "4",
                            "-c", "256", "-no-cnv", "-nr"]
        if inputs.get("prompt") != PROMPT or recorded.get("command") != expected_command:
            raise ValueError("capture command differs from reviewed profile")
        current = audit_capture(output / "capture", inputs["operator"], inputs["format"])
        if any(recorded.get(key) != value for key, value in current.items()):
            raise ValueError("captured tensors or metadata changed")
        return {"status": "PASS", "scope": current["scope"],
                "format": current["format"], "operator": current["operator"],
                "inputs_sha256": sha256(inputs_path),
                "result_sha256": sha256(output / "result.json")}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return {"status": "FAIL", "error": str(error)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--format", choices=FORMATS)
    parser.add_argument("--operator")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--audit-existing", action="store_true")
    args = parser.parse_args()
    if args.audit_existing:
        if any(value is not None for value in (args.model, args.binary, args.format, args.operator)):
            parser.error("--audit-existing only takes --output")
        result = audit_existing(args.output.resolve())
        (args.output / "audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"capture audit: {result['status']}")
        return 0 if result["status"] == "PASS" else 1
    if any(value is None for value in (args.model, args.binary, args.format, args.operator)):
        parser.error("capture requires --model, --binary, --format, and --operator")
    if args.timeout < 1 or not re.fullmatch(r"blk_0_[A-Za-z0-9_]+_weight", args.operator):
        parser.error("timeout must be positive and operator must be a layer-zero weight name")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"output must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    model = args.model.resolve(strict=True)
    binary = args.binary.resolve(strict=True)
    inputs = {"model": str(model), "model_sha256": sha256(model),
              "binary": str(binary), "binary_sha256": sha256(binary),
              "format": args.format, "operator": args.operator, "prompt": PROMPT}
    inputs_path = output / "inputs.json"
    inputs_path.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n")
    command = [str(binary), "-m", str(model), "-p", PROMPT, "-n", "2",
               "-t", "4", "-c", "256", "-no-cnv", "-nr"]
    env = os.environ.copy()
    env.update(LLAMA_Q4KM_CAPTURE_DIR=str(output / "capture"),
               LLAMA_Q4KM_CAPTURE_LAYER="0", LLAMA_Q4KM_CAPTURE_PHASE="decode")
    with (output / "console.log").open("w", encoding="utf-8") as log:
        try:
            run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                 env=env, timeout=args.timeout, check=False)
            returncode = run.returncode
        except subprocess.TimeoutExpired:
            returncode = -1
    result: dict[str, object] = {"status": "FAIL", "command": command,
                                 "returncode": returncode,
                                 "inputs_sha256": sha256(inputs_path),
                                 "model_sha256": inputs["model_sha256"],
                                 "binary_sha256": inputs["binary_sha256"],
                                 "console_sha256": sha256(output / "console.log")}
    try:
        if returncode != 0:
            raise ValueError(f"host capture exited with {returncode}")
        if (sha256(model) != inputs["model_sha256"] or
                sha256(binary) != inputs["binary_sha256"] or
                sha256(inputs_path) != result["inputs_sha256"]):
            raise ValueError("model, capture executable, or input manifest changed during the run")
        result.update(audit_capture(output / "capture", args.operator, args.format))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        result["error"] = str(error)
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"{args.format}: {result['status']} ({result.get('error', 'capture audited')})")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
