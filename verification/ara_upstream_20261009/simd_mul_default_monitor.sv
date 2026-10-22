`timescale 1ns/1ps
module simd_mul_default_monitor import ara_pkg::*; #(
  parameter int Sew = 0, Pipes = 0, Fixed = 1
)(input logic clk_i, rst_ni, input ara_op_e op, input logic [7:0] r);
  bit reported = 0;
  always @(negedge clk_i) begin
    #1;
    // The datapath operation is registered when Pipes > 0. Sampling away from
    // the active edge avoids mistaking combinational settling for a latch.
    if (rst_ni && op != VSMUL && r !== '0) begin
      if ($test$plusargs("OBSERVE_OLD_R")) begin
        if (!reported) $display("OLD_R_UNDRIVEN sew=%0d pipes=%0d fixed=%0d r=%h",8<<Sew,Pipes,Fixed,r);
        reported=1;
      end else $fatal(1,"ROUND_DEFAULT_NOT_ZERO sew=%0d pipes=%0d fixed=%0d r=%h",8<<Sew,Pipes,Fixed,r);
    end
  end
endmodule
bind simd_mul simd_mul_default_monitor #(.Sew(ElementWidth), .Pipes(NumPipeRegs), .Fixed(FixPtSupport))
  default_monitor (.clk_i(clk_i), .rst_ni(rst_ni), .op(op), .r(r));
