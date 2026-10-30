"""Tail Attention correctness against an independently executed GGML graph."""
import math
import re
import struct

from batch_spec import Command
from check_attention import f32, round32
from check_batch_qk import check_command, schema, TERMINAL
from check_rvv_qbs import require

FIELDS = ('visible', 'trial', 'native', 'map', 'status', 'selection', 'groups',
          'commands', 'calls', 'values', 'panels', 'copied', 'fcsr', 'vcsr', 'errors')
RESULT = re.compile('QUANT_TAIL_RESULT ' + ' '.join(f'{key}=(?P<{key}>[0-9]+)' for key in FIELDS) +
                    r' hex=(?P<hex>[0-9a-f]+)')
SUITE = 'QUANT_TAIL_SUITE_PASS prefixes=2 trials=6 outputs=768 native_calls=4'
QK = re.compile(r'QUANT_TAIL_QK visible=([0-9]+) trial=([0-9]+) seq=([0-9]+) '
                r'm=([0-9]+) n=([0-9]+) stride=32 activation=([0-9a-f]+) scores=([0-9a-f]+)')


def check_log(text, kind, goldens, rtl, key_data, oracle):
    require(kind in (0, 1) and set(goldens) == {5, 33}, 'Wrong profile or reference prefixes')
    gold = {}
    for prefix, payload in goldens.items():
        require(len(payload) == 6144, 'Wrong independent full-graph output extent')
        values = struct.unpack('<1536f', payload)
        require(all(math.isfinite(value) for value in values), 'Nonfinite independent golden')
        gold[prefix] = values[:768]
    fields = schema(rtl)
    row_bytes = 72 if kind else 136
    require(len(key_data) == 512 * row_bytes and callable(oracle), 'Missing independent QK inputs')
    cap = suite = terminal = False
    active = None
    trials, commands = [], []
    scores, queries = [], {}
    group = []
    severity = set()
    order = [(visible, trial, int(trial != 0)) for visible in (5, 33) for trial in range(3)]
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(match is not None and match[1] not in severity, 'UVM severity/duplicate')
            severity.add(match[1])
        if 'Core Test' in line:
            require(line == TERMINAL and suite and not terminal, 'Bad core termination')
            terminal = True
        if 'AKV_PERF' in line:
            raise ValueError('Unexpected F16 AKV work')
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            require(active is not None and active[2] and not suite and not terminal, 'Unexpected native work')
            require(len(commands) == len(scores), 'Previous command lacks score export')
            visible = active[0]
            require(len(group) < 2 * ((visible + 31) // 32), 'Extra native command')
            require(re.fullmatch(r'\[QBS_PERF\](?: [a-z][a-z0-9_]*=[0-9]+)+', line) is not None,
                    'Malformed hardware work')
            pairs = re.findall(r'([a-z][a-z0-9_]*)=([0-9]+)', line)
            require([key for key, _ in pairs] == fields, 'Hardware schema mismatch')
            row = {key: int(value) for key, value in pairs}
            tile, local = divmod(len(group), 2)
            first = tile * 32
            command = Command(kind, 0, 0 if not local else 4, 4 if not local else 2,
                              first, min(32, visible - first))
            check_command(row, command, len(commands) + 1)
            group.append(row)
            commands.append(row)
        if 'QUANT_TAIL_' not in line:
            continue
        require(not terminal, 'Program evidence after termination')
        capability = (f'QUANT_TAIL_CAP kind={kind} heads=6 dim=128 capacity=256 prefixes=5,33 '
                      f'native_repeats=2 k_token_stride={2 * row_bytes} v_token_stride=272 workspace=13120')
        if line == capability:
            require(not cap and not trials and active is None, 'Duplicate/late capability')
            cap = True
        elif line.startswith('QUANT_TAIL_BEGIN '):
            require(cap and not suite and active is None and len(trials) < 6, 'Unexpected trial')
            active = order[len(trials)]
            visible, trial, native = active
            require(line == f'QUANT_TAIL_BEGIN visible={visible} trial={trial} native={native}', 'Trial order')
            group = []
        elif QK.fullmatch(line):
            match = QK.fullmatch(line)
            require(active is not None and active[2] and len(commands) == len(scores) + 1,
                    'Score without unique native command')
            visible, trial, _native = active
            tile, local = divmod(len(group) - 1, 2)
            first, head, m = tile * 32, 4 if local else 0, 2 if local else 4
            n = min(32, visible - first)
            require(tuple(map(int, match.groups()[:5])) == (visible, trial, len(commands), m, n),
                    'Wrong score geometry/order')
            activation = bytes.fromhex(match[6])
            require(len(activation) == m * 136 and len(match[7]) == m * n * 8, 'Wrong score/Query extent')
            actual = [int(match[7][i:i + 8], 16) for i in range(0, len(match[7]), 8)]
            for row in range(m):
                query = activation[row * 136:(row + 1) * 136]
                require(queries.get(head + row, query) == query, 'Query changed across tiles/repeats/prefixes')
                queries[head + row] = query
                for column in range(n):
                    start = (first + column) * row_bytes
                    wanted, _flags = oracle(kind, key_data[start:start + row_bytes], query)
                    require(actual[row * n + column] == wanted and math.isfinite(f32(wanted)),
                            'Independent bit-exact QK mismatch')
            scores.append(dict(seq=len(commands), visible=visible, trial=trial, m=m, n=n,
                               output_bits=actual))
        elif RESULT.fullmatch(line):
            require(active is not None and len(trials) < 6, 'Result without trial')
            match = RESULT.fullmatch(line)
            result = {key: int(match[key]) for key in FIELDS}
            visible, trial, native = active
            tiles = (visible + 31) // 32
            count = 2 * tiles if native else 0
            wanted = dict(visible=visible, trial=trial, native=native, map=0, status=0, selection=0,
                          groups=native, commands=count, calls=count if native else 6 * visible,
                          values=visible if native else 6 * visible, panels=tiles if native else 0,
                          copied=visible * row_bytes if native else 0, vcsr=5, errors=0)
            require(all(result[key] == value for key, value in wanted.items()) and
                    result['fcsr'] <= 31 and len(group) == count and len(scores) == len(commands),
                    'Runtime work/status/CSR mismatch')
            require(len(match['hex']) == 768 * 8, 'Wrong output count')
            bits = [int(match['hex'][i:i + 8], 16) for i in range(0, len(match['hex']), 8)]
            values = [f32(value) for value in bits]
            require(all(math.isfinite(value) for value in values), 'Nonfinite output')
            require(all(round32(abs(round32(value - reference))) <=
                        round32(round32(0.004) + round32(round32(0.002) * abs(reference)))
                        for value, reference in zip(values, gold[visible])), 'Independent GGML output mismatch')
            if native:
                ordinary = trials[len(trials) - trial]
                require(result['fcsr'] == ordinary['fcsr'], 'Ordinary/native FCSR mismatch')
                if trial == 2:
                    require(bits == trials[-1]['output_bits'] and result['fcsr'] == trials[-1]['fcsr'],
                            'Repeated native bits/CSR changed')
            result['output_bits'] = bits
            trials.append(result)
            active = None
        elif line == SUITE:
            require(cap and not suite and active is None and len(trials) == 6, 'Incomplete/duplicate suite')
            suite = True
        else:
            raise ValueError('Unknown/malformed tail evidence')
    require(cap and suite and terminal and len(commands) == len(scores) == 12 and len(queries) == 6 and
            severity == {'UVM_ERROR', 'UVM_FATAL'}, 'Incomplete tail inquiry')
    return dict(state='TAIL_ATTENTION_NUMERICAL_AND_WORK_CHECKED', trials=trials,
                hardware_records=commands, prefixes=[5, 33], native_calls=4, commands=12,
                score_records=scores, independent_scores_bit_exact=True,
                independent_command_fflags=False, independent_query_quantizer=False,
                outputs_per_trial=768, repeat_bits_exact=True, paired_fcsr=True,
                independent_protocol_checked=False, performance=False, whole_model=False)
