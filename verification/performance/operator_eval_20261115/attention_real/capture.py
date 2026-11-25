"""Exact strided captured operands; no synthetic KV or prefix golden reuse."""
import json
import math
import struct
from pathlib import Path

from contract import OUT, require, sha

ORIGINAL = OUT/'e2e_qwen3_f16_attention_capture_20261106_01'
LONG = OUT/'operator_real_contexts_20261115_01'


def read_capture(directory, heads=(0,1)):
    directory = Path(directory).resolve(strict=True)
    require(directory == ORIGINAL or directory in [LONG/x for x in
            ('qwen3_512','qwen3_1024','llama32_128')], 'Unregistered real capture')
    receipt = json.loads((directory/'result.json').read_text())
    require(receipt['state'] in ('REAL_QWEN3_F16_BOUNDARIES_CAPTURED_NOT_RTL_ACCEPTED',
            'REAL_MODEL_ATTENTION_CAPTURED_NOT_RTL_ACCEPTED') and
            receipt['post_pins_match'] and not receipt['rtl_executed'] and
            not receipt['hardware_cycles_measured'], 'Capture not complete/host-only')
    inventory = receipt['artifacts']
    pins = {str(directory/'result.json'):sha(directory/'result.json')}

    def read(path):
        require(inventory.get(str(path)) == sha(path), 'Captured identity: '+str(path))
        pins[str(path)] = inventory[str(path)]
        return path.read_bytes()

    source_pins = json.loads(read(directory/'source-pins.json'))
    # Pin original identity inventories and actual model bytes, but never
    # inherit historical mutable source/RTL as this successor's inputs.
    model_pins = {p:h for p,h in source_pins.items() if p.endswith('.gguf')}
    require(len(model_pins) == 1 and next(iter(model_pins.values())) ==
            receipt['model_sha256'], 'Missing model identity')
    for p,h in model_pins.items():
        require(sha(p) == h, 'Captured model drift')
        pins[p] = h
    model = json.loads(read(directory/'capture/model.json'))
    block = directory/'capture/decode/block'
    params = json.loads(read(block/'attention_params-0.json'))
    tensors = {}
    for role,typ in (('attn_q_input','f32'),('attn_k_input','f16'),
                     ('attn_v_input','f16'),('attn_mask_input','f16'),('kqv_out','f32')):
        meta = json.loads(read(block/(role+'-0.json')))
        raw = read(block/(role+'-0.bin'))
        require(meta['type'] == typ and len(raw) == meta['nbytes'] and
                len(meta['shape']) == len(meta['strides']) == 4 and
                meta['shape'][3] == 1, 'Tensor type/size/batch')
        tensors[role] = meta,raw
    qm,q = tensors['attn_q_input']; km,k = tensors['attn_k_input']
    vm,v = tensors['attn_v_input']; mm,m = tensors['attn_mask_input']
    gm,gold = tensors['kqv_out']
    d,_,nh,_ = qm['shape']; capacity = km['shape'][1]; nk = km['shape'][2]
    require(d in (64,128) and qm['shape'][1] == 1 and nh % nk == 0 and
            km['shape'] == vm['shape'] == [d,capacity,nk,1] and
            gm['shape'] == [d*nh,1,1,1] and mm['shape'] == [capacity,1,1,1] and
            qm['strides'][0] == 4 and km['strides'][0] == vm['strides'][0] ==
            mm['strides'][0] == 2 and gm['strides'][0] == 4, 'Captured Decode geometry')
    ratio = nh//nk
    require(len(heads) == 2 and heads[1] == heads[0]+1 and heads[0] % ratio == 0 and
            0 <= heads[0] < heads[1] < nh and heads[0]//ratio == heads[1]//ratio,
            'Need two consecutive genuine query heads sharing one KV head')
    kg = heads[0]//ratio
    mask = b''.join(m[t*mm['strides'][0]:t*mm['strides'][0]+2] for t in range(capacity))
    maskbits = struct.unpack('<'+'H'*capacity,mask)
    tokens = next((i for i,b in enumerate(maskbits) if b == 0xfc00),capacity)
    require(tokens > 0 and all(b == 0 for b in maskbits[:tokens]) and
            all(b == 0xfc00 for b in maskbits[tokens:]), 'Full causal mask required')
    visible = receipt.get('decode_visible_tokens',receipt.get('phases',{}).get(
        'decode',{}).get('visible_prefixes',[None])[0])
    require(tokens == visible, 'Mask/receipt visible context disagreement')
    require(params['op'] == 'FLASH_ATTN_EXT' and params['max_bias'] == 0 and
            params['logit_softcap'] == 0 and abs(params['scale']-1/math.sqrt(d)) < 1e-7,
            'Plain model scale/bias/softcap')
    scale = struct.unpack('<I',struct.pack('<f',1/math.sqrt(d)))[0]
    data = dict(query=b''.join(q[h*qm['strides'][2]:h*qm['strides'][2]+d*4]+
                              bytes((128-d)*4) for h in heads), mask=mask)
    for role,meta,raw in (('key',km,k),('value',vm,v)):
        data[role] = b''.join(raw[kg*meta['strides'][2]+t*meta['strides'][1]:
            kg*meta['strides'][2]+t*meta['strides'][1]+d*2]+bytes((128-d)*2)
            for t in range(capacity))
    data['model_golden'] = b''.join(gold[h*d*4:(h+1)*d*4] for h in heads)
    provenance = dict(capture=str(directory),model_name=model['metadata']['general.name'],
        model_sha256=receipt['model_sha256'],model_path=next(iter(model_pins)),layer=0,
        phase='decode',captured_query_heads=nh,captured_kv_heads=nk,
        captured_gqa=ratio,query_head_indices=list(heads),kv_head_index=kg,
        visible_tokens=tokens,physical_capacity=capacity,dimension=d,
        scale_bits=scale,scale_source='Known model exact 1/sqrt(D), rounded once to F32; NOT rounded JSON',
        exported_scale_rounded=params['scale'],full_visible_kv=True,full_original_mask=True,
        kv_repetition=False,query_rotation=False,source_pins_sha256=sha(directory/'source-pins.json'))
    case = dict(id=directory.name+'_h%d_%d' % heads,suite='real_model',dimension=d,
        heads=2,kv_heads=1,tokens=tokens,capacity=capacity,initial_flags=8,
        scale_bits=scale,original_t137=directory == ORIGINAL and heads == (0,1),
        provenance=provenance)
    return case,data,pins


def model_error(bits, captured, atol=0.003, rtol=0.02):
    actual = struct.unpack('<'+'f'*len(bits),struct.pack('<'+'I'*len(bits),*bits))
    expected = struct.unpack('<'+'f'*len(bits),captured)
    errors = [abs(a-b) for a,b in zip(actual,expected)]
    bad = [i for i,(a,b) in enumerate(zip(actual,expected))
           if not (math.isfinite(a) and math.isfinite(b) and abs(a-b) <= atol+rtol*abs(b))]
    return dict(atol=atol,rtol=rtol,values=len(bits),max_abs_error=max(errors),
        failures=bad,all_outputs_within_tolerance=not bad,
        contract='Every output abs(actual-model)<=atol+rtol*abs(model); never bit-exact GGML')
