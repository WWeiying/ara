#!/usr/bin/env python3
from pathlib import Path

ROOT = Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/micro/cases")

FILES = {
    "quant1536_input": ("quantize_f32_to_q8_k_k1536", "input_f32.bin"),
    "quant1536_golden": ("quantize_f32_to_q8_k_k1536", "output_q8_k.bin"),
    "quant8960_input": ("quantize_f32_to_q8_k_k8960", "input_f32.bin"),
    "quant8960_golden": ("quantize_f32_to_q8_k_k8960", "output_q8_k.bin"),
    "q4_1536_weight": ("q4_k_x_q8_k_dot_n1536_nrc1", "weight_q4_k.bin"),
    "q4_1536_activation": ("q4_k_x_q8_k_dot_n1536_nrc1", "activation_q8_k.bin"),
    "q4_1536_golden": ("q4_k_x_q8_k_dot_n1536_nrc1", "output_f32.bin"),
    "q4_8960_weight": ("q4_k_x_q8_k_dot_n8960_nrc1", "weight_q4_k.bin"),
    "q4_8960_activation": ("q4_k_x_q8_k_dot_n8960_nrc1", "activation_q8_k.bin"),
    "q4_8960_golden": ("q4_k_x_q8_k_dot_n8960_nrc1", "output_f32.bin"),
    "q6_1536_weight": ("q6_k_x_q8_k_dot_n1536_nrc1", "weight_q6_k.bin"),
    "q6_1536_activation": ("q6_k_x_q8_k_dot_n1536_nrc1", "activation_q8_k.bin"),
    "q6_1536_golden": ("q6_k_x_q8_k_dot_n1536_nrc1", "output_f32.bin"),
    "q6_8960_weight": ("q6_k_x_q8_k_dot_n8960_nrc1", "weight_q6_k.bin"),
    "q6_8960_activation": ("q6_k_x_q8_k_dot_n8960_nrc1", "activation_q8_k.bin"),
    "q6_8960_golden": ("q6_k_x_q8_k_dot_n8960_nrc1", "output_f32.bin"),
}

print('.section .rodata,"a",@progbits')
print(".balign 64")
for symbol, (case, filename) in FILES.items():
    path = ROOT / case / filename
    if not path.is_file():
        raise SystemExit(f"missing capture data: {path}")
    print(f".global {symbol}_start")
    print(f".global {symbol}_end")
    print(f"{symbol}_start:")
    print(f'.incbin "{path}"')
    print(f"{symbol}_end:")
    print(".balign 64")
