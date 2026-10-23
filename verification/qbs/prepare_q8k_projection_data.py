#!/usr/bin/env python3
"""Independent full Q4_K projection reference using production Q8_K bytes."""
import argparse
import json
import math
from pathlib import Path
import struct

from run_half_scale_soc import atomic_json, digest, hashes


def q4_values(block):
    if len(block) != 144:
        raise ValueError("Q4_K block size")
    d, minimum = struct.unpack_from("<ee", block)
    scales, qs = block[4:16], block[16:]
    values = []
    for group in range(8):
        if group < 4:
            scale, bias = scales[group] & 63, scales[group+4] & 63
        else:
            scale = (scales[group+4] & 15) | ((scales[group-4] >> 6) << 4)
            bias = (scales[group+4] >> 4) | ((scales[group] >> 6) << 4)
        base, shift = (group // 2) * 32, (group % 2) * 4
        values.extend(d * scale * ((qs[base+j] >> shift) & 15) - minimum * bias for j in range(32))
    return values


def q8_rows(data, k):
    if k % 256 or len(data) != (k//256)*1168:
        raise ValueError("M4 Q8_K geometry")
    rows = [[] for _ in range(4)]
    for b in range(k//256):
        base = b*1168
        scales = struct.unpack_from("<4f", data, base)
        quants = struct.unpack_from("<1024b", data, base+16)
        sums = struct.unpack_from("<64h", data, base+1040)
        for r in range(4):
            values = quants[r::4]
            for group in range(16):
                if sum(values[group*16:(group+1)*16]) != sums[group*4+r]:
                    raise ValueError("Production golden bsums mismatch")
            rows[r].extend(scales[r]*q for q in values)
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--golden-run",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--capture",type=Path,default=Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators/blk_0_attn_q_weight"))
    a = p.parse_args()
    golden_run = a.golden_run.resolve(strict=True)
    report = json.loads((golden_run/"golden.json").read_text())
    prior = json.loads((golden_run/"manifest.json").read_text())
    golden = golden_run/"golden.bin"
    if (report["state"] != "PASS" or report["k"] != 1536 or report["m"] != 4
        or digest(golden) != report["golden_sha256"] or hashes(map(Path,prior)) != prior
        or digest(golden_run/"manifest.json") != report["manifest_sha256"]
        or digest(golden_run/"qemu.log") != report["log_sha256"]):
        raise ValueError("Production golden identity mismatch")
    capture = a.capture.resolve(strict=True)
    paths = [capture/n for n in ("weight_q4_K.bin","weight_q4_K.json","output_f32.bin","output_f32.json","activation_f32.bin","activation_f32.json")]
    source_pins = hashes([Path(__file__),golden,golden_run/"golden.json",*paths])
    weight, output, activation = [json.loads((capture/(n+".json")).read_text()) for n in ("weight_q4_K","output_f32","activation_f32")]
    if (weight["type"] != "q4_K" or weight["shape"] != [1536,1536,1,1] or weight["strides"] != [144,864,1327104,1327104]
        or output["type"] != "f32" or output["shape"] != [1536,15,1,1] or output["strides"] != [4,6144,92160,92160]
        or activation["type"] != "f32" or activation["shape"] != [1536,15,1,1] or activation["strides"] != [4,6144,92160,92160]):
        raise ValueError("Unexpected real projection geometry")
    weights = (capture/"weight_q4_K.bin").read_bytes()
    captured = (capture/"output_f32.bin").read_bytes()
    raw_input = (capture/"activation_f32.bin").read_bytes()
    if len(weights) != weight["nbytes"] or len(captured) != output["nbytes"] or len(raw_input) != activation["nbytes"]:
        raise ValueError("Capture byte size")
    actual_capture = Path(report["capture"]).read_bytes()
    if raw_input[:4*1536*4] != actual_capture:
        raise ValueError("Independent golden belongs to different activation rows")
    acts = q8_rows(golden.read_bytes(),1536)
    expected = [0.0]*(4*1536)
    max_drift = 0.0
    for n in range(1536):
        values = []
        for b in range(6):
            offset = (n*6+b)*144
            values.extend(q4_values(weights[offset:offset+144]))
        for r in range(4):
            value = math.fsum(w*x for w,x in zip(values,acts[r]))
            reference = struct.unpack_from("<f",captured,(r*1536+n)*4)[0]
            if not math.isfinite(value) or not math.isfinite(reference) or abs(value-reference)>2e-3+2e-3*abs(reference):
                raise ValueError(f"Independent projection disagrees with captured GGML output r={r} n={n}")
            max_drift = max(max_drift,abs(value-reference))
            expected[r*1536+n] = value
    packed = bytearray()
    for first in range(0,1536,4):
        for b in range(6):
            for r in range(4):
                offset = ((first+r)*6+b)*144
                packed.extend(weights[offset:offset+144])
    if hashes(map(Path,source_pins)) != source_pins:
        raise ValueError("Input drift during oracle calculation")
    out = a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    (out/"weight_r4.bin").write_bytes(packed)
    (out/"oracle_f32.bin").write_bytes(struct.pack("<6144f",*expected))
    (out/"activation_f32.bin").write_bytes(actual_capture)
    (out/"activation_q8k_m4.bin").write_bytes(golden.read_bytes())
    atomic_json(out/"manifest.json",source_pins)
    atomic_json(out/"data.json",dict(state="READY_NOT_RTL_VERIFIED",m=4,n=1536,k=1536,outputs=6144,
        max_capture_drift=max_drift,capture_atol=2e-3,capture_rtol=2e-3,oracle_atol=2e-4,oracle_rtol=2e-5,
        oracle="FP64 fsum of Q4_K row-major weights and independent production Q8_K bytes",
        manifest_sha256=digest(out/"manifest.json"),artifacts=hashes(out.glob("*.bin"))))


if __name__ == "__main__": main()
