import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import build_store_fault_flush_preflight as p


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.symbols = {name: 0x80010000 + i * 0x1000 for i, name in enumerate(p.SYMBOLS)}
        s = self.symbols
        self.writes = {s['tohost']: 1, s['g75_result']: 134, s['g75_result'] + 4: 0,
                       s['num_failed']: 0, s['sff_count']: 1, s['sff_marker']: 1}
        for b, name in enumerate(('sff_a', 'sff_b', 'sff_dest', 'sff_dump_a', 'sff_dump_b')):
            self.writes.update({s[name] + 8 * i: p.expected(b, i) for i in range(20)})
        self.writes.update({s['sff_index'] + 2 * i: v for i, v in enumerate(p.OFFSETS)})
        trap = [1, 7, p.BAD, s['sff_fault'], 0, 8, 24, 0x1800, 0, 0]
        self.writes.update({s['sff_trap'] + 8 * i: v for i, v in enumerate(trap)})
        for slot in range(2):
            self.writes.update({s['sff_cfg'] + slot * 32 + i * 8: v for i, v in enumerate((8, 24, 0, 128))})
            self.writes.update({s['sff_env'] + slot * 24 + i * 8: 0 for i in range(3)})
        self.text = 'core 0: exception trap_store_access_fault\n'

    def evaluate(self, writes=None, text=None):
        c = SimpleNamespace(pc=self.symbols['sff_recovery'], fpr_writes={},
                            memory_accesses=tuple((self.writes if writes is None else writes).items()),
                            vector_vl=8, vector_sew=64, vector_vstart=0)
        return p.validate([c], self.symbols, self.text if text is None else text)

    def test_complete(self):
        self.assertEqual(self.evaluate()['checks'], 134)

    def reject(self, address, value):
        w = copy.copy(self.writes); w[address] = value
        with self.assertRaises(ValueError): self.evaluate(w)

    def test_cause_cannot_be_misalignment(self):
        self.reject(self.symbols['sff_trap'] + 8, 6)

    def test_fault_element_must_be_zero(self):
        self.reject(self.symbols['sff_trap'] + 32, 1)

    def test_privilege(self):
        self.reject(self.symbols['sff_trap'] + 56, 0x800)

    def test_mprv(self):
        self.reject(self.symbols['sff_env'], 0x20000)

    def test_stale_source_recovery(self):
        self.reject(self.symbols['sff_dest'] + 16, p.expected(0, 2))

    def test_destination_tail_guard(self):
        self.reject(self.symbols['sff_dest'] + 80, 0)

    def test_full_source_tail(self):
        self.reject(self.symbols['sff_dump_a'] + 17 * 8, 0)

    def test_no_silent_missing_num_failed(self):
        w = copy.copy(self.writes); del w[self.symbols['num_failed']]
        with self.assertRaises(ValueError): self.evaluate(w)

    def test_extra_trap(self):
        with self.assertRaises(ValueError): self.evaluate(text=self.text * 2)

    def test_expected_model_has_no_active_tail_store(self):
        self.assertNotEqual(p.expected(0, 2), p.expected(1, 2))
        self.assertEqual([p.expected(2, i) for i in range(10, 20)], [p.GUARD] * 10)

    def test_frozen731_static_target(self):
        receipt = p.static()
        self.assertEqual(receipt['primary_target']['point']['raw_index'], 54)
        self.assertFalse(receipt['primary_target']['hit731'])
        self.assertFalse(receipt['FIFO_eight_points_targeted'])

    def test_actual_dependency_serialization_before_any_tool(self):
        receipt = {'pins': {str(p.APP): p.life.digest(p.APP)}}
        expected = p.Path(__file__).resolve().parent / 'reviewed_20261004/audit_readonly.py'
        def inspect(pins):
            self.assertIn(str(expected), pins)
            self.assertTrue(all(Path(path).is_file() for path in pins))
            raise RuntimeError('test stopped before output or software tools')
        with patch.object(p, 'static', return_value=receipt), patch.object(p.life, 'check', side_effect=inspect), \
             patch.object(p.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'test stopped'):
                p.build(p.OUT / 'store-fault-flush-test-never-created')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
