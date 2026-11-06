"""Check genuine post-prefill Decode inputs, not a relabelled Prefill row."""
from collections import Counter
import math
import re
import struct

from audit import require
from check_projection_capture import check as control_check

SOURCES = {'attn_norm-0':2048,'ffn_norm-0':2048,'ffn_swiglu-0':6144,'result_norm':2048}
PATTERN = ((2048,2048),(2048,1024),(2048,1024),(2048,2048),(2048,6144),(2048,6144),(6144,2048))


def fields(line):
    result = {}
    for word in line.split()[1:]:
        key,sep,value = word.partition('='); require(sep and key not in result,'Malformed Decode trace')
        result[key] = value
    return result


def check(text, original_projection_log):
    text = text.replace('\r',''); lines = text.splitlines()
    require('DECODE_CAPTURE_FAIL' not in text and 'Kernel panic' not in text and lines.count('GUEST_TEST_EXIT=0') == 1,
            'Decode capture/guest failure')
    begin = 'DECODE_CAPTURE_BEGIN prompt=40 token=22406 position=40 kv=q8_0 qbs=1'
    end = 'DECODE_CAPTURE_DONE sources=4 bytes=49152 stop=before_decode_vocabulary performance=not_measured'
    require(lines.count(begin) == lines.count(end) == 1,'Decode phase/terminal')
    original, control = control_check(original_projection_log)
    tokens = re.findall(r'^DECODE_CAPTURE_TOKENS count=40 ids=([0-9,]+)$',text,re.M)
    require(len(tokens) == 1 and list(map(int,tokens[0].split(','))) == control['token_ids'],'Prompt changed')
    start = text.index(begin); stop = text.index(end)
    require(text.index('DECODE_CAPTURE_TOKENS ') < start < stop,'Phase order')
    shapes = re.findall(r'^DECODE_CAPTURE_SHAPE source=(\S+) k=(\d+) rows=1 type=f32$',text,re.M)
    require(shapes == [(name,str(k)) for name,k in SOURCES.items()] and text.count('DECODE_CAPTURE_SHAPE ') == 4,
            'Decode source shapes')
    payloads = {}; previous = start
    for name,k in SOURCES.items():
        at = text.index('DECODE_CAPTURE_SHAPE source='+name+' '); require(previous < at,'Boundary order')
        matches = list(re.finditer(r'^DECODE_CAPTURE_DATA source='+re.escape(name)+r' offset=(\d+) bits=([0-9a-f]{128})$',text,re.M))
        require([int(m[1]) for m in matches] == list(range(0,k,16)) and at < matches[0].start(), 'Payload records')
        payload = b''.join(struct.pack('<I',int(m[2][i:i+8],16)) for m in matches for i in range(0,128,8))
        require(len(payload) == k*4 and all(math.isfinite(x[0]) for x in struct.iter_unpack('<f',payload)) and
                any(payload),'Invalid Decode input')
        previous = matches[-1].start(); payloads[name] = payload
    require(previous < stop and text.count('DECODE_CAPTURE_DATA ') == 768 and
            payloads['attn_norm-0'] != original[:8192],'Stale/relabelled Prefill data')
    require(not any(s.startswith(('GGML_RISCV_QBS_CALL ','GGML_RISCV_QBS_COMMAND '))
                    for s in text[:start].splitlines()),'Prefill commands mixed into Decode trace')
    calls = []; commands = 0; pending = None; received = 0; access = Counter()
    boundaries = {'attn_norm-0':(0,0),'ffn_norm-0':(4,192),'ffn_swiglu-0':(6,576),'result_norm':(196,17920)}
    for line in text[start:stop].splitlines():
        if line.startswith('DECODE_CAPTURE_SHAPE '):
            name = fields(line)['source']
            require((len(calls),commands) == boundaries[name] and (pending is None or received == pending[1]//32),
                    'Work outside capture boundary')
        elif line.startswith('GGML_RISCV_QBS_CALL '):
            require(pending is None or received == pending[1]//32,'Incomplete logical call')
            row = fields(line); index = len(calls)
            require(index < 196 and row['type'] in ('q4_K','q6_K') and row['mode'] == 'gemv' and
                    row['input_rows'] == '1' and row['split_k'] == '0','Wrong Decode call')
            pending = (int(row['k']),int(row['output_rows']),1 if row['type'] == 'q4_K' else 2)
            require(pending[:2] == PATTERN[index%7],'Wrong layer geometry')
            received = 0; calls.append(row)
        elif line.startswith('GGML_RISCV_QBS_COMMAND '):
            require(pending is not None,'Command outside call'); row = fields(line); commands += 1; received += 1
            k,n,profile = pending
            expected = dict(seq=commands,m=1,n=32,k_blocks=k//256,weight_profile=profile,activation_profile=1,
                            emulated=0,segmented=0)
            require(all(int(row[key]) == value for key,value in expected.items()) and received <= n//32,
                    'Wrong native command work')
            mode = int(row['access']); require(mode in (0,1,2,3) and (k <= 4096 or mode == 0),'Context eligibility')
            access[mode] += 1
    require(len(calls) == 196 and commands == 17920 and pending is not None and received == pending[1]//32 and
            sum(v for k,v in access.items() if k != 0) > 0,'Missing Decode work or activation-context path')
    prefill = [fields(s) for s in text[:start].splitlines() if s.startswith('GGML_RISCV_QUANT_PREFILL ')]
    decode = [fields(s) for s in text[start:stop].splitlines() if s.startswith('GGML_RISCV_QUANT_KV ')]
    output = [fields(s) for s in text[start:stop].splitlines() if s.startswith('GGML_RISCV_QUANT_KV_OUTPUT_TILE ')]
    require(len(prefill) == len(decode) == len(output) == 28 and
            all(r.get('status') == '0' and r.get('runtime_called') == '1' for r in (*prefill,*decode)) and
            all(r.get('status') == '0' and r.get('enabled') == '1' for r in output),'Actual Attention routes missing')
    return payloads,dict(phase='decode',prompt_tokens=40,input_token=22406,position=40,rows=1,sources=list(SOURCES),
                         complete_prefill_executed=True,complete_decode_executed=False,performance_measured=False,
                         native_projection_calls=196,native_projection_commands=17920,
                         activation_access_counts={str(k):v for k,v in sorted(access.items())},
                         input_differs_from_prefill=True,stop='before_decode_vocabulary')
