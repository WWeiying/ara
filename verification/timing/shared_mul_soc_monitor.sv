// Read-only activity evidence at the complete VMFPU ingress/result interfaces.
module shared_mul_soc_monitor (
  input logic clk_i, rst_ni,
  input logic in_valid, in_ready, out_valid, out_ready,
  input logic [1:0] in_sew, out_sew
);
  longint unsigned accepted[4], completed[4], blocked;
  always @(posedge clk_i) begin
    if (!rst_ni) begin
      foreach (accepted[s]) begin accepted[s]=0; completed[s]=0; end
      blocked=0;
    end else begin
      if (in_valid && !in_ready) blocked++;
      if (in_valid && in_ready) accepted[in_sew]++;
      if (out_valid && out_ready) completed[out_sew]++;
    end
  end
  initial begin
`ifdef ARA_SHARED_SIMD_MUL
    $display("MUL_SOC_MODE shared %m");
`else
    $display("MUL_SOC_MODE baseline %m");
`endif
  end
  final begin
    $display("MUL_SOC_ACTIVITY %m accepted=%0d,%0d,%0d,%0d completed=%0d,%0d,%0d,%0d blocked=%0d",
      accepted[0],accepted[1],accepted[2],accepted[3],
      completed[0],completed[1],completed[2],completed[3],blocked);
  end
endmodule

bind vmfpu shared_mul_soc_monitor i_mul_soc_monitor (
  .clk_i(clk_i), .rst_ni(rst_ni),
  .in_valid(vmul_in_valid), .in_ready(vmul_in_ready),
  .out_valid(vmul_out_valid), .out_ready(vmul_out_ready),
  .in_sew(vinsn_issue_q.vtype.vsew[1:0]),
  .out_sew(vinsn_processing_q.vtype.vsew[1:0])
);
