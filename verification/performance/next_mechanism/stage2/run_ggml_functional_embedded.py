#!/usr/bin/env python3
"""Structural build successor: frozen GGML as a normal embedded subdirectory."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('g4_sealed_runner', HERE/'run_ggml_functional.py')
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)
require, digest, write = v1.require, v1.digest, v1.write
NEW = ('run_ggml_functional_embedded.py', 'test_ggml_functional_embedded.py')
LIBRARIES = ('libggml.a', 'libggml-base.a', 'libggml-cpu.a')


def parent_cmake(ggml, binary):
    paths = [Path(p).resolve() for p in (ggml, binary)]
    require(all(not re.search(r'[";$\\\n\r]', str(p)) for p in paths), 'Unsafe CMake path')
    return ('cmake_minimum_required(VERSION 3.14...3.28)\n'
            'project(stage2_ggml_functional C CXX ASM)\n'
            f'add_subdirectory("{paths[0]}" "{paths[1]}")\n')


def unique_libraries(build):
    result = []
    for name in LIBRARIES:
        matches = sorted(p for p in Path(build).rglob(name) if p.is_file())
        require(len(matches) == 1, f'Exactly one {name} required, found {len(matches)}')
        require(matches[0].resolve().is_relative_to(Path(build).resolve()), 'Library outside fresh build')
        result.append(matches[0])
    return result


def prepare(out):
    v1.OWN = (*v1.OWN, *NEW)
    v1.prepare(out)
    inputs = out/'inputs'; g = inputs/'llama/ggml'
    parent = inputs/'embedded'; parent.mkdir()
    (parent/'CMakeLists.txt').write_text(parent_cmake(g, out/'ggml-build/frozen-ggml'))
    required = ('CMakeLists.txt', 'src/CMakeLists.txt', 'src/ggml-cpu/CMakeLists.txt',
                'cmake/common.cmake', 'cmake/ggml-config.cmake.in')
    require(all((g/p).is_file() for p in required), 'Missing embedded CMake source/template')
    require(not (g/'ggml.pc.in').exists(), 'Do not invent the missing standalone template')
    audit = dict(build_mode='embedded', llama_commit=v1.LLAMA_COMMIT,
        parent_source=str(parent/'CMakeLists.txt'), child_binary=str(out/'ggml-build/frozen-ggml'),
        required_frozen_cmake_sha256={p:digest(g/p) for p in required},
        standalone_pc_template_used=False, upstream_modified=False, live_source_used=False,
        package_config='Generated only; no find_package(GGML) or installed/imported GGML library',
        disabled_template_backends=['metal', 'et', 'vulkan', 'opencl', 'hexagon'],
        displayed_git_commit_is_source_identity=False,
        identity_rule='03959 full git archive plus SHA pins; upstream rev-parse may display enclosing signoff repository HEAD')
    write(out/'embedded-build-audit.json', audit)
    b = v1.base.Builder(out)
    b.commands = json.loads((out/'commands.json').read_text())
    b.run('embedded-host-tests', [sys.executable, '-B', '-m', 'unittest',
        'test_ggml_functional_embedded', '-v'], cwd=inputs)
    config = json.loads((out/'config.json').read_text())
    config.update(build_mode='embedded', displayed_git_commit_is_source_identity=False,
                  source_identity='Frozen 03959 git archive and SHA pins, not upstream rev-parse display')
    write(out/'config.json', config)
    pins = json.loads((out/'source-pins.json').read_text())
    for p in (parent/'CMakeLists.txt', out/'embedded-build-audit.json',
              out/'embedded-host-tests.log', out/'config.json'):
        pins[str(p)] = digest(p)
    write(out/'source-pins.json', pins)
    print('EMBEDDED_PREPARED '+str(out), flush=True)


def build(b):
    # Preserve the sealed build flags, oracle, wrappers and four guest images.
    out = b.output; inputs = out/'inputs'; sdk = inputs/'sdk'; g = inputs/'llama/ggml'
    toolchain = out/'toolchain.cmake'
    flags = '-march=rv64gcv_zfh_zvfh -mabi=lp64d -fno-fast-math -ffp-contract=off'
    toolchain.write_text('set(CMAKE_SYSTEM_NAME Linux)\nset(CMAKE_SYSTEM_PROCESSOR riscv64)\n'+
        f'set(CMAKE_C_COMPILER "{v1.CC}")\nset(CMAKE_CXX_COMPILER "{v1.CXX}")\n'+
        f'set(CMAKE_C_FLAGS "{flags}")\nset(CMAKE_CXX_FLAGS "{flags}")\n')
    opts = dict(BUILD_SHARED_LIBS='OFF', GGML_NATIVE='OFF', GGML_CCACHE='OFF', GGML_LTO='OFF',
        GGML_OPENMP='OFF', GGML_RVV='ON', GGML_RV_ZFH='ON', GGML_RV_ZVFH='ON',
        GGML_RV_ZICBOP='OFF', GGML_RV_ZIHINTPAUSE='OFF', GGML_RV_ZVFBFWMA='OFF',
        GGML_CPU_REPACK='ON', GGML_RISCV_QBS='ON', GGML_RISCV_AKV='OFF', GGML_BACKEND_DL='OFF',
        GGML_BUILD_TESTS='OFF', GGML_BUILD_EXAMPLES='OFF', CMAKE_BUILD_TYPE='Release',
        GGML_RISCV_QBS_RUNTIME_DIR=str(sdk/'software/qbs'), CMAKE_TOOLCHAIN_FILE=str(toolchain))
    build_dir = out/'ggml-build'
    v1.run_command(b, 'configure', ['cmake', '-S', inputs/'embedded', '-B', build_dir,
                                  *[f'-D{k}={v}' for k,v in opts.items()]])
    v1.run_command(b, 'library-build', ['cmake', '--build', build_dir, '--target', 'ggml', '-j4'], timeout=1800)
    libs = unique_libraries(build_dir)
    elf = out/'test'
    inc = ['-I'+str(p) for p in (g/'include', g/'src', g/'src/ggml-cpu', sdk/'software/qbs/include')]
    v1.run_command(b, 'frontend-link', [v1.CXX, *flags.split(), '-std=c++17', '-O3', '-UNDEBUG',
        '-DGGML_USE_RISCV_QBS', *inc, '-MD', '-MF', out/'frontend.d', inputs/'ggml_functional.cpp',
        '-static', '-pthread', '-Wl,--wrap=qbs_native_info', '-Wl,--wrap=qbs_native_execute_command',
        '-Wl,--wrap=ggml_graph_compute', '-Wl,-Map='+str(out/'link.map'),
        '-Wl,--start-group', *libs, '-Wl,--end-group', '-ldl', '-lm', '-o', elf])
    v1.run_command(b, 'native-qbexec-disassembly', [v1.CC.with_name('riscv64-linux-objdump'),
        '-d', '--disassemble=qbs_native_execute_command', elf])
    words = [int(v,16) for v in re.findall(r'(?m)^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s',
        (out/'native-qbexec-disassembly.log').read_text())]
    native = [word for word in words if word & 0x7f == 0x5b and (word >> 12) & 7 == 0]
    require({0x06b5045b, 0x0eb5045b} <= set(native) and
            all(not (word & (1 << 28)) for word in native), 'Ordinary QBEXEC only; no QBACC')
    oracle = out/'oracle'; oracle.mkdir()
    v1.run_command(b, 'oracle-build', ['gcc', '-std=gnu11', '-O2', '-fno-fast-math', '-ffp-contract=off',
        '-frounding-math', '-I'+str(sdk/'verification/qbs'), '-MD', '-MF', out/'oracle.d',
        inputs/'ggml_functional_oracle.c', sdk/'verification/qbs/qbs_ref.c', '-lm', '-o', out/'oracle-host'])
    v1.run_command(b, 'oracle-run', [out/'oracle-host', inputs/'activation_f32.bin', inputs/'weight_q4_K.bin', oracle])
    for arm in v1.check.ARMS:
        work = out/arm; work.mkdir()
        v1.run_command(b, arm+'-init', [v1.CC, '-march=rv64gc', '-mabi=lp64d', '-O2', '-static',
            '-DARM_NAME="'+arm+'"', '-MD', '-MF', work/'init.d', inputs/'ggml_functional_init.c', '-o', work/'init'])
        listing = work/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
            f'file /init {work/"init"} 755 0 0\nfile /test {elf} 755 0 0\n'+
            f'file /input.bin {inputs/"activation_f32.bin"} 644 0 0\n'+
            f'file /weight.bin {inputs/"weight_q4_K.bin"} 644 0 0\n')
        with (work/'initramfs.cpio').open('wb') as cpio:
            subprocess.run([v1.CPIO, listing], stdout=cpio, stderr=subprocess.PIPE, check=True, timeout=60)
    for dep in [*build_dir.rglob('*.o.d'), out/'frontend.d', out/'oracle.d',
                *[out/a/'init.d' for a in v1.check.ARMS]]:
        for name in shlex.split(dep.read_text().replace('\\\n', '').split(':',1)[1]):
            p = Path(name); b.pin(p if p.is_absolute() else build_dir/p)
    for directory in (build_dir, oracle, *[out/a for a in v1.check.ARMS]):
        for p in directory.rglob('*'):
            if p.is_file() and (directory != build_dir or p.suffix in ('.a', '.o', '.cmake', '.txt', '.json')):
                b.pin(p)
    for p in (elf, out/'oracle-host', toolchain, out/'link.map',
              out/'native-qbexec-disassembly.log'): b.pin(p)
    write(out/'build-pins.json', b.pins)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        v1.build = build
        v1.execute(args.output.resolve())
    else:
        prepare(args.output.resolve())
