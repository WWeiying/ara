import unittest
from entry_drain import drain_at


class EntryDrainTest(unittest.TestCase):
    def test_edges(self):
        entries = [dict(alloc=2, done=10), dict(alloc=5, done=7)]
        self.assertEqual(drain_at(entries, 2)['observed_remaining_cycles'], 0)
        self.assertEqual(drain_at(entries, 5)['observed_remaining_cycles'], 5)
        self.assertEqual(len(drain_at(entries, 6)['older_live']), 2)
        self.assertEqual(len(drain_at(entries, 7)['older_live']), 1)
        self.assertEqual(drain_at(entries, 10)['observed_remaining_cycles'], 0)

    def test_empty(self):
        self.assertEqual(drain_at([], 42)['older_live'], [])
