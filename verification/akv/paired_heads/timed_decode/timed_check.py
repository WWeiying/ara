"""Strict extra timing protocol followed by the unchanged numerical/work checker."""
import re
from timed_spec import original_check as old, s

TIMING = re.compile(r'NATIVE_PAIR_TIMING case=([0-3]) trial=([0-2]) '
                    r'start=([0-9]+) end=([0-9]+) cycles=([0-9]+)')


def check_log(text):
    filtered, timings, commands = [], [], []
    active = None
    pending_result = False
    busy = 0
    previous_end = -1
    for line in text.splitlines():
        if pending_result:
            s.require(line.startswith('NATIVE_PAIR_RESULT '), 'Timing must immediately precede RESULT')
        if 'NATIVE_PAIR_TIM' in line:
            match = TIMING.fullmatch(line)
            s.require(match is not None and active is not None and not pending_result,
                      'Malformed, extra, or misplaced timing record')
            case, trial, start, end, cycles = map(int, match.groups())
            s.require((case, trial) == active == divmod(len(timings), 3), 'Timing identity/order')
            s.require(0 <= start < end < 2**64 and start > previous_end and
                      cycles == end-start and cycles >= busy > 0, 'Invalid timing interval/busy bound')
            timings.append(dict(case=case, trial=trial, start=start, end=end,
                                cycles=cycles, command_busy_cycles=busy))
            previous_end, pending_result = end, True
            continue
        if line.startswith('NATIVE_PAIR_BEGIN '):
            s.require(active is None and len(timings) < 12, 'Nested/extra BEGIN')
            active = divmod(len(timings), 3)
            s.require(line == old.begin(*active), 'Wrong BEGIN order')
            busy = 0
        if line.startswith('[AKV_PERF] '):
            s.require(active is not None and not pending_result, 'Command outside timed call')
            row = s.numeric_fields(line[len('[AKV_PERF] '):], s.PERF_FIELDS)
            commands.append(row)
            busy += row['busy_cycles']
        if line.startswith('NATIVE_PAIR_RESULT '):
            s.require(active is not None and pending_result, 'Missing timing before RESULT')
            active, pending_result = None, False
        filtered.append(line)
    s.require(len(timings) == 12 and active is None and not pending_result, 'Incomplete timed suite')
    result = old.check_log('\n'.join(filtered)+'\n')
    for row, timing in zip(result['trials'], timings):
        s.require((row['case'], row['trial']) == (timing['case'], timing['trial']), 'Timing/result mismatch')
        s.require(row['hardware_totals']['busy_cycles'] == timing['command_busy_cycles'], 'Busy sum mismatch')
        row['cycles'] = timing['cycles']
    result.update(timings=timings, hardware_records=commands, complete_native_call_cycles=True,
                  scope='Derived real-input public execute_v2_native including runtime validation/admission and all internal work plus existing drain/fence; excludes caller query preparation, plan construction, post-call numerical/guard checks and UART; not model timing')
    return result
