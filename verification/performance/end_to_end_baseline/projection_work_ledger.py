#!/usr/bin/env python3
"""Replay historical model work and derive resource bounds, not model latency."""
import argparse
from collections import Counter
import json
from pathlib import Path

from audit import digest, require, verify_pins

# These are the two actual weight profiles in this Qwen3 Q4_K_M trace.
PROFILES = {1: ('q4_K', 144), 2: ('q6_K', 210)}


def verify_runtime_artifact(pins, path):
    path = Path(path)
    keys = {str(path), str(path.resolve(strict=True))}.intersection(pins)
    require(keys and all(pins[key] == digest(path) for key in keys),
            'Historical runtime artifact changed: '+str(path))


def fields(line):
    result = {}
    for word in line.split()[1:]:
        name, sep, value = word.partition('=')
        require(sep and name not in result, 'Malformed work trace')
        result[name] = value
    return result


def command_work(row):
    m, n, blocks, profile, access = (int(row[k]) for k in ('m', 'n', 'k_blocks', 'weight_profile', 'access'))
    require(m in (1, 4) and n > 0 and n % 4 == 0 and 0 < blocks <= 256 and profile in PROFILES,
            'Geometry/profile not covered by this ledger')
    require(row['activation_profile'] == '1' and row['emulated'] == row['segmented'] == '0' and
            access in (0, 1, 2, 3), 'Not an unsegmented native Q8_K projection')
    pairs = m*n*blocks*256
    weight = n*blocks*PROFILES[profile][1]
    # Native requests share one 128-bit R channel. This omits all metadata,
    # alignment waste, activation loads, bubbles and other memory consumers.
    transfer_floor = (weight+15)//16
    baseline_dot = (n//4)*blocks*(32 if m == 1 else 128)
    candidate_dot = baseline_dot//2 if m == 4 else baseline_dot
    return dict(commands=1, useful_pairs=pairs, eligible_pairs=pairs if m == 4 else 0,
                m1_commands=int(m == 1), m4_commands=int(m == 4),
                nominal_weight_payload_bytes=weight, weight_r_beat_floor=transfer_floor,
                baseline_dot_issue_budget=baseline_dot, candidate_dot_issue_budget=candidate_dot,
                baseline_dot_or_weight_floor=max(baseline_dot, transfer_floor),
                candidate_dot_or_weight_floor=max(candidate_dot, transfer_floor))


def check(text):
    mode = None; begun = []; ended = []; index = 0; seq = 0
    command_totals = {m: {} for m in (0, 1)}
    call_totals = {m: {} for m in (0, 1)}
    shapes = {m: Counter() for m in (0, 1)}
    call_shapes = {m: Counter() for m in (0, 1)}
    for line in text.replace('\r', '').splitlines():
        if line.startswith('REGISTER_MODEL_BEGIN '):
            require(mode is None, 'Nested model')
            mode = int(fields(line)['enabled'])
            require(mode == len(begun), 'Model order')
            begun.append(mode); index = 0; seq = 0
        elif line.startswith('GGML_RISCV_QBS_COMMAND '):
            require(mode in (0, 1) and index < 6, 'Command outside model step')
            row = fields(line); seq += 1
            require(int(row['seq']) == seq and int(row['graph_epoch']) == index+1, 'Command sequence/epoch')
            work = command_work(row)
            command_totals[mode].setdefault(index, Counter()).update(work)
            key = (index, int(row['m']), int(row['n']), int(row['k_blocks']),
                   int(row['weight_profile']), int(row['access']))
            shapes[mode][key] += 1
        elif line.startswith('GGML_RISCV_QBS_CALL '):
            require(mode in (0, 1) and index < 6, 'Call outside model step')
            row = fields(line)
            require(row['type'] in ('q4_K', 'q6_K') and row['split_k'] == '0', 'Unsupported logical call')
            m, n, k = (int(row[key]) for key in ('input_rows', 'output_rows', 'k'))
            require(m > 0 and n > 0 and k > 0 and k % 256 == 0 and
                    row['mode'] == ('gemv' if m == 1 else 'gemm'), 'Call geometry')
            call_totals[mode].setdefault(index, Counter()).update(calls=1, useful_pairs=m*n*k)
            call_shapes[mode][(index, row['type'], m, n, k)] += 1
        elif line.startswith('REGISTER_MODEL_STEP '):
            row = fields(line)
            require(mode in (0, 1) and (int(row['enabled']), int(row['kind']), int(row['step'])) ==
                    (mode, index//3, index%3), 'Step order')
            require(index in command_totals[mode] and index in call_totals[mode] and
                    command_totals[mode][index]['useful_pairs'] == call_totals[mode][index]['useful_pairs'],
                    'Logical calls and native commands do not conserve MAC work')
            index += 1
        elif line.startswith('REGISTER_MODEL_END '):
            require(mode is not None and int(fields(line)['enabled']) == mode and index == 6, 'Incomplete model')
            ended.append(mode); mode = None
    require(mode is None and begun == ended == [0, 1], 'Incomplete paired trace')
    require(command_totals[0] == command_totals[1] and call_totals[0] == call_totals[1] and
            shapes[0] == shapes[1] and call_shapes[0] == call_shapes[1], 'Attention choice changed projection work')
    stages = {}
    for label, indices in (('prefill', (0, 3)), ('decode', (1, 2, 4, 5))):
        totals = Counter()
        for i in indices:
            totals.update(command_totals[0][i]); totals['logical_calls'] += call_totals[0][i]['calls']
        stages[label] = dict(totals, matrix_candidate_mac_fraction=totals['eligible_pairs']/totals['useful_pairs'])
    return dict(stages_per_mode=stages,
                logical_shapes_per_mode=[dict(model_record=k[0], weight_type=k[1], m=k[2], n=k[3], k=k[4],
                                              calls=v, useful_pairs=k[2]*k[3]*k[4]*v)
                                         for k, v in sorted(call_shapes[0].items())],
                shapes_per_mode=[dict(model_record=k[0], m=k[1], n=k[2], k_blocks=k[3],
                                      weight_profile=k[4], access=k[5], commands=v)
                                 for k, v in sorted(shapes[0].items())],
                measured_modes=2, hardware_cycles_measured=False,
                limitations=['Historical native model work replay, not current model performance',
                             'MAC fraction is not cycle fraction or whole-inference coverage',
                             'Weight payload excludes activation/descriptor/alignment and is not measured DRAM traffic',
                             'Dot/transfer service floors omit FP, dependencies, arbitration and runtime costs',
                             'Prefill/Decode refer to model steps, not command M; final-output pruning may use M1 in Prefill'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = dict(state='CHECKING', hardware_cycles_measured=False)
    try:
        run = args.run.resolve(strict=True)
        original = json.loads((run/'result.json').read_text())
        require(original['state'] == 'PASS' and original['post_pins_match'] and
                digest(run/'source-pins.json') == original['source_pins_sha256'], 'Unaccepted historical model')
        # Replay the original numerical/route checker as well as work conservation.
        import sys
        here = Path(__file__).resolve().parent
        checker = here.parents[1]/'akv/quantized_kv/prefill/run_register_model_qemu.py'
        sys.path.insert(0, str(checker.parent))
        require(sys.flags.optimize == 0, 'Original assert-based checker requires Python assertions')
        input_pins = {str(p): digest(p) for p in (Path(__file__), here/'audit.py', checker,
                      checker.parent/'run_replay.py', run/'result.json', run/'source-pins.json',
                      run/'qemu.log', run/'link.command.json', run/'qemu.command.json')}
        from run_register_model_qemu import check as model_check
        text = (run/'qemu.log').read_text()
        require(model_check(text) == original['measured'], 'Historical numerical replay differs')
        measured = check(text)
        # Rehash runtime artifacts, not mutable source paths from an old checkout.
        pins = json.loads((run/'source-pins.json').read_text())
        link = json.loads((run/'link.command.json').read_text())
        qemu = json.loads((run/'qemu.command.json').read_text())
        runtime = [Path(p) for p in link if p.endswith('.a')]
        runtime += [run/'test', Path(qemu[0]), Path(qemu[qemu.index('-initrd')+1]),
                    Path(qemu[qemu.index('-kernel')+1]), Path(qemu[qemu.index('-bios')+1])]
        drive = qemu[qemu.index('-drive')+1]
        require(drive.startswith('file=') and ',readonly=on' in drive, 'Read-only model disk required')
        runtime.append(Path(drive.split(',', 1)[0].removeprefix('file=')))
        for path in runtime:
            verify_runtime_artifact(pins, path)
        runtime_pins = {str(p): digest(p) for p in runtime}
        verify_pins(input_pins)
        result.update(state='HISTORICAL_QWEN3_PROJECTION_WORK_REPLAY_PASS', measured=measured,
                      source_run=str(run), original_numerical_replay=True,
                      runtime_pins=runtime_pins, input_pins=input_pins,
                      current_rtl_tested=False, original_source_tree_fully_reaudited=False)
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__': main()
