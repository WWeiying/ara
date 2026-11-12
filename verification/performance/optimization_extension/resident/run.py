#!/usr/bin/env python3
"""Bounded Resident deployment contract tests; no Linux, EDA or board execution."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import shlex
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
LLAMA = Path('/home/wangwy/llama/llama.cpp')
HERE = ROOT / 'verification/performance/optimization_extension/resident'
PLATFORM = ROOT / 'software/llama/platform'
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
SDK_REV = 'f50092f2d22238c6be4b6c159a1ad71a4ea68678'
GNU = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT and not out.exists() and
            re.fullmatch(r'extension_resident_[A-Za-z0-9_-]+', out.name),
            'Fresh direct signoff extension_resident_* output required')
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    pins, commands, counts = {}, [], []
    report = dict(state='FAIL', sdk_revision=SDK_REV, board_acceptance=False,
                  native_execution=False, qemu_execution=False, rtl_execution=False,
                  performance_measured=False, real_platform_binding=False)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    env = dict(PATH='/usr/bin:/bin', HOME='/home/wangwy', LC_ALL='C', LANG='C')

    def pin(path):
        path = Path(path).resolve()
        digest = sha(path)
        require(str(path) not in pins or pins[str(path)] == digest, 'Input drift: ' + str(path))
        pins[str(path)] = digest

    def verify():
        for name, digest in pins.items():
            require(sha(name) == digest, 'Frozen source/tool drift: ' + name)

    def copy(source, dest):
        pin(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        pin(dest)

    def run(label, argv, expected=0):
        verify()
        argv = list(map(str, argv))
        pin(shutil.which(argv[0]) or argv[0])
        with (out / (label + '.log')).open('x') as log:
            done = subprocess.run(argv, cwd=out, env=env, stdin=subprocess.DEVNULL,
                                  stdout=log, stderr=subprocess.STDOUT, timeout=60)
        commands.append(dict(label=label, argv=argv, returncode=done.returncode, timeout_seconds=60))
        require(done.returncode == expected if expected is not None else done.returncode != 0,
                'Unexpected command status: ' + label)
        return (out / (label + '.log')).read_text()

    def deps(label, cc, flags, source):
        dep = out / (label + '.d')
        run(label + '-deps', [cc, *flags, '-M', '-MF', dep, source])
        for name in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]):
            pin(name)

    def host(label, cc, extra, bundle=False, default=False):
        inc = ['-I' + str(inputs / 'platform'), '-I' + str(inputs / 'arch'),
               '-I' + str(inputs / 'sdk/software/akv/include'),
               '-I' + str(inputs / 'sdk/software/akv/experimental')]
        scalar = ['-fno-vectorize', '-fno-slp-vectorize'] if cc.endswith('clang') else [
            '-fno-tree-vectorize', '-fno-tree-slp-vectorize']
        flags = ['-std=gnu11', '-O2', '-UNDEBUG', '-Wall', '-Wextra', '-Werror',
                 '-ffunction-sections', '-fdata-sections', '-ffreestanding', '-fno-builtin',
                 '-fno-fast-math', '-ffp-contract=off', *scalar, *extra, *inc]
        sdk = inputs / 'sdk/software/akv'
        core = [inputs / 'arch/platform.c', inputs / 'arch/entry.c',
                sdk / 'src/akv_runtime.c', sdk / 'src/akv_features.c']
        objects = []
        for index, source in enumerate(core):
            obj = out / (label + '-core-' + str(index) + '.o')
            deps(label + '-core-' + str(index), cc, flags, source)
            run(label + '-core-' + str(index), [cc, *flags, '-c', source, '-o', obj])
            pin(obj)
            objects.append(obj)
        archive = out / (label + '-core.a')
        run(label + '-archive', ['/usr/bin/ar', 'rcs', archive, *objects])
        pin(archive)
        if bundle:
            sources = [inputs / 'provider_bundle.c']
        else:
            sources = [inputs / 'platform/resident_provider.c',
                       inputs / ('default_test.c' if default else 'deployment_test.c')]
            if not default:
                flags += ['-DARA_RESIDENT_LINKED_BINDING=1']
        for index, source in enumerate(sources):
            deps(label + '-provider-' + str(index), cc, flags, source)
        exe = out / label
        run(label + '-link', [cc, *flags, *sources, archive, '-Wl,--gc-sections', '-lm', '-o', exe])
        pin(exe)
        symbols = run(label + '-symbols', ['/usr/bin/nm', exe])
        for symbol in ('akv_resident_platform_current_v1', 'ggml_akv_legacy_current_v1'):
            require(re.search(r'(?m)^\w+ T ' + symbol + '$', symbols), 'Missing strong provider hook')
        text = run(label + '-run', [exe])
        if default:
            require(text == 'RESIDENT_DEFAULT_DENY_PASS csr_reads=0 native_execution=0\n', 'Missing default denial')
        else:
            match = re.fullmatch(r'RESIDENT_DEPLOYMENT_HOST_PASS checks=(\d+) native_execution=0 board_acceptance=0\n', text)
            require(match and int(match[1]) >= 600, 'Incomplete deployment test')
            counts.append(int(match[1]))

    try:
        for directory, dest in ((PLATFORM, inputs / 'platform'), (HERE, inputs)):
            for source in directory.iterdir():
                if source.is_file():
                    copy(source, dest / source.name)
        for name in ('platform.h', 'platform.c', 'entry.h', 'entry.c', 'read_state.S'):
            copy(LLAMA / 'ggml/src/ggml-cpu/arch/riscv' / name, inputs / 'arch' / name)
        for source in (ROOT / 'AGENTS.md', LLAMA / 'AGENTS.md',
                       ROOT / 'hardware/docs/FPGA_OPTIMIZATION_HANDOFF_20261029.md',
                       ROOT / 'hardware/fpga/vcu118/migrations/qbs_akv_validated_20261029.json'):
            pin(source)
        raw = subprocess.check_output(['git', '-C', str(ROOT), 'archive', SDK_REV, 'software/akv'], timeout=30)
        (out / 'sdk-pinned.tar').write_bytes(raw)
        pin(out / 'sdk-pinned.tar')
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            for member in archive.getmembers():
                require((member.isfile() or member.isdir()) and not Path(member.name).is_absolute() and
                        '..' not in Path(member.name).parts, 'Unexpected SDK archive entry')
            archive.extractall(inputs / 'sdk')
        for path in (inputs / 'sdk').rglob('*'):
            if path.is_file():
                pin(path)
        report['sdk_local_assembly_consumed'] = False
        report['llama_head'] = subprocess.check_output(['git', '-C', str(LLAMA), 'rev-parse', 'HEAD']).decode().strip()
        report['ara_head'] = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).decode().strip()

        config = inputs / 'platform/configure_provider.cmake'
        bundle = inputs / 'provider_bundle.c'
        configure = ['/usr/bin/cmake', '-DARA_RESIDENT_DEPLOYMENT_SOURCE=' + str(inputs / 'deployment_test.c'),
                     '-DARA_RESIDENT_PROVIDER_OUTPUT=' + str(bundle), '-P', config]
        run('configure-bundle', configure)
        pin(bundle)
        before = sha(bundle)
        run('configure-refuse-overwrite', configure, expected=None)
        require(sha(bundle) == before, 'Bundle was overwritten')
        run('configure-require-source', ['/usr/bin/cmake', '-DARA_RESIDENT_PROVIDER_OUTPUT=' + str(inputs / 'absent.c'),
                                        '-P', config], expected=None)
        run('configure-missing-source', ['/usr/bin/cmake', '-DARA_RESIDENT_DEPLOYMENT_SOURCE=' + str(inputs / 'absent.c'),
                                        '-DARA_RESIDENT_PROVIDER_OUTPUT=' + str(inputs / 'other.c'), '-P', config], expected=None)
        run('configure-reject-relative', ['/usr/bin/cmake', '-DARA_RESIDENT_DEPLOYMENT_SOURCE=relative.c',
                                         '-DARA_RESIDENT_PROVIDER_OUTPUT=' + str(inputs / 'relative.c'), '-P', config], expected=None)
        host('default', '/usr/bin/gcc', [], default=True)
        host('host', '/usr/bin/gcc', [])
        host('ubsan', '/usr/bin/clang', ['-fsanitize=undefined', '-fno-sanitize-recover=all'])
        host('bundle', '/usr/bin/gcc', [], bundle=True)
        require(len(set(counts)) == 1, 'Host/UBSan/bundle check counts differ')

        flags = ['-std=gnu11', '-march=rv64gv_zfh_zvfh', '-mabi=lp64d', '-mno-relax', '-O2',
                 '-Wall', '-Wextra', '-Werror', '-ffreestanding', '-fno-builtin', '-fno-fast-math',
                 '-ffp-contract=off', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
                 '-I' + str(inputs / 'arch'), '-I' + str(inputs / 'sdk/software/akv/include'),
                 '-I' + str(inputs / 'sdk/software/akv/experimental')]
        for name, extra in (('gnu-default', []), ('gnu-linked', ['-DARA_RESIDENT_LINKED_BINDING=1'])):
            obj = out / (name + '.o')
            source = inputs / 'platform/resident_provider.c'
            deps(name, GNU, flags + extra, source)
            run(name + '-compile', [GNU, *flags, *extra, '-c', source, '-o', obj])
            pin(obj)
            dump = run(name + '-disasm', [GNU.with_name(GNU.name[:-3] + 'objdump'), '-d', '-M', 'no-aliases,numeric', obj])
            instructions = re.findall(r'(?m)^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s+(\S+)', dump)
            require(instructions, 'Empty GNU object')
            for raw_word, mnemonic in instructions:
                word = int(raw_word, 16)
                require(word & 127 not in (0x07,0x27,0x43,0x47,0x4b,0x4f,0x53,0x57,0x0b,0x2b,0x5b,0x7b),
                        'Non-scalar/accelerator opcode: ' + mnemonic)
                require(not (word & 127 == 0x73 and word not in (0x00100073,)), 'CSR access or syscall in adapter')
            undefined = run(name + '-undefined', [GNU.with_name(GNU.name[:-3] + 'nm'), '-u', obj])
            names = {line.split()[-1] for line in undefined.splitlines() if line.strip()}
            allowed = {'akv_resident_platform_read_state_v1'}
            if extra:
                allowed.add('ara_resident_deployment_current_v1')
            require(names <= allowed, 'Unexpected libc/runtime call: ' + repr(names))
        verify()
        report.update(state='RESIDENT_DEPLOYMENT_HOST_GNU_CHECKED', post_pins_match=True,
                      host_checks_per_mode=counts[0], host_modes=['GNU', 'Clang UBSan', 'configured bundle'],
                      scalar_gnu_objects=2, default_denial_checked=True,
                      scope='Contract adapter and synthetic authority; no real platform or numerical acceptance')
    except BaseException as exc:
        report['error'] = repr(exc)
    save(out / 'source-pins.json', pins)
    save(out / 'commands.json', commands)
    report['source_pins_sha256'] = sha(out / 'source-pins.json')
    save(out / 'artifact-pins.json', {str(p): sha(p) for p in out.rglob('*') if p.is_file() and str(p) not in pins})
    save(out / 'result.json', report)
    print(json.dumps(report, sort_keys=True), flush=True)
    return report['state'] != 'RESIDENT_DEPLOYMENT_HOST_GNU_CHECKED'


if __name__ == '__main__':
    raise SystemExit(main())
