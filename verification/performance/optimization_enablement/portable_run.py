#!/usr/bin/env python3
"""Fresh host GGML oracle and bounded policy checks; never launch a model or EDA."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
HERE = ROOT / 'verification/performance/optimization_enablement'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
SDK_REV = 'f50092f2d22238c6be4b6c159a1ad71a4ea68678'


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
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT and
            re.fullmatch(r'enablement_portable_[A-Za-z0-9_-]+', out.name), 'Direct signoff portable output required')
    if not out.exists():
        out.mkdir()
    require(set(p.name for p in out.iterdir()) <= {'preimage'}, 'Preserve existing run evidence')
    inputs = out / 'inputs'
    inputs.mkdir()
    pins, commands = {}, []
    result = dict(state='FAIL', native_execution=False, rtl_execution=False,
                  performance_measured=False, model_executed=False, fpga_acceptance=False,
                  sdk_revision=SDK_REV)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GGML_', 'AKV_'))}
    env.update(LC_ALL='C', LANG='C')

    def pin(path):
        path = Path(path).resolve()
        digest = sha(path)
        require(str(path) not in pins or pins[str(path)] == digest, 'Pin drift: ' + str(path))
        pins[str(path)] = digest

    def copy(src, dst):
        pin(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        pin(dst)

    def verify():
        for path, digest in pins.items():
            require(sha(path) == digest, 'Input drift: ' + path)

    def run(label, argv, timeout=120):
        argv = list(map(str, argv))
        pin(Path(shutil.which(argv[0]) or argv[0]))
        with (out / (label + '.log')).open('x') as log:
            done = subprocess.run(argv, cwd=out, env=env, stdin=subprocess.DEVNULL,
                                  stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        commands.append(dict(label=label, argv=argv, returncode=done.returncode))
        require(done.returncode == 0, 'Command failed: ' + label)
        return (out / (label + '.log')).read_text()

    def archive(repo, revision, relative, dst, label):
        raw = subprocess.check_output(['git', '-C', str(repo), 'archive', revision, relative])
        (out / (label + '.tar')).write_bytes(raw)
        pin(out / (label + '.tar'))
        with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
            for member in tar.getmembers():
                require((member.isfile() or member.isdir()) and '..' not in Path(member.name).parts
                        and not Path(member.name).is_absolute(), 'Unexpected archive entry')
            tar.extractall(dst)

    try:
        pin(__file__)
        for name in ('akv.cpp', 'resident.inc'):
            source = LLAMA / 'ggml/src/ggml-cpu/arch/riscv' / name
            pin(source)
            preimage = out / 'preimage' / name
            if preimage.exists():
                pin(preimage)
                diff = subprocess.run(['diff', '-u', str(preimage), str(source)], capture_output=True)
                require(diff.returncode in (0, 1), 'Cannot compare preimage')
                (out / (name + '.delta.patch')).write_bytes(diff.stdout)
        result['llama_head'] = subprocess.check_output(['git', '-C', str(LLAMA), 'rev-parse', 'HEAD']).decode().strip()
        (out / 'llama-existing-wip.diff').write_bytes(subprocess.check_output(
            ['git', '-C', str(LLAMA), 'diff', '--binary']))
        archive(LLAMA, result['llama_head'], 'ggml', inputs / 'llama', 'ggml-head')
        names = subprocess.check_output(['git', '-C', str(LLAMA), 'ls-files', '-m', '-o',
                                         '--exclude-standard', '-z', 'ggml']).decode().split('\0')
        for name in filter(None, names):
            copy(LLAMA / name, inputs / 'llama' / name)
        archive(ROOT, SDK_REV, 'software/akv', inputs / 'sdk', 'sdk-pinned')
        sdk = inputs / 'sdk/software/akv'
        ggml = inputs / 'llama/ggml'
        arch = ggml / 'src/ggml-cpu/arch/riscv'
        copy(ROOT / 'verification/akv/ggml_portability_test.cpp', inputs / 'portable_oracle.cpp')
        copy(ROOT / 'software/akv/tests/akv_portability_test.c', inputs / 'sdk_oracle.c')
        copy(HERE / 'portable_host_test.cpp', inputs / 'portable_host_test.cpp')
        for path in inputs.rglob('*'):
            if path.is_file():
                pin(path)
        run('ggml-configure', ['cmake', '-S', ggml, '-B', out / 'ggml-build',
            '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=OFF', '-DGGML_NATIVE=OFF',
            '-DGGML_OPENMP=OFF', '-DGGML_CCACHE=OFF', '-DGGML_BUILD_TESTS=OFF',
            '-DGGML_BUILD_EXAMPLES=OFF', '-DGGML_BACKEND_DL=OFF'])
        run('ggml-build', ['cmake', '--build', out / 'ggml-build', '-j2'], timeout=300)
        libs = [out / 'ggml-build/src' / name for name in ('libggml.a', 'libggml-cpu.a', 'libggml-base.a')]
        for lib in libs:
            pin(lib)
        common = ['-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror', '-Wno-unknown-pragmas',
                  '-fno-fast-math', '-ffp-contract=off', '-ffunction-sections', '-fdata-sections']
        includes = []
        for path in (ggml / 'include', ggml / 'src', ggml / 'src/ggml-cpu', arch,
                     sdk / 'include', sdk / 'experimental'):
            includes += ['-isystem', str(path)]
        sources = [sdk / 'src' / name for name in ('akv_runtime.c', 'akv_native_riscv.c',
            'akv_v2_native_riscv.c', 'akv_v2_reference.c', 'akv_prefill_reference.c',
            'akv_features.c', 'akv_decode.c')]
        sources += [arch / 'entry.c', arch / 'platform.c']
        results = []
        for mode, extra in (('gnu', []), ('ubsan', ['-fsanitize=undefined', '-fno-sanitize-recover=all'])):
            objects = []
            for index, source in enumerate(sources):
                obj = out / (mode + '-' + str(index) + '.o')
                flags = ['-std=c11', *common, *extra, *includes, '-DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1']
                dep = out / (mode + '-' + str(index) + '.d')
                run(mode + '-' + str(index) + '-deps', ['gcc', *flags, '-M', '-MF', dep, source])
                for name in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]):
                    pin(name)
                run(mode + '-' + str(index) + '-compile', ['gcc', *flags, '-c', source, '-o', obj])
                pin(obj)
                objects.append(obj)
            oracle = out / (mode + '-sdk-oracle')
            run(mode + '-sdk-link', ['gcc', '-std=c11', *common, *extra, *includes,
                inputs / 'sdk_oracle.c', *objects, '-Wl,--gc-sections', '-lm', '-o', oracle])
            text = run(mode + '-sdk-run', [oracle])
            require('PASS' in text and 'FAIL' not in text, 'SDK oracle did not complete')
            for profile in (0, 1):
                label = mode + '-profile-' + str(profile)
                exe = out / label
                flags = ['-std=c++17', *common, '-Wno-unused-function', *extra, *includes,
                    '-DGGML_RISCV_ACCEL_AUTO=' + str(profile), '-DGGML_AKV_RESIDENT=1',
                    '-DPORTABLE_BACKEND_SOURCE="' + str(arch / 'akv.cpp') + '"',
                    '-DPORTABLE_ORACLE_SOURCE="' + str(inputs / 'portable_oracle.cpp') + '"']
                dep = out / (label + '.d')
                run(label + '-deps', ['g++', *flags, '-M', '-MF', dep, inputs / 'portable_host_test.cpp'])
                for name in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]):
                    pin(name)
                run(label + '-link', ['g++', *flags, inputs / 'portable_host_test.cpp', *objects,
                    '-Wl,--gc-sections', '-Wl,--start-group', *libs, '-Wl,--end-group', '-pthread', '-ldl',
                    '-lm', '-o', exe])
                pin(exe)
                text = run(label + '-run', [exe])
                require(re.search(r'PORTABLE_HOST_PASS profile=' + str(profile) + r' checks=\d+', text)
                        and 'AKV GGML portability: PASS cases=18 concurrent_graphs=2 fallbacks=2 legacy=1' in text,
                        'Missing backend oracle completion')
                results.append(dict(mode=mode, profile=profile, log_sha256=sha(out / (label + '-run.log'))))
        verify()
        result.update(state='PORTABLE_HOST_CHECKED', checks=results, post_pins_match=True,
                      scope='Fresh host backend/oracle; not native hardware or board acceptance')
    except BaseException as exc:
        result['error'] = repr(exc)
    save(out / 'source-pins.json', pins)
    save(out / 'commands.json', commands)
    result['source_pins_sha256'] = sha(out / 'source-pins.json')
    save(out / 'result.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return result['state'] != 'PORTABLE_HOST_CHECKED'


if __name__ == '__main__':
    raise SystemExit(main())
