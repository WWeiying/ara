"""Preserve sealed tests; construct the actual PC mutation on a frozen dataclass."""
from dataclasses import replace
import unittest
import test_pure_war_preflight as original

PureWarOracleTests = original.PureWarOracleTests
TargetBindingTests = original.TargetBindingTests


class ActualPureWarTests(original.ActualPureWarTests):
    def test_actual_exact_one_pc_mutation(self):
        cs = list(self.cs)
        hits = [i for i, c in enumerate(cs) if c.pc == self.pre['symbols']['gpw_div']]
        self.assertEqual(len(hits), 1)
        index = hits[0]
        cs[index] = replace(cs[index], pc=cs[index].pc + 8)
        self.assertEqual(sum(a != b for a, b in zip(cs, self.cs)), 1)
        self.assertEqual(cs[index].instruction, original.q.DIV)
        with self.assertRaises(ValueError):
            original.q.validate(cs, self.pre['symbols'], self.text)


if __name__ == '__main__': unittest.main()
