"""Nine-format controlled requantization contract; no native-format capture claim."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
SDK_COMMIT = 'dbe2b78817ef45b912444afcb85ad6e01a2be135'
LLAMA_COMMIT = 'a2b7f30da9aadf88b0a068c447383ed2e26ee867'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
TOOLCHAIN = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')
ROWS = OUT / 'stage2_qwen3_rows8_20261109_02'
ROWS_PINS = '8f8775bcccc4bc2da08d14fca7f554d66786fde4337650242453714d8422d2b0'
ROWS_RECEIPT = '8bcd4e59062b98d086bcf0aa11d30380269b4aa4b6b7695968619037376ca6c5'
PARENT = OUT / 'operator_soc_20261115_activity_02'
ATOL = RTOL = 0.0002
POLICY = 'compiled_golden_exhaustive_compare_v1'

# format, hardware profile, elements/block, weight bytes/block, x32 symbol
TABLE = (
    ('q2_K', 7, 256, 84, None),
    ('q3_K', 5, 256, 110, 'q3k_gemv_32'),
    ('q4_K', 1, 256, 144, 'q4k_gemv_32'),
    ('q5_K', 4, 256, 176, 'q5k_gemv_32'),
    ('q6_K', 2, 256, 210, 'q6k_gemv_32'),
    ('q4_0', 3, 32, 18, None),
    ('q5_0', 8, 32, 22, None),
    ('q8_0', 6, 32, 34, 'q8_0_gemv_32'),
    ('iq4_nl', 9, 32, 18, None),
)
PROFILES = {name: dict(format=name, profile=p, block_elements=e, weight_block_bytes=w,
                       activation_profile=1 if e == 256 else 2,
                       activation_block_bytes=292 if e == 256 else 34,
                       quantizer='quantize_row_q8_K' if e == 256 else 'quantize_row_q8_0',
                       quant_vcsr=2 if e == 256 else 0, x32_symbol=symbol)
            for name, p, e, w, symbol in TABLE}
FIELDS = {
    'q2_K': ((80, 2, 2), (82, 2, 2), (0, 16, 1), (16, 64, 1)),
    'q3_K': ((108, 2, 2), (0, 32, 1), (32, 64, 1), (96, 12, 1)),
    'q4_K': ((0, 2, 2), (2, 2, 2), (4, 12, 1), (16, 128, 1)),
    'q5_K': ((0, 2, 2), (2, 2, 2), (4, 12, 1), (16, 32, 1), (48, 128, 1)),
    'q6_K': ((208, 2, 2), (192, 16, 1), (0, 128, 1), (128, 64, 1)),
    'q4_0': ((0, 2, 2), (2, 16, 1)),
    'q5_0': ((0, 2, 2), (2, 4, 1), (6, 16, 1)),
    'q8_0': ((0, 2, 2), (2, 32, 1)),
    'iq4_nl': ((0, 2, 2), (2, 16, 1)),
}


def cases():
    result = []
    for backend in ('native', 'rvv_x32'):
        for m in (1, 4):
            for fmt, p in PROFILES.items():
                established = bool(p['x32_symbol'])
                result.append(dict(p, id=f'qwen3_attn_q_requant_{fmt.lower()}_m{m}_n64_{backend}',
                    m=m, n=64, k=2048, tile=m, k_blocks=2048//p['block_elements'],
                    backend=backend, reuse='direct', runnable=True,
                    provenance='actual_Qwen3_Q4_K_dequantized_then_upstream_reference_requantized',
                    native_format_model_capture=False, original_f16_weights=False,
                    output_policy=POLICY,
                    kernel_symbol=('q4k_gemm_32x4' if fmt == 'q4_K' and m == 4 else
                        'q6k_gemm_32x4' if fmt == 'q6_K' and m == 4 else p['x32_symbol'] or
                        {7:'formats_q2k_x32',3:'formats_q4_0_x32',8:'formats_q5_0_x32',9:'formats_iq4nl_x32'}[p['profile']]),
                    kernel_shape='32x4' if fmt in ('q4_K','q6_K') and m == 4 else '32_outputs_per_input_row',
                    baseline_kind=('native_qbs_sdk' if backend == 'native' else
                        'established_format_x32_multi_output_rvv' if established else
                        'successor_format_x32_multi_output_rvv_candidate'),
                    primary_eligible=backend == 'native' or established))
    return result


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def repack(raw, fmt, n=64, k=2048):
    p = PROFILES[fmt]
    wb, kb = p['weight_block_bytes'], k//p['block_elements']
    if n % 32 or len(raw) != n*kb*wb:
        raise ValueError('Incomplete x32 weight geometry')
    packed = bytearray()
    for first in range(0, n, 32):
        for block in range(kb):
            for offset, length, size in FIELDS[fmt]:
                for element in range(0, length, size):
                    for row in range(first, first+32):
                        start = (row*kb+block)*wb+offset+element
                        packed.extend(raw[start:start+size])
    if len(packed) != len(raw):
        raise ValueError('Bad x32 field map')
    return bytes(packed)
