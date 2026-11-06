"""Explicit identity plus the existing complete-call/golden/ABBA checks."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'akv/quantized_kv/prefill'))
from check_selector_native import check_log as check_pair

BINDING='OUTPUT_NATIVE_BINDINGS baseline=register_pv candidate=output_tile qk=native quantizer=ggml'


def check_log(text,golden,q4):
    if text.splitlines().count(BINDING)!=1 or 'REGISTER_PV_' in text or 'SELECTOR_' in text:
        raise ValueError('Wrong experiment identity')
    result=check_pair(text.replace('OUTPUT_NATIVE_','SELECTOR_'),golden,q4,mode_field='candidate')
    result.update(comparison='register_pv_vs_output_residency',whole_model=False,
                  scope='Complete real Qwen3 GQA2 D128 visible20 Attention call')
    return result
