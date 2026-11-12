#!/usr/bin/env python3
"""Check frozen current software policy and platform admission; no native work."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
SDK_REV = 'f50092f2d22238c6be4b6c159a1ad71a4ea68678'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    if out != out.resolve() or out.parent != OUT or not re.fullmatch(
            r'enablement_host_[A-Za-z0-9_-]+', out.name) or out.exists():
        raise ValueError('A fresh direct signoff enablement_host_* output is required')
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    commands, pins = [], {}
    result = dict(state='FAIL', native_execution=False, performance_measured=False,
                  fpga_acceptance=False, sdk_revision=SDK_REV)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GGML_', 'AKV_'))}
    env.update(LC_ALL='C', LANG='C')

    def copy(source, name):
        target = inputs / name
        shutil.copyfile(source, target)
        pins[str(source)] = sha(source)
        pins[str(target)] = sha(target)
        return target

    def run(label, argv):
        argv = list(map(str, argv))
        tool = Path(shutil.which(argv[0]) or argv[0]).resolve()
        pins[str(tool)] = sha(tool)
        with (out / (label + '.log')).open('xb') as log:
            child = subprocess.run(argv, cwd=out, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, timeout=90)
        commands.append(dict(label=label, argv=argv, returncode=child.returncode))
        if child.returncode:
            raise RuntimeError(label + ' failed; see its log')
        return (out / (label + '.log')).read_text()

    try:
        pins[str(Path(__file__).resolve())] = sha(__file__)
        policy = copy(ROOT / 'software/llama/accel-options.h', 'accel-options.h')
        live_policy = LLAMA / 'ggml/src/ggml-cpu/arch/riscv/accel-options.h'
        if sha(policy) != sha(live_policy):
            raise ValueError('Canonical and actual llama default policies differ')
        pins[str(live_policy)] = sha(live_policy)
        test = copy(ROOT / 'software/llama/test_accel_options.cpp', 'test_accel_options.cpp')
        policy_checks = {}
        for mode in ('unset', '0', '1'):
            flags = [] if mode == 'unset' else ['-DGGML_RISCV_ACCEL_AUTO=' + mode]
            exe = out / ('policy-' + mode)
            run('policy-' + mode + '-compile', ['g++', '-std=c++17', '-O2', '-UNDEBUG',
                '-Wall', '-Wextra', '-Werror', '-DGGML_ACCEL_TEST_WRAP_GETENV=1', *flags,
                test, '-Wl,--wrap=getenv', '-o', exe])
            text = run('policy-' + mode + '-run', [exe])
            matched = re.fullmatch(r'PASS AUTO=([01]) checks=(\d+)\n', text)
            if not matched or int(matched[1]) != int(mode == '1'):
                raise ValueError('Missing or incorrect policy terminal record')
            policy_checks[mode] = int(matched[2])

        live = LLAMA / 'ggml/src/ggml-cpu/arch/riscv'
        platform = copy(live / 'platform.c', 'platform.c')
        copy(live / 'platform.h', 'platform.h')
        platform_test = copy(ROOT / 'verification/performance/next_mechanism/stage5/runtime/test_platform.c',
                             'test_platform.c')
        archive = subprocess.check_output(['git', '-C', str(ROOT), 'archive', SDK_REV, 'software/akv'])
        (out / 'sdk.tar').write_bytes(archive)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                if not (member.isfile() or member.isdir()) or '..' in Path(member.name).parts:
                    raise ValueError('Unexpected SDK archive entry')
            tar.extractall(inputs / 'sdk')
        sdk = inputs / 'sdk/software/akv'
        for path in (inputs / 'sdk').rglob('*'):
            if path.is_file():
                pins[str(path)] = sha(path)
        platform_checks = {}
        for name, compiler, extra in (
                ('host', 'gcc', []),
                ('ubsan', 'clang', ['-fsanitize=undefined', '-fno-sanitize-recover=all'])):
            exe = out / ('platform-' + name)
            run('platform-' + name + '-compile', [compiler, '-std=gnu11', '-O2', '-UNDEBUG',
                '-Wall', '-Wextra', '-Werror', '-fno-fast-math', '-ffp-contract=off',
                '-ffunction-sections', '-fdata-sections', *extra, '-I' + str(inputs),
                '-I' + str(sdk / 'include'), '-I' + str(sdk / 'experimental'), platform,
                platform_test, sdk / 'src/akv_runtime.c', sdk / 'src/akv_features.c',
                '-Wl,--gc-sections', '-lm', '-o', exe])
            text = run('platform-' + name + '-run', [exe])
            if text != 'PLATFORM_HOST_PASS checks=88 native_execution=0 board_acceptance=0\n':
                raise ValueError('Incomplete platform admission test')
            platform_checks[name] = 88
        if any(sha(path) != digest for path, digest in pins.items()):
            raise ValueError('Input identity drift')
        result.update(state='HOST_POLICY_AND_ADMISSION_PASS', policy_checks=policy_checks,
                      platform_checks=platform_checks, input_identity_match=True)
    except Exception as exc:
        result['error'] = repr(exc)
    save(out / 'source-pins.json', pins)
    save(out / 'commands.json', commands)
    result['source_pins_sha256'] = sha(out / 'source-pins.json')
    result['artifacts'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()}
    save(out / 'result.json', result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['state'] == 'HOST_POLICY_AND_ADMISSION_PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
