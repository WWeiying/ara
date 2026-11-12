#!/usr/bin/env python3
"""Four short Spike boots of the exact live selector; no native AKV or model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
HERE = ROOT / 'verification/performance/optimization_enablement'
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
ARCH = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv')
CXX = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-g++')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT and
            re.fullmatch(r'enablement_portable_[A-Za-z0-9_-]+', out.name) and not out.exists(), 'Fresh portable output required')
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    pins, commands = {}, []
    result = dict(state='FAIL', native_execution=False, selector_only=True, model_executed=False,
                  performance_measured=False, rtl_execution=False, fpga_acceptance=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GGML_', 'AKV_'))}
    env.update(LC_ALL='C', LANG='C')

    def pin(path):
        path = Path(path).resolve()
        digest = sha(path)
        require(str(path) not in pins or pins[str(path)] == digest, 'Input drift: ' + str(path))
        pins[str(path)] = digest

    def copy(src, dst):
        pin(src)
        shutil.copyfile(src, dst)
        pin(dst)

    def run(label, argv):
        argv = list(map(str, argv))
        pin(argv[0])
        with (out / (label + '.log')).open('x') as log:
            done = subprocess.run(argv, cwd=out, env=env, stdin=subprocess.DEVNULL,
                                  stdout=log, stderr=subprocess.STDOUT, timeout=90)
        commands.append(dict(label=label, argv=argv, returncode=done.returncode))
        require(done.returncode == 0, 'Failed: ' + label)
        return (out / (label + '.log')).read_text()

    try:
        pin(__file__)
        pin(ARCH / 'akv.cpp')
        source = (ARCH / 'akv.cpp').read_text()
        start = source.index('static bool portable_decode_selected(')
        end = source.index('static std::mutex & context_mutex()', start)
        (inputs / 'portable_selection.inc').write_text(source[start:end])
        pin(inputs / 'portable_selection.inc')
        copy(ARCH / 'accel-options.h', inputs / 'accel-options.h')
        copy(HERE / 'portable_target_test.cpp', inputs / 'test.cpp')
        old = ROOT / 'verification/performance/next_mechanism/stage4/m4_preflight'
        for name in ('runtime.cpp', 'start.S', 'link.ld'):
            copy(old / name, inputs / name)
        flags = ['-std=c++17', '-O2', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany',
            '-mno-relax', '-msmall-data-limit=0', '-fno-exceptions', '-fno-rtti', '-fno-stack-protector',
            '-fno-builtin', '-fno-tree-loop-distribute-patterns',
            '-ffunction-sections', '-fdata-sections', '-I' + str(inputs)]
        cases = []
        for profile in (0, 1):
            for features in (0, 1):
                label = 'profile-' + str(profile) + '-features-' + str(features)
                extra = ['-DGGML_RISCV_ACCEL_AUTO=' + str(profile)]
                if features:
                    extra.append('-DGGML_AKV_PORTABLE_FEATURES=1')
                elf = out / (label + '.elf')
                dep = out / (label + '.d')
                run(label + '-deps', [CXX, *flags, *extra, '-M', '-MF', dep, inputs / 'test.cpp', inputs / 'runtime.cpp'])
                for row in dep.read_text().replace('\\\n', '').splitlines():
                    for name in shlex.split(row.split(':', 1)[1]):
                        pin(name)
                run(label + '-build', [CXX, *flags, *extra, '-nostdlib', '-static', inputs / 'test.cpp',
                    inputs / 'runtime.cpp', inputs / 'start.S', '-T', inputs / 'link.ld',
                    '-Wl,--gc-sections', '-Wl,--build-id=none', '-lgcc', '-o', elf])
                pin(elf)
                symbols = run(label + '-symbols', [CXX.with_name('riscv64-unknown-elf-nm'), '-n', elf])
                def symbol(name):
                    matches = re.findall(r'^([0-9a-f]+) \w ' + name + '$', symbols, re.M)
                    require(len(matches) == 1, 'Missing symbol: ' + name)
                    return matches[0]
                cmd = out / (label + '.cmd')
                cmd.write_text('until pc 0 ' + symbol('test_exit') + '\nreg 0 a0\nstr ' + symbol('test_log') + '\nrs\n')
                pin(cmd)
                text = run(label + '-spike', [SPIKE, '-d', '--debug-cmd=' + str(cmd),
                    '--isa=rv64gcv_zfh_zvfh_zvl1024b', '-m2', elf])
                marker = 'PORTABLE_TARGET_PASS checks=448 profile=' + str(profile) + ' features=' + str(features)
                require(text.count(marker) == 1 and 'FAIL' not in text and 'TRAP' not in text and
                        len(re.findall(r'^0x0000000000000000$', text, re.M)) == 1, 'Incomplete target check')
                cases.append(dict(profile=profile, features=features, checks=448, elf_sha256=sha(elf)))
        for path, digest in pins.items():
            require(sha(path) == digest, 'Input drift: ' + path)
        result.update(state='PORTABLE_SELECTOR_GNU_SPIKE_CHECKED', cases=cases, post_pins_match=True)
    except BaseException as exc:
        result['error'] = repr(exc)
    save(out / 'source-pins.json', pins)
    save(out / 'commands.json', commands)
    result['source_pins_sha256'] = sha(out / 'source-pins.json')
    save(out / 'result.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return result['state'] != 'PORTABLE_SELECTOR_GNU_SPIKE_CHECKED'


if __name__ == '__main__':
    raise SystemExit(main())
