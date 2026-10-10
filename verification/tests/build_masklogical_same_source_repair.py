"""Build the focused native test only; no EDA launch or coverage admission."""
import argparse
from pathlib import Path

from build_gap38_i8_f16_lane3 import Build, ROOT, pins, require, save, verify

SOURCE = Path(__file__).with_name('masklogical_same_source_repair.c')


def build(out):
    out = Path(out).resolve()
    require(not out.exists(), 'Use a fresh output directory')
    out.mkdir(parents=True)
    b = Build(out)
    b.sources = pins([Path(__file__), SOURCE,
                     Path(__file__).with_name('build_gap38_i8_f16_lane3.py')])
    objects = [b.compile(b.common / name, name) for name in
               ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    objects.insert(0, b.compile(SOURCE, 'masklogical-test', ['-Wall', '-Wextra', '-Werror']))
    elf = out / 'input.elf'
    b.bind_sources([b.common / 'link.ld'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostartfiles',
            '-Wl,--gc-sections', f'-Wl,-Map={out / "input.map"}',
            f'-T{b.common / "link.ld"}', *objects, '-lm',
            f'-L{b.llvm / "lib/generic"}', '-lclang_rt.builtins-riscv64', '-o', elf], 'native-link')
    result = b.run([b.llvm / 'bin/llvm-objdump', '-d', '--no-show-raw-insn', elf], 'disassembly')
    dis = result.stdout.decode()
    # Objdump may use vmset/vmclr pseudos for same-source encodings. Retain
    # the complete disassembly for exact register and startup inspection.
    require('<main>:' in dis and '<_eoc>:' in dis, 'Missing native program or MMIO exit')
    fit = ROOT / 'verification/coverage/check_elf_fit.py'
    b.bind_sources([fit])
    b.run([ROOT / 'verification/tools/soc-venv/bin/python', fit,
           '--elf', elf, '--ram-bytes', '0x200000', '--output', out / 'elf-fit.json'], 'elf-fit')
    verify(b.sources)
    save(out / 'manifest.json', dict(status='BUILT_NOT_SIMULATED',
        case='masklogical_same_source_repair', cases=68, expected_checks=65860,
        expected_line='PASSED: masklogical_same_source cases=68 checks=65860 errors=0',
        native_elf=str(elf), binary_pins=pins([elf]), source_pins=b.sources,
        tool_pins=b.tools, link_inputs=b.link_inputs,
        geometry=dict(nr_lanes=4, vlen=1024),
        terminal='Native CRT MMIO at 0xd0000000; no COMMIT_TOHOST override',
        cold_source_contract='Fresh simulation; v24-v27 unwritten before their first use; '
                             'X source observation requires a four-state probe, not Spike',
        coverage_admitted=False, rtl_simulated=False,
        replaces_original_FOF=False))
    print(elf)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
