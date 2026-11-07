#!/usr/bin/env python3
"""Capture genuine F16 KV model boundaries; never estimate RTL cycles from host time."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import struct
import subprocess

from audit import digest, require, verify_pins
from prepare_wide_soc import RUNS, HERE
from run_supply_sdk import bind

HOST = RUNS/'akv-quantkv-host-capture-20261024-01'
MODEL = Path('/home/wangwy/llama/models/Qwen3-1.7B-Q4_K_M.gguf')
MODEL_SHA = 'd2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5'
BINARY_SHA = '5802d4feaaf3b4afff1bd67f9b76896c54813f6a8a572a86b266824cdae4a2b5'
ARTIFACTS_SHA = '8d1b9aa5bf0bb346e88fdd7f165836acd30cf927be8ed1c4e63c583c13960bed'
PROMPT = (
    'Explain how a processor can accelerate language model inference without building a separate large accelerator. '
    'Discuss the different behavior of prompt processing and token generation, the reuse of model weights, '
    'and the purpose of the key and value cache. Describe how vector arithmetic, local storage, memory bandwidth, '
    'and software scheduling work together. Explain why faster matrix multiplication alone does not guarantee '
    'the same improvement for the whole application. Include the costs of normalization, positional encoding, '
    'attention, and activation preparation. Finally, describe how a hardware designer should compare two '
    'implementations fairly, check their numerical results, and use measured execution stages to decide where '
    'to invest a limited amount of additional hardware. Give a structured answer with concrete examples.'
)
TENSORS = ('attn_q_input-0','attn_k_input-0','attn_v_input-0','attn_mask_input-0','kqv_out-0')


def tensor(folder,name,kind):
    meta=json.loads((folder/(name+'.json')).read_text());raw=(folder/(name+'.bin')).read_bytes()
    require(meta['type']==kind and len(raw)==meta['nbytes'],'Tensor type/byte mismatch: '+name)
    shape,strides=meta['shape'],meta['strides'];size=4 if kind=='f32' else 2
    require(len(shape)==len(strides)==4 and all(type(n) is int and n>0 for n in shape) and
            all(type(s) is int and s>=size and s%size==0 for s in strides) and strides[0]==size and
            len(raw)==size+sum((n-1)*s for n,s in zip(shape,strides)),
            'Malformed tensor extent/strides: '+name)
    return meta,raw


def finite_rows(meta,raw,rows):
    size=4 if meta['type']=='f32' else 2;fmt='<f' if size==4 else '<e'
    require(0<rows<=meta['shape'][1],'Invalid visible row count')
    for batch in range(meta['shape'][3]):
        for head in range(meta['shape'][2]):
            for row in range(rows):
                start=batch*meta['strides'][3]+head*meta['strides'][2]+row*meta['strides'][1]
                for d in range(meta['shape'][0]):
                    require(math.isfinite(struct.unpack_from(fmt,raw,start+d*size)[0]),
                            'Nonfinite active tensor data')


def validate(folder):
    phases={}
    for phase in ('prefill','decode'):
        root=folder/phase/'block'
        values={n:tensor(root,n,k) for n,k in zip(TENSORS,('f32','f16','f16','f16','f32'))}
        q,qd=values[TENSORS[0]];k,kd=values[TENSORS[1]];v,vd=values[TENSORS[2]]
        mask,md=values[TENSORS[3]];gold,gd=values[TENSORS[4]]
        queries=q['shape'][1];capacity=k['shape'][1]
        require(q['shape']==[128,queries,16,1] and k['shape']==v['shape']==[128,capacity,8,1] and
                64<=capacity<=512 and mask['shape'][0]==capacity and mask['shape'][1]>=queries and
                mask['shape'][2:]==[1,1] and gold['shape']==[2048,queries,1,1],
                'Not the requested Qwen3 F16 Attention geometry')
        require((64<=queries<=256) if phase=='prefill' else queries==1,'Wrong execution phase/query length')
        visible=[]
        for row in range(queries):
            bits=struct.unpack_from('<'+'H'*capacity,md,row*mask['strides'][1])
            count=0
            while count<capacity and bits[count]==0:count+=1
            require(count>0 and all(b==0xfc00 for b in bits[count:]),'Not a zero/-Inf causal prefix')
            visible.append(count)
        if phase=='prefill':require(visible==list(range(1,queries+1)),'Not a genuine first Prefill chunk')
        finite_rows(q,qd,queries);finite_rows(gold,gd,queries)
        finite_rows(k,kd,max(visible));finite_rows(v,vd,max(visible))
        params=json.loads((root/'attention_params-0.json').read_text())
        require(params['op']=='FLASH_ATTN_EXT' and params['max_bias']==params['logit_softcap']==0 and
                abs(params['scale']-1/math.sqrt(128))<1e-6,'Unexpected Attention features')
        phases[phase]=dict(query_shape=q['shape'],key_shape=k['shape'],value_shape=v['shape'],
            output_shape=gold['shape'],visible_prefixes=visible,
            tensor_layouts={name:meta for name,(meta,raw) in values.items()},parameters=params)
    require(phases['decode']['visible_prefixes']==[phases['prefill']['query_shape'][1]+1],
            'Decode does not follow the captured Prefill and first generated token')
    return phases


def run(output):
    out=output.absolute();require(out==out.resolve() and out.is_relative_to(RUNS),'Fresh verification output required')
    out.mkdir(parents=True,exist_ok=False)
    result=dict(state='PREPARING',child_pid=None,source='Host llama.cpp actual model execution',
                hardware_cycles_measured=False,rtl_executed=False,backend_admission_accepted=False)
    pins={};commands=[]
    def save():(out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    try:
        bind(pins,HOST/'build-artifacts.json',ARTIFACTS_SHA)
        for path,sha in json.loads((HOST/'build-artifacts.json').read_text()).items():bind(pins,path,sha)
        binary=HOST/'build/bin/llama-completion';bind(pins,binary,BINARY_SHA);bind(pins,MODEL,MODEL_SHA)
        for path in (Path(__file__),HERE/'test_capture_f16_attention.py'):bind(pins,path)
        capture=out/'capture';capture.mkdir()
        (out/'prompt.txt').write_text(PROMPT+'\n');bind(pins,out/'prompt.txt')
        argv=list(map(str,[binary,'-m',MODEL,'-p',PROMPT,'-n','2','-c','512','-b','512','-ub','512',
            '-t','8','-tb','8','-no-cnv','--load-mode','mmap','--no-warmup','--no-display-prompt',
            '--seed','1','--temp','0','-fa','on','-ctk','f16','-ctv','f16']))
        env={k:v for k,v in os.environ.items() if not k.startswith(('GGML_RISCV_','LLAMA_Q4KM_CAPTURE',
             'AKV_','LLAMA_ATTN_ROT_')) and k not in ('LD_PRELOAD','LD_LIBRARY_PATH')}
        env.update(LD_LIBRARY_PATH=str(HOST/'build/bin'),LLAMA_Q4KM_CAPTURE_DIR=str(capture),
                   LLAMA_Q4KM_CAPTURE_LAYER='0',LLAMA_Q4KM_CAPTURE_PROFILE='attention_core')
        commands.append(dict(argv=argv,timeout_seconds=300,
            capture_environment={k:v for k,v in env.items() if k.startswith('LLAMA_Q4KM_CAPTURE')}))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        verify_pins(pins);(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        with (out/'capture.log').open('xb') as stream:
            child=subprocess.Popen(argv,cwd=out,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            result.update(state='CAPTURING_REAL_F16_PREFILL_AND_DECODE',child_pid=child.pid);save()
            try:code=child.wait(timeout=300)
            except BaseException:
                os.killpg(child.pid,signal.SIGKILL);child.wait();raise
        result['child_pid']=None;commands[-1]['returncode']=code
        require(code==0,'Model capture failed; retain log')
        phases=validate(capture);verify_pins(pins)
        result.update(state='REAL_QWEN3_F16_BOUNDARIES_CAPTURED_NOT_RTL_ACCEPTED',phases=phases,
            post_pins_match=True,model_sha256=MODEL_SHA,binary_sha256=BINARY_SHA,
            source_pins_sha256=digest(out/'source-pins.json'),
            limitations=['Actual host model tensors, not ISA/RTL output or a timing reference',
                'F16 post-cache operands captured directly; never dequantized from quantized captures',
                'First native 64-query block is a future slice, not the complete captured Prefill node',
                'Rounded Attention parameter JSON is not a bit-exact binary op-parameter dump',
                'Numerical replay, native admission, target completion and performance remain separate'])
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        save();(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        result['artifacts']={str(p):digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('result.json','status.json')}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    def stop(sig,_frame):raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,stop)
    run(p.parse_args().output)
