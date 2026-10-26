"""Supplement the sealed model checker with native dispatch accounting."""
import hashlib
import json
from pathlib import Path
import sys

from check import check, require


def native_accounting(text):
    mode = None
    summaries = [{}, {}]
    fields = set(('gemv_calls gemm_calls input_rows output_rows activation_elements '
                  'output_elements dot_elements split_calls native_qbexec emulated_commands '
                  'command_dot_elements segmented_commands context_fill context_reuse '
                  'context_release').split()) | {f'commands_m{i}' for i in range(1, 9)}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('Q8K_MODEL_BEGIN '):
            mode = int(line.split('enabled=')[1])
            require(mode in (0, 1), 'Unknown process mode')
        elif line.startswith('GGML_RISCV_QBS_EXEC '):
            # The runtime emits these at child exit, after Q8K_MODEL_END.
            require(mode is not None, 'Unscoped native summary')
            pairs = [word.split('=', 1) for word in line.split()[1:]]
            require(all(len(p) == 2 for p in pairs), 'Malformed summary')
            row = dict(pairs)
            require(len(row) == len(pairs) and set(row) == fields | {'type'}, 'Summary fields')
            kind = row.pop('type')
            require(kind in ('Q4_K', 'Q6_K') and kind not in summaries[mode], 'Unexpected/duplicate format')
            require(all(value.isdecimal() for value in row.values()), 'Noninteger accounting')
            row = {name: int(value) for name, value in row.items()}
            require(row['native_qbexec'] > 0 and row['emulated_commands'] == 0, 'Not native execution')
            require(sum(row[f'commands_m{i}'] for i in range(1, 9)) == row['native_qbexec'], 'Command balance')
            require(row['gemv_calls'] > 0 and row['gemm_calls'] > 0 and row['commands_m4'] > 0,
                    'Missing decode/prefill projection')
            require(row['dot_elements'] > 0 and row['dot_elements'] == row['command_dot_elements'],
                    'Projection work not covered by native commands')
            require(row['context_fill'] == row['context_release'], 'Unreleased contexts')
            summaries[mode][kind] = row
    require(all(set(s) == {'Q4_K', 'Q6_K'} for s in summaries), 'Missing process/format summaries')
    require(summaries[0] == summaries[1], 'Different native workload across preparation modes')
    return summaries[0]


def audit(text):
    result = check(text)
    result['native_execution_by_format_per_process'] = native_accounting(text)
    result['scope'] = 'Q8K preparation OFF/ON; not RVV versus QBS or model timing'
    return result


if __name__ == '__main__':
    data = Path(sys.argv[1]).read_bytes()
    result = audit(data.decode())
    result['log_sha256'] = hashlib.sha256(data).hexdigest()
    print(json.dumps(result, indent=2, sort_keys=True))
