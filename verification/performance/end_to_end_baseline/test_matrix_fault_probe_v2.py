import unittest

from run_matrix_fault_schedule_v2 import probe_bench


class ProbePlacementTests(unittest.TestCase):
    def test_declarations_precede_probe(self):
        source='''module qbs_engine_tb;
  initial $display("MATRIX_ENGINE_CONFIG wide=%0d", Wide);
  import qbs_pkg::*;
  logic clk;
  always @(posedge clk) begin
      else if (axi_r_valid && axi_r_ready) response_delay <= response_gap;
  end
endmodule : qbs_engine_tb
'''
        result=probe_bench(source)
        self.assertGreater(result.index('`include "matrix_replay_probe.svh"'),result.index('logic clk;'))
        self.assertEqual(result.count('`include "matrix_replay_probe.svh"'),1)
        self.assertIn('MATRIX_FAST_FAULT_DRAIN',result)


if __name__=='__main__':unittest.main()
