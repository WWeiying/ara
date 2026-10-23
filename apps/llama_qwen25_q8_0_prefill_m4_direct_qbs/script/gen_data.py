#!/usr/bin/env python3
"""Generate either full-projection app, using the existing capture validator."""
import hashlib
import json
import math
from pathlib import Path
import runpy
import struct


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def generate():
    apps = Path(__file__).resolve().parents[2]
    app = Path.cwd()
    spec = json.loads((app / "case.json").read_text())
    if (spec["weight_type"], spec["k"], spec["rows"], spec["inputs"],
            spec["phase"], spec["operator"]) != (
            "q8_0", 896, 896, 4, "prefill", "blk_0_attn_q_weight"):
        raise ValueError("This paired app requires the complete captured Q projection")
    common = apps / "llama_qwen25_real/common/generate_qbs_case.py"
    runpy.run_path(str(common), run_name="__main__")
    generated = app / "generated"
    activations = struct.unpack("<3584f", (generated / "activation_f32.bin").read_bytes())
    if not all(math.isfinite(x) for x in activations):
        raise ValueError("Nonfinite captured activation")
    quantized = bytearray()
    activation_values = [[] for _ in range(4)]
    for input_row in range(4):
        for block in range(28):
            start = input_row * 896 + block * 32
            values = activations[start:start + 32]
            scale = f32(max(abs(x) for x in values) / 127.0)
            inverse = f32(1.0 / scale) if scale else 0.0
            # The existing RVV quantizer uses FP32 multiply then RNE conversion.
            qs = [round(f32(x * inverse)) for x in values]
            if any(q < -127 or q > 127 for q in qs):
                raise ValueError("Q8_0 quantization range")
            scale_bytes = struct.pack("<e", scale)
            stored_scale = struct.unpack("<e", scale_bytes)[0]
            quantized += scale_bytes + struct.pack("<32b", *qs)
            activation_values[input_row].extend(stored_scale * q for q in qs)

    # Read original row-major weights, not the R4 blob or runtime pack helpers.
    weights = (generated / "source_weight.bin").read_bytes()
    expected = [0.0] * 3584
    for row in range(896):
        weight_values = []
        for block in range(28):
            offset = (row * 28 + block) * 34
            scale = struct.unpack_from("<e", weights, offset)[0]
            qs = struct.unpack_from("<32b", weights, offset + 2)
            weight_values.extend(scale * q for q in qs)
        for input_row in range(4):
            value = math.fsum(w * a for w, a in zip(weight_values, activation_values[input_row]))
            if not math.isfinite(value):
                raise ValueError("Nonfinite scalar oracle")
            expected[input_row * 896 + row] = f32(value)
    captured = struct.unpack("<3584f", (generated / "golden_f32.bin").read_bytes())
    drift = []
    for actual, golden in zip(expected, captured):
        if not math.isfinite(golden) or abs(actual - golden) > 2e-3 + 2e-3 * abs(golden):
            raise ValueError("Independent oracle disagrees with capture at unchanged tolerance")
        drift.append(abs(actual - golden))
    oracle_path = generated / "oracle_f32.bin"
    quant_path = generated / "expected_q8_0.bin"
    oracle_path.write_bytes(struct.pack("<3584f", *expected))
    quant_path.write_bytes(quantized)
    for symbol, path in (("benchmark_oracle", oracle_path), ("benchmark_expected_q8", quant_path)):
        print(f'.balign 64\n.global {symbol}_start\n.global {symbol}_end\n'
              f'{symbol}_start:\n.incbin "{path.resolve()}"\n{symbol}_end:')
    provenance_path = generated / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["qbs"]["activation_layout"] = "A_M4_INTERLEAVED"
    provenance["qbs_activation_pack_in_timed_region"] = True
    provenance["runtime_timed_region"] = (
        "F32_to_Q8_0+M4_activation_interleave+per_command_descriptor_construction+"
        "command_fence_and_vsetvli+blocking_QBS_execution+result_vector_stores")
    provenance["scope"] = "single_full_projection_not_whole_model"
    provenance["independent_oracle"] = {
        "method": "FP64 scalar products and math.fsum of independently dequantized row-major inputs",
        "runtime_quantization": "exact expected bytes checked outside timed region",
        "outputs": 3584, "atol": 2e-4, "rtol": 2e-5,
        "captured_atol": 2e-3, "captured_rtol": 2e-3,
        "max_capture_drift": max(drift),
    }
    for path in (oracle_path, quant_path):
        provenance["tensors"][path.name] = {
            "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    generate()
