#!/usr/bin/env python3
import unittest
import run_seeded_coop_reset_owned as gate


class ResetOwnedTests(unittest.TestCase):
    def setUp(self):
        self.original=(gate.prior.prior.v1.ACCEPTED/'matrix_tb.sv').read_text()
        self.scenarios=(gate.HERE/'seeded_coop_scenarios.svh').read_text()
        old=gate.prior.BASE_BENCH
        try:
            gate.prior.BASE_BENCH=gate.base_bench
            self.text=gate.stable_sampling(gate.prior.prior.adapt(
                gate.prior.bench_source(self.original,self.scenarios)))
        finally: gate.prior.BASE_BENCH=old

    def test_entire_generated_tb_writers_and_forward_references(self):
        gate.audit_generated(self.text)
        for _,after in gate.DECLARATIONS: self.assertIn(after,self.text)
        self.assertIn('delayed_final <= 0; final_wait <= 0; first_write <= 0;',self.text)
        self.assertIn('else if (final_wait != 0) final_wait <= final_wait-1;',self.text)

    def test_reintroduced_initial_driver_is_rejected(self):
        with self.assertRaises(ValueError):
            gate.audit_generated(self.text.replace('logic [3:0] delayed_final;',
                                                  'logic [3:0] delayed_final = 0;'))

    def test_canonical_checker_and_flag_probes_remain(self):
        checker=self.original.split('  always_ff @(posedge clk) begin : score_vrf_commit',1)[1].split('  task automatic send_command',1)[0]
        self.assertIn(checker,self.text)
        self.assertIn('fflags_o === 5\'b0 && result_fflags === 5\'b0',self.text)
        self.assertIn('enqueued == dequeued && `SC.integer_queue_occupancy == 0',self.text)

    def test_final_ack_enable_does_not_change_in_active_sampling_region(self):
        self.assertNotIn('    cycles++;',self.text)
        self.assertEqual(self.text.count('    cycles <= cycles+1;'),1)
        self.assertIn('first_write && final_wait == 0 && cycles%5 == 0',self.text)


if __name__=='__main__': unittest.main()
