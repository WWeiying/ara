"""Check actual native commands, context lifetimes and physical service in ABBA."""
from audit import require
from check_decode_matched import check as check_outputs
from check_decode_native import K, PROFILE, CONTEXT_COUNTERS
from check_supply_decode import read_contract, fields, COUNTERS, WAIT, PHASES

ACCESS = ((1, 2), (2, 2), (2, 3), (1, 2), (2, 3), (0, 0), (1, 3))


def check(text, bus_bits, *oracle):
    result = check_outputs(text, *oracle)
    commands = [fields(line, '[QBS_PERF]') for line in text.replace('\r', '').splitlines()
                if line.startswith('[QBS_PERF] ')]
    require(len(commands) == 28, 'Matched native command count differs')
    activity = []
    for native_trial, trial in enumerate((1, 2)):
        for part, accesses in enumerate(ACCESS):
            selected = commands[native_trial * 14 + part * 2:native_trial * 14 + part * 2 + 2]
            blocks, profile = K[part] // 256, PROFILE[part]
            for tile, (command, access) in enumerate(zip(selected, accesses)):
                reused = int(access in (2, 3)); activation = blocks * 292
                weight = 32 * blocks * (144 if profile == 1 else 210)
                expected = dict(seq=native_trial * 14 + part * 2 + tile + 1,
                    m=1, n=32, vlen=1024, lanes=4, success=1, fault=0,
                    validation_fault=0, read_fault=0, useful_pairs=8192 * blocks,
                    dot_active_cycles=256 * blocks, activation_access=access,
                    activation_bytes=activation, weight_bytes=weight,
                    payload_bytes=16 + weight + (0 if reused else activation),
                    context_fill_count=int(access == 1), context_reuse_count=reused,
                    context_reuse_block_count=blocks if reused else 0,
                    context_read_bytes=activation if reused else 0,
                    activation_axi_bytes_saved=activation if reused else 0,
                    context_validation_fault_count=0)
                require(all(command.get(k) == v for k, v in expected.items()),
                        'Matched native shape/work/context differs')
                require(all(k in command for k in (*COUNTERS, *WAIT, *CONTEXT_COUNTERS)) and
                        all('phase_' + p + '_cycles' in command for p in PHASES) and
                        sum(command['phase_' + p + '_cycles'] for p in PHASES) == command['busy_cycles'] and
                        sum(command[k] for k in WAIT) == command['weight_prefetch_wait_cycles'] and
                        command['dot_active_cycles'] <= command['busy_cycles'],
                        'Matched native phase/wait accounting differs')
                read_contract(command, bus_bits, blocks, profile, 1)
            counters = {k: sum(c[k] for c in selected) for k in (*COUNTERS, *WAIT, *CONTEXT_COUNTERS)}
            row = result['parts'][trial * 7 + part]
            require(counters['busy_cycles'] <= row['execution'], 'Native busy outside matched call')
            activity.append(dict(trial=trial, part=part, counters=counters,
                phases={p: sum(c['phase_' + p + '_cycles'] for c in selected) for p in PHASES},
                sdk_outside_busy_cycles=row['execution'] - counters['busy_cycles']))
    result.update(native_activity=activity, native_work_checked=True,
                  native_counter_scope='Two native trials only, not RVV arithmetic activity')
    return result
