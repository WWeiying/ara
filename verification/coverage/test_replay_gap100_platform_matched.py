import unittest
from types import SimpleNamespace

import replay_gap100_platform_matched as m


class PlatformTests(unittest.TestCase):
    def test_exact_command_same_elf(self):
        cmd = m.command(None)
        self.assertEqual(cmd[-1], str(m.runner.PRE / 'input.elf'))
        self.assertEqual(cmd.count('--disable-dtb'), 1)
        self.assertIn('--pmpregions=0', cmd)
        self.assertIn('--priv=msu', cmd)
        self.assertIn('--isa=' + m.software.SPIKE_ISA, cmd)

    def commit(self, csr=0x344, value=0, memories=()):
        return SimpleNamespace(instruction=(csr << 20) | 0x25f3,
                               pc=0x80002000, gpr_writes={11: value}, memory_accesses=memories)

    def test_mtip_not_masked(self):
        with self.assertRaisesRegex(ValueError, 'MTIP'):
            m.state_scope([self.commit(value=128)])

    def test_non_bare_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SATP'):
            m.state_scope([self.commit(csr=0x180, value=8 << 60)])

    def test_mmio_rejected(self):
        with self.assertRaisesRegex(ValueError, 'MMIO'):
            m.state_scope([self.commit(memories=((0x02004000, (1 << 64) - 1),))])

    def test_actual_dut_case_scope(self):
        rows = m.runtime.commit_rows(m.runtime.RUN / 'commit_trace.csv')
        result = m.state_scope(m.runtime.retired_commits(rows))
        self.assertTrue(result['satp_always_bare'])
        self.assertTrue(result['mie_mtie_always_zero'])
        self.assertFalse(result['generic_mmu_equivalence_claimed'])


if __name__ == '__main__':
    unittest.main()
