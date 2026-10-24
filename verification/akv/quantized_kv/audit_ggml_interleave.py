#!/usr/bin/env python3
"""Replay context identity and actual quantization records without a new run."""
import argparse
import json
from pathlib import Path
from run_ggml_interleave import check_log, fields, require, digest, hashes, atomic_json


def check_identity(text):
    checked = check_log(text)
    for item in checked['runs']:
        kind, run, native = item['kind'], item['run'], item['native']
        begin = f'QUANT_INTERLEAVE_BEGIN kind={kind} run={run} '
        starts = [line for line in text.splitlines() if line.startswith(begin)]
        require(len(starts) == 1, 'Missing unique interval')
        section = text.split(starts[0] + '\n', 1)[1].split('QUANT_INTERLEAVE_END ', 1)[0]
        commands = [fields(line, 'GGML_RISCV_QBS_COMMAND') for line in section.splitlines()
                    if line.startswith('GGML_RISCV_QBS_COMMAND ')]
        lifetimes = [fields(line, 'GGML_RISCV_QBS_LIFETIME') for line in section.splitlines()
                     if line.startswith('GGML_RISCV_QBS_LIFETIME ')]
        contexts = [fields(line, 'GGML_RISCV_QBS_CROSS_OP') for line in section.splitlines()
                    if line.startswith('GGML_RISCV_QBS_CROSS_OP ')]
        require(len(lifetimes) == (1 if native else 2), 'Quantization was repeated or silently skipped')
        epoch = lifetimes[0]['graph_epoch']
        require(all(c['graph_epoch'] == epoch and c['context_id'] == '0' for c in commands),
                'Command graph epoch/context ID mismatch')
        require(all(c['graph_epoch'] == epoch for c in contexts), 'Reservation belongs to another graph')
        for index, life in enumerate(lifetimes):
            require(life['graph_epoch'] == epoch and life['bytes'] == '292' and
                    life['activation_type'] == 'q8_K' and life['quantize_time_valid'] == '1',
                    'Wrong activation quantization record')
            group = commands if native else commands[index * 2:index * 2 + 2]
            require(all(c['activation_seq'] == life['seq'] for c in group), 'Commands linked to another quantization')
            if native:
                require(all(c['source_id'] == life['source_id'] for c in contexts), 'Reservation source mismatch')
    lives = [line for line in text.splitlines() if line.startswith('GGML_RISCV_QBS_LIFETIME ')]
    summary = [fields(line, 'GGML_RISCV_QBS_LIFETIME_SUMMARY') for line in text.splitlines()
               if line.startswith('GGML_RISCV_QBS_LIFETIME_SUMMARY ')]
    require(len(lives) == 8 and len(summary) == 1, 'Quantization record/summary count mismatch')
    for key, value in dict(quantizations='8', quantized_bytes='2336', cross_op_fill='4',
                           cross_op_reuse='4', cross_op_release='4', cross_op_quantization_skips='4',
                           cross_op_activation_bytes_saved='1168').items():
        require(summary[0].get(key) == value, 'Wrong lifecycle summary ' + key)
    return dict(checked, quantizations=8, quantization_skips=4, quantized_bytes_saved=1168,
                graph_epoch_and_context_id_checked=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, out = args.run.resolve(strict=True), args.output.resolve()
    require(not out.is_relative_to(run), 'Independent audit output required')
    out.mkdir(parents=True, exist_ok=False)
    try:
        original = json.loads((run / 'result.json').read_text())
        status = json.loads((run / 'status.json').read_text())
        require(original['state'] == status['state'] == 'PASS' and status['child_pid'] is None,
                'Require terminal PASS')
        pins = json.loads((run / 'source-pins.json').read_text())
        require(digest(run / 'source-pins.json') == original['source_pins_sha256'] and
                digest(run / 'qemu.log') == original['log_sha256'], 'Execution evidence drift')
        require(all(digest(Path(p)) == sha for p, sha in pins.items()), 'Input drift')
        checked = check_identity((run / 'qemu.log').read_text().replace('\r\n', '\n'))
        require(all(original[k] == v for k, v in checked.items() if k in original and k != 'state'),
                'Original numerical/work replay differs')
        pins.update(hashes([Path(__file__), run / 'source-pins.json', run / 'result.json',
                            run / 'status.json', run / 'qemu.log']))
        atomic_json(out / 'source-pins.json', pins)
        atomic_json(out / 'result.json', dict(checked, state='INDEPENDENT_GGML_INTERLEAVE_ACCEPTED',
                    run=str(run), current_inputs_match=True, source_pins_sha256=digest(out / 'source-pins.json'),
                    original_result_sha256=digest(run / 'result.json')))
        print('INDEPENDENT_GGML_INTERLEAVE_ACCEPTED lifetimes=4 quantizations=8 skips=4')
    except BaseException as exc:
        atomic_json(out / 'result.json', dict(state='FAIL', error=repr(exc)))
        raise


if __name__ == '__main__': main()
