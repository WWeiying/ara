"""VCS boot SP is architectural DRAM end; relocation remains SRAM-local."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BootContractTests(unittest.TestCase):
    def test_fixture_matches_architectural_control_register(self):
        soc = (ROOT / 'hardware/src/ara_soc.sv').read_text()
        base = re.search(r"DRAMBase\s*=\s*64'h([0-9a-fA-F_]+)", soc)
        length = re.search(r"DRAMLength\s*=\s*64'h([0-9a-fA-F_]+)", soc)
        self.assertIsNotNone(base)
        self.assertIsNotNone(length)
        expected = sum(int(m[1].replace('_', ''), 16) for m in (base, length))
        header = (ROOT / 'apps/qbs_gap65_late_fault/contract.h').read_text()
        value = re.search(r'#define GAP65_BOOT_SP UINT64_C\((0x[0-9a-f]+)\)', header)
        self.assertEqual(int(value[1], 16), expected)
        self.assertNotEqual(expected, 0x80200000)
        crt = (ROOT / 'apps/common/crt0.S').read_text()
        self.assertIn('la      t0, dram_end_address_reg\n    ld      sp, 0(t0)', crt)
        app = ROOT / 'apps/qbs_gap65_late_fault'
        self.assertIn('{GAP65_BOOT_SP, GAP65_STACK_TOP, 1, 0, 128}', (app / 'main.c').read_text())
        self.assertIn('gap65_boot[0] = GAP65_BOOT_SP;', (app / 'host_model.c').read_text())
        self.assertIn('la sp, __gap65_stack_top', (app / 'entry.S').read_text())


if __name__ == '__main__':
    unittest.main()
