#!/usr/bin/env python3
"""One frozen GGML build, four bounded native-QEMU functional arms; no retries."""
import argparse
import difflib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
LLAMA = Path('/home/wangwy/llama/llama.cpp')
LLAMA_COMMIT = '03959acc0f649f9071668d5b72888284e4676d2b'
SDK_COMMIT = 'c2b7db195f5cce6b28b7bfb40b3fe10fe22715fa'
CAPTURE = OUT / 'stage2_qwen3_rows8_20261109_02'
QEMU = OUT / 'qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64'
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
CC, CXX = (PLATFORM / ('tools/bin/riscv64-linux-' + x) for x in ('gcc', 'g++'))
CPIO = PLATFORM / 'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
IMAGE, BIOS = (PLATFORM / ('images/' + x) for x in ('Image', 'fw_dynamic.bin'))
BASE = ROOT / 'verification/performance/chain_profile/q6_decode/build.py'
NATIVE = ROOT / 'verification/qbs/run_ggml_segmented.py'
OWN = ('run_ggml_functional.py', 'check_ggml_functional.py', 'test_ggml_functional.py',
       'ggml_functional.cpp', 'ggml_functional_init.c', 'ggml_functional_oracle.c')
HASHES = dict(
    qemu='37e3b4c100c3e8fbb7a248f3a0ab328797285dfe59e285fcf8540a14bd5b8e4c',
    old_abi='4d7bf2d7f78c44bab494d86aee4163a02087b6ad10a43f1ed0752ff3a98fa117',
    new_abi='691fcc9c0a674193c5f4879e43e9fb72404e822a39dd6037444ae75a2387dada',
    reference='adf815ed88e50d3f9d23dbb8fab2baa959d8d5aaebcd6f15cbd7a347678f423a',
    activation='4ba6296b70be49960bcce50b09efa38afb938993e38cd710ec6cf5ca951a441c',
    weight='b4a6e0165de521eadfd4245f3a7ef329965b5c9e1bab41f9a5822649cf422ac8')
ABI_ADDITIONS = (
    '#define QBS_QBACC_FUNCT7_BIT 3u\n'
    '#define QBS_VRF_CONTINUATION_CAPABILITY_INDEX 4u\n'
    '#define QBS_VRF_CONTINUATION_CAPABILITY_BIT 0u\n'
    '#define QBS_VRF_CONTINUATION_VLEN_BITS 1024u\n',
    '  if (index == QBS_VRF_CONTINUATION_CAPABILITY_INDEX) {\n'
    '#ifdef ARA_QBS_VRF_CONTINUATION\n'
    '    if (vlen_bits == QBS_VRF_CONTINUATION_VLEN_BITS)\n'
    '      return UINT64_C(1) << QBS_VRF_CONTINUATION_CAPABILITY_BIT;\n'
    '#endif\n    return 0;\n  }\n',
    '/* Encoding only: callers must query optional capability before execution. */\n'
    'static inline uint32_t qbs_encode_qbacc(unsigned vd, unsigned rs1,\n'
    '                                      unsigned rs2, unsigned m) {\n'
    '  return qbs_encode_qbexec(vd, rs1, rs2, m) |\n'
    '         (UINT32_C(1) << (25u + QBS_QBACC_FUNCT7_BIT));\n}\n\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


base = module('g4_base', HERE / 'q6_build.py' if (HERE / 'q6_build.py').exists() else BASE)
base.ROOT = ROOT
check = module('g4_check', HERE / 'check_ggml_functional.py')
require, digest, write = base.require, base.digest, base.write_json


def compatible_abi(old, new):
    reduced = new
    for block in ABI_ADDITIONS:
        require(reduced.count(block) == 1, 'ABI extension differs from exact audited addition')
        reduced = reduced.replace(block, '', 1)
    require(reduced == old, 'Ordinary QBEXEC ABI differs; no compatibility waiver')
    return dict(ordinary_qbexec_unchanged=True, additions='QBACC encoding/capability only',
                qbacc_used=False, required_runtime_capability4=0)


def pin_tools(b):
    for tool in (CC, CXX, CPIO, IMAGE, BIOS, QEMU, Path(sys.executable),
                 Path(shutil.which('gcc')), Path(shutil.which('cmake')), Path(shutil.which('make'))):
        b.pin(tool); b.pin(tool.resolve())
    for compiler in (CC, CXX):
        for name in ('cc1', 'cc1plus', 'as', 'ld', 'collect2', 'ar', 'ranlib'):
            value = subprocess.check_output([compiler, '-print-prog-name='+name], text=True).strip()
            p = Path(value) if Path(value).is_file() else Path(shutil.which(value))
            b.pin(p); b.pin(p.resolve())
        for name in ('libc.a', 'libm.a', 'libgcc.a', 'libgcc_eh.a', 'libstdc++.a',
                     'libpthread.a', 'libdl.a', 'crt1.o', 'crti.o', 'crtn.o', 'crtbeginT.o', 'crtend.o'):
            p = Path(subprocess.check_output([compiler, '-print-file-name='+name], text=True).strip())
            require(p.is_file(), 'Missing static runtime: '+str(p)); b.pin(p)
    objdump = CC.with_name('riscv64-linux-objdump')
    b.pin(objdump); b.pin(objdump.resolve())


def verify_pins(pins):
    for path, sha in pins.items():
        require(digest(path) == sha, 'Pinned identity drift: '+path)


def prepare(out):
    require(out.parent == OUT and re.fullmatch(r'stage2_ggml_functional_[A-Za-z0-9_]+', out.name)
            and not out.exists(), 'Fresh direct stage2_ggml_functional_* output required')
    out.mkdir(); b = base.Builder(out)
    inputs = out / 'inputs'; inputs.mkdir()
    for source, name in [(HERE / n, n) for n in OWN] + [(BASE, 'q6_build.py'), (NATIVE, 'native_tools.py')]:
        b.pin(source); shutil.copyfile(source, inputs / name); b.pin(inputs / name)
    b.archive(LLAMA, LLAMA_COMMIT, ['ggml'], inputs / 'llama')
    b.archive(ROOT, SDK_COMMIT, ['software/qbs', 'apps/common',
        'verification/qbs/qbs_ref.c', 'verification/qbs/qbs_ref.h'], inputs / 'sdk')
    for path in (inputs / 'llama', inputs / 'sdk'):
        for p in path.rglob('*'):
            if p.is_file(): b.pin(p)
    native = module('g4_native_tools', inputs / 'native_tools.py')
    require(digest(QEMU) == HASHES['qemu'], 'Unaccepted QEMU identity')
    for p in native.verify_native_build(QEMU): b.pin(p)
    model = QEMU.parent.parent / 'qemu-10.2.0/target/riscv'
    old, new = model / 'qbs_abi.h', inputs / 'sdk/apps/common/qbs_abi.h'
    require(digest(old) == HASHES['old_abi'] and digest(new) == HASHES['new_abi'], 'ABI SHA mismatch')
    audit = compatible_abi(old.read_text(), new.read_text())
    ref = inputs / 'sdk/verification/qbs/qbs_ref.c'
    require(digest(ref) == digest(model / 'qbs_ref.c') == HASHES['reference'], 'Reference SHA mismatch')
    require((model / 'qbs_ref.h').read_text() == (ref.with_suffix('.h')).read_text().replace(
        '../../apps/common/qbs_abi.h', 'qbs_abi.h'), 'Reference header differs')
    audit.update(old_sha256=digest(old), sdk_sha256=digest(new), reference_sha256=digest(ref),
        scope='New sidecar only; original runner unchanged. No QBACC or hardware/cycle acceptance.')
    write(out / 'abi-compatibility.json', audit); b.pin(out / 'abi-compatibility.json')
    (out / 'abi.diff').write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),
        new.read_text().splitlines(True), fromfile=str(old), tofile=str(new))))
    b.pin(out / 'abi.diff')
    receipt = json.loads((CAPTURE / 'result.json').read_text())
    require(receipt['state'] == 'CAPTURED_NOT_BENCHMARKED' and receipt['source_pins_match'] and
            receipt['rows'] == 8 and receipt['k'] == 2048 and
            receipt['views'][0]['tensor'] == 'blk.0.attn_q.weight', 'Wrong real capture')
    for n in ('result.json', 'source-pins.json'): b.pin(CAPTURE / n)
    # Recheck the capture's input identities as well as the selected raw artifacts.
    capture_pins = json.loads((CAPTURE / 'source-pins.json').read_text())
    verify_pins(capture_pins)
    for path in capture_pins: b.pin(path)
    for kind, name, size in (('activation', 'activation_f32.bin', 8*2048*4),
                             ('weight', 'weight_q4_K.bin', 128*8*144)):
        source = CAPTURE / 'attn_q' / name
        require(source.stat().st_size == size and digest(source) == HASHES[kind], 'Wrong '+kind)
        b.pin(source); shutil.copyfile(source, inputs / name); b.pin(inputs / name)
    pin_tools(b)
    # A compile-only interface preflight is not a library build or an executed arm.
    g = inputs / 'llama/ggml'; sdk = inputs / 'sdk/software/qbs'
    inc = ['-I'+str(p) for p in (g/'include', g/'src', g/'src/ggml-cpu', sdk/'include')]
    b.run('frontend-interface', [CXX, '-std=c++17', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d',
        '-DGGML_USE_RISCV_QBS', *inc, '-fsyntax-only', inputs / 'ggml_functional.cpp'])
    b.run('host-contract-tests', [sys.executable, '-B', '-m', 'unittest',
        'test_ggml_functional', '-v'], cwd=inputs)
    config = dict(state='PREPARED', llama_commit=LLAMA_COMMIT, sdk_commit=SDK_COMMIT,
        arms=list(check.ARMS), per_arm_timeout_seconds=600, library_builds=1,
        scope='Real GGML functional/selection/complete quantization only; native QEMU is not RTL or cycle evidence',
        oracle_caveat='Host oracle is independent of GGML packing/dispatch, but QEMU and host share pinned qbs_ref arithmetic',
        rvv_tolerance=[check.RVV_ATOL, check.RVV_RTOL], model_sha256=receipt['views'][0]['model_sha256'])
    write(out / 'config.json', config); b.pin(out / 'config.json')
    verify_pins(b.pins); write(out / 'source-pins.json', b.pins)
    print('PREPARED '+str(out), flush=True)


def run_command(b, name, argv, timeout=120, cwd=None):
    argv = list(map(str, argv)); cwd = Path(cwd or b.output)
    b.commands.append(dict(label=name, argv=argv, cwd=str(cwd), timeout=timeout))
    write(b.output / 'commands.json', b.commands)
    with (b.output / (name+'.log')).open('wb') as log:
        subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                       timeout=timeout, check=True)


def build(b):
    out = b.output; inputs = out / 'inputs'; sdk = inputs / 'sdk'; g = inputs / 'llama/ggml'
    toolchain = out / 'toolchain.cmake'
    flags = '-march=rv64gcv_zfh_zvfh -mabi=lp64d -fno-fast-math -ffp-contract=off'
    toolchain.write_text('set(CMAKE_SYSTEM_NAME Linux)\nset(CMAKE_SYSTEM_PROCESSOR riscv64)\n'+
        f'set(CMAKE_C_COMPILER "{CC}")\nset(CMAKE_CXX_COMPILER "{CXX}")\n'+
        f'set(CMAKE_C_FLAGS "{flags}")\nset(CMAKE_CXX_FLAGS "{flags}")\n')
    opts = dict(BUILD_SHARED_LIBS='OFF', GGML_NATIVE='OFF', GGML_CCACHE='OFF', GGML_LTO='OFF',
        GGML_OPENMP='OFF', GGML_RVV='ON', GGML_RV_ZFH='ON', GGML_RV_ZVFH='ON',
        GGML_RV_ZICBOP='OFF', GGML_RV_ZIHINTPAUSE='OFF', GGML_RV_ZVFBFWMA='OFF',
        GGML_CPU_REPACK='ON', GGML_RISCV_QBS='ON', GGML_RISCV_AKV='OFF', GGML_BACKEND_DL='OFF',
        GGML_BUILD_TESTS='OFF', GGML_BUILD_EXAMPLES='OFF', CMAKE_BUILD_TYPE='Release',
        GGML_RISCV_QBS_RUNTIME_DIR=str(sdk/'software/qbs'), CMAKE_TOOLCHAIN_FILE=str(toolchain))
    build_dir = out / 'ggml-build'
    run_command(b, 'configure', ['cmake', '-S', g, '-B', build_dir, *[f'-D{k}={v}' for k,v in opts.items()]])
    run_command(b, 'library-build', ['cmake', '--build', build_dir, '--target', 'ggml', '-j4'], timeout=1800)
    libs = [build_dir/'src'/n for n in ('libggml.a', 'libggml-base.a')]
    cpulibs = list(build_dir.rglob('libggml-cpu.a'))
    require(len(cpulibs) == 1, 'One CPU library required'); libs += cpulibs
    elf = out/'test'
    inc = ['-I'+str(p) for p in (g/'include', g/'src', g/'src/ggml-cpu', sdk/'software/qbs/include')]
    run_command(b, 'frontend-link', [CXX, *flags.split(), '-std=c++17', '-O3', '-UNDEBUG',
        '-DGGML_USE_RISCV_QBS', *inc, '-MD', '-MF', out/'frontend.d', inputs/'ggml_functional.cpp',
        '-static', '-pthread', '-Wl,--wrap=qbs_native_info', '-Wl,--wrap=qbs_native_execute_command',
        '-Wl,--wrap=ggml_graph_compute', '-Wl,-Map='+str(out/'link.map'),
        '-Wl,--start-group', *libs, '-Wl,--end-group', '-ldl', '-lm', '-o', elf])
    run_command(b, 'native-qbexec-disassembly', [CC.with_name('riscv64-linux-objdump'),
        '-d', '--disassemble=qbs_native_execute_command', elf])
    words = [int(v,16) for v in re.findall(r'(?m)^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s',
        (out/'native-qbexec-disassembly.log').read_text())]
    native = [word for word in words if word & 0x7f == 0x5b and (word >> 12) & 7 == 0]
    require({0x06b5045b, 0x0eb5045b} <= set(native) and
            all(not (word & (1 << 28)) for word in native), 'Ordinary QBEXEC only; no QBACC')
    oracle = out/'oracle'; oracle.mkdir()
    run_command(b, 'oracle-build', ['gcc', '-std=gnu11', '-O2', '-fno-fast-math', '-ffp-contract=off',
        '-frounding-math', '-I'+str(sdk/'verification/qbs'), '-MD', '-MF', out/'oracle.d',
        inputs/'ggml_functional_oracle.c', sdk/'verification/qbs/qbs_ref.c', '-lm', '-o', out/'oracle-host'])
    run_command(b, 'oracle-run', [out/'oracle-host', inputs/'activation_f32.bin', inputs/'weight_q4_K.bin', oracle])
    for arm in check.ARMS:
        work = out/arm; work.mkdir()
        run_command(b, arm+'-init', [CC, '-march=rv64gc', '-mabi=lp64d', '-O2', '-static',
            '-DARM_NAME="'+arm+'"', '-MD', '-MF', work/'init.d', inputs/'ggml_functional_init.c', '-o', work/'init'])
        listing = work/'initramfs.list'
        listing.write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
            f'file /init {work/"init"} 755 0 0\nfile /test {elf} 755 0 0\n'+
            f'file /input.bin {inputs/"activation_f32.bin"} 644 0 0\n'+
            f'file /weight.bin {inputs/"weight_q4_K.bin"} 644 0 0\n')
        with (work/'initramfs.cpio').open('wb') as cpio:
            subprocess.run([CPIO, listing], stdout=cpio, stderr=subprocess.PIPE, check=True, timeout=60)
    for dep in [*build_dir.rglob('*.o.d'), out/'frontend.d', out/'oracle.d',
                *[out/a/'init.d' for a in check.ARMS]]:
        # CMake .o.d paths are relative to the library build root.
        for name in shlex.split(dep.read_text().replace('\\\n', '').split(':',1)[1]):
            p = Path(name); b.pin(p if p.is_absolute() else build_dir/p)
    for directory in (build_dir, oracle, *[out/a for a in check.ARMS]):
        for p in directory.rglob('*'):
            if p.is_file() and (directory != build_dir or p.suffix in ('.a', '.o', '.cmake', '.txt', '.json')):
                b.pin(p)
    for p in (elf, out/'oracle-host', toolchain, out/'link.map',
              out/'native-qbexec-disassembly.log'): b.pin(p)
    write(out/'build-pins.json', b.pins)


def execute(out):
    require(out.parent == OUT and HERE == out/'inputs', 'Execute the frozen input runner only')
    require(not (out/'report.json').exists(), 'Never reuse or retry an attempted gate')
    b = base.Builder(out); b.pins.update(json.loads((out/'source-pins.json').read_text()))
    b.commands = json.loads((out/'commands.json').read_text())
    report = dict(state='RUNNING', scope=json.loads((out/'config.json').read_text()), arms=[],
        owner_pid=os.getpid(), owner_cgroup=Path('/proc/self/cgroup').read_text(),
        source_pins_sha256=digest(out/'source-pins.json'), retries=0, cycles_evidence=False)
    write(out/'report.json', report)
    try:
        verify_pins(b.pins)
        build(b)
        verify_pins(b.pins)
        for arm in check.ARMS:
            work = out/arm
            command = [QEMU, '-M', 'virt', '-cpu',
                'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true',
                '-smp', '1', '-m', '512M', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
                '-bios', BIOS, '-kernel', IMAGE, '-initrd', work/'initramfs.cpio',
                '-append', 'console=ttyS0 rdinit=/init']
            write(work/'command.json', list(map(str,command)))
            with (work/'qemu.log').open('wb') as log:
                with subprocess.Popen(list(map(str,command)), stdout=log, stderr=subprocess.STDOUT) as p:
                    report.update(active_arm=arm, qemu_pid=p.pid,
                        qemu_cgroup=Path(f'/proc/{p.pid}/cgroup').read_text())
                    require(report['qemu_cgroup'] == report['owner_cgroup'], 'QEMU escaped service owner')
                    write(out/'report.json', report)
                    started = time.monotonic()
                    try: rc = p.wait(timeout=600)
                    except subprocess.TimeoutExpired:
                        p.kill(); p.wait(); raise
            require(rc == 0, 'Nonzero QEMU exit: '+arm)
            item = check.check_arm(arm, (work/'qemu.log').read_text(errors='replace'), out/'oracle')
            item.update(qemu_wall_seconds=time.monotonic()-started, qemu_log_sha256=digest(work/'qemu.log'))
            write(work/'check.json', item); report['arms'].append(item)
            print('ARM_PASS '+arm, flush=True); write(out/'report.json', report)
        verify_pins(b.pins)
        report.update(state='PASS', source_and_image_postpins=True, numerical_checked=True,
                      selection_checked=True, complete_quantization_checked=True)
    except Exception as error:
        report.update(state='FAIL', error=repr(error), automatic_retry=False)
        raise
    finally:
        report['evidence_sha256'] = {str(p):digest(p) for p in out.rglob('*') if p.is_file() and
            p.name in ('qemu.log', 'check.json', 'abi-compatibility.json', 'build-pins.json')}
        write(out/'report.json', report)
        print(report['state']+' '+str(out/'report.json'), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    (execute if a.execute else prepare)(a.output.resolve())
