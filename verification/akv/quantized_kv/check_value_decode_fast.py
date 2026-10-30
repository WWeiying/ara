"""Strict full-workload V decode evidence; scalar bit comparisons plus word hash."""
import math
import re
import struct

from check_rvv_qbs import require
from check_value_decode import BOUNDARY, TERMINAL, ORDER

CAP = 'QUANT_VALUE_FAST_CAP profiles=2 heads=2 visible=128 capacity=256 d=128 trials=8 hash=word_fnv64'
SUITE = 'QUANT_VALUE_FAST_SUITE_PASS trials=8 actual_outputs=262144 finite_boundary_outputs=3584 exact=1'
RESULT = re.compile(r'QUANT_VALUE_FAST_RESULT kind=([01]) trial=([0-3]) optimized=([01]) '
    r'cycles=([1-9][0-9]*) outputs=32768 fcsr=0 vcsr=5 compared=32768 errors=0')
HASH = re.compile(r'QUANT_VALUE_FAST_HASH kind=([01]) outputs=32768 hash=([0-9a-f]{16})')


def expected_hash(data):
    require(len(data) == 69632, 'Wrong original V extent')
    value = 14695981039346656037
    for head in range(2):
        for token in range(128):
            for block in range(4):
                start = (head * 256 + token) * 136 + block * 34
                scale = struct.unpack_from('<e', data, start)[0]
                require(math.isfinite(scale), 'Nonfinite visible scale')
                for (integer,) in struct.iter_unpack('b', data[start+2:start+34]):
                    word = struct.unpack('<I', struct.pack('<f', scale * integer))[0]
                    value = ((value ^ word) * 1099511628211) & ((1 << 64) - 1)
    return f'{value:016x}'


def check_log(text, values):
    require(len(values) == 2, 'Both actual model V tensors required')
    expected = [expected_hash(data) for data in values]
    trials, hashes, severity = [], [], set()
    cap = boundary = active = suite = terminal = False
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(match is not None and match[1] not in severity, 'UVM failure/duplicate')
            severity.add(match[1])
        if 'Core Test' in line:
            require(line == TERMINAL and suite and not terminal, 'Bad/premature terminal')
            terminal = True
        require('QBS_PERF' not in line and 'AKV_PERF' not in line, 'Unrelated custom work')
        if 'QUANT_VALUE_' not in line:
            continue
        require(not terminal, 'Record after termination')
        if line == CAP:
            require(not cap and not trials, 'Duplicate capability declaration')
            cap = True
        elif line == BOUNDARY:
            require(cap and not boundary and not trials and not active, 'Boundary order/duplicate')
            boundary = True
        elif line.startswith('QUANT_VALUE_FAST_BEGIN '):
            index = len(trials)
            kind, trial = divmod(index, 4)
            require(cap and boundary and not active and not suite and index < 8 and
                    len(hashes) == kind and line ==
                    f'QUANT_VALUE_FAST_BEGIN kind={kind} trial={trial} optimized={ORDER[trial]}',
                    'Wrong ABBA begin or missing previous capture hash')
            active = True
        elif RESULT.fullmatch(line):
            match = RESULT.fullmatch(line)
            index = len(trials)
            kind, trial = divmod(index, 4)
            require(active and index < 8 and tuple(map(int, match.groups()[:3])) ==
                    (kind, trial, ORDER[trial]), 'Wrong trial')
            trials.append(dict(kind=kind, trial=trial, optimized=ORDER[trial],
                               cycles=int(match[4]), compared=32768, fcsr=0, vcsr=5))
            active = False
        elif HASH.fullmatch(line):
            match = HASH.fullmatch(line)
            kind = len(hashes)
            require(not active and not suite and kind < 2 and len(trials) == 4*(kind+1) and
                    int(match[1]) == kind and match[2] == expected[kind],
                    'Wrong/missing/duplicate independent reference word hash')
            hashes.append(match[2])
        elif line == SUITE:
            require(len(trials) == 8 and len(hashes) == 2 and not active and not suite,
                    'Incomplete/duplicate suite')
            suite = True
        else:
            raise ValueError('Malformed/unknown V-decode evidence')
    require(cap and boundary and suite and terminal and not active and
            severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete transcript')
    performance = []
    for kind in range(2):
        sums = {str(mode): sum(t['cycles'] for t in trials if t['kind'] == kind and
                              t['optimized'] == mode) for mode in (0, 1)}
        performance.append(dict(kind=kind, sums=sums, speedup=sums['0']/sums['1'],
                               cycle_reduction_percent=100*(1-sums['1']/sums['0'])))
    return dict(state='NUMERICAL_AND_TIMING_CHECKED', trials=trials, performance=performance,
                independent_host_hashes=hashes, hash_algorithm='word_fnv64',
                boundary_elements=3584, model_speedup_claimed=False,
                scope='Full finite Q8_0 V decode workload; scalar per-word equality, not full Attention')
