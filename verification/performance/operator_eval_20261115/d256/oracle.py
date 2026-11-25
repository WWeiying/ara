"""Real captured operands, token-order independent reference and fixed model tolerance."""
import json
import math
import struct
from contract import CAPTURE,require,sha,fnv
from arithmetic import Arithmetic,value


def pack(values,width):return b''.join(x.to_bytes(width//8,'little') for x in values)
def unpack(raw,width):return list(struct.unpack('<'+{16:'H',32:'I'}[width]*(len(raw)//(width//8)),raw))


def capture():
    casepath=CAPTURE/'replay/cases/operator/decode/attention_core/case.json'
    case=json.loads(casepath.read_text());selection=json.loads((CAPTURE/'selection.json').read_text())
    require(case['scale']==1.0 and case['atol']==0.004 and case['rtol']==0.002 and
        not case['max_bias'] and not case['logit_softcap'] and not case['v_transposed'],
        'Original scale/features/tolerance changed')
    require(all(selection[k]==v for k,v in dict(source_head_dim=256,source_query_heads=4,
        source_kv_heads=1,selected_kv_head=0,selected_query_head_begin=0,selected_query_heads=4,
        physical_kv_capacity=256).items()),'Original head mapping changed')
    full=CAPTURE.parent/'gemma3-1b-q4km-attention-d256-full-meta-20260901'
    pins={str(p):sha(p) for p in (casepath,CAPTURE/'selection.json',CAPTURE/'model.json')}
    data={}
    for role,label,width,shape,strides in (
        ('query','attn_q_input',32,[256,1,4,1],[4,1024,1024,4096]),
        ('key','attn_k_input',16,[256,256,1,1],[2,512,131072,131072]),
        ('value','attn_v_input',16,[256,256,1,1],[2,512,131072,131072]),
        ('mask','attn_mask_input',16,[256,1,1,1],[2,512,512,512]),
        ('model','kqv_out',32,[1024,1,1,1],[4,4096,4096,4096])):
        p=CAPTURE/'decode/block'/(label+'-0.json');m=json.loads(p.read_text());raw=p.with_suffix('.bin').read_bytes()
        require(m['type']==('f32' if width==32 else 'f16') and m['shape']==shape and m['strides']==strides and
            m['nbytes']==len(raw) and len(raw)==math.prod(shape)*width//8,'Captured geometry: '+role)
        for q in (p,p.with_suffix('.bin')):pins[str(q)]=sha(q)
        origin=full/'decode/block'/p.with_suffix('.bin').name
        require(origin.read_bytes()==raw,'Selected data differs from complete original capture: '+role)
        pins[str(origin)]=sha(origin);data[role]=raw
    params=CAPTURE/'decode/block/attention_params-0.json';p=json.loads(params.read_text())
    require(p['op']=='FLASH_ATTN_EXT' and p['scale']==1 and p['max_bias']==p['logit_softcap']==0,
            'Captured exact scale/features')
    pins[str(params)]=sha(params)
    mask=unpack(data['mask'],16)
    require(mask[:17]==[0]*17 and mask[17:]==[0xfc00]*239,'All 17 effective K and original full causal mask required')
    return data,pins


def reference(data,sf):
    require(unpack(data['mask'],16)==[0]*17+[0xfc00]*239,'Reference requires unchanged full captured mask')
    a=Arithmetic(sf);q32=unpack(data['query'],32);k=unpack(data['key'],16);v=unpack(data['value'],16)
    require(len(q32)==1024 and len(k)==len(v)==65536 and
        all(x&0x7f800000!=0x7f800000 for x in q32) and
        all(x&0x7c00!=0x7c00 for x in k[:4352]+v[:4352]),'Finite real operand geometry required')
    q16=[a.cast(32,16,x) for x in q32];q=[a.cast(16,32,x) for x in q16]
    output=[];stages=[];max_updates=[]
    for h in range(4):
        initial=a.flags;scores=[]
        for t in range(17):
            dot=0
            for d in range(256):dot=a.op('fma',32,q[h*256+d],a.cast(16,32,k[t*256+d]),dot)
            scores.append(a.add(a.op('mul',32,dot,0x3f800000),0))
        stages.append(dict(head=h,phase='QK',sticky_delta=a.flags&~initial))
        maximum=0xff800000;exponents=[];scales=[];updates=[]
        for t,score in enumerate(scores):
            scale=0x3f800000
            if value(score)>value(maximum):
                scale=a.expf(a.sub(maximum,score));maximum=score;updates.append(t)
            scales.append(scale);exponents.append(a.sub(score,maximum))
        weights=[a.vector_exp(x) for x in exponents]
        total=0
        for weight,scale in zip(weights,scales):total=a.add(a.op('mul',32,total,scale),weight)
        acc=[0]*256;rescale_fmas=0
        for t in range(17):
            if scales[t]!=0x3f800000:
                acc=[a.cast(32,16,a.op('mul',32,a.cast(16,32,x),scales[t])) for x in acc]
            if weights[t]:
                acc=[a.cast(32,16,a.op('fma',32,a.cast(16,32,x),weights[t],a.cast(16,32,old)))
                    for x,old in zip(v[t*256:(t+1)*256],acc)]
                rescale_fmas+=256
        inverse=a.op('div',32,0x3f800000,total)
        output.extend(a.op('mul',32,a.cast(16,32,x),inverse) for x in acc)
        stages.append(dict(head=h,phase='PV',fma_elements=rescale_fmas,weight_zero_tokens=weights.count(0)))
        max_updates.append(updates)
    expected=unpack(data['model'],32);errors=[abs(value(x)-value(y)) for x,y in zip(output,expected)]
    failures=[i for i,(x,y) in enumerate(zip(output,expected)) if not (math.isfinite(value(x)) and
        math.isfinite(value(y)) and abs(value(x)-value(y))<=0.004+0.002*abs(value(y)))]
    require(not failures,'Independent D256 schedule fails original model tolerance: '+str(failures[:16]))
    return dict(bits=output,query_half=pack(q16,16).hex(),natural_flags=a.flags,expected_fcsr=a.flags|8,
        output_hash=fnv(pack(output,32)),stages=stages,max_update_tokens=max_updates,expf_samples=a.exp_samples,
        model_comparison=dict(atol=0.004,rtol=0.002,values=1024,failures=failures,max_abs_error=max(errors),
            max_tolerance_ratio=max(e/(0.004+0.002*abs(value(y))) for e,y in zip(errors,expected))),
        qk_fmas=4*17*256,pv_fmas=4*17*256,vector_exp_fmas=8*4*17,
        schedule='F16 query; dimension-ordered F32 QK; token-order online max/F32 rescale and sum; vector exp; F32-weight/FMA then F16 narrowing PV; F32 normalization')
