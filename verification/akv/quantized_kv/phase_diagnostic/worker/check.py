"""Strict three-call diagnostic only; never substitutes for six-call acceptance."""
import math
import re
import struct

from batch_spec import Command
from check_attention import f32, round32
from check_batch_qk import check_command, schema, TERMINAL
from check_rvv_qbs import require

ORDER = (0, 1, 2)
PREFIX = 'QUANT_DIAG_HSB_'
SUITE = PREFIX + 'SUITE_PASS trials=3 outputs=768 rvv_exact=1 repeat_checks=0'
RESULT = re.compile(
    PREFIX + r'RESULT trial=([0-2]) mode=([0-2]) cycles=([1-9][0-9]*) '
    r'calls=([0-9]+) dots=([0-9]+) commands=([0-9]+) values=([0-9]+) '
    r'panels=([0-9]+) copied=([0-9]+) quantizations=6 map=0 status=0 selection=0 '
    r'groups=([01]) executor=0 fcsr=([0-9]+) vcsr=5 max_abs=([0-9a-f]{8}) '
    r'pair_max_abs=([0-9a-f]{8}) pair_bits_differ=([0-9]+) errors=0 hex=([0-9a-f]+)')


def capability():
    return (PREFIX + 'CAP kind=1 heads=6 d=128 visible=128 kv_head=0 trials=3 '
            'scale=3db504f3 k_token_stride=144 v_token_stride=272 workspace=13120')


def check_log(text, golden, rtl):
    require(len(golden) == 6144, 'Wrong real model golden extent')
    gold = struct.unpack('<1536f', golden)[:768]
    require(all(math.isfinite(x) for x in gold), 'Nonfinite model golden')
    fields = schema(rtl)
    trials, records, group = [], [], []
    cap = suite = terminal = False
    active = None
    severity = set()
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(match is not None and match[1] not in severity, 'UVM failure/duplicate')
            severity.add(match[1])
        if 'Core Test' in line:
            require(line == TERMINAL and suite and not terminal, 'Premature/invalid termination')
            terminal = True
        require('AKV_PERF' not in line, 'Unexpected F16 command')
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            require(not terminal and active == 2 and len(group) < 8, 'QBS outside B')
            require(re.fullmatch(r'\[QBS_PERF\](?: [a-z][a-z0-9_]*=[0-9]+)+', line) is not None,
                    'Malformed native work')
            pairs = re.findall(r'([a-z][a-z0-9_]*)=([0-9]+)', line)
            require([k for k, _ in pairs] == fields, 'Native work schema mismatch')
            row = {k: int(v) for k, v in pairs}
            tile, local = divmod(len(group), 2)
            check_command(row, Command(1, 0, 4 if local else 0, 2 if local else 4, tile*32, 32),
                          len(records)+1)
            records.append(row)
            group.append(row)
        if any(p in line for p in ('QUANT_THREEWAY_', 'QUANT_ATTN_', 'QUANT_STRIDED_', 'QUANT_COMMON_')):
            raise ValueError('Predecessor transcript cannot substitute for diagnostic')
        if PREFIX not in line:
            continue
        require(not terminal, 'Evidence after termination')
        if line == capability():
            require(not cap and not trials and active is None, 'Duplicate/late capability')
            cap = True
        elif line.startswith(PREFIX+'BEGIN '):
            i = len(trials)
            require(cap and not suite and active is None and i < 3 and
                    line == f'{PREFIX}BEGIN trial={i} mode={i}', 'Wrong diagnostic order')
            active, group = i, []
        elif RESULT.fullmatch(line):
            m = RESULT.fullmatch(line)
            i, mode = int(m[1]), int(m[2])
            require(active == i == mode == len(trials), 'Unexpected trial result')
            work = tuple(int(m[j]) for j in range(4, 11))
            expected = ((8, 0, 8, 128, 4, 9216, 1) if mode == 2 else
                        (768 if mode == 0 else 8, 768, 0, 768 if mode == 0 else 128, 0, 0, 0))
            require(work == expected and len(group) == (8 if mode == 2 else 0), 'Incorrect actual work')
            require(int(m[11]) <= 31 and len(m[15]) == 768*8, 'Wrong flags/output extent')
            bits = [int(m[15][n:n+8], 16) for n in range(0, len(m[15]), 8)]
            values = [f32(x) for x in bits]
            require(all(math.isfinite(x) for x in values), 'Nonfinite output')
            deltas = [round32(abs(round32(x-y))) for x, y in zip(values, gold)]
            require(all(d <= round32(round32(0.004)+round32(round32(0.002)*abs(g)))
                        for d, g in zip(deltas, gold)), 'Original model golden mismatch')
            require(f32(int(m[12], 16)) == max(deltas), 'Wrong golden error metric')
            if trials:
                base = trials[0]['output_bits']
                pair = max(round32(abs(round32(x-f32(y)))) for x, y in zip(values, base))
                differences = sum(x != y for x, y in zip(bits, base))
                require(int(m[11]) == trials[0]['fcsr'], 'Cross-mode flags differ')
            else:
                pair, differences = 0.0, 0
            require(f32(int(m[13], 16)) == pair and int(m[14]) == differences, 'Wrong paired metric')
            require(mode == 2 or differences == 0, 'Shared RVV changed arithmetic')
            busy = sum(r['busy_cycles'] for r in group)
            require(int(m[3]) >= busy, 'Busy exceeds full call')
            trials.append(dict(trial=i, mode=mode, cycles=int(m[3]), fcsr=int(m[11]), vcsr=5,
                               output_bits=bits, qbs_busy_cycles=busy, calls=work[0], dots=work[1],
                               commands=work[2], values=work[3], panels=work[4], copied=work[5],
                               quantizations=6))
            active = None
        elif line == SUITE:
            require(cap and active is None and len(trials) == 3 and not suite, 'Incomplete/duplicate suite')
            suite = True
        else:
            raise ValueError('Malformed/unknown diagnostic evidence')
    require(cap and suite and terminal and active is None and len(records) == 8 and
            severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete diagnostic transcript')
    return dict(state='DIAGNOSTIC_NUMERICAL_AND_WORK_CHECKED', trials=trials,
                hardware_records=records, original_golden_checked=True, diagnostic_only=True,
                repeat_checks=0, performance_acceptance=False)
