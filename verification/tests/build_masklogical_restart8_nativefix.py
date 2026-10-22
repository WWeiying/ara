"""Native-only harness successor. No RTL build or EDA execution."""
import argparse
from pathlib import Path
import re

import build_masklogical_restart8 as original

HERE = Path(__file__).resolve()
SOURCE = HERE.with_name('masklogical_restart8_nativefix.c')


def check_native(disassembly, link_log):
    original.require(not re.search(r'\becall\b', disassembly), 'Native ECALL forbidden')
    names = set(re.findall(r'^[0-9a-f]+ <([^>]+)>:', disassembly, re.M))
    original.require('printf_' in names and 'printf' not in names,
                     'Native must use apps/common printf_')
    forbidden = {'iprintf', 'puts', '_fstat', '_fstat_r', '_write', '_write_r',
                 '_exit', '_sbrk', '_sbrk_r', '_vfprintf_r', 'vfprintf'}
    original.require(not names.intersection(forbidden), 'Unexpected native libc runtime')
    original.require(not re.search(r'/(?:libc|libgloss)\.a(?:\(|\s|$)', link_log),
                     'Native libc/libgloss archive forbidden')
    return dict(status='PASS', printf_symbol='printf_', ecall_count=0,
                libc_linked=False, libgloss_linked=False)


class NativeBuild(original.Build):
    def compile(self, *args, **kwargs):
        self.bind_sources([HERE, SOURCE])
        return super().compile(*args, **kwargs)

    def link(self, argv, label):
        if label == 'native-link':
            argv = ['-nostdlib' if str(a) == '-nostartfiles' else a
                    for a in argv if str(a) != '-lm']
        result = super().link(argv, label)
        if label == 'native-link':
            elf = self.out / 'input.elf'
            dis = self.run([self.llvm / 'bin/llvm-objdump', '-d', elf],
                           'native-no-syscalls-disassembly').stdout.decode()
            proof = check_native(dis, (self.out / 'native-link.log').read_text())
            original.save(self.out / 'native-runtime-proof.json', proof)
        return result


def build(out):
    # Only this process changes the imported builder's source selection.
    # Frozen helper files and the old ELF are never edited.
    original.SOURCE = SOURCE
    original.Build = NativeBuild
    original.build(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
