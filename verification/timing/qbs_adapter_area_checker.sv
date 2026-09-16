// SPDX-License-Identifier: SHL-0.51
// Frozen pre-area adapter: compare the public interface on every cycle.
module qbs_adapter_area_checker import qbs_pkg::*; #(
  parameter int unsigned ActivationContextBase = 0,
  parameter bit NativeView = 1'b0
) (
  input logic clk_i, rst_ni, clear_weight_i, clear_activation_i,
  input qbs_weight_profile_e weight_profile_i,
  input qbs_activation_profile_e activation_profile_i,
  input logic [2:0] weight_row_count_i,
  input qbs_activation_layout_e activation_layout_i,
  input logic [3:0] m_i,
  input logic weight_write_valid_i, weight_write_ready_o, weight_write_group_i,
  input logic [1:0] weight_write_row_i,
  input logic [9:0] weight_write_offset_i,
  input logic [127:0] weight_write_data_i,
  input logic [15:0] weight_write_strb_i,
  input logic activation_write_valid_i, activation_write_ready_o,
  input logic [1:0] activation_write_context_i,
  input logic [11:0] activation_write_offset_i,
  input logic [127:0] activation_write_data_i,
  input logic [15:0] activation_write_strb_i,
  input logic weight_read_i, activation_read_i,
  input logic [7:0] read_k_i,
  input logic [127:0] weight_window_o [4][2],
  input logic [255:0] activation_window_o [4],
  input logic [7:0] weight_side_o [4][20], activation_side_o [4][36],
  input logic [3:0] weight_complete_o, activation_complete_o,
  input logic all_weight_complete_o, all_activation_complete_o,
  input logic [31:0] accepted_weight_bytes_o, accepted_activation_bytes_o
);
  logic ref_wr, ref_ar, ref_awc, ref_aac;
  logic [3:0] ref_wc, ref_ac;
  logic [31:0] ref_wbytes, ref_abytes;
  logic [127:0] ref_ww [4][2];
  logic [255:0] ref_aw [4];
  logic [7:0] ref_ws [4][20], ref_as [4][36];
  longint unsigned checked_cycles = 0;
  longint unsigned clear_cycles = 0;
  qbs_weight_profile_e last_weight_profile;
  qbs_activation_profile_e last_activation_profile;

  qbs_block_adapter_area_reference #(.ActivationContextBase(ActivationContextBase),
                                     .NativeView(NativeView)) i_reference (
    .weight_write_ready_o(ref_wr), .activation_write_ready_o(ref_ar),
    .weight_complete_o(ref_wc), .activation_complete_o(ref_ac),
    .all_weight_complete_o(ref_awc), .all_activation_complete_o(ref_aac),
    .accepted_weight_bytes_o(ref_wbytes), .accepted_activation_bytes_o(ref_abytes),
    .weight_window_o(ref_ww), .activation_window_o(ref_aw),
    .weight_side_o(ref_ws), .activation_side_o(ref_as),
    .weight_block_o(), .activation_block_o(), .*
  );

  always @(posedge clk_i) begin
    #1ps;
    if (rst_ni) begin
      assert ({weight_write_ready_o, activation_write_ready_o,
               accepted_weight_bytes_o, accepted_activation_bytes_o} ===
              {ref_wr, ref_ar, ref_wbytes, ref_abytes})
        else $fatal(1, "QBS adapter handshake/counter mismatch base=%0d cycle=%0d",
                    ActivationContextBase, checked_cycles);
      // INIT installs the next profile before the synchronous clear. The
      // engine cannot consume completion in this cycle; old bytes belong to
      // the previous profile. Handshakes and byte counters remain checked.
      if (checked_cycles != 0) begin
        if (weight_profile_i != last_weight_profile)
          assert (clear_weight_i) else $fatal(1, "weight profile changed without clear");
        if (activation_profile_i != last_activation_profile)
          assert (clear_activation_i) else $fatal(1, "activation profile changed without clear");
      end
      if (!clear_weight_i)
        assert ({weight_complete_o, all_weight_complete_o} === {ref_wc, ref_awc})
          else $fatal(1, "QBS weight completion mismatch base=%0d cycle=%0d", ActivationContextBase, checked_cycles);
      if (!clear_activation_i)
        assert ({activation_complete_o, all_activation_complete_o} === {ref_ac, ref_aac})
          else $fatal(1, "QBS activation completion mismatch base=%0d cycle=%0d", ActivationContextBase, checked_cycles);
      if (clear_weight_i || clear_activation_i) clear_cycles++;
      last_weight_profile = weight_profile_i;
      last_activation_profile = activation_profile_i;
      if (weight_read_i) begin
        foreach (ref_ww[row, plane])
          assert (weight_window_o[row][plane] === ref_ww[row][plane])
            else $fatal(1, "QBS adapter weight window mismatch");
        foreach (ref_ws[row, b])
          assert (weight_side_o[row][b] === ref_ws[row][b])
            else $fatal(1, "QBS adapter weight side mismatch");
      end
      if (activation_read_i) begin
        foreach (ref_aw[ctx])
          assert (activation_window_o[ctx] === ref_aw[ctx])
            else $fatal(1, "QBS adapter activation window mismatch");
        foreach (ref_as[ctx, b])
          assert (activation_side_o[ctx][b] === ref_as[ctx][b])
            else $fatal(1, "QBS adapter activation side mismatch");
      end
      checked_cycles++;
    end
  end
  final $display("QBS area adapter equivalence base=%0d cycles=%0d clear_cycles=%0d",
                 ActivationContextBase, checked_cycles, clear_cycles);
endmodule

bind qbs_block_adapter qbs_adapter_area_checker #(
  .ActivationContextBase(ActivationContextBase), .NativeView(NativeView)
) i_area_adapter_check (.*);
