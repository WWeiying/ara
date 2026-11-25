#!/usr/bin/env python3
"""Capture actual model Attention at longer contexts; never measure RTL speed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

OUT=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
PRIOR=OUT/'e2e_qwen3_f16_attention_capture_20261106_01'
BIN=OUT/'akv-quantkv-host-capture-20261024-01/build/bin'
INPUTS=Path('/home/wangwy/fpga_runs/minimal_core_20261113_01')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):
            h.update(b)
    return h.hexdigest()


def save(path,value):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def capture(out,key,length):
    work=out/(key+'_'+str(length));work.mkdir()
    pinfile=PRIOR/'source-pins.json'
    prior=json.loads(pinfile.read_text())
    pins={}
    for path,expected in prior.items():
        p=Path(path)
        if p.parent==BIN:
            if sha(p)!=expected:
                raise ValueError('Frozen host capture binary/library drift: '+path)
            pins[path]=expected
    require={'llama-completion','libllama-completion-impl.so','libllama.so.0.0.10395',
             'libggml-cpu.so.0.19.0','libggml.so.0.19.0','libggml-base.so.0.19.0',
             'libllama-common.so.0.0.10395'}
    if {Path(p).name for p in pins}!=require:
        raise ValueError('Incomplete host binary/library provenance')
    identity=INPUTS/'measurement-build.json'
    original=json.loads(identity.read_text())
    info=original['models'][key];model=Path(info['path'])
    if sha(model)!=info['sha256']:
        raise ValueError('Model identity drift')
    prompt=INPUTS/'prompts'/f'{key}_{length}.json'
    value=json.loads(prompt.read_text())
    if sha(prompt)!=original['input_sha256'][prompt.name] or len(value['tokens'])!=length:
        raise ValueError('Prompt identity/token count')
    pins.update({str(model):sha(model),str(prompt):sha(prompt),str(identity):sha(identity),
                 str(pinfile):sha(pinfile),str(Path(__file__).resolve()):sha(__file__)})
    (work/'prompt.txt').write_text(value['prompt'])
    pins[str(work/'prompt.txt')]=sha(work/'prompt.txt')
    save(work/'source-pins.json',pins)
    command=[str(BIN/'llama-completion'),'-m',str(model),'-f',str(work/'prompt.txt'),
        '-n','2','-c','2048','-b','2048','-ub','2048','-t','8','-tb','8','-ngl','0',
        '-no-cnv','--load-mode','mmap','--no-warmup','--no-display-prompt',
        '--seed','1','--temp','0','-fa','on','-ctk','f16','-ctv','f16']
    env=dict(os.environ,LD_LIBRARY_PATH=str(BIN),LLAMA_Q4KM_CAPTURE_DIR=str(work/'capture'),
        LLAMA_Q4KM_CAPTURE_LAYER='0',LLAMA_Q4KM_CAPTURE_PROFILE='attention_core',
        GGML_RISCV_QBS='0',GGML_RISCV_AKV='0',GGML_RISCV_ACCEL_AUTO='0',
        GGML_RISCV_QBS_EMULATE='0',GGML_RISCV_AKV_EMULATE='0')
    save(work/'command.json',dict(argv=command,host_capture_only=True,
        expected_prompt_tokens=length,expected_decode_visible_tokens=length+1))
    report=dict(state='FAIL',rtl_executed=False,hardware_cycles_measured=False,
                model=key,model_sha256=info['sha256'],expected_prompt_tokens=length)
    with (work/'host.log').open('x') as f:
        proc=subprocess.Popen(command,env=env,stdout=f,stderr=subprocess.STDOUT,cwd=work)
        save(work/'status.json',dict(state='HOST_CAPTURE',child_pid=proc.pid))
        try:
            rc=proc.wait(timeout=600)
        except BaseException:
            proc.terminate();proc.wait(timeout=15);raise
    if rc:
        raise ValueError('Host capture exit '+str(rc))
    tensors={}
    for phase in ('prefill','decode'):
        block=work/'capture'/phase/'block'
        tensors[phase]={}
        for role in ('attn_q_input','attn_k_input','attn_v_input','attn_mask_input','kqv_out'):
            p=block/(role+'-0.json');meta=json.loads(p.read_text())
            payload=block/(role+'-0.bin')
            if payload.stat().st_size!=meta['nbytes']:
                raise ValueError('Tensor byte count '+str(payload))
            tensors[phase][role]=meta
        q=tensors[phase]['attn_q_input']
        if q['shape'][1]!=(length if phase=='prefill' else 1):
            raise ValueError('Captured query token count does not match requested workload')
    # The exported causal mask independently identifies the effective Decode prefix.
    import struct
    mask=work/'capture/decode/block/attn_mask_input-0.bin'
    raw=mask.read_bytes();vals=struct.unpack('<'+'e'*(len(raw)//2),raw)
    visible=sum(v!=float('-inf') for v in vals)
    if visible!=length+1 or any(v!=0 for v in vals[:visible]) or any(v!=float('-inf') for v in vals[visible:]):
        raise ValueError('Unexpected Decode visibility/mask')
    for name,expected in pins.items():
        if sha(name)!=expected:
            raise ValueError('Capture input drift: '+name)
    artifacts={str(p):sha(p) for p in work.rglob('*') if p.is_file() and p.name!='status.json'}
    report.update(state='REAL_MODEL_ATTENTION_CAPTURED_NOT_RTL_ACCEPTED',tensors=tensors,
        decode_visible_tokens=visible,post_pins_match=True,artifacts=artifacts,
        limitations=['Host outputs are model tensors/reference inputs, not RTL timing.',
                     'Capture metadata hardcodes an ISA label; actual execution is host CPU.',
                     'RTL replay must independently establish its numerical contract and actual paths.'])
    save(work/'result.json',report)
    save(work/'status.json',dict(state=report['state'],child_pid=None))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if out.parent!=OUT or not out.name.startswith('operator_real_contexts_20261115_'):
        raise ValueError('Wrong output scope')
    out.mkdir()
    report=dict(state='FAIL',completed=[],rtl_executed=False,hardware_cycles_measured=False)
    try:
        for key,length in (('qwen3',512),('qwen3',1024),('llama32',128)):
            capture(out,key,length);report['completed'].append(key+'_'+str(length))
            save(out/'status.json',dict(state='CAPTURING',completed=report['completed']))
        report['state']='REAL_CONTEXT_INPUTS_READY_NOT_RTL_ACCEPTED'
    except Exception as exc:
        report['error']=repr(exc)
    save(out/'result.json',report)
    save(out/'status.json',report)
    print(json.dumps(report),flush=True)
    return report['state']=='FAIL'


if __name__=='__main__':
    raise SystemExit(main())
