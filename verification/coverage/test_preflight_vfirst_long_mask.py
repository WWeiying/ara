import dataclasses
import json
import unittest
from unittest.mock import patch

import preflight_vfirst_long_mask as tool


class HostTests(unittest.TestCase):
    def test_eight_exact_cases(self):
        self.assertEqual(tool.POSITIONS, (2, 4, 128, 256, 512, 1023, None, 0))
        for pos in tool.POSITIONS:
            data = tool.mask(pos)
            self.assertEqual(sum(bin(v).count('1') for v in data), 0 if pos is None else 1)
            self.assertEqual(tool.first_set(data), (1 << 64) - 1 if pos is None else pos)

    def test_first_priority_independent(self):
        for a, b in ((2, 512), (128, 1023), (0, 4)):
            data = bytes(x | y for x, y in zip(tool.mask(a), tool.mask(b)))
            self.assertEqual(tool.first_set(data), min(a, b))

    def test_invalid_masks_reject(self):
        for pos in (-1, 1024):
            with self.assertRaises(ValueError): tool.mask(pos)
        with self.assertRaises(ValueError): tool.first_set(bytes(127))

    def test_ledger_and_384_checks(self):
        self.assertEqual((20 + 20 + 8) * 8, 384)
        self.assertEqual(tool.ledger_gold(None), [(1 << 64) - 1, 1024, 0, 1024, 3, 0, 0, 0])

    def test_implicit_vector_rejected(self):
        prefix = '80002000: 57 70 05 00 '
        text = '\n'.join(prefix + m for m in ('vsetvli', 'vlm.v', 'vfirst.m', 'vs1r.v'))
        self.assertEqual(len(tool.linked(text)), 4)
        with self.assertRaises(ValueError): tool.linked(text + '\n' + prefix + 'vle64.v')

    def test_actual_objdump_word_format(self):
        text = '\n'.join('80002000: 4208a757\t' + m for m in ('vsetvli', 'vlm.v', 'vfirst.m', 'vs1r.v'))
        self.assertEqual(len(tool.linked(text)), 4)
        with self.assertRaises(ValueError): tool.linked(text + '\n80002004: 4208a757\tvle8.v')


class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = tool.OUT / 'vfirst-long-mask-preflight-agent-20261007-02/preflight.json'
        if not path.exists(): raise unittest.SkipTest('Actual software preflight not built yet')
        cls.pre = json.loads(path.read_bytes()); cls.symbols = cls.pre['symbols']
        cls.trace = tool.Path(cls.pre['reference']);cls.commits = tool.build.parse_spike_commits(cls.trace)

    def reject(self, commits):
        with patch.object(tool.build, 'parse_spike_commits', return_value=commits):
            with self.assertRaises(ValueError): tool.validate(self.trace, self.symbols)

    def test_actual(self):
        result = tool.validate(self.trace, self.symbols)
        self.assertEqual(result, {k: v for k, v in self.pre['counts'].items() if k != 'runtime'})

    def test_wrong_rd(self):
        commits = list(self.commits)
        i = next(i for i, c in enumerate(commits) if c.pc == self.symbols['vfirst_scalar_op'])
        rd = commits[i].instruction >> 7 & 31
        commits[i] = dataclasses.replace(commits[i], gpr_writes={rd: 3})
        self.reject(commits)

    def test_missing_whole_readback(self):
        self.reject([c for c in self.commits if c.pc != self.symbols['vfirst_whole_readback']])

    def test_unexpected_vfirst_writer(self):
        commits = list(self.commits)
        i = next(i for i, c in enumerate(commits) if c.pc == self.symbols['vfirst_scalar_op'])
        commits[i] = dataclasses.replace(commits[i], vector_writes={0: 0})
        self.reject(commits)

    def test_guard_store_corruption(self):
        commits = list(self.commits); address = self.symbols['vfirst_snapshot']
        i = next(i for i, c in enumerate(commits) if (address, tool.GUARD) in c.memory_accesses)
        c = commits[i]
        commits[i] = dataclasses.replace(c, memory_accesses=tuple(
            (a, 0 if a == address else v) for a, v in c.memory_accesses))
        self.reject(commits)


if __name__ == '__main__': unittest.main()
