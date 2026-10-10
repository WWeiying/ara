import unittest
from types import SimpleNamespace

import check_gap100_runtime as m


class RuntimeTests(unittest.TestCase):
    def test_exact_trap_sequence(self):
        expected = m.expected_handler_causes()
        self.assertEqual(len(expected), 23)
        self.assertEqual(sum(csr == 0x142 for csr, _ in expected), 2)
        commits = [SimpleNamespace(instruction=(csr << 20) | 0x2373, gpr_writes={6: value})
                   for csr, value in expected]
        self.assertEqual(m.handler_causes(commits), expected)
        for changed in (commits[:-1], commits + [commits[-1]], list(reversed(commits))):
            with self.assertRaises(ValueError):
                m.handler_causes(changed)

    def test_unknown_handler_cause(self):
        commits = [SimpleNamespace(instruction=(csr << 20) | 0x2373, gpr_writes={6: value})
                   for csr, value in m.expected_handler_causes()]
        commits[0].gpr_writes = {6: 5}
        with self.assertRaises(ValueError):
            m.handler_causes(commits)

    def test_no_prefix_or_unknown_scalar_acceptance(self):
        rows = [dict(trap=0), dict(trap=1)]
        result = dict(status='TERMINAL_TOHOST_MATCH', mismatch=None, stopped_at_unobservable=None,
                      skipped_unobservable_register_values=0, ara_retired_instructions=2,
                      ara_committed_instructions=1, matched_instructions=1)
        self.assertTrue(m.scalar_qualified(result, rows))
        for key, value in [('status', 'PREFIX'), ('skipped_unobservable_register_values', 1),
                           ('ara_retired_instructions', 1), ('matched_instructions', 0),
                           ('stopped_at_unobservable', {})]:
            changed = dict(result, **{key: value})
            self.assertFalse(m.scalar_qualified(changed, rows))

    def row(self, **change):
        result = dict(pc=0x80002000, insn=0x13, rd=0, rd_wdata=0, trap=0,
                      mem_addr=0, mem_rmask=0, mem_wmask=0, mem_wdata=0)
        result.update(change)
        return result

    def test_no_fake_nop_memory(self):
        with self.assertRaises(ValueError):
            m.retired_commits([self.row(mem_wmask=255)])

    def test_rv64_compressed_integer_memory(self):
        self.assertEqual(m.scalar_memory(0xfe06), ('write', 8))
        for quadrant in (0, 2):
            for funct, expected in [(2, ('read', 4)), (3, ('read', 8)),
                                    (6, ('write', 4)), (7, ('write', 8))]:
                self.assertEqual(m.scalar_memory((funct << 13) | quadrant), expected)
        self.assertIsNone(m.scalar_memory(0x13))
        self.assertIsNone(m.scalar_memory(0xa001))

    def test_trap_effect_rejected(self):
        with self.assertRaises(ValueError):
            m.retired_commits([self.row(trap=1, mem_rmask=255)])

    def test_actual_spike_handler_pcs(self):
        pre = m.runner.life.read_bound(m.runner.PRE / 'preflight-manifest.json', m.runner.PRE_SEAL)
        commits = m.software.shared.parse_spike_commits(m.runner.PRE / 'spike.trace')
        pcs = m.handler_read_pcs(commits)
        self.assertEqual(len(pcs), 2)
        m.handler_causes([c for c in commits if c.pc in pcs])
        self.assertFalse(pre['scalar_comparison_qualified'])


if __name__ == '__main__':
    unittest.main()
