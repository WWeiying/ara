#!/usr/bin/env python3

import json
import os
import struct
import sys
from pathlib import Path


CAPTURE_ROOT = Path(os.environ.get(
    "Q4KM_CAPTURE_ROOT",
    "/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m",
))
MAGIC = 0x514B4D4F
ATTENTION_RVV = 1 << 0
ATTENTION_AKV = 1 << 1
ATTENTION_TILED_RVV = 1 << 2
ATTENTION_AKV_V2 = 1 << 3

KIND = {
    "linear_q4": 1,
    "linear_q6": 2,
    "add": 3,
    "silu_mul": 4,
    "rms_norm": 5,
    "rope": 6,
    "attention_core": 7,
    "set_rows_f32_f16": 8,
    "get_rows_f32": 9,
    "get_rows_q4_k": 10,
}


def load_json(path):
    return json.loads(path.read_text())


def tensor(meta_path):
    meta_path = meta_path.resolve()
    meta = load_json(meta_path)
    data_path = meta_path.with_suffix(".bin")
    if not data_path.is_file() or data_path.stat().st_size != meta["nbytes"]:
        raise SystemExit(f"invalid tensor pair: {meta_path}")
    return {
        "meta": meta_path,
        "data": data_path,
        "type": meta["type"],
        "shape": [int(value) for value in meta["shape"]],
        "nbytes": int(meta["nbytes"]),
    }


def resolve_case(case_id):
    manifest = load_json(CAPTURE_ROOT / "replay/manifest.json")
    matches = [entry for entry in manifest["cases"] if entry["id"] == case_id]
    if len(matches) != 1:
        raise SystemExit(f"unknown or non-leaf case: {case_id}")
    entry = matches[0]
    if entry["level"] not in ("operator", "operator-leaf", "operator-calibration"):
        raise SystemExit(f"case is not an operator or calibration leaf: {case_id}")
    return entry


def f32_bits(value):
    return struct.unpack("<I", struct.pack("<f", float(value)))[0]


def emit_blob(symbol, value):
    print(".balign 64")
    print(f".global {symbol}_start")
    print(f".global {symbol}_end")
    print(f"{symbol}_start:")
    if value is not None:
        print(f'.incbin "{value["data"]}"')
    print(f"{symbol}_end:")


def make_spec(case_id, implementation):
    entry = resolve_case(case_id)
    flags = 0
    args = [0] * 8
    params = [0.0] * 8
    blobs = {name: None for name in ("input_a", "input_b", "input_c", "input_d", "golden")}

    if entry["level"] == "operator":
        directory = CAPTURE_ROOT / entry["path"]
        op = load_json(directory / "operator.json")
        weight_type = op["weight_type"]
        weight = tensor(directory / f"weight_{weight_type}.json")
        activation = tensor(directory / "activation_f32.json")
        golden = tensor(directory / "output_f32.json")
        kind = "linear_q4" if weight_type.lower() == "q4_k" else "linear_q6"
        blobs.update(input_a=weight, input_b=activation, golden=golden)
        args[:3] = [weight["shape"][0], weight["shape"][1], activation["shape"][1]]
        params[:2] = [2.0e-4, 2.0e-4]
    else:
        directory = CAPTURE_ROOT / entry["path"]
        case = load_json(directory / "case.json")
        kind = case["kind"]

        def ref(key):
            return tensor(directory / case[key])

        blobs["input_a"] = ref("input_a")
        blobs["golden"] = ref("golden")
        params[:2] = [case.get("atol", 3.0e-4), case.get("rtol", 3.0e-4)]
        if kind == "rms_norm":
            blobs["input_b"] = ref("weight")
            args[:2] = [blobs["input_a"]["shape"][0],
                        blobs["input_a"]["nbytes"] // (4 * blobs["input_a"]["shape"][0])]
            params[2] = case["epsilon"]
        elif kind in ("add", "silu_mul"):
            blobs["input_b"] = ref("input_b")
            args[0] = blobs["golden"]["nbytes"] // 4
        elif kind == "rope":
            blobs["input_b"] = ref("position")
            args[:5] = [case["n_dims"], case["mode"],
                        blobs["input_a"]["shape"][0],
                        blobs["input_a"]["shape"][1],
                        blobs["input_a"]["shape"][2]]
            params[2:] = [case["freq_base"], case["freq_scale"], case["ext_factor"],
                          case["attn_factor"], case["beta_fast"], case["beta_slow"]]
        elif kind == "attention_core":
            if implementation == "rvv":
                flags |= ATTENTION_RVV
            elif implementation == "akv":
                flags |= ATTENTION_AKV
            elif implementation == "tiled_rvv":
                flags |= ATTENTION_TILED_RVV
            elif implementation == "akv_v2":
                flags |= ATTENTION_AKV_V2
            elif implementation != "ref":
                raise SystemExit(
                    "attention implementation must be 'ref', 'rvv', "
                    "'tiled_rvv', 'akv', or 'akv_v2'"
                )
            blobs["input_b"] = ref("key")
            blobs["input_c"] = ref("value")
            blobs["input_d"] = ref("mask")
            qshape = blobs["input_a"]["shape"]
            kshape = blobs["input_b"]["shape"]
            args[:5] = [qshape[0], qshape[1], qshape[2], kshape[1], kshape[2]]
            params[2:4] = [case["scale"], case.get("max_bias", 0.0)]
        elif kind == "set_rows_f32_f16":
            blobs["input_b"] = ref("index")
            width = blobs["input_a"]["shape"][0] * blobs["input_a"]["shape"][1]
            rows = blobs["golden"]["nbytes"] // (2 * width)
            args[:3] = [width, rows, case["destination_rows"]]
        elif kind in ("get_rows_f32", "get_rows_q4_k"):
            blobs["input_b"] = ref("index")
            args[:2] = [blobs["golden"]["shape"][0], blobs["golden"]["shape"][1]]
        else:
            raise SystemExit(f"unsupported operator kind: {kind}")

    return kind, flags, args, params, blobs


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(
            "usage: gen_data.py CASE_ID [ref|rvv|tiled_rvv|akv|akv_v2]"
        )
    case_id = sys.argv[1]
    implementation = sys.argv[2] if len(sys.argv) == 3 else "ref"
    kind, flags, args, params, blobs = make_spec(case_id, implementation)

    print('.section .rodata,"a",@progbits')
    print(".balign 64")
    print(".global llama_case_config")
    print("llama_case_config:")
    for value in (MAGIC, 1, KIND[kind], flags):
        print(f".long {value}")
    for value in args:
        print(f".long {value}")
    for value in params:
        print(f".long 0x{f32_bits(value):08x}")
    for name in ("input_a", "input_b", "input_c", "input_d", "golden"):
        shape = blobs[name]["shape"] if blobs[name] else [0, 0, 0, 0]
        for value in shape:
            print(f".long {value}")
        print(f".long {blobs[name]['nbytes'] if blobs[name] else 0}")

    print(".balign 8")
    print(".global llama_case_name")
    print("llama_case_name:")
    display_name = (
        f"{case_id}/{implementation}" if kind == "attention_core" else case_id
    )
    escaped = display_name.replace("\\", "\\\\").replace('"', '\\"')
    print(f'.asciz "{escaped}"')
    for name, value in blobs.items():
        emit_blob(f"llama_{name}", value)


if __name__ == "__main__":
    main()
