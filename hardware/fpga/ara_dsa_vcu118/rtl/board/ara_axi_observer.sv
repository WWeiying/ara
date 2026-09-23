// SPDX-License-Identifier: SHL-0.51
// Passive counters at the 64-bit LLC output, before DDR width conversion.
module ara_axi_observer #(
  parameter type req_t = logic,
  parameter type rsp_t = logic
) (
  input logic clk_i, rst_ni, soc_rst_ni, enable_i, clear_i,
  input req_t req_i,
  input rsp_t rsp_i,
  output logic [14:0][63:0] counters_o
);
  wire ar = req_i.ar_valid && rsp_i.ar_ready;
  wire aw = req_i.aw_valid && rsp_i.aw_ready;
  wire r = rsp_i.r_valid && req_i.r_ready;
  wire w = req_i.w_valid && rsp_i.w_ready;
  wire b = rsp_i.b_valid && req_i.b_ready;
  wire read_error = r && rsp_i.r.resp[1];
  wire write_error = b && rsp_i.b.resp[1];
  logic [63:0] reads_q, writes_q;
  logic [14:0][63:0] metrics_q;
  logic [7:0] write_bytes;
  always_comb begin
    write_bytes = 0;
    for (int i = 0; i < $bits(req_i.w.strb); i++)
      write_bytes = write_bytes + 8'(req_i.w.strb[i]);
    counters_o = metrics_q;
    counters_o[8] = reads_q;
    counters_o[9] = writes_q;
    // A response ID does not uniquely identify an address with multiple
    // outstanding requests. Never report last AW/AR as the failing address.
    counters_o[13] = 0;
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      reads_q <= 0;
      writes_q <= 0;
      metrics_q <= '0;
    end else begin
      case ({ar, r && rsp_i.r.last})
        2'b10: reads_q <= reads_q + 1;
        2'b01: reads_q <= reads_q - 1;
        default: ;
      endcase
      case ({aw, b})
        2'b10: writes_q <= writes_q + 1;
        2'b01: writes_q <= writes_q - 1;
        default: ;
      endcase
      if (!soc_rst_ni) begin
        reads_q <= 0;
        writes_q <= 0;
      end
      if (clear_i) metrics_q <= '0;
      else if (enable_i) begin
        metrics_q[0] <= metrics_q[0] + 64'(ar);
        metrics_q[1] <= metrics_q[1] + 64'(aw);
        // Bus occupancy bytes, not requested bytes for narrow transfers,
        // nor physical DDR traffic (refresh/ECC/MIG activity is not counted).
        metrics_q[2] <= metrics_q[2] + (r ? 64'($bits(rsp_i.r.data)/8) : 0);
        metrics_q[3] <= metrics_q[3] + (w ? 64'(write_bytes) : 0);
        metrics_q[4] <= metrics_q[4] + 64'(req_i.ar_valid && !rsp_i.ar_ready);
        metrics_q[5] <= metrics_q[5] + 64'(req_i.aw_valid && !rsp_i.aw_ready);
        metrics_q[6] <= metrics_q[6] + 64'(rsp_i.r_valid && !req_i.r_ready);
        metrics_q[7] <= metrics_q[7] + 64'(req_i.w_valid && !rsp_i.w_ready);
        if (ar) metrics_q[10] <= 64'(req_i.ar.addr);
        if (aw) metrics_q[11] <= 64'(req_i.aw.addr);
        metrics_q[12] <= metrics_q[12] + 64'(read_error) + 64'(write_error);
        if (read_error)
          metrics_q[14] <= (64'(rsp_i.r.id) << 8) | 64'(rsp_i.r.resp);
        if (write_error)
          metrics_q[14] <= (64'(rsp_i.b.id) << 8) | 64'(rsp_i.b.resp) | 64'h4;
      end
    end
  end
endmodule
