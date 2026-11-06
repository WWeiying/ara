#!/usr/bin/env python3
"""Isolated ordinary-RVV ELF build only; the SoC owner runs simulation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
MAIN = Path('/home/wangwy/openproject/ara_dsa')
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
OUTPUT = VERIFY/'verification/out/e2e_wide_soc_memory_smoke_build_20261106_01'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
OWNED = ('wide_soc_memory_smoke.c', 'wide_soc_memory_smoke.S',
         'wide_soc_memory_smoke_test.py', 'wide_soc_memory_smoke_build.py')
COMMON = ('crt0.S', 'encoding.h', 'printf.c', 'printf.h', 'serial.c', 'print_trap_cause.c', 'arch.link.ld')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def elf_layout(path):
    data = Path(path).read_bytes()
    require(data[:6] == b'\x7fELF\x02\x01', 'Expected little-endian ELF64')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    _, kind, machine, _, entry, phoff, shoff, _, _, phsize, phnum, shsize, shnum, _ = header
    require(kind == 2 and machine == 243 and entry == 0x80000000, 'Wrong target/entry')
    loads = []
    for i in range(phnum):
        ptype, flags, offset, va, pa, filesz, memsz, alignment = struct.unpack_from('<IIQQQQQQ', data, phoff+i*phsize)
        if ptype == 1:
            require(0x80000000 <= va <= va+memsz <= 0x80100000 and pa == va and filesz <= memsz,
                    'ELF load exceeds common 1 MiB L2 window')
            loads.append(dict(address=va, file_bytes=filesz, memory_bytes=memsz, flags=flags, alignment=alignment))
    require(bool(loads), 'No loadable memory')
    for i in range(shnum):
        _, _, flags, address, _, size, _, _, _, _ = struct.unpack_from('<IIQQQQIIQQ', data, shoff+i*shsize)
        if flags & 2 and size:
            require(address % 32 == 0, 'Allocated section not aligned for both physical widths')
    return dict(entry=entry, loads=loads, all_allocated_sections_32byte_aligned=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    require(args.build, 'Explicit isolated ELF build required')
    owned = {str(HERE/n) for n in OWNED}
    inventories = []
    for d in sorted((VERIFY/'verification/out').iterdir()):
        p = d/'source-pins.json'
        if p.is_file():
            pins = json.loads(p.read_text())
            require(not owned.intersection(pins), 'Owned input already sealed: '+str(p))
            inventories.append(dict(path=str(p), sha256=digest(p),
                                    inherited_documentation=[k for k in pins if k.lower().endswith('.md')]))
    OUTPUT.mkdir(exist_ok=False)
    pins, identities, commands = {}, {}, []
    env = {k:v for k,v in os.environ.items() if k not in
           ('LD_PRELOAD', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C')
    result = dict(state='WIDE_SOC_MEMORY_SMOKE_BUILD_FAIL', target_executed=False, simulation_executed=False,
                  rtl_changed=False, production_path_changed=False, performance_measured=False,
                  physical_bus_width_assumed=False, same_elf_for_128_and_256=True)

    def pin(path, expected=None):
        lexical = Path(path).absolute(); actual = lexical.resolve(strict=True); value = digest(actual)
        require(expected is None or expected == value, 'Input mismatch: '+str(path))
        require(str(actual) not in pins or pins[str(actual)] == value, 'Input drift: '+str(path))
        pins[str(actual)] = value; identities[str(lexical)] = str(actual)
        return value

    def verify():
        require(all(str(Path(p).resolve(strict=True)) == q for p,q in identities.items()), 'Path drift')
        require(all(digest(p) == h for p,h in pins.items()), 'Input/tool/image drift')

    def run(argv, label):
        argv = list(map(str, argv)); pin(argv[0]); verify()
        row = dict(label=label, argv=argv, cwd=str(OUTPUT), timeout_seconds=120); commands.append(row)
        write(OUTPUT/'commands.json', commands)
        child = subprocess.run(argv, cwd=OUTPUT, env=env, capture_output=True, timeout=120)
        (OUTPUT/(label+'.log')).write_bytes(child.stdout+child.stderr)
        row['returncode'] = child.returncode; write(OUTPUT/'commands.json', commands)
        require(child.returncode == 0, label+' failed; preserve first output')
        verify()
        return child.stdout.decode()

    try:
        write(OUTPUT/'worker-pin-inventory.json', inventories)
        source = OUTPUT/'source-snapshot'; source.mkdir()
        common = source/'common'; common.mkdir()
        for src, dest in [(HERE/n, source/n) for n in OWNED]+[(MAIN/'apps/common'/n, common/n) for n in COMMON]:
            h = pin(src)
            with dest.open('xb') as stream:
                stream.write(src.read_bytes())
            pin(dest, h)
        template = (common/'arch.link.ld').read_text()
        require('ALIGN(ALIGNMENT)' in template and 'LENGTH = 0x00100000' in template, 'Unexpected common linker template')
        linker = common/'link.ld'
        linker.write_text(template.replace('ALIGNMENT', '32'))
        pin(linker)
        pin(CC)
        version = run([CC, '--version'], 'compiler-version')
        require('gcc' in version.lower() and 'zcc' not in str(CC).lower(), 'Expected non-ZCC GCC toolchain')
        tools = dict(driver=str(CC.resolve()), version=version.splitlines()[0])
        for name in ('cc1', 'as', 'collect2', 'ld'):
            path = Path(run([CC, '-print-prog-name='+name], 'tool-'+name).strip()).resolve(strict=True)
            require(path.is_file(), 'Missing compiler tool: '+name)
            pin(path); tools[name] = str(path)
        flags = ['-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax', '-O2',
                 '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-fno-tree-loop-distribute-patterns',
                 '-fno-builtin', '-ffreestanding', '-ffunction-sections', '-fdata-sections',
                 '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
                 '-fno-common', '-I'+str(common)]
        sources = ([source/'wide_soc_memory_smoke.c', source/'wide_soc_memory_smoke.S']+
                   [common/n for n in ('crt0.S', 'printf.c', 'serial.c', 'print_trap_cause.c')])
        objects = []
        for i, src in enumerate(sources):
            obj = OUTPUT/f'{i}.o'
            text = run([CC, *flags, '-M', '-MT', 'object', src], f'deps-{i}')
            for dependency in shlex.split(text.replace('\\\n', ' ').split(':', 1)[1]):
                pin(dependency)
            run([CC, *flags, '-Wall', '-Wextra', '-c', src, '-o', obj], f'compile-{i}')
            pin(obj); objects.append(obj)
        libgcc = Path(run([CC, *flags, '-print-file-name=libgcc.a'], 'runtime-libgcc').strip()).resolve(strict=True)
        pin(libgcc)
        elf = OUTPUT/'wide_soc_memory_smoke.elf'
        run([CC, *flags, '-static', '-nostdlib', '-nostartfiles', *objects, libgcc,
             '-Wl,--gc-sections,--no-relax,-Map='+str(OUTPUT/'link.map'), '-T', linker, '-o', elf], 'link')
        pin(elf)
        objdump = CC.with_name('riscv64-unknown-elf-objdump'); pin(objdump)
        dis = run([objdump, '-d', '-M', 'no-aliases', elf], 'disassembly')
        scalar_dis = run([objdump, '-d', '-M', 'no-aliases', objects[0]], 'scalar-oracle-disassembly')
        require(not re.search(r'\t(?:vset\w*|vl\w*\.[vms]|vs\w*\.[vms])\s', scalar_dis),
                'Compiler vectorized the scalar oracle')
        for width in (8, 16, 32, 64):
            require(f'vle{width}.v' in dis and f'vse{width}.v' in dis, 'Missing ordinary vector width')
        require('v0.t' in dis and 'ta,ma' in dis and 'tu,mu' in dis and 'vlm.v' in dis, 'Missing vector policy/mask')
        layout = elf_layout(elf)
        run([sys.executable, '-B', source/'wide_soc_memory_smoke_test.py'], 'host-tests')
        verify()
        result.update(state='WIDE_SOC_MEMORY_SMOKE_ELF_BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=digest(elf),
                      toolchain=tools, compile_flags=flags, runtime_archive=str(libgcc), runtime_archive_sha256=digest(libgcc),
                      common_startup=str(MAIN/'apps/common/crt0.S'),
                      linker_recipe='apps/common/arch.link.ld template: ALIGNMENT -> 32, fixed for both bus widths',
                      layout=layout, scalar_cases=180, vector_cases=240, vector_instructions=1924,
                      natural_alignment_only=True, agnostic_register_bytes_compared=False, post_pins_match=True,
                      run_log_checker=str(HERE/'wide_soc_memory_smoke_test.py')+' --log <main-owned-SoC-log>',
                      limitations=['ELF and host oracle/static tests only; main owns all SoC execution',
                                   '4 KiB physical-address boundaries in mapped flat memory, not MMU/PMP testing',
                                   'Actual 256-bit full-beat traffic requires main AXI trace evidence; not inferred from this ELF'])
    except Exception as exc:
        result.update(error=repr(exc), post_pins_match=False)
    finally:
        write(OUTPUT/'source-pins.json', pins); write(OUTPUT/'path-identities.json', identities)
        write(OUTPUT/'commands.json', commands)
        result['source_pins_sha256'] = digest(OUTPUT/'source-pins.json')
        result['artifacts'] = {str(p):digest(p) for p in sorted(OUTPUT.rglob('*')) if p.is_file() and p.name != 'result.json'}
        write(OUTPUT/'result.json', result)
    print(json.dumps(result, indent=2))
    return int(result['state'] != 'WIDE_SOC_MEMORY_SMOKE_ELF_BUILT_NOT_EXECUTED')


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.exit(main())
