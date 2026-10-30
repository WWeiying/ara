"""Closed paired actual-GGML contract. QEMU supplies no RTL timing evidence."""
import math
import re


def require(ok, message):
    if not ok:
        raise ValueError(message)


def check_log(text):
    require(not re.search(r'GROUPED_GGML_FAIL|QUANT_STRIDED_FAIL|Assertion\b.*failed|'
                          r'terminate called|Segmentation fault|Kernel panic|Aborted', text),
            'Guest failure text')
    rows = [line for line in text.splitlines() if line.startswith(
        ('GROUPED_GGML', 'GGML_RISCV_QUANT_KV', 'GUEST_TEST_EXIT'))]
    cursor = commands = panels = copied = decodes = 0
    thread_observations = []

    def exact(expected):
        nonlocal cursor
        require(cursor < len(rows) and rows[cursor] == expected,
                'Missing or wrong record: ' + expected)
        cursor += 1

    def matched(pattern):
        nonlocal cursor
        match = re.fullmatch(pattern, rows[cursor]) if cursor < len(rows) else None
        require(match is not None, 'Missing or malformed completion')
        cursor += 1
        return match

    def csr(match, frm=0, exact_flags=True):
        flags, reference, vcsr = map(int, match.group(1, 2, 3))
        require(all(value & ~31 == frm << 5 and value & 8 for value in (flags, reference)) and vcsr == 5,
                'CSR mismatch, rounding/sticky flag lost, or VCSR changed')
        require(not exact_flags or flags == reference, 'Exact CSR flags mismatch')
        return (flags if exact_flags else flags & ~31), vcsr

    def trace(grouped, row, layout, visible=128, selection=0):
        nonlocal commands, panels, copied, decodes
        accepted = selection == 0
        tiles = (visible + 31) // 32
        attempts = 4 * tiles if accepted else 0
        groups = 2 if accepted else 0
        values = 2 * visible if accepted else 0
        count = 2 * tiles if accepted and layout == 'token_major' else 0
        payload = 2 * visible * row if count else 0
        ts, hs = (row, 256 * row) if layout == 'contiguous' else (2 * row, row)
        exact(f'GGML_RISCV_QUANT_KV status={0 if accepted else 1} mapping=0 memory=1 runtime_called=1 '
              f'command_attempts={attempts} groups={groups} value_decodes={values} executor_status=0')
        exact(f'GGML_RISCV_QUANT_KV_LAYOUT selection={selection} key_panels={count} key_bytes={payload} '
              f'workspace=13120 k_token_stride={ts} k_head_stride={hs}')
        exact(f'GGML_RISCV_QUANT_KV_PV grouped={grouped} completed_groups={groups}')
        commands += attempts
        panels += count
        copied += payload
        decodes += values

    for kind, row in (('q8_0', 136), ('q4_0', 72)):
        for layout in ('contiguous', 'token_major'):
            for visible in (128, 5):
                previous = {}
                for repeat in range(2):
                    pair = []
                    for grouped in range(2):
                        prefix = (f'kind={kind} layout={layout} mode=native visible={visible} '
                                  f'repeat={repeat} grouped={grouped}')
                        exact('GROUPED_GGML_BEGIN ' + prefix)
                        trace(grouped, row, layout, visible)
                        end = matched(re.escape('GROUPED_GGML_END ' + prefix) +
                                      r' outputs=1536 flags=(\d+) ref_flags=(\d+) vcsr=(\d+) '
                                      r'max_abs=([0-9.e+-]+) exact_pair=' + str(grouped))
                        state = csr(end)
                        maximum = float(end[4])
                        require(math.isfinite(maximum) and maximum >= 0, 'Invalid numerical summary')
                        require(grouped not in previous or previous[grouped] == state,
                                'Repeated CSR changed')
                        previous[grouped] = state
                        pair.append(state)
                    require(pair[0] == pair[1], 'Old/new CSR mismatch')
        for mode in ('mask', 'thread', 'memory', 'rounding', 'reference'):
            pair = []
            for grouped in range(2):
                prefix = f'kind={kind} layout=token_major mode={mode} grouped={grouped}'
                exact('GROUPED_GGML_BEGIN ' + prefix)
                if mode in ('mask', 'rounding'):
                    trace(grouped, row, 'token_major', selection=6 if mode == 'mask' else 2)
                if mode == 'thread':
                    observation = matched(re.escape(f'GROUPED_GGML_THREAD_CSR kind={kind} mode=thread grouped={grouped}') +
                                          r' actual_fcsr=(\d+) ref_fcsr=(\d+) actual_vcsr=5 ref_vcsr=5 '
                                          r'actual_new_flags=(\d+) ref_new_flags=(\d+) aggregate=0')
                    actual, reference, new_actual, new_reference = map(int, observation.groups())
                    require(new_actual == actual & 23 and new_reference == reference & 23,
                            'Incorrect thread-local new-flags observation')
                    thread_observations.append(dict(kind=kind, grouped=grouped,
                        actual_fcsr=actual, reference_fcsr=reference, actual_new_flags=new_actual,
                        reference_new_flags=new_reference, aggregate=False))
                end = matched(re.escape('GROUPED_GGML_END ' + prefix) +
                              r' outputs=1536 flags=(\d+) ref_flags=(\d+) vcsr=(\d+) exact=1')
                pair.append(csr(end, 1 if mode == 'rounding' else 0, exact_flags=mode != 'thread'))
                if mode == 'thread':
                    require((int(end[1]), int(end[2])) == (actual, reference), 'Thread observation/completion mismatch')
            require(pair[0] == pair[1], 'Fallback old/new CSR mismatch')
        exact(f'GROUPED_GGML_PROFILE_PASS kind={kind} outputs=1536 native_calls=16 fallback_calls=10 inputs_unchanged=1')
    exact('GROUPED_GGML_SUITE_PASS profiles=2 layouts=2 native_calls=32 fallback_calls=20 '
          'executor=native_qbs performance=not_measured')
    exact('GUEST_TEST_EXIT=0')
    require(cursor == len(rows), 'Extra evidence records')
    return dict(state='GROUPED_PV_GGML_CHECKED', native_calls=32, native_pairs=16,
                fallback_calls=20, outputs_per_call=1536, native_command_attempts=commands,
                key_panels=panels, key_bytes=copied, value_decodes=decodes,
                thread_csr_observations=thread_observations,
                whole_model=False, rtl_performance=False)
