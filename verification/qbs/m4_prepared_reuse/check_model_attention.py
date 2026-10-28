"""Strict activity reconciliation for the fixed paired Qwen model workload.

This checks reported quantized-Attention dispatch, not retired instructions,
numerical correctness by itself, or hardware latency.
"""
import argparse
import json
from pathlib import Path


def check(text):
    active = None
    rows = {0: [], 1: []}
    steps = {0: 0, 1: 0}
    pending = []
    for line in text.splitlines():
        if line.startswith('Q8K_MODEL_BEGIN enabled='):
            active = int(line.split('=')[1])
            if active not in rows or rows[active]:
                raise ValueError('Unexpected model start')
        elif line.startswith('GGML_RISCV_QUANT_KV '):
            if active is None:
                raise ValueError('Unscoped Attention')
            f = {k: int(v) for k, v in (word.split('=') for word in line.split()[1:])}
            expected = dict(status=0, mapping=0, memory=1, runtime_called=1,
                            command_attempts=4, groups=2, value_decodes=0, executor_status=0)
            step = steps[active] % 3
            if step == 0:
                expected.update(status=1, mapping=5, memory=0, runtime_called=0,
                                command_attempts=0, groups=0)
            else:
                expected['value_decodes'] = 2 * (4 + step)
            if f != expected:
                raise ValueError('Unexpected dispatch/work: ' + repr(f))
            pending.append(f)
        elif line.startswith('Q8K_MODEL_STEP '):
            f = dict(word.split('=') for word in line.split()[1:])
            if active is None or int(f['enabled']) != active or (int(f['kind']), int(f['step'])) != divmod(steps[active], 3):
                raise ValueError('Step scope/order')
            if len(pending) != 28:
                raise ValueError('Expected all 28 Attention layers')
            rows[active].extend(pending)
            pending = []
            steps[active] += 1
        elif line.startswith('Q8K_MODEL_END '):
            if active is None or int(line.split('=')[1]) != active or pending or steps[active] != 6:
                raise ValueError('Incomplete model')
            active = None
    if active is not None or pending or steps != {0: 6, 1: 6} or rows[0] != rows[1]:
        raise ValueError('Incomplete or different Attention workload')
    if text.splitlines().count('Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured') != 1:
        raise ValueError('Missing paired model completion')
    return dict(scope='Quantized KV dispatch activity per model configuration; not hardware timing',
                model_configurations=2, calls_per_configuration=168,
                decode_completed_per_configuration=112, prefill_shape_fallback_per_configuration=56,
                command_attempts_per_configuration=sum(r['command_attempts'] for r in rows[0]),
                value_decodes_per_configuration=sum(r['value_decodes'] for r in rows[0]),
                paired_activity_equal=True, native_akv_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    raw = args.log.read_text()
    result = check(raw)
    for bad in (raw.replace('command_attempts=4', 'command_attempts=0', 1),
                raw.replace('runtime_called=1', 'runtime_called=0', 1),
                raw.replace('mapping=5', 'mapping=6', 1)):
        try:
            check(bad)
        except ValueError:
            continue
        raise ValueError('Mutation not rejected')
    print(json.dumps(dict(result, negative_tests=3), indent=2))
