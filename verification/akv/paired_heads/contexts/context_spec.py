"""Reviewed KV-context geometry; no runtime selection or kernel implementation."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.append(str(HERE.parent))
import threeway_build as old_build
import attention_run as shared

ORDER = ('rvv', 'generic', 'paired', 'paired', 'generic', 'rvv')
CAPTURE_ROOT = Path('/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252')
NAMES = dict(input_a='attn_q_input-0',input_b='attn_k_input-0',input_c='attn_v_input-0',
             input_d='attn_mask_input-0',golden='kqv_out-0')


def tiles(kv):
    shared.require(type(kv) is int and kv in (128,256), 'Only reviewed KV128/256 contexts')
    return kv//64


def sequence(kv, variant):
    t = tiles(kv)
    shared.require(variant in ORDER, 'Unknown variant')
    if variant == 'rvv':
        return []
    panel = variant == 'paired'
    body = [6]*(32 if panel else 256)+[2]*(64 if panel else 128)
    return ([4]+body+([5]+body)*(t-1)+[3])*2


def expected(kv):
    t = tiles(kv)
    variants = {}
    for name in ('generic','paired'):
        seq = sequence(kv,name)
        variants[name] = dict(commands=len(seq),column_load=seq.count(6),
            column_panel=seq.count(6) if name == 'paired' else 0,row_load=seq.count(2),
            logical_columns=(128 if name == 'paired' else 256)*2*t,
            replay_bytes=(65536 if name == 'paired' else 131072)*t)
    return dict(trials=6,order=list(ORDER),outputs_per_trial=512,commands=2*sum(v['commands'] for v in variants.values()),
        rvv=dict(commands=0),**variants, per_native_trial=dict(v2_full=2,v2_refill=2*(t-1),release=2,
        q_external_bytes=1024,kv_external_bytes=65536*t,read_payload_bytes=65536*t+1152,
        read_ranges=262+256*(t-1)))


def subset(kv):
    tiles(kv)
    return (f'CONTEXT_THREEWAY_SUBSET source=qwen25_kv{kv} kv={kv} capacity=256 '
            'qheads=0,1,6,7 kvheads=0,1 outputs=512 derived=1 outputbytes=2048')
