#!/usr/bin/env python3
"""Frozen setup-only mocks and real GNU RV64 object audit; no device access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
SIGNOFF = ROOT.parent/'ara_dsa_signoff_integration'
OUT = SIGNOFF/'verification/out'
HERE = Path(__file__).resolve().parent
DIRECT = Path('software/llama/platform/linux/direct')
TESTS = Path('verification/performance/resident_deployment/direct_cost')
GNU = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')
RVCC = GNU/'riscv64-linux-gcc'
SUMMARY = re.compile(r'^DIRECT_CLIENT_PASS cases=(\d+) checks=(\d+) mock_calls=(\d+) '
                     r'info=(\d+) acquire=(\d+) release=(\d+)$', re.M)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')


def output(path):
    path = Path(path).absolute()
    require(path == path.resolve() and path.parent == OUT and
            re.fullmatch(r'resident_direct_client_[A-Za-z0-9_-]+', path.name),
            'Use a fresh direct signoff verification/out/resident_direct_client_* output')
    return path


def audit_instructions(code):
    require(bool(code), 'Empty executable section')
    offset = compressed = scalar = ecalls = 0
    allowed = {0x03, 0x0f, 0x13, 0x17, 0x1b, 0x23, 0x2f, 0x33, 0x37, 0x3b, 0x63, 0x67, 0x6f}
    while offset < len(code):
        require(offset+2 <= len(code), 'Truncated instruction halfword')
        half = int.from_bytes(code[offset:offset+2], 'little')
        if half & 3 != 3:
            quadrant, function = half & 3, half >> 13
            require(half != 0 and not (quadrant in (0, 2) and function in (1, 5)),
                    f'Floating/reserved compressed instruction at {offset:#x}: {half:04x}')
            compressed += 1; offset += 2
            continue
        require(half & 0x1f != 0x1f and offset+4 <= len(code), 'Long/truncated instruction')
        word = int.from_bytes(code[offset:offset+4], 'little')
        opcode = word & 0x7f
        if opcode == 0x73:
            require(word == 0x00000073, f'Non-ecall SYSTEM/CSR instruction: {word:08x}')
            ecalls += 1
        else:
            require(opcode in allowed, f'Non-scalar/custom/vector/FP opcode at {offset:#x}: {word:08x}')
        scalar += 1; offset += 4
    return dict(bytes=len(code), compressed=compressed, scalar=scalar, ecalls=ecalls)


def executable_sections(data):
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01', 'Not ELF64 little-endian')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    require(header[1] == 1 and header[2] == 243, 'Not a relocatable RISC-V object')
    start, entry_size, count, names_index = header[6], header[11], header[12], header[13]
    require(entry_size == 64 and count > 0 and names_index < count and
            start+count*64 <= len(data), 'Invalid section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, start+i*64) for i in range(count)]
    names = sections[names_index]
    require(names[4]+names[5] <= len(data), 'Invalid section names')
    names = data[names[4]:names[4]+names[5]]
    result = {}
    for section in sections:
        if not section[2] & 4 or not section[5]:
            continue
        require(section[1] == 1 and section[4]+section[5] <= len(data) and section[0] < len(names),
                'Invalid executable section')
        name = names[section[0]:].split(b'\0', 1)[0].decode('ascii')
        require(name not in result, 'Duplicate executable section')
        result[name] = data[section[4]:section[4]+section[5]]
    require(bool(result), 'No machine code audited')
    return result


class AuditTests(unittest.TestCase):
    def test_scalar_and_ecall(self):
        result = audit_instructions(bytes.fromhex('01001305050073000000'))
        self.assertEqual(result, dict(bytes=10, compressed=1, scalar=2, ecalls=1))

    def test_forbidden_opcodes(self):
        # Vector ALU/load/store, FP/load/store/FMA, all custom slots, and CSRs.
        for word in (0x00007057, 0x02050007, 0x02050027, 0x00000053, 0x00003007,
                     0x00003027, 0x00000043, 0x00000047, 0x0000004b, 0x0000004f,
                     0x0000000b, 0x0000002b, 0x0000405b, 0x0000007b,
                     0x00302573, 0x00802573, 0x5c002573, 0x00100073):
            with self.subTest(word=hex(word)), self.assertRaises(ValueError):
                audit_instructions(word.to_bytes(4, 'little'))
        for half in (0, 0x2000, 0xa000, 0x2002, 0xa002, 0x001f):
            with self.subTest(half=hex(half)), self.assertRaises(ValueError):
                audit_instructions(half.to_bytes(2, 'little'))

    def test_empty_truncated_or_non_object(self):
        for blob in (b'', b'\x01', b'\x13\0', b'\x01\0\x13'):
            with self.assertRaises(ValueError): audit_instructions(blob)
        for blob in (b'', b'not an ELF', bytes(64)):
            with self.assertRaises(ValueError): executable_sections(blob)

    def test_output_boundary(self):
        self.assertEqual(output(OUT/'resident_direct_client_unit').parent, OUT)
        for path in (Path('/tmp/resident_direct_client_x'), OUT/'nested/resident_direct_client_x', OUT/'old'):
            with self.assertRaises(ValueError): output(path)


def prepare(out, gcc_runtime_dir=None):
    require(not out.exists(), 'Preserve every previous attempt')
    require(subprocess.check_output(['git', '-C', str(SIGNOFF), 'branch', '--show-current'],
                                    text=True).strip() == 'ara_dsa_signoff_integration', 'Wrong signoff branch')
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()
    pins = {}
    sources = [ROOT/'AGENTS.md', *(ROOT/DIRECT/name for name in
                ('direct_client.c', 'direct_client.h', 'direct_uapi.h')),
               ROOT/TESTS/'test_client.c', ROOT/TESTS/'test_client.py']
    for source in sources:
        destination = inputs/source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pins[str(source)] = sha(source)
        shutil.copyfile(source, destination)
        require(sha(destination) == pins[str(source)], 'Source snapshot race')
        pins[str(destination)] = sha(destination)
        destination.chmod(0o444)
    pins[str(SIGNOFF/'AGENTS.md')] = sha(SIGNOFF/'AGENTS.md')
    tools = {name: shutil.which(name, path='/usr/bin:/bin') for name in ('gcc', 'clang')}
    require(all(tools.values()), 'GCC and Clang are both required')
    tools.update(rvcc=str(RVCC), objdump=str(GNU/'riscv64-linux-objdump'),
                 readelf=str(GNU/'riscv64-linux-readelf'), nm=str(GNU/'riscv64-linux-nm'),
                 python=str(Path(sys.executable).resolve()))
    for tool in tools.values():
        path = Path(tool).resolve(strict=True); pins[str(path)] = sha(path)
    runtime = None
    if gcc_runtime_dir is not None:
        runtime = str(inputs/'gcc-runtime')
        Path(runtime).mkdir()
        # Narrow the runtime search path: do not import an entire environment.
        for base, soname in (('libasan.so', 'libasan.so.6'), ('libubsan.so', 'libubsan.so.1')):
            source = (gcc_runtime_dir/soname).resolve(strict=True)
            require(source.read_bytes()[:4] == b'\x7fELF', 'Not a real sanitizer runtime')
            pins[str(source)] = sha(source)
            for name in (base, soname):
                destination = Path(runtime)/name
                shutil.copyfile(source, destination)
                require(sha(destination) == pins[str(source)], 'Sanitizer runtime snapshot race')
                pins[str(destination)] = sha(destination)
                destination.chmod(0o444)
    plan = dict(tools=tools, scope='Mocked direct setup/teardown only; no kernel/device/compute execution',
                scalar_arch='rv64gc', scalar_abi='lp64d', compiler_optimizations=['O0', 'O2', 'O3'],
                abi_float_note='Toolchain hard-float ABI; emitted executable bytes must contain no FP instructions',
                required_scalar_cflags=['-fno-tree-vectorize', '-fno-tree-slp-vectorize',
                                       '-fno-builtin', '-fno-stack-protector'],
                scalar_constraint='Default GNU wrapper adds unaudited stack-check libc helpers; '
                                  'the self-contained proof requires explicit -fno-stack-protector',
                automatic_retry=False, production_changed=False, gcc_sanitizer_runtime=runtime)
    save(out/'plan.json', plan); pins[str(out/'plan.json')] = sha(out/'plan.json')
    save(out/'source-pins.json', pins)
    review = sha(out/'source-pins.json')
    print('FROZEN '+str(out)+' source-pins-sha256='+review, flush=True)
    env = os.environ.copy(); env['PYTHONDONTWRITEBYTECODE'] = '1'; env['CCACHE_DISABLE'] = '1'
    return subprocess.run([tools['python'], '-B', str(inputs/TESTS/'test_client.py'), '--run',
                           '--output', str(out), '--review-sha256', review], env=env).returncode


def run_frozen(out, review):
    require(Path(__file__).resolve() == out/'inputs'/TESTS/'test_client.py' and
            sha(out/'source-pins.json') == review, 'Frozen reviewed test driver required')
    pins = json.loads((out/'source-pins.json').read_text())
    plan = json.loads((out/'plan.json').read_text()); tools = plan['tools']
    require(not (out/'attempt.json').exists(), 'One attempt per frozen output')
    save(out/'attempt.json', dict(source_pins_sha256=review, pid=os.getpid()))
    work = out/'work'; work.mkdir()
    commands, host_results, object_results = [], [], []
    report = dict(state='FAIL', scope=plan['scope'], source_pins_sha256=review,
                  production_changed=False, device_opened=False, target_executed=False,
                  host=host_results, rv64=object_results)
    env = os.environ.copy(); env.update(PYTHONDONTWRITEBYTECODE='1', CCACHE_DISABLE='1',
        ASAN_OPTIONS='detect_leaks=1:abort_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')

    def verify():
        for name, digest in pins.items():
            require(sha(name) == digest, 'Input identity drift: '+name)

    def command(label, argv):
        verify()
        commands.append(dict(label=label, argv=list(map(str, argv)), cwd=str(work)))
        save(out/'commands.json', commands)
        with (out/(label+'.log')).open('x') as stream:
            result = subprocess.run(list(map(str, argv)), cwd=work, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=120)
        verify()
        require(result.returncode == 0, f'{label}: exit {result.returncode}; see log')
        return (out/(label+'.log')).read_text()

    try:
        verify()
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(AuditTests)
        with (out/'audit-unit-tests.log').open('x') as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        require(result.wasSuccessful(), 'Machine-code auditor self-tests failed')
        for name in ('gcc', 'clang', 'rvcc', 'objdump'):
            command(name+'-version', [tools[name], '--version'])
        direct = out/'inputs'/DIRECT
        test = out/'inputs'/TESTS/'test_client.c'
        flags = ['-std=gnu11', '-g', '-Wall', '-Wextra', '-Werror', '-Wformat=2',
                 '-DARA_AKV_DIRECT_CLIENT_TEST', '-I'+str(direct)]
        summary = None
        for compiler in ('gcc', 'clang'):
            for variant in ('O0', 'O2', 'asan-ubsan'):
                name = compiler+'-'+variant; binary = work/name
                extra = ['-'+variant] if variant != 'asan-ubsan' else [
                    '-O1', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-fno-omit-frame-pointer', '-fno-pie', '-no-pie']
                if compiler == 'gcc' and variant == 'asan-ubsan' and plan['gcc_sanitizer_runtime']:
                    runtime = plan['gcc_sanitizer_runtime']
                    extra += ['-L'+runtime, '-Wl,-rpath,'+runtime]
                command(name+'-compile', [tools[compiler], *flags, *extra, test, direct/'direct_client.c', '-o', binary])
                log = command(name+'-run', [binary])
                matches = SUMMARY.findall(log)
                require(len(matches) == 1, 'Missing/duplicate host test summary')
                numbers = tuple(map(int, matches[0]))
                require(numbers[0] >= 850 and numbers[1] > 10000 and all(v > 0 for v in numbers[2:]),
                        'Incomplete setup test matrix')
                require(summary is None or numbers == summary, 'Compiler-dependent test coverage')
                summary = numbers
                host_results.append(dict(compiler=compiler, variant=variant, state='PASS',
                    cases=numbers[0], checks=numbers[1], mock_calls=numbers[2],
                    get_info=numbers[3], acquire=numbers[4], release=numbers[5]))
        for optimization in ('O0', 'O2', 'O3'):
            obj = work/('direct-'+optimization+'.o')
            command('rv64-'+optimization+'-compile', [tools['rvcc'], '-std=gnu11', '-'+optimization,
                '-march=rv64gc', '-mabi=lp64d', *plan['required_scalar_cflags'],
                '-Wall', '-Wextra', '-Werror', '-I'+str(direct),
                '-c', direct/'direct_client.c', '-o', obj])
            sections = executable_sections(obj.read_bytes())
            audit = {name: audit_instructions(code) for name, code in sections.items()}
            require(sum(v['ecalls'] for v in audit.values()) > 0, 'No real raw syscall instructions')
            disassembly = command('rv64-'+optimization+'-disassembly', [tools['objdump'], '-dr', '-M', 'no-aliases', obj])
            require('ecall' in disassembly and all('<ara_akv_direct_'+name+'>:' in disassembly
                    for name in ('open', 'acquire', 'release', 'close')), 'Incomplete production disassembly')
            require(not command('rv64-'+optimization+'-undefined', [tools['nm'], '-u', obj]).strip(),
                    'Unaudited external helper in scalar object')
            command('rv64-'+optimization+'-attributes', [tools['readelf'], '-hA', obj])
            object_results.append(dict(optimization=optimization, state='PASS', sha256=sha(obj),
                                      sections=audit, all_executable_bytes_audited=True))
        verify()
        report.update(state='PASS', audit_unit_tests=result.testsRun, post_pins_match=True,
                      setup_ioctl_whitelist=['GET_INFO', 'ACQUIRE', 'RELEASE'], production_issues=[],
                      scalar_build_constraint=plan['scalar_constraint'],
                      required_scalar_cflags=plan['required_scalar_cflags'])
    except Exception as error:
        report['error'] = repr(error)
    save(out/'result.json', report)
    artifacts = {str(path.relative_to(out)): sha(path) for path in out.rglob('*') if path.is_file()}
    save(out/'artifact-pins.json', artifacts)
    with (out/'SHA256SUMS').open('x') as checksums:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.name != 'SHA256SUMS':
                checksums.write(sha(path)+'  '+str(path.relative_to(out))+'\n')
    print(json.dumps(report, sort_keys=True), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--run', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--review-sha256', help=argparse.SUPPRESS)
    parser.add_argument('--gcc-runtime-dir', type=Path,
                        help='Optional libasan.so.6/libubsan.so.1 directory, snapshotted and pinned')
    args = parser.parse_args(); out = output(args.output)
    return run_frozen(out, args.review_sha256) if args.run else prepare(out, args.gcc_runtime_dir)


if __name__ == '__main__':
    raise SystemExit(main())
