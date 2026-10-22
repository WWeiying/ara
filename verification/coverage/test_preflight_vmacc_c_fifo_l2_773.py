import dataclasses
import json
import os
import unittest

import preflight_vmacc_c_fifo_l2_773 as q
import test_preflight_vmacc_c_fifo773 as prior


class ActualL2(prior.ActualFixture):
    @classmethod
    def setUpClass(cls):
        directory = q.old.Path(os.environ.get('VMACC_L2_PREFLIGHT', str(
            q.OUT / 'vmacc-C-fifo-l2-preflight773-agent-20261007-02'))).resolve()
        cls.manifest = directory / 'runtime-qualified.json'
        cls.preflight = json.loads(cls.manifest.read_bytes())
        q.require(cls.preflight['status'] == 'VMACC_FIFO_L2_RUNTIME_AND_EVERY_VECTOR_GOLD_PREFLIGHT_PASS_NOT_DUT',
                  'Actual runtime-qualified fixture required')
        q.life.check(cls.preflight['input_pins'])
        cls.symbols = cls.preflight['symbols']
        cls.trace = q.old.Path(cls.preflight['reference'])
        cls.commits = q.old.build.parse_spike_commits(cls.trace)
        from elftools.elf.elffile import ELFFile
        with q.old.Path(cls.preflight['ELF']).open('rb') as stream:
            cls.segments = [(p['p_paddr'], p['p_paddr'] + p['p_memsz'])
                            for p in ELFFile(stream).iter_segments() if p['p_type'] == 'PT_LOAD']

    def test_failure_counter_corruption(self):
        # Original negative changed a32-bit checks store's discarded upper bits, not num_failed.
        address = self.symbols['num_failed'] - 4
        indices = [i for i, c in enumerate(self.commits) if c.instruction & 0x7f == 0x23
                   and c.instruction >> 12 & 7 == 3 and (address, 0) in c.memory_accesses]
        self.assertEqual(len(indices), 1)
        commits = list(self.commits)
        i = indices[0]
        accesses = tuple((a, 1 << 32 if a == address else v) for a, v in commits[i].memory_accesses)
        self.assertNotEqual(accesses, commits[i].memory_accesses)
        commits[i] = dataclasses.replace(commits[i], memory_accesses=accesses)
        self.reject(commits)

    def test_every_actual_vector_writer_against_integer_gold(self):
        self.assertEqual(q.vector_gold(self.commits), self.preflight['numerical_vectors'])
        recovery = next(c for c in self.commits if c.pc == self.symbols['vmacc_ring_recovery'])
        self.assertEqual(set(recovery.vector_writes), {24})
        self.assertEqual(recovery.vector_vl, 4)
        self.assertEqual(recovery.vector_lmul, 'm8')

    def test_recovery_known_tail_corruption(self):
        commits = list(self.commits)
        i = next(i for i, c in enumerate(commits) if c.pc == self.symbols['vmacc_ring_recovery'])
        writes = dict(commits[i].vector_writes)
        writes[24] ^= 1 << 1000
        commits[i] = dataclasses.replace(commits[i], vector_writes=writes)
        with self.assertRaises(ValueError):
            q.vector_gold(commits)

    def test_recovery_extra_register_write(self):
        commits = list(self.commits)
        i = next(i for i, c in enumerate(commits) if c.pc == self.symbols['vmacc_ring_recovery'])
        writes = dict(commits[i].vector_writes)
        writes[25] = 0
        commits[i] = dataclasses.replace(commits[i], vector_writes=writes)
        with self.assertRaises(ValueError):
            q.vector_gold(commits)

    def test_actual_runtime_bounds(self):
        self.assertEqual(q.runtime(self.commits, self.symbols, self.segments), self.preflight['runtime'])
        self.assertEqual(self.preflight['runtime']['stack_depth'], 48)
        self.assertEqual(self.preflight['runtime']['stack_top'], 0x80040000)

    def test_runtime_outside_stack(self):
        commits = list(self.commits)
        i = next(i for i, c in enumerate(commits) if 2 in c.gpr_writes)
        writes = dict(commits[i].gpr_writes)
        writes[2] = 0x80200000
        commits[i] = dataclasses.replace(commits[i], gpr_writes=writes)
        with self.assertRaises(ValueError):
            q.runtime(commits, self.symbols, self.segments)

    def test_segment_stack_overlap(self):
        with self.assertRaises(ValueError):
            q.runtime(self.commits, self.symbols, self.segments + [(q.STACK_LOW, q.TOP)])

    def test_scalar_prestate_address_corruption(self):
        commits = list(self.commits)
        i = next(i for i, c in enumerate(commits) if c.pc >= q.LOW and c.memory_accesses)
        accesses = tuple((a + 8, v) for a, v in commits[i].memory_accesses)
        commits[i] = dataclasses.replace(commits[i], memory_accesses=accesses)
        with self.assertRaises(ValueError):
            q.runtime(commits, self.symbols, self.segments)

    def test_terminal_effect_rejected(self):
        commits = list(self.commits)
        commits[-1] = dataclasses.replace(commits[-1], gpr_writes={10: 1})
        with self.assertRaises(ValueError):
            q.runtime(commits, self.symbols, self.segments)


class Transform(unittest.TestCase):
    def test_exact_one_literal(self):
        self.assertIn('+  li sp, 0x80040000', q.source_transform(q.ORIGINAL.read_text(), q.START.read_text()))

    def test_other_change_rejected(self):
        with self.assertRaises(ValueError):
            q.source_transform(q.ORIGINAL.read_text(), q.START.read_text().replace('li a0, 3', 'li a0, 1'))

    def test_wrong_stack_rejected(self):
        with self.assertRaises(ValueError):
            q.source_transform(q.ORIGINAL.read_text(), q.START.read_text().replace('0x80040000', '0x80040010'))


if __name__ == '__main__':
    unittest.main()
