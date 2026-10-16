import subprocess
import tempfile
import unittest
from pathlib import Path

from build_dual_linux import enable_ddr2, sha256_file


class DualTreeTest(unittest.TestCase):
    def test_streaming_hash(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'data'
            path.write_bytes(b'abc')
            self.assertEqual(sha256_file(path),
                             'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')

    def tree(self, root, size='0x7eff0000'):
        dts = root / 'test.dts'
        dtb = root / 'test.dtb'
        dts.write_text('/dts-v1/; / { #address-cells=<2>; #size-cells=<2>; '
                       'chosen { bootargs="unchanged"; }; memory@80000000 { '
                       'device_type="memory"; reg=<0 0x80000000 0 ' + size + '>; }; };')
        subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(dtb), str(dts)], check=True)
        return dtb

    def test_preserves_hole_and_bootargs(self):
        with tempfile.TemporaryDirectory() as d:
            dtb = self.tree(Path(d))
            enable_ddr2(dtb)
            value = subprocess.check_output(['fdtget', '-t', 'x', str(dtb),
                                              '/memory@80000000', 'reg'], text=True)
            self.assertEqual(value.strip(), '0 80000000 0 7eff0000 1 0 0 80000000')
            self.assertEqual(subprocess.check_output(['fdtget', str(dtb), '/chosen',
                                                      'bootargs'], text=True).strip(), 'unchanged')
            with self.assertRaises(ValueError):
                enable_ddr2(dtb)

    def test_rejects_unreviewed_layout(self):
        with tempfile.TemporaryDirectory() as d:
            dtb = self.tree(Path(d), '0x80000000')
            before = dtb.read_bytes()
            with self.assertRaises(ValueError):
                enable_ddr2(dtb)
            self.assertEqual(before, dtb.read_bytes())


if __name__ == '__main__':
    unittest.main()
