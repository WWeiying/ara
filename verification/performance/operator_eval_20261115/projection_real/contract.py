"""Native real-Qwen3 projection selection. Shapes come from locked capture metadata."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
SDK_COMMIT='dbe2b78817ef45b912444afcb85ad6e01a2be135'
LLAMA_COMMIT='a2b7f30da9aadf88b0a068c447383ed2e26ee867'
LLAMA=Path('/home/wangwy/llama/llama.cpp')
TOOLCHAIN=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')
PARENT=OUT/'operator_soc_20261115_activity_02'
DECODE=OUT/'e2e_decode_capture_20261106_01'
PREFILL=OUT/'e2e_ffn_capture_20261106_02'
MODEL=Path('/home/wangwy/llama/models/Qwen3-1.7B-Q4_K_M.gguf')
MODEL_SHA='d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5'
RECEIPTS={
    'decode':(DECODE,'16a0b450843ba41276c4f56dfbd9abcf974020c6db97b19e1cda10b6864bf52f'),
    'prefill':(PREFILL,'698c4b83f6eda896d6adc40a9458560fe5fcaeb965ecf197da9f09260f158c01'),
}
ATOL=RTOL=0.0002
POLICY='compiled_golden_exhaustive_compare_v1'
ACTIVATIONS={'attn_q':'attn_norm-0','ffn_gate':'ffn_norm-0','ffn_down':'ffn_swiglu-0'}
SELECTION=(('ffn_down','decode',1,128),('attn_q','decode',1,64),
           ('ffn_gate','decode',1,64),('ffn_down','prefill',4,64))
FIELDS={
    'q4_K':((0,2,2),(2,2,2),(4,12,1),(16,128,1)),
    'q6_K':((208,2,2),(192,16,1),(0,128,1),(128,64,1)),
}


def receipt(phase):
    path,sha=RECEIPTS[phase]
    raw=(path/'result.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError('Capture receipt drift: '+phase)
    return json.loads(raw)


def cases():
    selected=[]
    for operator,phase,m,n in SELECTION:
        record=receipt(phase)
        meta=next(w for w in record['weights'] if w['tensor'] == f'blk.0.{operator}.weight')
        fmt={'Q4_K':'q4_K','Q6_K':'q6_K'}[meta['type']]
        k=meta['k']
        for backend in ('native','rvv_x32'):
            selected.append(dict(id=f'qwen3_real_{phase}_{operator}_m{m}_n{n}_{backend}',operator=operator,
                phase=phase,position=40 if phase == 'decode' else None,source=str(RECEIPTS[phase][0]),
                activation_source=ACTIVATIONS[operator],tensor=meta['tensor'],format=fmt,
                profile=1 if fmt == 'q4_K' else 2,activation_profile=1,block_elements=256,
                weight_block_bytes=144 if fmt == 'q4_K' else 210,activation_block_bytes=292,
                m=m,n=n,k=k,k_blocks=k//256,tile=m,reuse='direct',backend=backend,
                x32_symbol='q4k_gemv_32' if fmt == 'q4_K' else 'q6k_gemv_32',
                kernel_symbol='q6k_gemm_32x4' if m == 4 else
                    'q4k_gemv_32' if fmt == 'q4_K' else 'q6k_gemv_32',
                kernel_shape='32x4' if m == 4 else '32_outputs_per_input_row',
                quantizer='quantize_row_q8_K',quant_vcsr=2,runnable=True,
                provenance='native_model_weight_capture_with_real_'+phase+'_activation',
                native_format_model_capture=True,requantized=False,original_f16_weights=False,
                output_policy=POLICY,baseline_kind='native_qbs_sdk' if backend == 'native' else
                    'established_format_x32_multi_output_rvv',primary_eligible=True))
    return selected


def owned_output(path):
    path=path.resolve()
    if path.parent != OUT.resolve() or not path.name.startswith('operator_projection_real_prepare_20261115_'):
        raise ValueError('Owned operator_projection_real_prepare_20261115_* directory required')
    return path


def fnv(data):
    value=2166136261
    for byte in data:
        value=((value^byte)*16777619)&0xffffffff
    return value


def repack(raw,fmt,n,k):
    wb=144 if fmt == 'q4_K' else 210
    kb=k//256
    if n%32 or k%256 or len(raw) != n*kb*wb:
        raise ValueError('Incomplete full-K x32 geometry')
    packed=bytearray()
    for first in range(0,n,32):
        for block in range(kb):
            for offset,length,size in FIELDS[fmt]:
                for element in range(0,length,size):
                    for row in range(first,first+32):
                        start=(row*kb+block)*wb+offset+element
                        packed.extend(raw[start:start+size])
    return bytes(packed)
