"""Strict Qwen3 model-pair audit: logits, phases, routes and native work."""
import re
from audit import require


def check(text):
    mode=None;begun=[];ended=[];steps={0:[],1:[]};prefill={0:[],1:[]};decode={0:[],1:[]}
    output={0:[],1:[]};register={0:[],1:[]};comparisons=[];shapes=[]
    lines=text.replace('\r','').splitlines()
    for line in lines:
        if line.startswith('OUTPUT_MODEL_BEGIN '):
            require(mode is None,'Nested model')
            m=re.fullmatch(r'OUTPUT_MODEL_BEGIN enabled=([01])',line);require(m is not None,'Model begin')
            mode=int(m[1]);require(mode==len(begun),'Model order');begun.append(mode)
        elif line.startswith('OUTPUT_MODEL_END '):
            require(mode is not None and line==f'OUTPUT_MODEL_END enabled={mode}','Model end')
            ended.append(mode);mode=None
        elif line.startswith('OUTPUT_MODEL_SHAPE '):
            m=re.fullmatch(r'OUTPUT_MODEL_SHAPE model=qwen3_1p7b prompt_tokens=(\d+) n_ctx=128 n_batch=64',line)
            require(mode is not None and m is not None and 33<=int(m[1])<=64,'Model shape');shapes.append(int(m[1]))
        elif line.startswith('OUTPUT_MODEL_STEP '):
            m=re.fullmatch(r'OUTPUT_MODEL_STEP enabled=([01]) kind=([01]) step=([012]) token=(\d+) fcsr=(\d+) vcsr=(\d+) outputs=151936',line)
            require(mode is not None and m is not None and int(m[1])==mode,'Model step identity')
            kind,step,token,fc,vc=map(int,m.groups()[1:]);index=len(steps[mode])
            require((kind,step)==(index//3,index%3) and fc<=31 and fc&8 and vc<=7,'Step/CSR sequence')
            steps[mode].append((kind,step,token,fc,vc))
        elif line.startswith(('GGML_RISCV_QUANT_PREFILL ','GGML_RISCV_QUANT_KV ',
                              'GGML_RISCV_QUANT_KV_OUTPUT_TILE ','GGML_RISCV_QUANT_KV_REGISTER_PV ')):
            require(mode is not None,'Native work outside model')
            tag=line.split()[0];fields={}
            for word in line.split()[1:]:
                k,sep,v=word.partition('=');require(sep and v.isdecimal() and k not in fields,'Malformed native work')
                fields[k]=int(v)
            require(fields.get('status')==0,'Rejected/failed expected fast path')
            if tag.endswith('_OUTPUT_TILE') or tag.endswith('_REGISTER_PV'):
                selected=mode if tag.endswith('_OUTPUT_TILE') else 1-mode
                require(fields.get('enabled')==selected and fields.get('completed_groups',0)>0,'Wrong Decode route')
                (output if tag.endswith('_OUTPUT_TILE') else register)[mode].append(fields['completed_groups'])
            else:
                require(fields.get('mapping')==0 and fields.get('memory')==1 and fields.get('runtime_called')==1,'Mapping/memory admission')
                if tag.endswith('_PREFILL'):
                    require(fields.get('selection')==0 and fields.get('commands',0)>0 and fields.get('groups',0)>0,'Prefill activity')
                    prefill[mode].append(fields)
                else:
                    require(fields.get('command_attempts',0)>0 and fields.get('groups',0)>0 and fields.get('executor_status')==0,'Decode activity')
                    decode[mode].append(fields)
        elif line.startswith('OUTPUT_MODEL_COMPARE '):comparisons.append(line)
    expected=[f'OUTPUT_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1' for k in range(2) for s in range(3)]
    require(mode is None and begun==ended==[0,1] and len(shapes)==2 and shapes[0]==shapes[1],'Incomplete paired models')
    require(len(steps[0])==6 and steps[0]==steps[1],'Token/CSR streams differ')
    require(len(prefill[0])==len(prefill[1])==56 and prefill[0]==prefill[1],'Prefill changed or missing')
    require(len(decode[0])==len(decode[1])==112 and decode[0]==decode[1],'Decode work changed or missing')
    require(len(output[0])==len(output[1])==len(register[0])==len(register[1])==112 and
            output[0]==output[1]==register[0]==register[1],'Decode route coverage incomplete')
    require(comparisons==expected and lines.count('OUTPUT_MODEL_SUITE_PASS comparisons=6 performance=not_measured')==1 and
            lines.count('GUEST_TEST_EXIT=0')==1 and 'OUTPUT_MODEL_FAIL' not in text and 'Kernel panic' not in text,'Numerical/guest verdict')
    return dict(state='PAIRED_QWEN3_MODEL_PASS',logits_compared=911616,comparisons=6,
                prompt_tokens=shapes[0],prefill_calls_per_mode=56,decode_calls_per_mode=112,
                identical_tokens_and_csr=True,identical_native_work=True,performance_measured=False)
