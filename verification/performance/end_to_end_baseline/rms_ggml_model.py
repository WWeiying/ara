"""Full-logit/route acceptance plus exact ordered-Norm work, never QEMU timing."""
from collections import Counter
import re

from audit import require
from trace_context_model import check as check_native


def driver(source):
    before = '        if (!child) {execl(programs[variant],programs[variant],outputs[variant],static_cast<char *>(nullptr));_exit(127);}'
    after = '''        if (!child) {
            need(!setenv("GGML_RISCV_ORDERED_RMS","1",1),"norm_policy");
            need(!setenv("GGML_RISCV_ORDERED_RMS_TRACE","1",1),"norm_trace");
            execl(programs[variant],programs[variant],outputs[variant],static_cast<char *>(nullptr));_exit(127);
        }'''
    require(source.count(before) == 1, 'Exact independent model driver anchor required')
    return source.replace(before, after, 1)


def norm_work(text):
    mode = None
    records = []
    rows = []
    calls = Counter()
    sums = Counter()
    outputs = Counter()
    for line in text.replace('\r', '').splitlines():
        if line.startswith('TRACE_CONTEXT_VARIANT_BEGIN '):
            require(mode is None and line in ('TRACE_CONTEXT_VARIANT_BEGIN variant=0',
                                             'TRACE_CONTEXT_VARIANT_BEGIN variant=1'), 'Norm variant boundary')
            mode = int(line[-1])
        elif line.startswith('GGML_RISCV_RMS'):
            require(mode == 1, 'Only the candidate may emit new Norm work')
            match = re.fullmatch(r'GGML_RISCV_RMS_EXEC enabled=1 fused=([01]) ith=0 nth=1 width=(128|2048) '
                                 r'sum_fast=(\d+) sum_scalar=0 output_fast=(\d+) output_scalar=0', line)
            require(match is not None, 'Malformed/disabled/fallback/parallel Norm execution')
            fused, width, total, output = map(int, match.groups())
            require(total > 0 and output == (total if fused else 0), 'Norm sum/output route mismatch')
            calls[width] += 1
            sums[width] += total
            outputs[width] += output
            rows.append(dict(fused=fused, width=width, sum_rows=total, output_rows=output))
        elif line.startswith('OUTPUT_MODEL_STEP '):
            require(mode in (0, 1), 'Step outside model variant')
            if mode == 1:
                index = len(records)
                require(index < 4, 'Extra Norm model step')
                kind, step = divmod(index, 2)
                require(line.startswith(f'OUTPUT_MODEL_STEP enabled=1 kind={kind} step={step} '),
                        'Norm model step order')
                expected = {128: 26880, 2048: 2202} if step == 0 else {128: 672, 2048: 57}
                require(calls == {128: 56, 2048: 57} and sums == expected,
                        'Norm nodes/rows do not match the full Qwen3 graph')
                records.append(dict(kind=kind, step=step, calls=dict(calls), sum_rows=dict(sums),
                                    output_rows=dict(outputs), operators=rows))
                calls, sums, outputs, rows = Counter(), Counter(), Counter(), []
        elif line.startswith('TRACE_CONTEXT_VARIANT_END '):
            require(mode is not None and line == f'TRACE_CONTEXT_VARIANT_END variant={mode}' and not rows,
                    'Unclosed/extra Norm work')
            mode = None
    require(mode is None and not rows and len(records) == 4, 'Incomplete candidate Norm graph')
    return dict(operators=452, sum_rows=59622, steps=records,
                independent_legacy_baseline=True, performance_measured=False)


def check(text, control, schema):
    require('RMS_GGML_MODEL_FAIL' not in text, 'Norm model driver failed')
    return dict(native=check_native(text, control, schema), norm=norm_work(text))
