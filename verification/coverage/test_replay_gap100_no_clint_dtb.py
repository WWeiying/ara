import unittest

import replay_gap100_no_clint_dtb as m


class DtbTests(unittest.TestCase):
    def test_exact_removal(self):
        before = {'/': {}, '/cpus': {'a': '00'}, '/soc/clint@2000000':
                  {'compatible': b'riscv,clint0\0'.hex()}}
        path = m.clint_path(before)
        self.assertEqual(path, '/soc/clint@2000000')
        m.validate_change(before, {k: v for k, v in before.items() if k != path}, path)
        for after in ({'/': {}, '/cpus': {'a': '01'}}, {'/': {}}):
            with self.assertRaises(ValueError):
                m.validate_change(before, after, path)

    def test_ambiguous_clint_rejected(self):
        compatible = {'compatible': b'riscv,clint0\0'.hex()}
        with self.assertRaises(ValueError):
            m.clint_path({'/a': compatible, '/b': compatible})

    def test_malformed_binary_rejected(self):
        for blob in (b'', b'\0' * 40, b'\xff' * 100):
            with self.assertRaises(ValueError):
                m.fdt_nodes(blob)

    def test_boot_rom_not_disabled(self):
        cmd = m.command(m.OUT / 'fresh')
        self.assertNotIn('--disable-dtb', cmd)
        self.assertIn('--dtb=' + str(m.OUT / 'fresh/no-clint.dtb'), cmd)
        self.assertEqual(cmd[-1], str(m.runner.PRE / 'input.elf'))


if __name__ == '__main__':
    unittest.main()
