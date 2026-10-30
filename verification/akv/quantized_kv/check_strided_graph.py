"""Strict actual-GGML functional acceptance; QEMU is not a timing source."""
import math
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_log(text):
    require(not re.search(r'Assertion\b.*\bfailed|terminate called|Segmentation fault|QUANT_STRIDED_FAIL', text),
            'Guest failure text')
    rows = [line for line in text.splitlines() if line.startswith(
        ('QUANT_STRIDED_', 'GGML_RISCV_QUANT_KV', 'GUEST_TEST_EXIT='))]
    cursor = 0
    commands = copies = copied = decodes = 0

    def exact(expected):
        nonlocal cursor
        require(cursor < len(rows) and rows[cursor] == expected, 'Missing or wrong record: ' + expected)
        cursor += 1

    def matched(pattern):
        nonlocal cursor
        match = re.fullmatch(pattern, rows[cursor]) if cursor < len(rows) else None
        require(match is not None, 'Missing or malformed acceptance record')
        cursor += 1
        return match

    for kind, row_bytes in (('q8_0', 136), ('q4_0', 72)):
        for layout in ('contiguous', 'token_major'):
            token_stride = row_bytes if layout == 'contiguous' else 2 * row_bytes
            head_stride = 256 * row_bytes if layout == 'contiguous' else row_bytes
            for visible in (128, 5):
                previous = None
                for repeat in range(2):
                    prefix = f'kind={kind} layout={layout} mode=native visible={visible} repeat={repeat}'
                    exact('QUANT_STRIDED_BEGIN ' + prefix)
                    attempt = 4 * ((visible + 31) // 32)
                    count = 0 if layout == 'contiguous' else 2 * ((visible + 31) // 32)
                    payload = 0 if layout == 'contiguous' else 2 * visible * row_bytes
                    exact('GGML_RISCV_QUANT_KV status=0 mapping=0 memory=1 runtime_called=1 '
                          f'command_attempts={attempt} groups=2 value_decodes={2 * visible} executor_status=0')
                    exact(f'GGML_RISCV_QUANT_KV_LAYOUT selection=0 key_panels={count} key_bytes={payload} '
                          f'workspace=13120 k_token_stride={token_stride} k_head_stride={head_stride}')
                    end = matched(re.escape('QUANT_STRIDED_END ' + prefix) +
                                  r' flags=(\d+) vcsr=(\d+) max_abs=([0-9.e+-]+)')
                    flags, vcsr, maximum = int(end[1]), int(end[2]), float(end[3])
                    require(flags <= 31 and vcsr <= 7 and math.isfinite(maximum) and maximum >= 0,
                            'Invalid numerical or CSR completion')
                    require(previous is None or previous == (flags, vcsr), 'Repeated CSR state changed')
                    previous = flags, vcsr
                    commands += attempt
                    copies += count
                    copied += payload
                    decodes += 2 * visible
        for mode in ('mask_fallback', 'thread_fallback', 'memory_fallback'):
            prefix = f'kind={kind} layout=token_major mode={mode}'
            exact('QUANT_STRIDED_BEGIN ' + prefix)
            if mode == 'mask_fallback':
                exact('GGML_RISCV_QUANT_KV status=1 mapping=0 memory=1 runtime_called=1 '
                      'command_attempts=0 groups=0 value_decodes=0 executor_status=0')
                exact('GGML_RISCV_QUANT_KV_LAYOUT selection=6 key_panels=0 key_bytes=0 workspace=13120 '
                      f'k_token_stride={2 * row_bytes} k_head_stride={row_bytes}')
            exact('QUANT_STRIDED_END ' + prefix + ' exact=1')
        exact(f'QUANT_STRIDED_PROFILE_PASS kind={kind} outputs=1536 native_calls=8 fallback_cases=3 inputs_unchanged=1')
    exact('QUANT_STRIDED_SUITE_PASS profiles=2 layouts=2 native_calls=16 fallback_cases=6 '
          'executor=native_qbs performance=not_measured')
    exact('GUEST_TEST_EXIT=0')
    require(cursor == len(rows), 'Unknown or extra evidence records')
    return dict(state='STRIDED_GGML_GRAPH_CHECKED', profiles=2, layouts=2, native_calls=16,
                native_command_attempts=commands, key_panels=copies, key_bytes=copied,
                value_decodes=decodes, fallback_cases=6, visible_prefixes=[128, 5],
                whole_model=False, rtl_performance=False)
