"""Strict compact ABBA/work check; full numerical checks run in the pinned ELF."""
import math
from pathlib import Path
import re
import shlex
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from batch_spec import Command
from check_batch_qk import check_command, schema, TERMINAL
from check_rvv_qbs import require

ORDER = (0, 1, 1, 0)
CAP = ('QUANT_GROUPED_CAP kind=q4_0 heads=6 d=128 visible=128 kv_head=0 trials=4 '
       'scale=3db504f3 k_token_stride=144 v_token_stride=272 workspace=13120')
SUITE = 'QUANT_GROUPED_SUITE_PASS trials=4 outputs=768 exact_all=1'
RESULT = re.compile(
    r'QUANT_GROUPED_RESULT trial=([0-3]) enabled=([01]) api=([01]) cycles=([1-9][0-9]*) '
    r'commands=8 values=128 panels=4 copied=9216 quantizations=6 map=0 status=0 selection=0 '
    r'groups=1 executor=0 fcsr=([0-9]+) vcsr=5 max_abs=([0-9a-f]{8}) differences=0 errors=0 '
    r'digest=([0-9a-f]{16})')


def check_log(text, golden, rtl, expected_argv=None):
    require(len(golden) == 6144, 'Original full golden extent')
    gold = struct.unpack('<1536f', golden)[:768]
    require(all(math.isfinite(v) for v in gold), 'Nonfinite gold')
    # Compact UART is not an independent recomputation of every result element.
    max_allowed = max(0.004 + 0.002 * abs(v) for v in gold)
    fields = schema(rtl)
    trials, records, group = [], [], []
    active = None
    cap = suite = terminal = header = False
    severity = set()
    for lineno, line in enumerate(text.splitlines()):
        if line.startswith('Command:'):
            require(lineno == 0 and not header and expected_argv is not None and
                    shlex.split(line[len('Command:'):].strip()) == list(map(str, expected_argv)),
                    'Unexpected command header')
            header = True
            continue
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(match is not None and match[1] not in severity, 'UVM error/duplicate')
            severity.add(match[1])
        if 'Core Test' in line:
            require(line == TERMINAL and suite and not terminal, 'Premature/invalid termination')
            terminal = True
        require('AKV_PERF' not in line and 'AKV_SUMMARY' not in line, 'Unexpected F16 work')
        if 'QBS_PERF' in line:
            require(not terminal and active is not None and len(group) < 8, 'Work outside active trial')
            require(re.fullmatch(r'\[QBS_PERF\](?: [a-z][a-z0-9_]*=[0-9]+)+', line) is not None,
                    'Malformed work')
            pairs = re.findall(r'([a-z][a-z0-9_]*)=([0-9]+)', line)
            require([k for k, _ in pairs] == fields, 'Work schema mismatch')
            row = {k: int(v) for k, v in pairs}
            tile, local = divmod(len(group), 2)
            check_command(row, Command(1, 0, 4 if local else 0, 2 if local else 4, tile*32, 32), len(records)+1)
            group.append(row)
            records.append(row)
        if 'QUANT_' not in line:
            continue
        require(not terminal and not suite, 'Program evidence after suite/terminal')
        if line == CAP:
            require(not cap and not trials and active is None, 'Duplicate/late capability')
            cap = True
        elif line.startswith('QUANT_GROUPED_BEGIN'):
            i = len(trials)
            require(cap and active is None and i < 4 and
                    line == f'QUANT_GROUPED_BEGIN trial={i} enabled={ORDER[i]} api={ORDER[i]}', 'Wrong ABBA order/API')
            active, group = i, []
        elif RESULT.fullmatch(line):
            m = RESULT.fullmatch(line)
            i = int(m[1])
            require(active == i == len(trials) and int(m[2]) == int(m[3]) == ORDER[i] and len(group) == 8,
                    'Result order/API/work')
            error = struct.unpack('<f', bytes.fromhex(m[6])[::-1])[0]
            require(math.isfinite(error) and 0 <= error <= max_allowed + 1e-7, 'Invalid error metric')
            require(int(m[5]) <= 31 and int(m[4]) >= sum(r['busy_cycles'] for r in group), 'CSR/busy bound')
            row = dict(trial=i, enabled=ORDER[i], api=ORDER[i], cycles=int(m[4]), fcsr=int(m[5]),
                       vcsr=5, max_abs_bits=m[6], digest=m[7], qbs_busy_cycles=sum(r['busy_cycles'] for r in group),
                       commands=8, values=128, panels=4, copied=9216, quantizations=6)
            require(not trials or all(row[k] == trials[0][k] for k in ('fcsr', 'vcsr', 'digest', 'max_abs_bits')),
                    'Cross-mode output/CSR metric differs')
            trials.append(row)
            active = None
        elif line == SUITE:
            require(cap and active is None and len(trials) == 4, 'Incomplete suite')
            suite = True
        else:
            raise ValueError('Unknown/malformed program evidence')
    require(cap and suite and terminal and active is None and len(records) == 32 and
            severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete transcript')
    sums = {str(mode): sum(t['cycles'] for t in trials if t['enabled'] == mode) for mode in (0, 1)}
    return dict(state='COMPACT_ABBA_AND_WORK_CHECKED', trials=trials, hardware_records=records,
                sums=sums, speedup=sums['0']/sums['1'], same_elf=True,
                on_target_full_numerical_checks=True, independent_host_output_recompute=False,
                independent_protocol_checked=False, hardware_only=False, whole_model=False,
                deployment_approved=False)
