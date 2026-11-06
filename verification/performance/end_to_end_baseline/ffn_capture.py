"""Decode first-layer FFN inputs and audit the preceding real native work."""
import math
import re
import struct

from audit import require
from check_projection_capture import check as check_projection

SOURCES = {'attn_norm-0': 2048, 'ffn_norm-0': 2048, 'ffn_swiglu-0': 6144}


def environment(model_source):
    start = '    env("GGML_RISCV_QBS", "1");'
    end = '    std::printf("OUTPUT_MODEL_BEGIN enabled=%u\\n", mode);'
    require(model_source.count(start) == model_source.count(end) == 1, 'Environment anchors')
    block = model_source[model_source.index(start):model_source.index(end)]
    # Command lines require both the aggregate trace and lifetime trace gates.
    for key in ('GGML_RISCV_QBS_TRACE', 'GGML_RISCV_QBS_TRACE_LIFETIME'):
        old = 'env("'+key+'", "0")'
        require(block.count(old) == 1, 'Trace anchor: '+key)
        block = block.replace(old, 'env("'+key+'", "1")')
    # Use the accepted output-tile choice. Only tracing is changed.
    return 'static void configure_capture() {\n    constexpr unsigned mode = 1;\n'+block+'}\n'


def check(text, original_projection_log):
    text = text.replace('\r', '')
    require('FFN_CAPTURE_FAIL' not in text and 'Kernel panic' not in text and
            text.splitlines().count('GUEST_TEST_EXIT=0') == 1, 'Capture/guest failure')
    require(text.splitlines().count('FFN_CAPTURE_SCOPE model=qwen3_1p7b layer=0 qbs=1 kv=q8_0 trace=1') == 1 and
            text.splitlines().count('FFN_CAPTURE_DONE sources=3 bytes=163840 stop=before_first_down performance=not_measured') == 1,
            'Capture scope/terminal')
    tokens = re.findall(r'^FFN_CAPTURE_TOKENS count=40 ids=([0-9,]+)$', text, re.M)
    _, original = check_projection(original_projection_log)
    require(len(tokens) == 1 and list(map(int, tokens[0].split(','))) == original['token_ids'], 'Prompt changed')
    shapes = re.findall(r'^FFN_CAPTURE_SHAPE source=(\S+) k=(\d+) rows=4 tokens=40 type=f32$', text, re.M)
    require(shapes == [(source, str(k)) for source, k in SOURCES.items()] and
            text.count('FFN_CAPTURE_SHAPE ') == 3, 'Capture boundaries')
    payloads = {}
    first = text.index('FFN_CAPTURE_TOKENS ')
    for source, k in SOURCES.items():
        shape = text.index(f'FFN_CAPTURE_SHAPE source={source} ')
        require(first < shape, 'Capture order')
        rows = re.findall(r'^FFN_CAPTURE_DATA source='+re.escape(source)+r' row=(\d+) offset=(\d+) bits=([0-9a-f]{128})$', text, re.M)
        require([(int(r), int(o)) for r, o, _ in rows] == [(r, o) for r in range(4) for o in range(0, k, 16)],
                'Missing/reordered/extra payload')
        payload = b''.join(struct.pack('<I', int(bits[i:i+8], 16)) for _, _, bits in rows for i in range(0, 128, 8))
        require(len(payload) == k*16 and all(math.isfinite(x[0]) for x in struct.iter_unpack('<f', payload)) and
                len({payload[r*k*4:(r+1)*k*4] for r in range(4)}) == 4, 'Invalid or repeated activation rows')
        positions = [m.start() for m in re.finditer(r'^FFN_CAPTURE_DATA source='+re.escape(source)+r' ', text, re.M)]
        require(len(positions) == len(rows) and shape < positions[0], 'Malformed payload records')
        first = positions[-1]; payloads[source] = payload
    require(text.count('FFN_CAPTURE_DATA ') == 2560 and first < text.index('FFN_CAPTURE_DONE '), 'Payload extent')
    prior, _ = check_projection(original_projection_log)
    require(payloads['attn_norm-0'] == prior, 'First QKV boundary changed')
    # Actual native work before the capture stops: Q,V,K,Wo,gate,up for 40 rows.
    calls = []
    commands = []
    for line in text.splitlines():
        if line.startswith('FFN_CAPTURE_SHAPE '):
            source = line.split('source=',1)[1].split()[0]
            expected = {'attn_norm-0': (0,0), 'ffn_norm-0': (4,1920), 'ffn_swiglu-0': (6,5760)}[source]
            require((len(calls),len(commands)) == expected, 'Native work outside its source-defined boundary')
        if line.startswith(('GGML_RISCV_QBS_CALL ', 'GGML_RISCV_QBS_COMMAND ')):
            row = dict(v.split('=', 1) for v in line.split()[1:])
            (calls if line.startswith('GGML_RISCV_QBS_CALL ') else commands).append(row)
    require([(r['type'], r['mode'], int(r['k']), int(r['input_rows']), int(r['output_rows']), int(r['split_k']))
             for r in calls] == [('q4_K','gemm',2048,40,2048,0),('q6_K','gemm',2048,40,1024,0),
                                 ('q4_K','gemm',2048,40,1024,0),('q4_K','gemm',2048,40,2048,0),
                                 ('q4_K','gemm',2048,40,6144,0),('q4_K','gemm',2048,40,6144,0)],
            'Wrong projection path before FFN capture')
    profiles = ['1']*640+['2']*320+['1']*4800
    require(len(commands) == 5760 and all(int(c['seq']) == i+1 and c['emulated'] == c['segmented'] == '0' and
            c['m'] == '4' and c['n'] == '32' and c['k_blocks'] == '8' and c['weight_profile'] == profiles[i] and
            c['activation_profile'] == '1' and c['access'] == '0' for i, c in enumerate(commands)),
            'Wrong native projection work')
    prefill = [line for line in text.splitlines() if line.startswith('GGML_RISCV_QUANT_PREFILL ')]
    require(len(prefill) == 1 and 'status=0 ' in prefill[0] and 'runtime_called=1 ' in prefill[0], 'Native Attention missing')
    return payloads, dict(sources=list(SOURCES), rows=4, tokens=40, native_projection_commands=5760,
                          qkv_boundary_bitwise_unchanged=True, complete_model_executed=False,
                          performance_measured=False, kv='q8_0', runtime_path='native_qbs_and_grouped_prefill')
