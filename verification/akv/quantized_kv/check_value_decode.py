"""Independent finite-Q8_0 output hash plus strict ABBA/native completion gate."""
import math
import re
import struct

from check_rvv_qbs import require

CAP = 'QUANT_VALUE_CAP profiles=2 heads=2 visible=128 capacity=256 d=128 trials=8'
BOUNDARY = 'QUANT_VALUE_BOUNDARY scales=14 signed_bytes=256 outputs=3584 exact=1 errors=0'
SUITE = 'QUANT_VALUE_SUITE_PASS trials=8 actual_outputs=262144 finite_boundary_outputs=3584 exact=1'
TERMINAL = 'Core Test *** SUCCESS *** (tohost = 0)'
ORDER = (0, 1, 1, 0)
RESULT = re.compile(r'QUANT_VALUE_RESULT kind=([01]) trial=([0-3]) optimized=([01]) '
    r'cycles=([1-9][0-9]*) outputs=32768 fcsr=0 vcsr=5 hash=([0-9a-f]{16}) errors=0')


def update_hash(value, data):
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return value


def expected_hash(data):
    require(len(data) == 69632, 'Wrong original V extent')
    value = 14695981039346656037
    for head in range(2):
        for token in range(128):
            first = (head * 256 + token) * 136
            for block in range(4):
                start = first + block * 34
                scale = struct.unpack_from('<e', data, start)[0]
                require(math.isfinite(scale), 'Nonfinite visible scale')
                for (integer,) in struct.iter_unpack('b', data[start+2:start+34]):
                    # Half precision * signed-eight-bit is exact in double and
                    # F32, including signed zero. No reduction/order assumption.
                    value = update_hash(value, struct.pack('<f', scale * integer))
    return f'{value:016x}'


def check_log(text, values):
    require(len(values) == 2, 'Both actual model V tensors required')
    hashes = [expected_hash(data) for data in values]
    trials = []
    cap = boundary = active = suite = terminal = False
    severity = set()
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
        require(not terminal, 'Program record after termination')
        if line == CAP:
            require(not cap and not trials, 'Duplicate capability declaration')
            cap = True
        elif line == BOUNDARY:
            require(cap and not boundary and not active and not trials, 'Boundary order/duplicate')
            boundary = True
        elif line.startswith('QUANT_VALUE_BEGIN '):
            index = len(trials)
            kind, trial = divmod(index, 4)
            require(cap and boundary and not active and not suite and index < 8 and
                line == f'QUANT_VALUE_BEGIN kind={kind} trial={trial} optimized={ORDER[trial]}', 'Wrong ABBA begin')
            active = True
        elif RESULT.fullmatch(line):
            match = RESULT.fullmatch(line)
            index = len(trials)
            kind, trial = divmod(index, 4)
            require(active and index < 8 and tuple(map(int, match.groups()[:3])) ==
                    (kind, trial, ORDER[trial]) and match[5] == hashes[kind],
                    'Wrong trial or independent finite-Q8_0 hash')
            trials.append(dict(kind=kind, trial=trial, optimized=ORDER[trial], cycles=int(match[4]),
                               fcsr=0, vcsr=5, checksum=match[5]))
            active = False
        elif line == SUITE:
            require(boundary and len(trials) == 8 and not active and not suite, 'Incomplete/duplicate suite')
            suite = True
        else:
            raise ValueError('Malformed/unknown V-decode evidence')
    require(cap and boundary and suite and terminal and not active and
            severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete native V decode transcript')
    performance = []
    for kind in range(2):
        sums = {str(mode):sum(t['cycles'] for t in trials if t['kind'] == kind and t['optimized'] == mode)
                for mode in (0, 1)}
        performance.append(dict(kind=kind, sums=sums, speedup=sums['0']/sums['1'],
                               cycle_reduction_percent=100*(1-sums['1']/sums['0'])))
    return dict(state='NUMERICAL_AND_TIMING_CHECKED', trials=trials, performance=performance,
        independent_host_hashes=hashes, boundary_elements=3584, model_speedup_claimed=False,
        scope='Finite Q8_0 V decoding only, not complete Attention or GGML deployment')
