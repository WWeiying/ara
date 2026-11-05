// SPDX-License-Identifier: SHL-0.51
// Read-only integration probe. Counts are lane requests, not RVV instructions.
module shared_fma_soc_monitor import ara_pkg::*; import rvv_pkg::*; #(
  parameter bit SharedFma = 0
) (
  input logic clk_i, rst_ni, in_valid, in_ready, out_valid, out_ready,
  input ara_op_e op,
  input vew_e sew,
  input logic latency_stall,
  input logic [4:0] flags
);
  longint unsigned cycles, issued, retired, blocked, latency_wait, fma[4];
  longint signed outstanding;
  initial $display("FMA_SOC_MONITOR %m shared=%0d",SharedFma);
  always @(posedge clk_i) begin
    if (!rst_ni) begin
      cycles=0; issued=0; retired=0; blocked=0; latency_wait=0; outstanding=0;
      foreach (fma[i]) fma[i]=0;
    end else begin
      cycles++;
      if (in_valid && in_ready) begin
        issued++; outstanding++;
        if (op inside {VFADD,VFSUB,VFRSUB,VFMUL,[VFMACC:VFNMSUB],
                       VFREDUSUM,VFREDOSUM,VFWREDUSUM,VFWREDOSUM}) fma[sew]++;
      end
      if (out_valid && out_ready) begin
        retired++; outstanding--;
        assert (!$isunknown(flags)) else $fatal(1,"Unknown FPU flags %m");
      end
      assert (outstanding >= 0) else $fatal(1,"Unmatched FPU response %m");
      if (in_valid && !in_ready) blocked++;
      if (latency_stall) latency_wait++;
    end
  end
  final begin
    assert (outstanding == 0) else $error("Unretired FPU requests %m: %0d",outstanding);
    $display("FMA_SOC_SUMMARY %m shared=%0d cycles=%0d issued=%0d retired=%0d blocked=%0d latency_wait=%0d fma=%0d,%0d,%0d,%0d",
        SharedFma,cycles,issued,retired,blocked,latency_wait,fma[0],fma[1],fma[2],fma[3]);
  end
endmodule

bind vmfpu shared_fma_soc_monitor #(.SharedFma(SharedFma)) i_fma_soc_monitor (
  .clk_i, .rst_ni,
  .in_valid(vfpu_in_valid), .in_ready(vfpu_in_ready),
  .out_valid(vfpu_out_valid), .out_ready(vfpu_out_ready),
  .op(vinsn_issue_q.op), .sew(vinsn_issue_q.vtype.vsew),
  .latency_stall(latency_stall), .flags(vfpu_ex_flag_fn)
);
