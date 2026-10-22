import copy
import json
import unittest

import check_cache_port1_sv39_offline as m


class OfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = json.loads((m.runner.PRE / 'preflight-manifest.json').read_bytes())
        cls.records = m.rows(m.RUN / 'commit_trace.csv')

    def test_actual_dut_oracle(self):
        result = m.architecture(self.records, self.pre['symbols'])
        self.assertEqual(result['checks'], 35)
        self.assertEqual(len(result['trap_rows']), 2)

    def test_wrong_trap_pc(self):
        rows = copy.deepcopy(self.records)
        next(r for r in rows if r['trap'])['pc'] += 4
        with self.assertRaises(ValueError): m.architecture(rows, self.pre['symbols'])

    def test_extra_trap(self):
        rows = copy.deepcopy(self.records)
        rows[0]['trap'] = 1
        with self.assertRaises(ValueError): m.architecture(rows, self.pre['symbols'])

    def test_wrong_output(self):
        rows = copy.deepcopy(self.records)
        addr = self.pre['symbols']['gcb_out'] + 8
        candidates = [r for r in rows if r['mem_addr'] == addr and r['mem_wmask']]
        candidates[-1]['mem_wdata'] ^= 1
        with self.assertRaises(ValueError): m.architecture(rows, self.pre['symbols'])

    def test_wrong_linked_pte(self):
        rows = copy.deepcopy(self.records)
        addr = self.pre['symbols']['gcb_leaf'] + 4 * 8
        next(r for r in reversed(rows) if r['mem_addr'] == addr and r['mem_wmask'])['mem_wdata'] ^= 0x400
        with self.assertRaises(ValueError): m.architecture(rows, self.pre['symbols'])

    def test_partial_terminal(self):
        rows = copy.deepcopy(self.records)
        rows[-1]['mem_wmask'] = 15
        with self.assertRaises(ValueError): m.architecture(rows, self.pre['symbols'])

    def test_scalar_boundaries(self):
        valid = dict(status='TERMINAL_TOHOST_MATCH', matched_instructions=12335,
            matched_scalar_writes=4015, matched_scalar_memory_accesses=2062,
            ara_committed_instructions=12335, ara_retired_instructions=12337,
            ara_trap_events=2, skipped_unobservable_register_values=0,
            stopped_at_unobservable=None, mismatch=None, matched_floating_writes=0,
            rvfi_store_data_layout='unshifted')
        m.validate_scalar(valid)
        for key, value in [('ara_trap_events', 0), ('matched_instructions', 12334),
                           ('skipped_unobservable_register_values', 1), ('mismatch', {}),
                           ('skipped_unobservable_register_values', False), ('matched_floating_writes', False)]:
            changed = dict(valid, **{key: value})
            with self.assertRaises(ValueError): m.validate_scalar(changed)


if __name__ == '__main__':
    unittest.main()
