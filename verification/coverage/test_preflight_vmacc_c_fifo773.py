import dataclasses
import json
import unittest
from unittest.mock import patch

import preflight_vmacc_c_fifo773 as q


class ActualFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = q.OUT / 'vmacc-C-fifo-preflight773-agent-20261007-03/preflight.json'
        cls.preflight = q.life.read_bound(cls.manifest,
            '8de1fdf45417ad90914339149d0aa68eb9de66de5b4d2e0d7c848c3253658b4f')
        q.life.check(cls.preflight['input_pins'])
        cls.symbols = cls.preflight['symbols']
        cls.trace = q.Path(cls.preflight['reference'])
        cls.commits = q.build.parse_spike_commits(cls.trace)

    def reject(self, commits):
        with patch.object(q.build, 'parse_spike_commits', return_value=commits):
            with self.assertRaises(ValueError):
                q.validate(self.trace, self.symbols)

    def mutate_store(self, address, value):
        commits = list(self.commits)
        indices = [i for i, c in enumerate(commits)
                   if any(a == address and v is not None for a, v in c.memory_accesses)]
        self.assertTrue(indices)
        i = indices[-1]
        c = commits[i]
        accesses = tuple((a, value if a == address and v is not None else v) for a, v in c.memory_accesses)
        self.assertEqual(sum(a == address and v is not None for a, v in c.memory_accesses), 1)
        commits[i] = dataclasses.replace(c, memory_accesses=accesses)
        self.reject(commits)

    def test_actual(self):
        self.assertEqual(q.validate(self.trace, self.symbols), self.preflight['counts'])

    def test_full_vrf_corruption(self):
        self.mutate_store(self.symbols['vmacc_ring_vrf'] + 16 + 3072, 0xff)

    def test_phase2_preserved_tail_corruption(self):
        self.mutate_store(self.symbols['vmacc_ring_vrf'] + 4128 + 16 + 4095, 0xff)

    def test_guard_corruption(self):
        self.mutate_store(self.symbols['vmacc_ring_vrf'], 0)

    def test_csr_corruption(self):
        self.mutate_store(self.symbols['vmacc_ring_csr'] + 40, 1024)

    def test_failure_counter_corruption(self):
        self.mutate_store(self.symbols['num_failed'] - 4, (1 << 32) | 2344)

    def test_wrong_tohost(self):
        self.mutate_store(self.symbols['tohost'], 3)

    def test_missing_target(self):
        i = next(i for i, c in enumerate(self.commits) if c.pc == self.symbols['vmacc_ring_op'])
        self.reject(self.commits[:i] + self.commits[i + 1:])

    def test_extra_target(self):
        c = next(c for c in self.commits if c.pc == self.symbols['vmacc_ring_op'])
        self.reject(self.commits + [c])

    def test_wrong_opcode(self):
        commits = list(self.commits)
        i = next(i for i, c in enumerate(commits) if c.pc == self.symbols['vmacc_ring_op'])
        commits[i] = dataclasses.replace(commits[i], instruction=commits[i].instruction ^ (1 << 25))
        self.reject(commits)

    def test_wrong_vl(self):
        commits = list(self.commits)
        i = next(i for i, c in enumerate(commits) if c.pc == self.symbols['vmacc_ring_op'])
        commits[i] = dataclasses.replace(commits[i], vector_vl=1020)
        self.reject(commits)

    def test_immutable_source_read_corruption(self):
        commits = list(self.commits)
        i = next(i for i, c in enumerate(commits) if c.instruction & 0x7f == 3 and
                 (self.symbols['vmacc_ring_source'], None) in c.memory_accesses)
        c = commits[i]
        self.assertEqual(len(c.gpr_writes), 1)
        commits[i] = dataclasses.replace(c, gpr_writes={r: v ^ 1 for r, v in c.gpr_writes.items()})
        self.reject(commits)

    def test_ring_all_start_pointers_and_wrong_alternation(self):
        for start in range(4):
            visits = [[] for _ in range(4)]
            bad = [[] for _ in range(4)]
            for i, length in enumerate([256] * 4 + [255] * 4 + [256] * 4):
                visits[(start + i) % 4].append(length)
            for i, length in enumerate([256, 255] * 6):
                bad[(start + i) % 4].append(length)
            self.assertTrue(all(v == [256, 255, 256] for v in visits))
            self.assertFalse(all(set(v) == {256, 255} for v in bad))

    def test_every_actual_vector_writer_against_integer_gold(self):
        writers = [c for c in self.commits if c.vector_writes]
        self.assertEqual(len(writers), 19)
        a = bytes((i ^ 0xa5) & 255 for i in range(1024))
        b = bytes((2 * i + 1) & 255 for i in range(1024))
        for c, base in zip(writers[:4], (0, 8, 16, 24)):
            self.assertEqual(c.vector_writes, {r: int.from_bytes(bytes([0x5a]) * 128, 'little')
                                               for r in range(base, base + 8)})
        for c, base, data in zip(writers[4:6], (8, 16), (a, b)):
            self.assertEqual(c.vector_writes, {base + r: int.from_bytes(data[128*r:128*(r+1)], 'little')
                                               for r in range(8)})
        acc = [0x5a] * 1024
        for index, c in enumerate(writers[6:]):
            if index < 12:
                for i in range(1020 if 4 <= index < 8 else 1024):
                    acc[i] = (acc[i] + a[i] * b[i]) & 255
            else:
                for i in range(4):
                    acc[i] = (acc[i] + 1) & 255
            self.assertEqual(c.vector_writes, {24 + r: int.from_bytes(bytes(acc[128*r:128*(r+1)]), 'little')
                                               for r in range(8)})


if __name__ == '__main__':
    unittest.main()
