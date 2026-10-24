#!/usr/bin/env python3
"""Check actual projection/quantized-Attention/projection context interleaving."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import signal
import sys

sys.dont_write_bytecode = True
from run_live_graph import HERE, ROOT, require, digest, hashes, atomic_json, run_command, verify_native_build

PRIOR = ROOT / 'verification/out/akv-quantkv-ggml-live-20261024-02-control'


def fields(line, prefix):
    require(line.startswith(prefix + ' '), 'Wrong trace family')
    tokens = line[len(prefix) + 1:].split()
    require(all(token.count('=') == 1 for token in tokens), 'Malformed trace fields')
    parsed = dict(token.split('=', 1) for token in tokens)
    require(len(parsed) == len(tokens), 'Duplicate trace fields')
    return parsed


def check_log(text):
    require('QUANT_INTERLEAVE_FAIL' not in text and 'Assertion' not in text, 'Numerical failure')
    terminal = 'QUANT_INTERLEAVE_SUITE_NUMERICAL_PASS profiles=2 runs=6 native_runs=4 trace_validation_required=1 performance=not_measured'
    require(text.splitlines().count(terminal) == text.splitlines().count('GUEST_TEST_EXIT=0') == 1,
            'Missing successful terminal records')
    require(text.count('GUEST_TEST_EXIT=') == 1, 'Extra guest status')
    runs = []
    for kind in ('q8_0', 'q4_0'):
        baseline = None
        previous = None
        for run in range(3):
            native = run != 0
            mode = 'native' if native else 'baseline'
            begin = f'QUANT_INTERLEAVE_BEGIN kind={kind} run={run} mode={mode} context={int(native)} cross_op={int(native)} quant_kv={int(native)} threads=1'
            require(text.splitlines().count(begin) == 1, 'Missing/duplicate graph start')
            body = text.split(begin + '\n', 1)[1]
            pattern = (rf'QUANT_INTERLEAVE_END kind={kind} run={run} mode={mode} projection_outputs=128 attention_outputs=1536 '
                       r'projection_digest=([0-9a-f]{16}) attention_digest=([0-9a-f]{16}) fcsr=(\d+) vcsr=3 '
                       r'gold_max_abs=([0-9.e+-]+) ordinary_max_abs=([0-9.e+-]+) inputs_unchanged=1')
            end_lines = [line for line in body.splitlines() if line.startswith('QUANT_INTERLEAVE_END ')]
            require(bool(end_lines), 'Missing graph completion')
            end = re.fullmatch(pattern, end_lines[0])
            require(end is not None and int(end[3]) <= 31 and all(math.isfinite(float(x)) for x in end.groups()[3:]),
                    'Invalid numerical graph completion')
            section = body.split(end_lines[0] + '\n', 1)[0]
            require('QUANT_INTERLEAVE_BEGIN ' not in section, 'Nested graph interval')
            lines = section.splitlines()
            commands = [(i, fields(line, 'GGML_RISCV_QBS_COMMAND')) for i, line in enumerate(lines)
                        if line.startswith('GGML_RISCV_QBS_COMMAND ')]
            contexts = [(i, fields(line, 'GGML_RISCV_QBS_CROSS_OP')) for i, line in enumerate(lines)
                        if line.startswith('GGML_RISCV_QBS_CROSS_OP ')]
            attentions = [(i, line) for i, line in enumerate(lines) if line.startswith('GGML_RISCV_QUANT_KV')]
            require(len(commands) == 4, 'Projection command count differs')
            for _, command in commands:
                require(command['weight_type'] == 'q4_K' and command['weight_profile'] == '1' and
                        command['activation_profile'] == '1' and command['m'] == '1' and command['n'] == '32' and
                        command['k_blocks'] == '1' and command['segmented'] == command['emulated'] == '0',
                        'Wrong projection implementation or geometry')
            if native:
                require(len(contexts) == 2 and len(attentions) == 1, 'Missing lifetime or Attention execution')
                fill_i, fill = contexts[0]
                release_i, release = contexts[1]
                first_i, first = commands[0]
                last_i, last = commands[3]
                require(fill_i < first_i < commands[1][0] < attentions[0][0] < release_i < commands[2][0] < last_i,
                        'Not a real interleaved lifetime')
                require(fill['action'] == 'fill_keep' and release['action'] == 'reuse_release' and
                        fill['quantization_skipped'] == '0' and release['quantization_skipped'] == '1' and
                        release['activation_bytes_saved'] == '292', 'Activation reuse was not effective')
                for key in ('graph_epoch', 'source_id', 'generation'):
                    require(fill[key] == release[key], 'Context identity changed')
                require([c['access'] for _, c in commands] == ['1', '2', '2', '3'] and
                        all(c['context_generation'] == fill['generation'] for _, c in commands) and
                        all(c['activation_seq'] == release['activation_seq'] and c['linked'] == '1' for _, c in commands) and
                        int(first['activation_seq']) > 0,
                        'Commands do not consume the same activation lifetime')
                require(attentions[0][1] == 'GGML_RISCV_QUANT_KV status=0 mapping=0 memory=1 runtime_called=1 command_attempts=16 groups=2 value_decodes=256 executor_status=0',
                        'Attention did not execute the complete quantized entry')
                require(end[1] == baseline[1] and end[3] == baseline[3], 'Projection bits or FCSR changed')
                if previous is not None:
                    require(end[2] == previous, 'Repeated Attention output changed')
                previous = end[2]
            else:
                require(not contexts and not attentions and all(c['access'] == '0' for _, c in commands),
                        'Baseline unexpectedly enabled contexts or quantized Attention')
                baseline = end
            runs.append(dict(kind=kind, run=run, native=native, projection_digest=end[1],
                             attention_digest=end[2], fcsr=int(end[3]), vcsr=3))
    require(text.count('QUANT_INTERLEAVE_BEGIN ') == text.count('QUANT_INTERLEAVE_END ') == 6 and
            text.count('GGML_RISCV_QUANT_KV ') == 4 and text.count('GGML_RISCV_QBS_COMMAND ') == 24 and
            text.count('GGML_RISCV_QBS_CROSS_OP ') == 8, 'Extra or missing graph work')
    return dict(state='INTERLEAVED_GGML_CHECKED', runs=runs, profiles=2, native_lifetimes=4,
                quantized_attention_command_attempts=64, projection_commands=24, whole_model=False, rtl_performance=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state='PREFLIGHT', pid=os.getpid(), child_pid=None)
    def save(): atomic_json(out / 'status.json', state)
    def interrupted(sig, _frame): raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, interrupted)
    def run(argv, name, timeout):
        def started(pid):
            state.update(state=name.upper(), child_pid=pid)
            save()
        atomic_json(out / (name + '.command.json'), list(map(str, argv)))
        try:
            require(run_command(list(map(str, argv)), out / (name + '.log'), timeout,
                                os.environ.copy(), started) == 0, name + ' failed')
        finally:
            state['child_pid'] = None
            save()
    save()
    try:
        receipt = json.loads((PRIOR / 'result.json').read_text())
        require(receipt['state'] == 'PASS', 'Actual GGML prerequisite not accepted')
        pins = json.loads((PRIOR / 'source-pins.json').read_text())
        require(digest(PRIOR / 'source-pins.json') == receipt['source_pins_sha256'], 'Prior receipt drift')
        original_build = Path(json.loads((PRIOR / 'status.json').read_text())['build'])
        libraries = [original_build / 'ggml/src' / ('lib' + name + '.a') for name in ('ggml', 'ggml-cpu', 'ggml-base')]
        pinned = [Path(__file__), HERE / 'run_live_graph.py', PRIOR / 'result.json', PRIOR / 'status.json',
                  PRIOR / 'source-pins.json', PRIOR / 'initramfs.list', PRIOR / 'init', *libraries,
                  HERE / 'ggml_interleave/test.cpp', HERE / 'ggml_interleave/CMakeLists.txt']
        pins.update(hashes(pinned))
        def unchanged(): require(all(digest(Path(p)) == sha for p, sha in pins.items()), 'Interleaving source/artifact drift')
        unchanged()
        atomic_json(out / 'source-pins.json', pins)
        toolchain = '/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake'
        run(['/usr/bin/cmake', '-S', HERE / 'ggml_interleave', '-B', out / 'build',
             '-DCMAKE_TOOLCHAIN_FILE=' + toolchain, '-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_EXE_LINKER_FLAGS=-static', '-DGGML_ACCEPTED_BUILD=' + str(original_build)], 'configure', 180)
        run(['/usr/bin/cmake', '--build', out / 'build', '-j4'], 'build', 180)
        binary = out / 'build/ggml-quant-kv-interleave'
        listing = (PRIOR / 'initramfs.list').read_text().splitlines()
        listing = [f'file /test {binary} 755 0 0' if line.startswith('file /test ') else line for line in listing]
        require(sum(line.startswith('file /test ') for line in listing) == 1, 'Missing guest program slot')
        (out / 'initramfs.list').write_text('\n'.join(listing) + '\n')
        cpio = Path('/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio')
        import subprocess
        with (out / 'initramfs.cpio').open('wb') as dest, (out / 'cpio.log').open('wb') as log:
            subprocess.run([cpio, out / 'initramfs.list'], stdout=dest, stderr=log, check=True, timeout=60)
        pins.update(hashes([binary, out / 'initramfs.list', out / 'initramfs.cpio', out / 'build/CMakeCache.txt']))
        atomic_json(out / 'source-pins.json', pins)
        unchanged()
        command = json.loads((PRIOR / 'qemu.command.json').read_text())
        command[command.index('-initrd') + 1] = str(out / 'initramfs.cpio')
        verify_native_build(Path(command[0]))
        run(command, 'qemu', 600)
        result = check_log((out / 'qemu.log').read_text().replace('\r\n', '\n'))
        unchanged()
        result.update(state='PASS', current_inputs_match=True, log_sha256=digest(out / 'qemu.log'),
                      source_pins_sha256=digest(out / 'source-pins.json'))
        atomic_json(out / 'result.json', result)
        state.update(state='PASS', result=result)
    except BaseException as exc:
        state.update(state='INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL', error=repr(exc))
        atomic_json(out / 'result.json', dict(state=state['state'], error=repr(exc)))
        raise
    finally:
        state['child_pid'] = None
        save()


if __name__ == '__main__': main()
