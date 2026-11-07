#!/usr/bin/env python3
"""Export exact real F16 Attention subsets and independently check their mapping."""
import argparse
import json
import math
from pathlib import Path
import struct

from audit import digest, require, verify_pins
from capture_f16_attention import TENSORS, tensor, validate
from prepare_wide_soc import RUNS, HERE
from run_supply_sdk import bind

CAPTURE = RUNS/'e2e_qwen3_f16_attention_capture_20261106_01'
CAPTURE_SHA = 'd4ab9d3cd381a5e8831a7fe7cf9300f82cfc121d53f83868dfa4eab57dd1e985'
SCALE_BITS = 0x3db504f3
SCALE = struct.unpack('<f',struct.pack('<I',SCALE_BITS))[0]
NAMES = ('query','key','value','mask','golden')


def rows(meta, raw, heads, tokens):
    """Keep original element bytes; materialize only head/token subset strides."""
    require(0 < heads <= meta['shape'][2] and 0 < tokens <= meta['shape'][1],
            'Subset outside captured tensor')
    size = 4 if meta['type'] == 'f32' else 2
    width = meta['shape'][0]*size
    return b''.join(raw[h*meta['strides'][2]+t*meta['strides'][1]:
                        h*meta['strides'][2]+t*meta['strides'][1]+width]
                    for h in range(heads) for t in range(tokens))


def independent_attention(query, key, value, visible):
    """F64 stable Softmax reference for data provenance, not native FP16 semantics."""
    nq = len(visible)
    q = struct.unpack('<'+'f'*(len(query)//4),query)
    k = struct.unpack('<'+'e'*(len(key)//2),key)
    v = struct.unpack('<'+'e'*(len(value)//2),value)
    expected = []
    for t, count in enumerate(visible):
        for h in range(2):
            qr = q[(h*nq+t)*128:(h*nq+t+1)*128]
            scores = [math.fsum(a*b for a,b in zip(qr,k[j*128:(j+1)*128]))*SCALE
                      for j in range(count)]
            maximum = max(scores)
            weights = [math.exp(s-maximum) for s in scores]
            total = math.fsum(weights)
            expected.extend(math.fsum(weights[j]*v[j*128+d] for j in range(count))/total
                            for d in range(128))
    return expected


def independent_decode(query, key, value, visible):
    """Scalar mapping reference for GGML's F16 per-token Decode recurrence."""
    require(len(visible)==1,'Decode reference requires one query')
    f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
    f16=lambda x:struct.unpack('<e',struct.pack('<e',x))[0]
    q=struct.unpack('<256f',query)
    k=struct.unpack('<'+'e'*(len(key)//2),key)
    v=struct.unpack('<'+'e'*(len(value)//2),value)
    outputs=[]
    for head in range(2):
        qr=[f16(x) for x in q[head*128:(head+1)*128]]
        accumulator=[0.0]*128;maximum=-math.inf;total=0.0
        for token in range(visible[0]):
            score=f32(f32(math.fsum(a*b for a,b in zip(qr,k[token*128:(token+1)*128])))*SCALE)
            old_scale=coefficient=1.0
            if score>maximum:
                old_scale=f32(math.exp(f32(maximum-score)));maximum=score
                accumulator=[f16(f32(x*old_scale)) for x in accumulator]
            else:coefficient=f32(math.exp(f32(score-maximum)))
            accumulator=[f16(f32(x+y*coefficient)) for x,y in
                         zip(accumulator,v[token*128:(token+1)*128])]
            total=f32(f32(total*old_scale)+coefficient)
        outputs.extend(f32(x*f32(1.0/total)) for x in accumulator)
    return outputs


def subset(root, phase):
    require(phase in ('prefill','decode'),'Unknown phase')
    folder = root/phase/'block'
    items = [tensor(folder,n,k) for n,k in zip(TENSORS,('f32','f16','f16','f16','f32'))]
    (q,qd),(k,kd),(v,vd),(m,md),(g,gd) = items
    nq = 64 if phase == 'prefill' else 1
    visible = list(range(1,65)) if phase == 'prefill' else [
        next((i for i in range(m['shape'][0]) if struct.unpack_from('<H',md,i*2)[0] != 0),m['shape'][0])]
    data = dict(query=rows(q,qd,2,nq),key=rows(k,kd,1,k['shape'][1]),
                value=rows(v,vd,1,v['shape'][1]),mask=rows(m,md,1,nq))
    # GGML result is token-major [all_q_heads * D, query_tokens]. Retain heads
    # 0/1 for each query, not a contiguous prefix of the whole output tensor.
    data['golden'] = b''.join(gd[t*g['strides'][1]:t*g['strides'][1]+2*128*4]
                              for t in range(nq))
    high_precision = independent_attention(data['query'],data['key'],data['value'],visible)
    expected = high_precision if phase=='prefill' else independent_decode(
        data['query'],data['key'],data['value'],visible)
    gold = struct.unpack('<'+'f'*(len(data['golden'])//4),data['golden'])
    errors = [abs(a-b) for a,b in zip(gold,expected)]
    require(len(gold) == 2*nq*128 and all(math.isfinite(a) and
            abs(a-b) <= 2e-5+2e-5*abs(b) for a,b in zip(gold,expected)),
            'Captured golden differs from independently mapped F16 Attention')
    conversion = None
    if phase == 'decode':
        data['query_f16'] = b''.join(struct.pack('<e',x) for (x,) in struct.iter_unpack('<f',data['query']))
        require(all(math.isfinite(x) for (x,) in struct.iter_unpack('<e',data['query_f16'])),
                'Decode query conversion overflow')
        conversion = 'IEEE binary16 RNE reference; target conversion and CSR still require execution'
    return data,dict(phase=phase,query_tokens=nq,query_heads=2,kv_heads=1,
        head_dim=128,kv_capacity=k['shape'][1],visible_prefixes=visible,
        outputs=len(gold),mapped_head_indices=[0,1],mapped_kv_head_index=0,
        query_token_stride_bytes=512,query_head_stride_bytes=nq*512,
        key_value_token_stride_bytes=256,key_value_head_stride_bytes=k['shape'][1]*256,
        mask_token_stride_bytes=m['shape'][0]*2,output_token_stride_bytes=1024,
        independent_mapping_reference=('F64 dot and stable Softmax from captured F32 Q and F16 KV'
            if phase=='prefill' else 'Scalar F16 Q conversion and per-token F16 output recurrence with F32 Softmax state'),
        max_abs_mapping_error=max(errors),mapping_atol=2e-5,mapping_rtol=2e-5,
        f64_no_intermediate_rounding_max_abs_difference=max(abs(a-b) for a,b in zip(gold,high_precision)),
        native_numerical_reference=False,decode_query_conversion=conversion)


def prepare(output):
    out=output.absolute()
    require(out==out.resolve() and out.is_relative_to(RUNS),'Fresh sole verification output required')
    out.mkdir(parents=True,exist_ok=False)
    pins={};result=dict(state='PREPARING',rtl_executed=False,performance_measured=False,whole_model=False)
    try:
        bind(pins,CAPTURE/'result.json',CAPTURE_SHA)
        capture=json.loads((CAPTURE/'result.json').read_text())
        require(capture['state']=='REAL_QWEN3_F16_BOUNDARIES_CAPTURED_NOT_RTL_ACCEPTED' and
                capture['post_pins_match'] and not capture['hardware_cycles_measured'],
                'Wrong real capture receipt')
        bind(pins,CAPTURE/'source-pins.json',capture['source_pins_sha256'])
        for group in (json.loads((CAPTURE/'source-pins.json').read_text()),capture['artifacts']):
            for p,sha in group.items():bind(pins,p,sha)
        for p in (Path(__file__),HERE/'test_f16_native_data.py',HERE/'capture_f16_attention.py',
                  HERE/'audit.py'):bind(pins,p)
        phases=validate(CAPTURE/'capture')
        require(phases==capture['phases'],'Independent typed capture replay differs')
        # The captured JSON rounds scale to six digits. Bind the actual model
        # construction to the standard F32 1/sqrt(D), never silently parse it
        # as the exact binary operation parameter.
        scale_source=RUNS/'e2e_output_graph_20261106_01/llama/src/models/qwen3.cpp'
        bind(pins,scale_source,'06f400665980d30fd357886a5d14b541adda06d159a5b7f0ce929ca36788778c')
        text=scale_source.read_text()
        require('1.0f/sqrtf(float(n_embd_head))' in text,'Qwen3 scale construction changed')
        frozen=RUNS/'e2e_output_graph_20261106_01'
        bind(pins,frozen/'source-pins.json')
        inventory=json.loads((frozen/'source-pins.json').read_text())
        for name in ('ops.cpp','vec.h'):
            path=frozen/'llama/ggml/src/ggml-cpu'/name
            bind(pins,path,inventory[str(path)])
        records={};assembly=['.section .rodata.f16_real,"a",@progbits\n']
        for phase in ('prefill','decode'):
            data,record=subset(CAPTURE/'capture',phase);records[phase]=record
            for name,blob in data.items():
                path=out/(phase+'_'+name+'.bin');path.write_bytes(blob);bind(pins,path)
                symbol='f16_'+phase+'_'+name
                assembly.append(f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{path}"\n')
        (out/'data.S').write_text(''.join(assembly));bind(pins,out/'data.S')
        verify_pins(pins);(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        result.update(state='REAL_QWEN3_F16_SUBSETS_MAPPING_PASS_NOT_NATIVE_ACCEPTED',phases=records,
            capture_result_sha256=CAPTURE_SHA,scale_bits=SCALE_BITS,
            scale_source=str(scale_source),scale_binary_dump_available=False,
            scale_contract='F32 1/sqrt(128) from pinned Qwen3 graph source, not rounded JSON',
            source_pins_sha256=digest(out/'source-pins.json'),post_pins_match=True,
            limitations=['One KV group of real Prefill first64 queries and genuine Decode visible137',
                        'Exact subset bytes, but materialized contiguous head/query layout is not full GGML adapter timing',
                        'Independent GGML mapping references are not bit-exact native SDK recurrence oracles',
                        'No native admission, target completion, numerical or performance acceptance'])
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        if not (out/'source-pins.json').exists():
            (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        result['artifacts']={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name!='result.json'}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    prepare(p.parse_args().output)
