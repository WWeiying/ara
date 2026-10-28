#!/usr/bin/env python3
"""Replay identity-audited real quantized Prefill tensors on the host, not RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = root / 'verification/out'
    audit = base / 'quant-prefill-capture-audit-20261028-01'
    pins = json.loads((audit / 'manifest.json').read_text())
    assert json.loads((audit / 'result.json').read_text())['state'] == 'PASS'
    for name, expected in pins.items():
        assert digest(name) == expected, name
    source = Path(__file__).parent / 'replay_capture.cpp'
    ggml = Path('/home/wangwy/llama/llama-q4km-extract/ggml')
    libraries = base / 'akv-quantkv-host-capture-20261024-01/build/bin'
    # Preserve the executable name: distro g++ may be a ccache wrapper symlink.
    compiler = Path(shutil.which('g++'))
    extras = [Path(__file__), source, Path(__file__).parent / 'prefix_schedule.h',
              root / 'software/akv/experimental/quantized_kv/online.h',
              audit / 'manifest.json', audit / 'result.json', compiler]
    extras += list(ggml.rglob('*.h'))
    pins.update({str(p.resolve()): digest(p) for p in extras})
    (out / 'inputs.json').write_text(json.dumps(pins, indent=2) + '\n')
    binary = out / 'replay'
    cmd = [str(compiler), '-std=c++17', '-O2', '-march=native', '-Wall', '-Wextra',
           '-Werror', '-fno-fast-math', '-ffp-contract=fast', '-frounding-math',
           '-I' + str(root), '-I' + str(ggml / 'include'), '-I' + str(ggml / 'src'),
           str(source), '-L' + str(libraries), '-Wl,-rpath,' + str(libraries),
           '-lggml-cpu', '-lggml-base', '-lm', '-o', str(binary)]
    commands = [cmd]
    (out / 'commands.json').write_text(json.dumps(commands, indent=2))
    with (out / 'build.log').open('w') as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    results = {}
    for kind in ('q4_0', 'q8_0'):
        capture = base / 'quant-prefill-capture-20261028-01' / kind / 'prefill/block'
        cmd = [str(binary), str(capture), kind]
        commands.append(cmd)
        (out / 'commands.json').write_text(json.dumps(commands, indent=2))
        run = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=60)
        (out / (kind + '.log')).write_text(run.stdout)
        assert run.returncode == 0, run.stdout
        assert run.stdout.startswith('REAL_PREFIX_PASS type=' + kind), run.stdout
        results[kind] = run.stdout.strip()
    for name, expected in pins.items():
        assert digest(name) == expected, name
    result = dict(state='PASS', results=results, binary_sha256=digest(binary),
                  scope='Host real-data scheduling equivalence; not hardware timing',
                  performance_measured=False, production_integration=False)
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
