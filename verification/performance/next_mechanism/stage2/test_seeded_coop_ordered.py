#!/usr/bin/env python3
from pathlib import Path
import unittest

import run_seeded_coop_ordered as gate


class OrderedTests(unittest.TestCase):
    def setUp(self):
        self.original=(gate.prior.v1.ACCEPTED/'matrix_tb.sv').read_text()
        self.scenarios=(gate.HERE/'seeded_coop_scenarios.svh').read_text()
        self.text=gate.bench_source(self.original,self.scenarios)

    def test_all_new_monitors_follow_canonical_score_declarations(self):
        self.assertLess(self.text.index('  logic score_commit;'),self.text.index('    cycles++;'))
        self.assertLess(self.text.index('  integer score_vd;'),self.text.index('    cycles++;'))
        self.assertLess(self.text.index('  task automatic expect_fault('),
                        self.text.index('  always_ff @(posedge clk or negedge rst_n) begin\n    if (!rst_n) begin\n      delayed_final'))
        self.assertLess(self.text.index('    cycles++;'),self.text.index('  task automatic load_seed_vectors;'))

    def test_seed_ports_stay_before_dut_and_checker_is_identical(self):
        self.assertLess(self.text.index('  logic command_seed = 0;'),self.text.index('  qbs_engine_composed #('))
        checker=self.original.split('  always_ff @(posedge clk) begin : score_vrf_commit',1)[1].split('  task automatic send_command',1)[0]
        self.assertIn(checker,self.text)
        self.assertEqual(self.text.count('    cycles++;'),1)
        local=gate.prior.adapt(self.text)
        self.assertLess(local.index('  integer score_vd;'),local.index('  int local_seed_checks=0'))


if __name__=='__main__': unittest.main()
