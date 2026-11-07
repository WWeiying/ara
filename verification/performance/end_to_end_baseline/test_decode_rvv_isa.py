from pathlib import Path
import unittest

from run_decode_rvv_isa import libraries, spike_command, SPIKE


class DecodeRVVISATests(unittest.TestCase):
    def test_exact_elf_and_io_only_extlib_configuration(self):
        elf = Path('/immutable/input.elf'); plugin = Path('/isolated/ports.so')
        argv = spike_command(plugin, elf)
        self.assertEqual(argv[0], str(SPIKE)); self.assertEqual(argv[-1], str(elf))
        self.assertIn('--pmpregions=1', argv)
        self.assertIn('--isa=rv64gcv_zfh_zvfh_zvl1024b', argv)
        self.assertIn('--instructions=20000000', argv)
        self.assertNotIn('--disable-dtb', argv)
        self.assertNotIn('--pmpregions=0', argv)
        self.assertLess(argv.index('--extlib='+str(plugin)), argv.index('--device=spike_soc_ports'))
        self.assertIn('-m0x80000000:0x1000000,0xbf000000:0x1000000', argv)

    def test_dynamic_libraries_resolved_and_inventoried(self):
        a, b = Path('/usr/bin/python3').resolve(), Path('/usr/bin/dtc').resolve()
        text = f'liba.so => {a} (0x123)\n\t{b} (0x234)\nlinux-vdso.so.1 (0x0)\n'
        self.assertEqual(libraries(text), sorted([str(a), str(b)]))
        with self.assertRaises(ValueError): libraries('libmissing.so => not found\n')
        with self.assertRaises(ValueError): libraries('linux-vdso.so.1 (0x0)\n')


if __name__ == '__main__': unittest.main()
