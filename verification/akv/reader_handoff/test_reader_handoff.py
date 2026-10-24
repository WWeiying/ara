"""Source/ABI contracts and GNU object compilation only; no simulator."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
FLAGS = ['-march=rv64gcv', '-mabi=lp64d', '-mcmodel=medany', '-mno-relax',
         '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffreestanding',
         '-fno-builtin', '-fno-common', '-fno-tree-vectorize',
         '-ffunction-sections', '-fdata-sections', '-DNR_LANES=4', '-DVLEN=1024',
         '-I'+str(ROOT/'apps/common')]


class ReaderHandoffTest(unittest.TestCase):
    def test_trap_preserves_every_scratch_register(self):
        text = (HERE/'probe.S').read_text()
        handler = text.split('rh_trap_handler:\n', 1)[1].split('.size rh_trap_handler', 1)[0]
        instructions = [x.strip() for x in handler.splitlines()
                        if x.strip() and not x.strip().startswith('/*')]
        self.assertEqual(instructions[:3], ['addi sp, sp, -16', 'sd t0, 0(sp)', 'sd t1, 8(sp)'])
        self.assertEqual(instructions[-4:], ['ld t1, 8(sp)', 'ld t0, 0(sp)', 'addi sp, sp, 16', 'mret'])
        for line in instructions:
            self.assertRegex(line, r'^(?:addi|sd|ld|csrr|csrw|la|mret)\b')
            self.assertNotRegex(line, r'\b(?:ra|a[0-7]|s[0-9]+|t[2-6]|gp|tp|v[0-9]+)\b')
        for csr in ('mcause', 'mtval', 'mepc'):
            self.assertIn('csrr t0, '+csr, handler)
        self.assertIn('addi t0, t0, 4\n    csrw mepc, t0', handler)

    def test_isa_and_no_normal_vlsu_between_owners(self):
        text = (HERE/'probe.S').read_text()
        region = text.split('rh_qbs_site:\n', 1)[1].split('vse16.v v16', 1)[0]
        words = [int(x, 16) for x in re.findall(r'\.word (0x[0-9a-f]+)', region)]
        self.assertEqual(words, [0x00b5045b, 0x0005385b])
        for word, rd, funct3 in ((words[0], 8, 0), (words[1], 16, 3)):
            self.assertEqual(word & 127, 0x5b)
            self.assertEqual((word >> 7) & 31, rd)
            self.assertEqual((word >> 12) & 7, funct3)
        self.assertNotRegex(region, r'\b(?:vle|vse|vlse|vsse)[0-9]+\.v\b')
        self.assertIn('li a0, 4', region)
        self.assertEqual(text.count('vmv.x.s'), 3)

    def test_source_scope_and_exact_accounting(self):
        text = (HERE/'main.c').read_text()
        calls = re.findall(r'pair\((\d),QBS_ACTIVATION_ACCESS_(\w+),(\d),(\d)\)', text)
        self.assertEqual(calls, [('0','DIRECT','0','0'), ('1','DIRECT','1','0'),
            ('2','DIRECT','0','0'), ('3','FILL','0','0'),
            ('4','REUSE','0','1'), ('5','RELEASE','0','1')])
        self.assertEqual(re.findall(r'resident\((\d),(\d)\)', text),
                         [('0','0'),('1','0'),('2','0'),('3','0'),('4','1'),('5','1'),('6','1')])
        self.assertNotIn('SKIP', text)
        for required in ('rh_trap_cause!=5', 'rh_trap_tval!=0',
                         'rh_trap_epc!=(uintptr_t)rh_qbs_site', 'fault ? seed[i]',
                         'qbs_commands!=6', 'akv_commands!=65', 'rows_checked!=62',
                         'words_checked!=192', 'activation.d=2.0f',
                         'access>=QBS_ACTIVATION_ACCESS_REUSE ? NULL', 'poison_akv();'):
            self.assertIn(required, text)
        self.assertLess(text.index('pair(1,'), text.index('pair(3,'))
        self.assertLess(text.index('pair(3,'), text.index('if (full(1)'))
        self.assertLess(text.index('if (full(1)'), text.index('pair(4,'))

    def test_gnu_objects_and_relocatable_link(self):
        self.assertTrue(CC.is_file(), 'GNU RISC-V compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='reader-handoff-') as temp:
            out = Path(temp)
            def run(argv):
                result = subprocess.run(list(map(str, argv)), capture_output=True,
                                        text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                return result.stdout
            for source in ('main.c', 'probe.S'):
                run([CC, *FLAGS, '-c', HERE/source, '-o', out/(source+'.o')])
            run([CC, '-march=rv64gcv', '-mabi=lp64d', '-nostdlib', '-r',
                 out/'main.c.o', out/'probe.S.o', '-o', out/'fixture.o'])
            disassembly = run([CC.with_name('riscv64-unknown-elf-objdump'), '-dr', out/'fixture.o'])
            self.assertRegex(disassembly, r'<rh_qbs_site>:\n\s*[0-9a-f]+:\s+00b5045b\s')
            for opcode in ('0005385b','00b5605b','0005345b','0000505b'):
                self.assertIn(opcode, disassembly)
            self.assertIn('mret', disassembly)
            symbols = run([CC.with_name('riscv64-unknown-elf-nm'), '-u', out/'fixture.o'])
            self.assertEqual(symbols.split(), ['U', 'printf_'])


if __name__ == '__main__':
    unittest.main()
