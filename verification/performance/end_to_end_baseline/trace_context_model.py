"""Mechanical sealed model fixture and strict cross-library full-logit comparison."""
import re
from collections import Counter

from audit import require
from check_output_model import check as original_check

SUITE = ('TRACE_CONTEXT_SUITE_PASS variants=2 comparisons=4 logits=607744 '
         'bytes_per_variant=2431060 performance=not_measured')


def fixture(source):
    anchor='\nint main() {'
    require(source.count(anchor)==1 and source.count('step < 3')==1,'Sealed fixture anchors')
    source=source[:source.index(anchor)].replace('step < 3','step < 2',1)
    unused='static void read(FILE *f, const void *p, size_t n)'
    require(unused not in source,'Unexpected const read declaration')
    reader='static void read(FILE *f, void *p, size_t n) { need(std::fread(p, 1, n, f) == n, "read"); }\n'
    require(source.count(reader)==1,'Original unused read helper')
    source=source.replace(reader,'',1)
    trace='env("GGML_RISCV_QBS_TRACE", "0")'
    require(source.count(trace)==1 and source.count('env("GGML_RISCV_QBS_TRACE_LIFETIME", "0")')==1,
            'Trace gate anchors')
    source=source.replace(trace,'env("GGML_RISCV_QBS_TRACE", "1")',1)
    return source+'''\nint main(int argc, char **argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0); std::setvbuf(stderr, nullptr, _IONBF, 0);
    need(argc == 2, "arguments");
    generate(1, argv[1]);
    return 0;
}
'''


PROJECTIONS = (('attn_q',2048,2048),('attn_v',2048,1024),('attn_k',2048,1024),
               ('attn_output',2048,2048),('ffn_gate',2048,6144),('ffn_up',2048,6144),('ffn_down',6144,2048))


def call_schema(weights,step):
    require(step in (0,1),'Model step')
    require(len(weights)==197 and len({row['tensor'] for row in weights})==197,'Model weight inventory')
    expected=[]
    for layer in range(28):
        for name,k,n in PROJECTIONS:
            row=weights[len(expected)]
            require(row['tensor']==f'blk.{layer}.{name}.weight' and row['k']==k and row['n']==n and
                    row['type'] in ('q4_K','q6_K'),'Model tensor schema')
            m=1 if step or (layer==27 and name.startswith('ffn_')) else 40
            expected.append(dict(type=row['type'],mode='gemv' if m==1 else 'gemm',k=k,input_rows=m,output_rows=n,split_k=0))
    row=weights[-1]
    require(row==dict(tensor='output.weight',k=2048,n=151936,type='q6_K'),'Model vocabulary schema')
    expected.append(dict(type='q6_K',mode='gemv',k=2048,input_rows=1,output_rows=151936,split_k=0))
    return expected


def check(text,control,weights):
    schema={step:call_schema(weights,step) for step in (0,1)}
    original_check(control)
    reference={}
    for m in re.finditer(r'^OUTPUT_MODEL_STEP enabled=1 kind=([01]) step=([01]) token=(\d+) fcsr=(\d+) vcsr=(\d+) outputs=151936$',
                         control.replace('\r',''),re.M):
        kind,step,token,fc,vc=map(int,m.groups());require((kind,step) not in reference,'Duplicate control step')
        reference[kind,step]=(token,fc,vc)
    require(len(reference)==4,'Incomplete accepted control')
    attention_reference=[];record=None
    for line in control.replace('\r','').splitlines():
        if line=='OUTPUT_MODEL_BEGIN enabled=1':record=0
        elif line=='OUTPUT_MODEL_END enabled=1':record=None
        elif record is not None:
            if line.startswith('OUTPUT_MODEL_STEP enabled=1 '):record+=1
            elif record in (0,1,3,4) and line.startswith(('GGML_RISCV_QUANT_PREFILL ','GGML_RISCV_QUANT_KV ',
                                                       'GGML_RISCV_QUANT_KV_')):attention_reference.append(line)
    lines=text.replace('\r','').splitlines();mode=None;begun=[];ended=[];steps=[[],[]]
    work=[[],[]];models=[[],[]];shapes=[[],[]];counts=[dict(prefill=0,decode=0,output=0,register=0,qbs=0) for _ in range(2)]
    comparisons=[];summaries=[[],[]];dot=[0,0];by_profile=[{},{}];coverage=[[],[]]
    require('TRACE_CONTEXT_MODEL_FAIL' not in text and 'OUTPUT_MODEL_FAIL' not in text and
            'Kernel panic' not in text and lines.count('GUEST_TEST_EXIT=0')==1,'Model/guest failure')
    for line in lines:
        if line.startswith('TRACE_CONTEXT_VARIANT_BEGIN '):
            m=re.fullmatch(r'TRACE_CONTEXT_VARIANT_BEGIN variant=([01])',line)
            require(m is not None and mode is None and int(m[1])==len(begun),'Variant order')
            mode=int(m[1]);begun.append(mode)
        elif line.startswith('TRACE_CONTEXT_VARIANT_END '):
            require(mode is not None and line==f'TRACE_CONTEXT_VARIANT_END variant={mode}','Variant end')
            ended.append(mode);mode=None
        elif line.startswith(('OUTPUT_MODEL_BEGIN ','OUTPUT_MODEL_END ')):
            require(mode is not None and line in ('OUTPUT_MODEL_BEGIN enabled=1','OUTPUT_MODEL_END enabled=1'),
                    'Wrong Attention choice');models[mode].append(line)
        elif line.startswith('OUTPUT_MODEL_SHAPE '):
            require(mode is not None and line=='OUTPUT_MODEL_SHAPE model=qwen3_1p7b prompt_tokens=40 n_ctx=128 n_batch=64',
                    'Model configuration changed');shapes[mode].append(line)
        elif line.startswith('OUTPUT_MODEL_STEP '):
            m=re.fullmatch(r'OUTPUT_MODEL_STEP enabled=1 kind=([01]) step=([01]) token=(\d+) fcsr=(\d+) vcsr=(\d+) outputs=151936',line)
            require(mode is not None and m is not None,'Model step scope');kind,step,token,fc,vc=map(int,m.groups())
            require((kind,step)==(len(steps[mode])//2,len(steps[mode])%2) and
                    (token,fc,vc)==reference[kind,step],'Token/CSR differs from accepted control')
            require(counts[mode]['prefill']==28*(kind+1) and counts[mode]['decode']==28*(kind+step) and
                    counts[mode]['qbs']==197*(len(steps[mode])+1),'Incomplete work at model step')
            steps[mode].append((kind,step,token,fc,vc))
        elif line.startswith(('GGML_RISCV_QUANT_PREFILL ','GGML_RISCV_QUANT_KV ', 'GGML_RISCV_QUANT_KV_')):
            require(mode is not None,'Attention outside variant');fields={}
            for word in line.split()[1:]:
                key,sep,value=word.partition('=')
                require(sep and key not in fields and value.isdecimal(),'Malformed Attention work');fields[key]=int(value)
            tag=line.split()[0]
            require(tag in ('GGML_RISCV_QUANT_PREFILL','GGML_RISCV_QUANT_KV','GGML_RISCV_QUANT_KV_OUTPUT_TILE',
                            'GGML_RISCV_QUANT_KV_REGISTER_PV','GGML_RISCV_QUANT_KV_LAYOUT','GGML_RISCV_QUANT_KV_PV'),
                    'Unrecognized Attention work evidence')
            if tag not in ('GGML_RISCV_QUANT_KV_LAYOUT','GGML_RISCV_QUANT_KV_PV'):
                require(fields.get('status')==0,'Attention failed')
            if tag.endswith('_OUTPUT_TILE') or tag.endswith('_REGISTER_PV'):
                output=tag.endswith('_OUTPUT_TILE')
                require(fields.get('enabled')==int(output) and fields.get('completed_groups',0)>0,'Attention route changed')
                counts[mode]['output' if output else 'register']+=1
            elif tag.endswith('_LAYOUT'):
                require(fields.get('selection')==0 and all(fields.get(k,0)>0 for k in
                    ('key_panels','key_bytes','workspace','k_token_stride','k_head_stride')),'KV layout work')
                counts[mode]['layout']=counts[mode].get('layout',0)+1
            elif tag.endswith('_PV'):
                require(fields.get('grouped')==0 and fields.get('completed_groups',0)>0,'PV route')
                counts[mode]['pv']=counts[mode].get('pv',0)+1
            else:
                require(fields.get('mapping')==0 and fields.get('memory')==1 and fields.get('runtime_called')==1,
                        'Attention admission changed')
                if tag.endswith('_PREFILL'):
                    require(fields.get('commands',0)>0 and fields.get('groups',0)>0 and fields.get('selection')==0,
                            'Prefill work');counts[mode]['prefill']+=1
                else:
                    require(fields.get('command_attempts',0)>0 and fields.get('groups',0)>0 and fields.get('executor_status')==0,
                            'Decode work');counts[mode]['decode']+=1
            work[mode].append(line)
        elif line.startswith('GGML_RISCV_QBS_CALL '):
            require(mode is not None,'Projection outside variant')
            m=re.fullmatch(r'GGML_RISCV_QBS_CALL type=q[46]_K mode=(?:gemv|gemm) k=(\d+) input_rows=(\d+) output_rows=(\d+) split_k=0',line)
            require(m is not None and all(int(v)>0 for v in m.groups()),'Projection route changed')
            fields=dict(word.split('=',1) for word in line.split()[1:])
            fields={key:int(value) if key not in ('type','mode') else value for key,value in fields.items()}
            step=len(steps[mode])%2;index=counts[mode]['qbs']-197*len(steps[mode])
            require(0<=index<197 and fields==schema[step][index],'Projection differs from sealed GGUF/graph schema')
            k,rows,n=int(m[1]),int(m[2]),int(m[3]);dot[mode]+=k*rows*n
            counter=by_profile[mode].setdefault(fields['type'],Counter())
            counter.update({fields['mode']+'_calls':1,'input_rows':rows,'output_rows':n,
                            'activation_elements':k*rows,'output_elements':rows*n,'dot_elements':k*rows*n,
                            'commands_m1':n//32 if rows==1 else 0,'commands_m4':rows//4*(n//32) if rows>1 else 0})
            if rows==1 and k<=4096:counter.update(eligible_context_calls=1,eligible_context_commands=n//32)
            counts[mode]['qbs']+=1;work[mode].append(line)
        elif line.startswith('GGML_RISCV_QBS_EXEC '):
            require(mode is not None,'Projection summary outside variant');fields={}
            for word in line.split()[1:]:
                key,sep,value=word.partition('=');require(sep and key not in fields,'Malformed projection summary')
                if key=='type':
                    require(value in ('Q4_K','Q6_K'),'Unknown projection profile')
                    fields[key]={'Q4_K':'q4_K','Q6_K':'q6_K'}[value]
                else:require(value.isdecimal(),'Projection summary not integer');fields[key]=int(value)
            require(fields['native_qbexec']>0 and fields['emulated_commands']==fields['segmented_commands']==fields['split_calls']==0 and
                    sum(fields[f'commands_m{i}'] for i in range(1,9))==fields['native_qbexec'] and
                    fields['command_dot_elements']==fields['dot_elements'],'Native command summary')
            summaries[mode].append(fields);work[mode].append(line)
        elif line.startswith('GGML_RISCV_QBS_COVERAGE '):
            require(mode is not None,'Coverage outside variant');fields={}
            for word in line.split()[1:]:
                key,sep,value=word.partition('=');require(sep and key not in fields,'Malformed QBS coverage')
                if key=='type':
                    require(value in ('Q4_K','Q6_K'),'Unexpected coverage profile')
                    fields[key]={'Q4_K':'q4_K','Q6_K':'q6_K'}[value]
                else:require(value.isdecimal(),'Coverage counter not integer');fields[key]=int(value)
            require(fields['candidate_tensors']>0 and 0<=fields['selected_tensors']<=fields['candidate_tensors'] and
                    0<=fields['selected_elements']<=fields['candidate_elements'],'Coverage bounds')
            coverage[mode].append(fields);work[mode].append(line)
        elif line.startswith('TRACE_CONTEXT_COMPARE '):comparisons.append(line)
    wanted=[f'TRACE_CONTEXT_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
            for k in range(2) for s in range(2)]
    require(mode is None and begun==ended==[0,1] and all(m==['OUTPUT_MODEL_BEGIN enabled=1','OUTPUT_MODEL_END enabled=1'] for m in models)
            and list(map(len,shapes))==[1,1] and list(map(len,steps))==[4,4] and steps[0]==steps[1],
            'Incomplete paired model execution')
    require(counts[0]==counts[1]==dict(prefill=56,decode=56,output=56,register=56,layout=56,pv=56,qbs=788) and work[0]==work[1],
            'Native work differs between libraries')
    require([s for s in work[0] if s.startswith(('GGML_RISCV_QUANT_PREFILL ','GGML_RISCV_QUANT_KV ',
                                               'GGML_RISCV_QUANT_KV_'))]==attention_reference,
            'Attention work differs from accepted control')
    for variant in range(2):
        require({s['type'] for s in summaries[variant]}=={'q4_K','q6_K'} and len(summaries[variant])==2 and
                sum(s['gemv_calls']+s['gemm_calls'] for s in summaries[variant])==788 and
                sum(s['dot_elements'] for s in summaries[variant])==dot[variant] and
                all(sum(s[key] for s in summaries[variant])>0 for key in ('commands_m1','commands_m4','context_fill','context_reuse','context_release')),
                'Projection summary does not match logical calls/contexts')
        require(len(coverage[variant])==2 and {c['type'] for c in coverage[variant]}=={'q4_K','q6_K'},'Missing tensor coverage')
        for row in summaries[variant]:
            counted=by_profile[variant][row['type']]
            for key in ('gemv_calls','gemm_calls','input_rows','output_rows','activation_elements','output_elements',
                        'dot_elements','commands_m1','commands_m4'):
                require(row.get(key)==counted[key],'Profile/mode summary differs from logical calls: '+key)
            require(row['context_fill']<=counted['eligible_context_calls'] and row['context_release']<=counted['eligible_context_calls'] and
                    row['context_fill']+row['context_reuse']+row['context_release']==counted['eligible_context_commands'],
                    'Context counts do not match eligible command work')
            require(all(row[f'commands_m{i}']==0 for i in (2,3,5,6,7,8)),'Unexpected command M')
    require(comparisons==wanted and lines.count(SUITE)==1,'Full-logit comparison incomplete')
    return dict(comparisons=4,logits_compared=607744,bytes_per_variant=2431060,prompt_tokens=40,decode_steps=1,
                kv_kinds=['q8_0/q8_0','q4_0/q8_0'],attention='output_tile',native_work_per_variant=counts[0],
                identical_full_logits=True,identical_tokens_and_csr=True,identical_native_work=True,
                native_summaries=summaries[0],tokens_and_csr_match_control=True,performance_measured=False)
