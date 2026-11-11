"""Read GGUF tensor metadata only and scale the measured Smol workload."""
import json
from pathlib import Path
import struct

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
TYPES = {2: 'Q4_0', 6: 'Q5_0', 8: 'Q8_0', 12: 'Q4_K', 14: 'Q6_K'}
WIDTH = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


def tensors(path):
    with Path(path).open('rb') as f:
        def read(fmt):
            return struct.unpack('<' + fmt, f.read(struct.calcsize('<' + fmt)))[0]
        def string():
            return f.read(read('Q')).decode('utf-8')
        def skip(kind):
            if kind == 8:
                f.seek(read('Q'), 1)
            elif kind == 9:
                item, count = read('I'), read('Q')
                if item in WIDTH:
                    f.seek(WIDTH[item] * count, 1)
                else:
                    for _ in range(count):
                        skip(item)
            else:
                f.seek(WIDTH[kind], 1)
        assert f.read(4) == b'GGUF' and read('I') in (2, 3)
        count, metadata = read('Q'), read('Q')
        for _ in range(metadata):
            string(); skip(read('I'))
        result = []
        for _ in range(count):
            name = string(); dims = [read('Q') for _ in range(read('I'))]
            kind = read('I'); read('Q')
            result.append((name, dims, kind))
        return result


def work(spec, model):
    rows = tensors(model['path'])
    output = next((t for t in rows if t[0] == 'output.weight'), None)
    if output is None:
        _, dims, kind = next(t for t in rows if t[0] == 'token_embd.weight')
        rows.append(('output.weight', dims, kind))
    dots, commands, nonqbs = {}, {}, 0
    for name, dims, kind in rows:
        if len(dims) != 2 or name == 'token_embd.weight':
            continue
        k, n = dims
        activation_rows = 3 if name == 'output.weight' else spec['prompt_tokens'] + 2
        mtiles = 3 if name == 'output.weight' else (spec['prompt_tokens'] + 3) // 4 + 2
        if kind not in TYPES:
            nonqbs += k * n * activation_rows
            continue
        fmt = TYPES[kind]
        dots[fmt] = dots.get(fmt, 0) + k * n * activation_rows
        commands[fmt] = commands.get(fmt, 0) + ((n + 31) // 32) * mtiles
    return dict(dot_elements_per_mode=dots, approximate_commands_per_mode=commands,
                non_qbs_dot_elements_per_mode=nonqbs)


if __name__ == '__main__':
    inventory = json.loads((OUT/'stage5_models_prepare_20261110_04/model-inventory.json').read_text())
    result = {}
    for p in OUT.glob('stage5_models_execution_final_*/spec.json'):
        spec = json.loads(p.read_text())
        result[spec['id']] = work(spec, inventory[spec['model']])
    measured = json.loads((OUT/'stage5_models_smol_prefill_audit_20261110_02/checked.json').read_text())['qbs']
    dots = sum(v['dot_elements'] for v in measured.values())
    commands = sum(v['native_qbexec'] for v in measured.values())
    for value in result.values():
        value['dot_ratio_vs_measured_smol'] = sum(value['dot_elements_per_mode'].values()) / dots
        value['command_ratio_vs_measured_smol'] = sum(value['approximate_commands_per_mode'].values()) / commands
        value['dot_scaled_pair_seconds'] = 896.7 * value['dot_ratio_vs_measured_smol']
        value['command_scaled_pair_seconds'] = 896.7 * value['command_ratio_vs_measured_smol']
    print(json.dumps(dict(measured_smol_pair_seconds=896.7, measured_dots_per_mode=dots,
                         measured_commands_per_mode=commands, estimates=result), indent=2, sort_keys=True))
