// Uses the same AXI field layout and widths as the frozen VCU118 DDR boundary.
`include "axi/typedef.svh"
package fifo_probe_pkg;
  `AXI_TYPEDEF_W_CHAN_T(w_t, logic [511:0], logic [63:0], logic [1:0])
  `AXI_TYPEDEF_R_CHAN_T(r_t, logic [511:0], logic [7:0], logic [1:0])
  localparam w_t WStrbMask = '{strb: '1, default: '0};
  localparam w_t WUserMask = '{user: '1, default: '0};
  localparam r_t RUserMask = '{user: '1, default: '0};
endpackage

module fifo_probe import fifo_probe_pkg::*; (
  input logic soc_clk, ui_clk, soc_rst_n, ui_rst_n,
  input w_t w_in,
  input r_t r_in,
  input logic [2:0] valid_i, ready_i,
  output logic [2:0] ready_o, valid_o,
  output w_t w_out, w_const_out,
  output r_t r_out
);
  w_t w_const;
  r_t r_const;
  // Exercise cross-boundary constant propagation, including strobes spanning
  // two 64-bit slices and the constant return-user field used by the MIG.
  assign w_const = '{data: w_in.data, strb: '1, last: w_in.last, user: '0};
  assign r_const = '{id: r_in.id, data: r_in.data, resp: r_in.resp,
                     last: r_in.last, user: '0};
  cdc_fifo_gray #(.T(w_t), .LOG_DEPTH(5)) i_w (
    .src_clk_i(soc_clk), .src_rst_ni(soc_rst_n), .src_data_i(w_in),
    .src_valid_i(valid_i[0]), .src_ready_o(ready_o[0]),
    .dst_clk_i(ui_clk), .dst_rst_ni(ui_rst_n), .dst_data_o(w_out),
    .dst_valid_o(valid_o[0]), .dst_ready_i(ready_i[0])
  );
  cdc_fifo_gray #(.T(w_t), .LOG_DEPTH(5)) i_w_const (
    .src_clk_i(soc_clk), .src_rst_ni(soc_rst_n), .src_data_i(w_const),
    .src_valid_i(valid_i[1]), .src_ready_o(ready_o[1]),
    .dst_clk_i(ui_clk), .dst_rst_ni(ui_rst_n), .dst_data_o(w_const_out),
    .dst_valid_o(valid_o[1]), .dst_ready_i(ready_i[1])
  );
  cdc_fifo_gray #(.T(r_t), .LOG_DEPTH(5)) i_r (
    .src_clk_i(ui_clk), .src_rst_ni(ui_rst_n), .src_data_i(r_const),
    .src_valid_i(valid_i[2]), .src_ready_o(ready_o[2]),
    .dst_clk_i(soc_clk), .dst_rst_ni(soc_rst_n), .dst_data_o(r_out),
    .dst_valid_o(valid_o[2]), .dst_ready_i(ready_i[2])
  );
endmodule
