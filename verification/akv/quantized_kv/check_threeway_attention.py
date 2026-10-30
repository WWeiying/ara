"""Check raw H/S/B work, original model gold, flags and same-ELF repeats."""
import math
import re
import struct

from batch_spec import Command
from check_attention import f32, round32
from check_batch_qk import check_command, schema, TERMINAL
from check_rvv_qbs import require

ORDER = (0, 1, 2, 2, 1, 0)
SUITE = 'QUANT_THREEWAY_SUITE_PASS trials=6 outputs=768 rvv_exact=1 repeats_exact=1'
RESULT = re.compile(
    r'QUANT_THREEWAY_RESULT trial=([0-5]) mode=([0-2]) cycles=([1-9][0-9]*) '
    r'calls=([0-9]+) dots=([0-9]+) commands=([0-9]+) values=([0-9]+) '
    r'panels=([0-9]+) copied=([0-9]+) quantizations=6 map=0 status=0 selection=0 '
    r'groups=([01]) executor=0 fcsr=([0-9]+) vcsr=5 max_abs=([0-9a-f]{8}) '
    r'pair_max_abs=([0-9a-f]{8}) pair_bits_differ=([0-9]+) errors=0 hex=([0-9a-f]+)')


def capability(kind):
    return (f'QUANT_THREEWAY_CAP kind={kind} heads=6 d=128 visible=128 kv_head=0 '
            f'trials=6 scale=3db504f3 k_token_stride={144 if kind else 272} '
            'v_token_stride=272 workspace=13120')


def check_log(text, kind, golden, rtl):
    require(kind in (0, 1) and len(golden) == 6144, 'Wrong format/model golden extent')
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
        require('AKV_PERF' not in line, 'Unexpected F16 AKV command')
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            require(not terminal and active is not None and ORDER[active] == 2 and len(group) < 8,
                    'QBS command outside native trial')
            require(re.fullmatch(r'\[QBS_PERF\](?: [a-z][a-z0-9_]*=[0-9]+)+', line) is not None,
                    'Malformed native work')
            pairs = re.findall(r'([a-z][a-z0-9_]*)=([0-9]+)', line)
            require([k for k, _ in pairs] == fields, 'Native work schema mismatch')
            row = {k: int(v) for k, v in pairs}
            tile, local = divmod(len(group), 2)
            command = Command(kind, 0, 4 if local else 0, 2 if local else 4, tile * 32, 32)
            check_command(row, command, len(records) + 1)
            records.append(row)
            group.append(row)
        if 'QUANT_ATTN_' in line or 'QUANT_STRIDED_' in line or 'QUANT_COMMON_' in line:
            raise ValueError('Predecessor transcript cannot substitute for a three-way run')
        if 'QUANT_THREEWAY_' not in line:
            continue
        require(not terminal, 'Program evidence after termination')
        if line == capability(kind):
            require(not cap and not trials and active is None, 'Duplicate/late capability')
            cap = True
        elif line.startswith('QUANT_THREEWAY_BEGIN '):
            i = len(trials)
            require(cap and not suite and active is None and i < 6 and
                    line == f'QUANT_THREEWAY_BEGIN trial={i} mode={ORDER[i]}', 'Wrong mirrored order')
            active, group = i, []
        elif RESULT.fullmatch(line):
            m = RESULT.fullmatch(line)
            i, mode = int(m[1]), int(m[2])
            require(active == i == len(trials) and mode == ORDER[i], 'Unexpected trial result')
            work = tuple(int(m[j]) for j in range(4, 11))
            expected = (8, 0, 8, 128, 4, 128 * (72 if kind else 136), 1) if mode == 2 else (
                768 if mode == 0 else 8, 768, 0, 768 if mode == 0 else 128, 0, 0, 0)
            require(work == expected and len(group) == (8 if mode == 2 else 0), 'Incorrect actual work')
            require(int(m[11]) <= 31 and len(m[15]) == 768 * 8, 'Wrong flags/output extent')
            bits = [int(m[15][n:n+8], 16) for n in range(0, len(m[15]), 8)]
            values = [f32(x) for x in bits]
            require(all(math.isfinite(x) for x in values), 'Nonfinite output')
            deltas = [round32(abs(round32(x-y))) for x, y in zip(values, gold)]
            require(all(d <= round32(round32(0.004) + round32(round32(0.002)*abs(g)))
                        for d, g in zip(deltas, gold)), 'Original model golden mismatch')
            require(f32(int(m[12], 16)) == max(deltas), 'Wrong golden error metric')
            if trials:
                base = trials[0]['output_bits']
                pair = max(round32(abs(round32(x-f32(y)))) for x, y in zip(values, base))
                differences = sum(x != y for x, y in zip(bits, base))
                require(int(m[11]) == trials[0]['fcsr'], 'Cross-mode flags differ')
            else:
                pair, differences = 0.0, 0
            require(f32(int(m[13], 16)) == pair and int(m[14]) == differences, 'Wrong paired error metric')
            require(mode == 2 or differences == 0, 'Shared RVV changed head-major arithmetic')
            require(int(m[3]) >= sum(r['busy_cycles'] for r in group), 'Busy exceeds full call')
            trials.append(dict(trial=i, mode=mode, cycles=int(m[3]), fcsr=int(m[11]), vcsr=5,
                               output_bits=bits, qbs_busy_cycles=sum(r['busy_cycles'] for r in group),
                               calls=work[0], dots=work[1], commands=work[2], values=work[3],
                               panels=work[4], copied=work[5], quantizations=6))
            active = None
        elif line == SUITE:
            require(cap and active is None and len(trials) == 6 and not suite, 'Incomplete/duplicate suite')
            suite = True
        else:
            raise ValueError('Malformed/unknown three-way evidence')
    require(cap and suite and terminal and active is None and len(records) == 16 and
            severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete three-way transcript')
    for first, last in ((0, 5), (1, 4), (2, 3)):
        require(all(trials[first][key] == trials[last][key] for key in ('output_bits', 'fcsr', 'vcsr')),
                'Same-mode repetition differs')
    sums = {str(mode): sum(t['cycles'] for t in trials if t['mode'] == mode) for mode in range(3)}
    return dict(state='THREEWAY_NUMERICAL_AND_WORK_CHECKED', trials=trials, hardware_records=records,
                sums=sums, shared_schedule_speedup=sums['0']/sums['1'],
                qbs_incremental_speedup=sums['1']/sums['2'], combined_speedup=sums['0']/sums['2'],
                same_elf=True, original_golden_checked=True, hardware_only=False, whole_model=False,
                independent_protocol_checked=False, deployment_approved=False)
