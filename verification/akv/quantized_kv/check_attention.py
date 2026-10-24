"""Strict whole-group ABBA transcript, original gold and actual QBS work gate."""
import math
import re
import struct

from batch_spec import Command
from check_batch_qk import check_command, schema, TERMINAL
from check_rvv_qbs import require

ORDER = (0, 1, 1, 0)
SUITE = 'QUANT_ATTN_SUITE_PASS trials=4 outputs=768 golden_tolerance=1 ordinary_repeats_exact=1'
RESULT = re.compile(r'QUANT_ATTN_RESULT trial=([0-3]) shared=([01]) cycles=([1-9][0-9]*) '
    r'calls=([0-9]+) values=([0-9]+) fcsr=([0-9]+) vcsr=5 '
    r'max_abs=([0-9a-f]{8}) pair_max_abs=([0-9a-f]{8}) pair_bits_differ=([0-9]+) errors=0 hex=([0-9a-f]+)')


def f32(bits):
    return struct.unpack('<f', struct.pack('<I', bits))[0]


def round32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def check_log(text, kind, golden, rtl):
    require(kind in (0, 1) and len(golden) == 6144, 'Wrong profile/golden tensor')
    gold = struct.unpack('<1536f', golden)[:768]
    require(all(math.isfinite(x) for x in gold), 'Nonfinite independent original gold')
    fields = schema(rtl)
    trials, records = [], []
    cap = active = suite = terminal = False
    group = []
    severity = set()
    capability = f'QUANT_ATTN_CAP kind={kind} heads=6 d=128 visible=128 kv_head=0 trials=4 scale=3db504f3'
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(match is not None and match[1] not in severity, 'UVM failure/duplicate')
            severity.add(match[1])
        if 'Core Test' in line:
            require(line == TERMINAL and suite and not terminal, 'Bad/premature core success')
            terminal = True
        if 'AKV_PERF' in line:
            raise ValueError('Unexpected F16 AKV work in quantized KV test')
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            require(active and ORDER[len(trials)] == 1 and len(group) < 8, 'Unexpected command outside shared call')
            require(re.fullmatch(r'\[QBS_PERF\](?: [a-z][a-z0-9_]*=[0-9]+)+', line) is not None, 'Malformed work')
            pairs = re.findall(r'([a-z][a-z0-9_]*)=([0-9]+)', line)
            require([k for k, _ in pairs] == fields, 'Work schema/duplicate mismatch')
            row = {k:int(v) for k, v in pairs}
            tile, local = divmod(len(group), 2)
            command = Command(kind, 0, 0 if local == 0 else 4, 4 if local == 0 else 2, tile*32, 32)
            check_command(row, command, len(records)+1)
            group.append(row)
            records.append(row)
        if 'QUANT_ATTN_' not in line:
            continue
        require(not terminal, 'Program record after termination')
        if line == capability:
            require(not cap and not trials and not active, 'Duplicate capabilities')
            cap = True
        elif line.startswith('QUANT_ATTN_BEGIN '):
            i = len(trials)
            require(cap and not suite and not active and i < 4 and
                    line == f'QUANT_ATTN_BEGIN trial={i} shared={ORDER[i]}', 'ABBA order/duplicate begin')
            active, group = True, []
        elif RESULT.fullmatch(line):
            match = RESULT.fullmatch(line)
            i = len(trials)
            require(active and i < 4 and (int(match[1]), int(match[2])) == (i, ORDER[i]) and
                    len(group) == (8 if ORDER[i] else 0), 'Result order/actual command count')
            require((int(match[4]), int(match[5])) == ((8, 128) if ORDER[i] else (768, 768)) and
                    int(match[6]) <= 31 and len(match[10]) == 768*8, 'Software work/FRM/output extent')
            bits = [int(match[10][n:n+8], 16) for n in range(0, len(match[10]), 8)]
            values = [f32(x) for x in bits]
            require(all(math.isfinite(x) for x in values), 'Nonfinite output')
            deltas = [round32(abs(round32(x-y))) for x, y in zip(values, gold)]
            require(all(d <= round32(round32(0.004)+round32(round32(0.002)*abs(y)))
                        for d, y in zip(deltas, gold)),
                    'Independent original model golden mismatch')
            require(f32(int(match[7], 16)) == max(deltas), 'Incorrect original-gold error metric')
            if trials:
                previous = [f32(x) for x in trials[0]['output_bits']]
                pair_delta = max(round32(abs(round32(x-y))) for x, y in zip(values, previous))
                differences = sum(x != y for x, y in zip(bits, trials[0]['output_bits']))
            else:
                pair_delta, differences = 0.0, 0
            require(f32(int(match[8], 16)) == pair_delta and int(match[9]) == differences,
                    'Incorrect paired numerical-difference metric')
            require(int(match[3]) >= sum(x['busy_cycles'] for x in group), 'Impossible timed work')
            trials.append(dict(trial=i, shared=ORDER[i], cycles=int(match[3]), fcsr=int(match[6]),
                vcsr=5, output_bits=bits, max_abs=max(deltas), pair_max_abs=pair_delta,
                pair_bits_differ=differences, qk_calls=int(match[4]), v_decodes=int(match[5])))
            active = False
        elif line == SUITE:
            require(cap and not active and len(trials) == 4 and not suite, 'Incomplete/duplicate suite')
            suite = True
        else:
            raise ValueError('Malformed/unknown quantized Attention evidence')
    require(cap and suite and terminal and not active and len(records) == 16 and
            severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete whole Attention transcript')
    for first, last in ((0, 3), (1, 2)):
        require(all(trials[first][key] == trials[last][key] for key in ('output_bits', 'fcsr', 'vcsr')),
                'Same-mode repetition differs')
    sums = {str(mode):sum(t['cycles'] for t in trials if t['shared'] == mode) for mode in (0, 1)}
    return dict(state='NUMERICAL_AND_WORK_CHECKED', trials=trials, hardware_records=records, sums=sums,
        speedup=sums['0']/sums['1'], cycle_reduction_percent=100*(1-sums['1']/sums['0']),
        max_pair_abs=max(t['pair_max_abs'] for t in trials),
        scope='Real complete six-head GQA group with reconstructed GGML schedule and original primitives, not model execution',
        independent_protocol_checked=False, deployment_approved=False)
