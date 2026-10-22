import unittest
import copy
from dataclasses import replace
from types import SimpleNamespace
import build_csr_satp_sepc785 as p


class MatrixTests(unittest.TestCase):
    def test_independent_dimensions(self):
        self.assertEqual(len(p.expected(0x6600)), 42)
        self.assertEqual(p.expected(0x6600)[-3:], [0, 0, 0x6600])
        self.assertEqual(p.expected(0x6600)[4], 8 << 60)

    def test_ppn_full_44_bit_domain(self):
        self.assertEqual(p.PPN[1], (1 << 44) - 1)
        self.assertTrue(all(0 <= v < 1 << 44 for v in p.PPN))
        self.assertEqual(p.PPN[2] ^ p.PPN[3], p.PPN[1])

    def test_canonical_sepc(self):
        for value in p.EPC:
            top = value >> 39
            self.assertEqual(top, (1 << 25) - 1 if value >> 38 & 1 else 0)
        self.assertTrue(all((v & ~1) & 1 == 0 for v in p.EPC))

    def test_mprv_rejected(self):
        with self.assertRaises(ValueError): p.expected(1 << 17)

    def test_mie_rejected(self):
        with self.assertRaises(ValueError): p.expected(8)

    def test_boolean_status_rejected(self):
        with self.assertRaises(ValueError): p.expected(False)

    def test_privilege_return_rejected(self):
        c = SimpleNamespace(vector_writes=[], pc=0x80000000, instruction=0x30200073)
        with self.assertRaisesRegex(ValueError, 'Privilege'): p.validate([c], {'trap_fail': 0x80000100})

    def test_high_fetch_rejected(self):
        c = SimpleNamespace(vector_writes=[], pc=0xffffffc000000000, instruction=0x13)
        with self.assertRaisesRegex(ValueError, 'Fetch'): p.validate([c], {'trap_fail': 0x80000100})

    def test_literal_source_matches_gold(self):
        source = p.APP.read_text()
        self.assertIn('0xfffffffffffUL', source)
        self.assertIn('checks != 44 || position != 42', source)
        self.assertNotIn('sret', source.lower().replace('// no sret:', ''))

    def test_reference_has_compressed_alignment(self):
        self.assertTrue(p.SPIKE_ISA.startswith('rv64gcv_'))


class ActualTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p.shared.check(p.REGRESSION_PINS)
        cls.symbols = {k: p.shared._elf_symbol(p.REGRESSION / 'input.elf', p.shared.LLVM / 'llvm-readelf', k)
            for k in ('tohost', 'g75_result', 'g75_trap', 'num_failed', 'trap_fail', 'matrix_observed', 'matrix_guards')}
        commits = list(p.shared.parse_spike_commits(p.REGRESSION / 'spike.trace'))
        start = next(i for i, c in enumerate(commits) if c.pc == 0x80000000)
        end = next(i for i, c in enumerate(commits) if any(a == cls.symbols['tohost'] and v is not None
                                                        for a, v in c.memory_accesses))
        cls.commits = commits[start:end + 1]

    def test_actual_full_reference(self):
        result = p.validate(self.commits, self.symbols)
        self.assertEqual(result['entry_to_tohost_retired'], 673)
        self.assertEqual(result['all_reference_memory_accesses'], 168)
        self.assertEqual(result['checks'], 44)

    def test_wrong_warl_readback(self):
        commits = copy.deepcopy(self.commits)
        c = next(c for c in commits if c.instruction >> 20 == 0x180 and
                 c.instruction & 127 == 0x73 and (c.instruction >> 12) & 7 == 2)
        rd = (c.instruction >> 7) & 31
        c.gpr_writes[rd] ^= 1 << 43
        with self.assertRaisesRegex(ValueError, 'readback'): p.validate(commits, self.symbols)

    def test_wrong_observed_store(self):
        commits = copy.deepcopy(self.commits)
        address = self.symbols['matrix_observed'] + 7 * 8
        c = next(c for c in reversed(commits) if any(a == address and v is not None for a, v in c.memory_accesses))
        commits[commits.index(c)] = replace(c, memory_accesses=tuple(
            (a, v ^ 1 if a == address and v is not None else v) for a, v in c.memory_accesses))
        with self.assertRaisesRegex(ValueError, '42-value'): p.validate(commits, self.symbols)

    def test_guard_write(self):
        commits = copy.deepcopy(self.commits)
        commits[-1] = replace(commits[-1], memory_accesses=commits[-1].memory_accesses +
                             ((self.symbols['matrix_guards'], p.GUARDS[0]),))
        with self.assertRaisesRegex(ValueError, 'Guard'): p.validate(commits, self.symbols)

    def test_high_ppn_never_used_for_access(self):
        commits = copy.deepcopy(self.commits)
        commits[-1] = replace(commits[-1], memory_accesses=commits[-1].memory_accesses + ((0xfffffffffffff000, None),))
        with self.assertRaisesRegex(ValueError, 'physical'): p.validate(commits, self.symbols)

    def test_extra_csr_write(self):
        commits = copy.deepcopy(self.commits)
        c = copy.deepcopy(next(c for c in commits if c.instruction >> 20 == 0x180 and
                          c.instruction & 127 == 0x73 and (c.instruction >> 12) & 7 == 1))
        commits.insert(-1, c)
        with self.assertRaises(ValueError): p.validate(commits, self.symbols)

    def test_failure_tohost(self):
        commits = copy.deepcopy(self.commits)
        commits[-1] = replace(commits[-1], memory_accesses=tuple((a, 3 if a == self.symbols['tohost'] else v)
                                           for a, v in commits[-1].memory_accesses))
        with self.assertRaisesRegex(ValueError, 'success'): p.validate(commits, self.symbols)


if __name__ == '__main__': unittest.main()
