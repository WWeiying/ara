"""Host-only causal oracle tests. No simulation or measured coverage claims."""
import copy
import csv
from pathlib import Path
import tempfile
import unittest

import cache_port1_refill_successor as s


class SuccessorTests(unittest.TestCase):
    def reject_change(self, cycle, field, value):
        rows = copy.deepcopy(s.sample_contract())
        rows[cycle][field] = value
        with self.assertRaises(ValueError):
            s.oracle(rows)

    def test_host_contract_not_system_qualification(self):
        result = s.oracle(s.sample_contract())
        self.assertEqual(result['target_raw_positions'], [6, 7, 21, 23, 27])
        self.assertFalse(result['system_population_admissible'])
        self.assertFalse(result['CPU_PTW_path_qualified'])
        self.assertIsNone(result['measured_FSM_increment'])

    def test_last_beat_must_coincide_with_B_grant(self):
        self.reject_change(0, 'axi_rvalid', 0)
        self.reject_change(1, 'axi_rvalid', 1)

    def test_previous_grant_not_arbitrary_ack(self):
        self.reject_change(1, 'rd_ack_q', 0)
        self.reject_change(3, 'rd_ack_q', 0)

    def test_matching_last_handshake(self):
        self.reject_change(0, 'axi_rready', 0)
        self.reject_change(0, 'axi_rlast', 0)
        self.reject_change(0, 'axi_rid', 0)

    def test_other_port_mshr_owner_required(self):
        self.reject_change(1, 'mshr_owner', 1)
        self.reject_change(1, 'mshr_valid', 0)

    def test_refill_cause_not_merely_replay_state(self):
        self.reject_change(1, 'load_ack', 0)
        self.reject_change(1, 'return_valid', 0)
        self.reject_change(1, 'wr_cl_vld', 0)

    def test_no_reset_kill_or_hit_selected_completion(self):
        self.reject_change(2, 'rst_n', 0)
        self.reject_change(3, 'kill_req', 1)
        self.reject_change(3, 'any_hit', 1)

    def test_saved_address_and_distinct_lines(self):
        self.reject_change(1, 'b_addr', s.A)
        self.reject_change(3, 'b_addr', s.B + 32)

    def test_B_completion_mandatory(self):
        self.reject_change(5, 'data_rvalid', 0)
        self.reject_change(5, 'data_rdata', s.B_WORD ^ 1)
        self.reject_change(5, 'data_rid', 0)
        with self.assertRaises(ValueError):
            s.oracle(s.sample_contract()[:4])

    def test_gaps_unknowns_nonbinary_and_foreign_fields(self):
        self.reject_change(3, 'cycle', 4)
        self.reject_change(2, 'rd_ack', 'x')
        self.reject_change(1, 'wr_cl_vld', 2)
        rows = s.sample_contract()
        rows[0]['unreviewed'] = 1
        with self.assertRaises(ValueError):
            s.oracle(rows)

    def test_actual_probe_schema_csv(self):
        probe = (s.HERE / 'cache_port1_refill_successor_probe.sv').read_text()
        self.assertIn(','.join(s.FIELDS) + r'\n', probe)
        with tempfile.TemporaryDirectory(dir=s.OUT) as name:
            path = Path(name) / 'host-example.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=s.FIELDS)
                writer.writeheader()
                writer.writerows(s.sample_contract())
            self.assertEqual(s.read_trace(path), s.sample_contract())
            self.assertFalse(s.oracle(s.read_trace(path))['system_population_admissible'])

    def test_fixture_does_not_force_internal_state(self):
        fixture = (s.HERE / 'cache_port1_refill_successor_fixture.sv').read_text()
        self.assertNotIn('force ', fixture)
        self.assertNotIn('release ', fixture)
        self.assertNotIn('dut.state_q =', fixture)
        self.assertNotIn('dut.state_q <=', fixture)
        self.assertIn('return_valid <= a_last_valid;', fixture)
        self.assertIn('MUST NOT be admitted to the system population', fixture)


if __name__ == '__main__':
    unittest.main()
