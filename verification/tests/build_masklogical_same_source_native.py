"""Native-only printing successor; original computation and CRT are unchanged."""
import argparse
from pathlib import Path
import re

from build_gap38_i8_f16_lane3 import Build, ROOT, pins, require, save, sha, verify

SOURCE = Path(__file__).with_name('masklogical_same_source_native.c')
ORIGINAL = Path(__file__).with_name('masklogical_same_source_repair.c')
ORIGINAL_SHA = '858b384be8b936ad8c8acd30d22775235cb0bffbf3e8e475ef600eac50099931'
OLD_ELF_SHA = 'b303202028b57c63ad29a9e3268fdbbd24f409cc2de4567c0757906380ac9930'


def native_gate(dis):
    names = set(re.findall(r'^[0-9a-f]+ <([^>]+)>:', dis, re.M))
    forbidden = {'printf', '_printf_r', 'vfprintf', '_vfprintf_r', '_vfiprintf_r',
                 'puts', '_puts_r', '__sfvwrite_r', '__smakebuf_r', '_fstat', '_fstat_r',
                 '_write', '_write_r', '_read', '_sbrk', '_open', '_close', '_lseek'}
    require(not names & forbidden, 'Native image contains newlib stdio/syscall path: ' + str(names & forbidden))
    require(not re.search(r'\becall\b', dis), 'Native image contains ECALL')
    require({'main', '_eoc', 'printf_', '_putchar'} <= names, 'Missing native main/MMIO/printf path')
    main = dis.split('<main>:\n', 1)[1].split('\n\n', 1)[0]
    require(re.search(r'\b(?:jalr|jal)\b[^\n]*<printf_>', main), 'Main output does not call native printf_')
    return dict(status='PASS', no_ecall=True, no_newlib_stdio=True, main_calls='printf_', terminal='_eoc MMIO')


def build(out):
    require(not out.exists(), 'Fresh build directory required')
    require(sha(ORIGINAL) == ORIGINAL_SHA, 'Original matrix computation changed')
    out.mkdir(parents=True)
    b = Build(out)
    b.sources = pins([Path(__file__), SOURCE, ORIGINAL, Path(__file__).with_name('build_gap38_i8_f16_lane3.py')])
    objects = [b.compile(b.common / n, n) for n in
               ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    objects.insert(0, b.compile(SOURCE, 'masklogical-test', ['-Wall', '-Wextra', '-Werror']))
    elf = out / 'input.elf'
    b.bind_sources([b.common / 'link.ld'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostartfiles', '-Wl,--gc-sections',
            f'-Wl,-Map={out / "input.map"}', f'-T{b.common / "link.ld"}', *objects, '-lm',
            f'-L{b.llvm / "lib/generic"}', '-lclang_rt.builtins-riscv64', '-o', elf], 'native-link')
    dis = b.run([b.llvm / 'bin/llvm-objdump', '-d', '--no-show-raw-insn', elf], 'disassembly').stdout.decode()
    gate = native_gate(dis)
    save(out / 'native-stdio-gate.json', gate)
    fit = ROOT / 'verification/coverage/check_elf_fit.py'
    b.bind_sources([fit])
    b.run([ROOT / 'verification/tools/soc-venv/bin/python', fit, '--elf', elf,
           '--ram-bytes', '0x200000', '--output', out / 'elf-fit.json'], 'elf-fit')
    verify(b.sources)
    require(sha(elf) != OLD_ELF_SHA, 'Successor must have a distinct ELF identity')
    save(out / 'manifest.json', dict(status='BUILT_NOT_SIMULATED',
         case='masklogical_same_source_native', cases=68, expected_checks=65860,
         expected_line='PASSED: masklogical_same_source cases=68 checks=65860 errors=0',
         native_elf=str(elf), binary_pins=pins([elf]), source_pins=b.sources, tool_pins=b.tools,
         link_inputs=b.link_inputs, geometry=dict(nr_lanes=4, vlen=1024),
         original_matrix_sha256=ORIGINAL_SHA, superseded_elf_sha256=OLD_ELF_SHA,
         superseded_failure_class='NATIVE_HARNESS_NEWLIB_STDIO_SYSCALL_NOT_RTL',
         change='Wrapper includes stdio.h then apps/common/printf.h before unchanged original matrix',
         startup_changed=False, native_stdio_gate=gate,
         terminal='Native CRT MMIO at 0xd0000000; no COMMIT_TOHOST override',
         coverage_admitted=False, rtl_simulated=False))
    print(elf)
    print('ELF_SHA256=' + sha(elf))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    build(p.parse_args().output.resolve())
