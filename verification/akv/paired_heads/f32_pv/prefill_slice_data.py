"""Exact-coordinate slice of a genuine Prefill capture; no quantization/model."""
import hashlib
import json
import math
from pathlib import Path
import struct

CAPTURE = Path('/home/wangwy/llama/captures/smollm2-135m-q4_k_m-prefill-m64-20260901')
SHAPES = {
    'attn_q_input-0':('f32',[64,64,9,1],[4,256,16384,147456],147456),
    'attn_k_input-0':('f16',[64,256,3,1],[2,128,32768,98304],98304),
    'attn_v_input-0':('f16',[64,256,3,1],[2,128,32768,98304],98304),
    'attn_mask_input-0':('f16',[256,64,1,1],[2,512,32768,32768],32768),
    'kqv_out-0':('f32',[576,64,1,1],[4,2304,147456,147456],147456)}


def require(ok,message):
    if not ok:
        raise ValueError(message)


def crop(blobs):
    require(set(blobs) == set(SHAPES),'Missing/extra source tensor')
    require(all(len(blobs[name]) == spec[3] for name,spec in SHAPES.items()),'Original tensor extents')
    query = b''.join(blobs['attn_q_input-0'][h*16384+t*256:h*16384+(t+1)*256]
                     for h in range(9) for t in range(32,36))
    mask = blobs['attn_mask_input-0'][32*512:36*512]
    golden = blobs['kqv_out-0'][32*2304:36*2304]
    result = dict(query=query,key=blobs['attn_k_input-0'],value=blobs['attn_v_input-0'],
                  mask=mask,golden=golden)
    require([len(result[n]) for n in ('query','key','value','mask','golden')] ==
            [9216,98304,98304,2048,9216],'Slice extents')
    for h in range(9):
        for local in range(4):
            for d in range(64):
                require(query[(h*4*64+local*64+d)*4:(h*4*64+local*64+d+1)*4] ==
                        blobs['attn_q_input-0'][(h*64*64+(local+32)*64+d)*4:
                                                  (h*64*64+(local+32)*64+d+1)*4],
                        'Query coordinate mismatch')
    for t in range(4):
        values = struct.unpack_from('<256H',mask,t*512)
        require(all(x == (0 if i < 33+t else 0xfc00) for i,x in enumerate(values)),
                'Original causal mask does not match positions32--35')
    return result


def load(capture=CAPTURE):
    capture = capture.resolve(strict=True)
    block = capture/'prefill/chunk-0/block'
    files,blobs = [],{}
    for name,(kind,shape,strides,size) in SHAPES.items():
        meta_path,binary = block/(name+'.json'),block/(name+'.bin')
        meta = json.loads(meta_path.read_text())
        require((meta['type'],meta['shape'],meta['strides'],meta['nbytes']) ==
                (kind,shape,strides,size),'Capture tensor geometry mismatch')
        blobs[name] = binary.read_bytes()
        files += [meta_path,binary]
        if name != 'attn_mask_input-0':
            require(all(math.isfinite(x) for (x,) in struct.iter_unpack('<f' if kind == 'f32' else '<e',blobs[name])),
                    'Nonfinite original tensor')
    case_path = capture/'replay/cases/operator/prefill/chunk_0/attention_core/case.json'
    case = json.loads(case_path.read_text())
    require(case['scale'] == .125 and case['atol'] == .004 and case['rtol'] == .002 and
            case['max_bias'] == 0 and case['logit_softcap'] == 0 and not case['v_transposed'],
            'Original numerical contract changed')
    expected = dict(head_dim=64,query_tokens=64,past_tokens=0,query_heads=9,kv_heads=3,gqa_rows=3)
    require(all(case['provenance'][k] == v for k,v in expected.items()),'Capture provenance mismatch')
    files.append(case_path)
    for name in ('run.conf','model.json','prompt.txt','completion.log'):
        path = capture/name
        if path.is_file():
            files.append(path)
    return crop(blobs),{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
