from types import SimpleNamespace as NS
import unittest
import build_gap99_preflight as m


class OracleTests(unittest.TestCase):
    def test_observations(self):
        words = m.expected_observations(0)
        self.assertEqual(len(words), 12)
        self.assertEqual(words[2], 0x20000)
        self.assertEqual(words[8], 0x20800)
        self.assertEqual(words[0], words[6])

    def test_signature_failure(self):
        symbols = dict(tohost=8, g75_result=16, num_failed=24, g75_trap=32, trap_fail=64, g99_observed=128)
        commits = [NS(vector_writes={}, pc=0, memory_accesses=[(8, 3)])]
        with self.assertRaises(ValueError):
            m.validate(commits, symbols)

    def test_trap_rejected(self):
        symbols = dict(trap_fail=64)
        with self.assertRaises(ValueError):
            m.validate([NS(vector_writes={}, pc=64)], symbols)

    def test_vector_rejected(self):
        with self.assertRaises(ValueError):
            m.validate([NS(vector_writes={1: 1}, pc=0)], dict(trap_fail=64))


if __name__ == "__main__":
    unittest.main()
