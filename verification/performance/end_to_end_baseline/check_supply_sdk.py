"""SDK checks for physical supply experiments; compute width stays fixed."""
import struct

from audit import require
import check_supply_decode as decode
import full_projection as prefill


def oracle(build, kind):
    if kind == 'decode':
        return ([(build / f'part_{p}_expected.bin').read_bytes() for p in range(7)],
                [(build / f'activation_{s}.bin').read_bytes() for s in range(4)],
                list(struct.unpack('<7I', (build / 'profiles.bin').read_bytes())),
                list(struct.unpack('<7I', (build / 'flags.bin').read_bytes())))
    require(kind == 'prefill', 'Unknown SDK workload')
    return [(build / f'attn_{p}_expected.bin').read_bytes() for p in ('q', 'k', 'v')]


def check(text, kind, bus_bits, expected):
    if kind == 'decode':
        return decode.check(text, *expected, bus_bits)
    require(kind == 'prefill' and bus_bits in (128, 256), 'Unknown SDK experiment')
    # Here wide=1 denotes the matrix-dot implementation, NOT the AXI width.
    result = prefill.check(text, 1, expected)
    commands = [decode.fields(line, '[QBS_PERF]') for line in text.splitlines()
                if line.startswith('[QBS_PERF] ')]
    for index, command in enumerate(commands):
        decode.read_contract(command, bus_bits, 8, 1 if index < 96 else 2, 4)
        require(all(k in command for k in (*decode.COUNTERS, *decode.WAIT, *decode.CONTEXT_COUNTERS)) and
                sum(command['phase_' + p + '_cycles'] for p in decode.PHASES) == command['busy_cycles'] and
                sum(command[k] for k in decode.WAIT) == command['weight_prefetch_wait_cycles'] and
                all(command[k] == 0 for k in decode.CONTEXT_COUNTERS),
                'Prefill phase/response/context accounting mismatch')
    result['counters'] = {k: sum(c[k] for c in commands)
                          for k in (*decode.COUNTERS, *decode.WAIT, *decode.CONTEXT_COUNTERS)}
    return result


def timing(measured, kind):
    row = measured['total'] if kind == 'decode' else measured['trials'][0]
    return {key: row[key] for key in ('region', 'preparation', 'admission', 'execution')}


def paired(narrow, wide, kind):
    """Correctness is mandatory; a speedup is an outcome, not a PASS gate."""
    keys = ('useful_pairs', 'dot_issue_count', 'whole_model', 'full_ggml', 'preparation_included')
    keys += ('commands', 'outputs', 'full_k', 'full_n') if kind == 'decode' else ('qbs_commands', 'full_n')
    require(all(narrow[k] == wide[k] for k in keys), 'Unequal paired workload')
    require([p['checksum'] for p in narrow['parts']] == [p['checksum'] for p in wide['parts']],
            'Unequal paired output checksums')
    a, b = timing(narrow, kind), timing(wide, kind)
    require(all(v > 0 for v in (*a.values(), *b.values())), 'Missing positive SDK phase')
    speedups = {key: a[key] / b[key] for key in a}
    count = lambda value, key: (sum(p['counters'][key] for p in value['activity'])
                               if kind == 'decode' else value['counters'][key])
    require(count(narrow, 'weight_bytes') == count(wide, 'weight_bytes') and
            count(narrow, 'payload_bytes') == count(wide, 'payload_bytes'), 'Unequal physical payload')
    return dict(cycles128=a, cycles256=b, speedups=speedups,
                busy_cycles128=narrow['qbs_busy_cycles'], busy_cycles256=wide['qbs_busy_cycles'],
                r_beats128=count(narrow, 'r_beats'), r_beats256=count(wide, 'r_beats'),
                region_cycles_reduced_at_least_10_percent=b['region'] <= .9 * a['region'],
                region_regression_above_2_percent=b['region'] > 1.02 * a['region'],
                same_work=True, whole_model=False, matrix_dot_identical=True)
