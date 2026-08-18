#!/usr/bin/env python3

import struct
from pathlib import Path


ROOT = Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m")
CASE = ROOT / "decode/operators/blk_0_ffn_gate_weight"
MICRO = ROOT / "micro/cases/q4_k_x_q8_k_dot_n1536_nrc1"
GENERATED = Path(__file__).resolve().parent / "generated"

QK_K = 256
K = 1536
ROWS = 32
INPUTS = 4
Q4_BLOCK_BYTES = 144
Q8_BLOCK_BYTES = 292
BLOCKS = K // QK_K


def write(name, data):
    GENERATED.mkdir(parents=True, exist_ok=True)
    path = GENERATED / name
    path.write_bytes(data)
    return path


def repack_q4_x32(row_major):
    row_bytes = BLOCKS * Q4_BLOCK_BYTES
    packed = bytearray()
    for block in range(BLOCKS):
        blocks = [
            row_major[row * row_bytes + block * Q4_BLOCK_BYTES:
                      row * row_bytes + (block + 1) * Q4_BLOCK_BYTES]
            for row in range(ROWS)
        ]
        for offset in (0, 2):
            for source in blocks:
                packed.extend(source[offset:offset + 2])
        for offset, length in ((4, 12), (16, 128)):
            for byte in range(length):
                for source in blocks:
                    packed.append(source[offset + byte])
    return bytes(packed)


def repack_q8_x4(single):
    packed = bytearray()
    for block in range(BLOCKS):
        source = single[block * Q8_BLOCK_BYTES:(block + 1) * Q8_BLOCK_BYTES]
        scale = source[0:4]
        quants = source[4:260]
        packed.extend(scale * INPUTS)
        for value in quants:
            packed.extend(bytes([value]) * INPUTS)

        sums = [0] * (QK_K // 4)
        signed = [value if value < 128 else value - 256 for value in quants]
        for index in range(QK_K * INPUTS):
            src_id = index % INPUTS
            src_offset = index // INPUTS
            dst = ((index >> 6) << 2) + (index & 3)
            assert src_id < INPUTS
            sums[dst] += signed[src_offset]
        packed.extend(struct.pack("<64h", *sums))
    return bytes(packed)


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def nearest_int(value):
    # Bit-exact copy of ggml-quants.c:nearest_int for this value range.
    bits = struct.unpack("<I", struct.pack("<f", f32(value + 12582912.0)))[0]
    return (bits & 0x007FFFFF) - 0x00400000


def quantize_q8_k(values):
    output = bytearray()
    for block in range(BLOCKS):
        source = values[block * QK_K:(block + 1) * QK_K]
        maximum = 0.0
        absolute_maximum = 0.0
        for value in source:
            if abs(value) > absolute_maximum:
                absolute_maximum = abs(value)
                maximum = value

        if absolute_maximum == 0.0:
            scale = 0.0
            quants = [0] * QK_K
        else:
            inverse_scale = f32(-127.0 / maximum)
            scale = f32(1.0 / inverse_scale)
            quants = [min(127, nearest_int(f32(inverse_scale * value)))
                      for value in source]

        sums = [sum(quants[index:index + 16])
                for index in range(0, QK_K, 16)]
        output.extend(struct.pack("<f", scale))
        output.extend(struct.pack("<256b", *quants))
        output.extend(struct.pack("<16h", *sums))
    return bytes(output)


weight_all = (CASE / "weight_q4_K.bin").read_bytes()
row_bytes = BLOCKS * Q4_BLOCK_BYTES
weight_rows = weight_all[:ROWS * row_bytes]
activation_f32 = struct.unpack(
    f"<{K}f", (CASE / "activation_f32.bin").read_bytes())
activation = quantize_q8_k(activation_f32)
golden_all = (CASE / "output_f32.bin").read_bytes()
golden = golden_all[:ROWS * 4]

assert len(weight_rows) == ROWS * row_bytes
assert len(activation) == BLOCKS * Q8_BLOCK_BYTES
assert len(golden) == ROWS * 4

repacked_weights = repack_q4_x32(weight_rows)
repacked_activation = repack_q8_x4(activation)

# Keep each timed implementation on an independent address range.  This makes
# the comparison insensitive to scalar-cache state left by an earlier region.
paths = {
    "weight_original.bin": write("weight_original.bin", weight_rows),
    "activation_original.bin": write("activation_original.bin", activation * INPUTS),
    "weight_vl1024.bin": write("weight_vl1024.bin", weight_rows),
    "activation_vl1024.bin": write("activation_vl1024.bin", activation * INPUTS),
    "weight_gemv.bin": write("weight_gemv.bin", repacked_weights),
    "activation_gemv.bin": write("activation_gemv.bin", activation * INPUTS),
    "weight_gemm.bin": write("weight_gemm.bin", repacked_weights),
    "activation_gemm.bin": write("activation_gemm.bin", repacked_activation),
    "golden_f32.bin": write("golden_f32.bin", golden),
}

print('.section .rodata,"a",@progbits')
for symbol, path in paths.items():
    name = symbol.removesuffix(".bin")
    print(".balign 64")
    print(f".global {name}_start")
    print(f".global {name}_end")
    print(f"{name}_start:")
    print(f'.incbin "{path}"')
    print(f"{name}_end:")
