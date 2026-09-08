// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_sram_adapter_checker import qbs_pkg::*; #(
  parameter int unsigned ActivationContextBase = 0
) (
  input logic clk_i, rst_ni, clear_weight_i, clear_activation_i,
  input logic weight_pending_q_valid, activation_pending_q_valid,
  input logic weight_read_i, activation_read_i,
  input logic [7:0] read_k_i,
  input qbs_weight_profile_e weight_profile_i,
  input qbs_activation_profile_e activation_profile_i,
  input logic [2:0] weight_row_count_i,
  input qbs_activation_layout_e activation_layout_i,
  input logic [3:0] m_i,
  input logic weight_write_valid_i, weight_write_group_i,
  input logic weight_write_ready_o, activation_write_ready_o,
  input logic [31:0] weight_consumed, activation_consumed,
  input logic [31:0] weight_remaining, activation_remaining,
  input logic [9:0] pending_weight_offset,
  input logic [11:0] pending_activation_offset,
  input logic [1:0] weight_write_row_i,
  input logic [9:0] weight_write_offset_i,
  input logic [127:0] weight_write_data_i,
  input logic [15:0] weight_write_strb_i,
  input logic activation_write_valid_i,
  input logic [1:0] activation_write_context_i,
  input logic [11:0] activation_write_offset_i,
  input logic [127:0] activation_write_data_i,
  input logic [15:0] activation_write_strb_i,
  input logic [7:0] weight_block_o [4][QbsMaxWeightBlockBytes],
  input logic [7:0] activation_block_o [4][QbsMaxActivationBlockBytes],
  input logic weight_byte_valid_q [4][QbsMaxWeightBlockBytes],
  input logic activation_byte_valid_q [4][QbsMaxActivationBlockBytes],
  input logic [3:0] weight_complete_o, activation_complete_o,
  input logic all_weight_complete_o, all_activation_complete_o,
  input logic [31:0] accepted_weight_bytes_o, accepted_activation_bytes_o
);
  logic [7:0] ref_weight [4][QbsMaxWeightBlockBytes];
  logic [7:0] ref_activation [4][QbsMaxActivationBlockBytes];
  logic [3:0] ref_weight_complete, ref_activation_complete;
  logic ref_all_weight, ref_all_activation;
  logic [31:0] ref_weight_bytes, ref_activation_bytes;

  qbs_block_adapter_reference #(.ActivationContextBase(ActivationContextBase))
      i_reference (
    .weight_block_o(ref_weight), .activation_block_o(ref_activation),
    .weight_complete_o(ref_weight_complete),
    .activation_complete_o(ref_activation_complete),
    .all_weight_complete_o(ref_all_weight),
    .all_activation_complete_o(ref_all_activation),
    .accepted_weight_bytes_o(ref_weight_bytes),
    .accepted_activation_bytes_o(ref_activation_bytes),
    .weight_write_valid_i(weight_write_valid_i && weight_write_ready_o),
    .activation_write_valid_i(activation_write_valid_i && activation_write_ready_o), .*
  );

  logic [7:0] k_q;
  logic wr_q, ar_q;
  logic signed [7:0] wq [2][4][8], aq [2][4][8], scale [2][16];
  logic [7:0] minimum [2][16];
  logic signed [15:0] aux [2][16];
  logic [15:0] wd [2][4], wmin [2][4];
  logic [31:0] ad [2][4];
  int cycles, reads, wpend, apend, dual;
  int wblocked, ablocked, wfires, afires, wjoin, ajoin, trace_count;
  bit trace_active;
  int trace_file;
  initial begin
    trace_file = $fopen($sformatf("sram_adapter_%0d.csv", ActivationContextBase), "w");
    $fdisplay(trace_file, "cycle,wvalid,wready,avalid,aready,woff,aoff,wpend,apend,pending_woff,pending_aoff,wcommit_old,wcommit_new,acommit_old,acommit_new,wremain_old,wremain_new,aremain_old,aremain_new,wread,aread,k,wbytes,abytes");
  end
  for (genvar i = 0; i < 2; i++) begin : gen_decode
    qbs_profile_decoder i_decoder (
      .profile_i(weight_profile_i), .activation_profile_i,
      .m_i(m_i > 4 ? 3'd4 : 3'(m_i)), .row_count_i(3'd4), .k_base_i(k_q),
      .weight_block_i(i == 0 ? weight_block_o : ref_weight),
      .activation_block_i(i == 0 ? activation_block_o : ref_activation),
      .k_per_context_o(), .group_index_o(), .group_end_o(), .stream_valid_o(),
      .weight_quant_o(wq[i]), .activation_quant_o(aq[i]),
      .group_scale_o(scale[i]), .group_min_o(minimum[i]), .group_aux_o(aux[i]),
      .weight_d_o(wd[i]), .weight_dmin_o(wmin[i]), .activation_d_o(ad[i])
    );
  end
  always @(posedge clk_i) begin
    wr_q <= rst_ni && weight_read_i;
    ar_q <= rst_ni && activation_read_i;
    k_q <= read_k_i;
    if (rst_ni) begin
      if (weight_pending_q_valid) wpend++;
      if (activation_pending_q_valid) apend++;
      if (weight_write_valid_i && weight_write_ready_o) wfires++;
      if (activation_write_valid_i && activation_write_ready_o) afires++;
      if (weight_write_valid_i && !weight_write_ready_o && !clear_weight_i) wblocked++;
      if (activation_write_valid_i && !activation_write_ready_o && !clear_activation_i) ablocked++;
      if ((|weight_consumed[15:0]) && (|weight_consumed[31:16])) wjoin++;
      if ((|activation_consumed[15:0]) && (|activation_consumed[31:16])) ajoin++;
      if (weight_write_valid_i && weight_write_ready_o &&
          activation_write_valid_i && activation_write_ready_o) dual++;
      if (|weight_consumed || |activation_consumed) trace_active = 1;
      if (trace_active && trace_count < 128) begin
        $fdisplay(trace_file, "%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%04h,%04h,%04h,%04h,%04h,%04h,%04h,%04h,%0d,%0d,%0d,%0d,%0d",
            cycles, weight_write_valid_i, weight_write_ready_o,
            activation_write_valid_i, activation_write_ready_o,
            weight_write_offset_i, activation_write_offset_i,
            weight_pending_q_valid, activation_pending_q_valid,
            pending_weight_offset, pending_activation_offset,
            weight_consumed[15:0], weight_consumed[31:16],
            activation_consumed[15:0], activation_consumed[31:16],
            weight_remaining[15:0], weight_remaining[31:16],
            activation_remaining[15:0], activation_remaining[31:16],
            weight_read_i, activation_read_i, read_k_i,
            accepted_weight_bytes_o, accepted_activation_bytes_o);
        trace_count++;
      end
    end
  end
  final begin
    $display("QBS SRAM checker base=%0d cycles=%0d read_windows=%0d weight_pending=%0d activation_pending=%0d simultaneous=%0d",
             ActivationContextBase, cycles, reads, wpend, apend, dual);
    $display("QBS SRAM writes base=%0d wfire=%0d afire=%0d wblocked=%0d ablocked=%0d wold_new_commit=%0d aold_new_commit=%0d",
             ActivationContextBase, wfires, afires, wblocked, ablocked, wjoin, ajoin);
    $fclose(trace_file);
  end
  always @(negedge clk_i) begin
    #1ps;
    if (rst_ni) begin
      if (!weight_pending_q_valid) begin
        assert ({weight_complete_o, all_weight_complete_o, accepted_weight_bytes_o} ===
            {ref_weight_complete, ref_all_weight, ref_weight_bytes} &&
            weight_byte_valid_q === i_reference.weight_byte_valid_q)
          else $fatal(1, "SRAM weight control mismatch base=%0d t=%0t", ActivationContextBase, $time);
      end
      if (!activation_pending_q_valid) begin
        assert ({activation_complete_o, all_activation_complete_o, accepted_activation_bytes_o} ===
            {ref_activation_complete, ref_all_activation, ref_activation_bytes} &&
            activation_byte_valid_q === i_reference.activation_byte_valid_q)
          else $fatal(1, "SRAM activation control mismatch base=%0d t=%0t", ActivationContextBase, $time);
      end
      if (wr_q) begin
        assert (all_weight_complete_o);
        for (int r = 0; r < weight_row_count_i; r++)
          assert (wq[0][r] === wq[1][r] &&
                  {wd[0][r], wmin[0][r], scale[0][4*r], minimum[0][4*r]} ===
                  {wd[1][r], wmin[1][r], scale[1][4*r], minimum[1][4*r]})
            else $fatal(1, "SRAM weight window mismatch base=%0d k=%0d row=%0d", ActivationContextBase, k_q, r);
      end
      if (ar_q) begin
        assert (all_activation_complete_o);
        for (int c = 0; c < (m_i > 4 ? 4 : m_i); c++)
          assert (aq[0][c] === aq[1][c] &&
                  {ad[0][c], aux[0][c]} === {ad[1][c], aux[1][c]})
            else $fatal(1, "SRAM activation window mismatch base=%0d k=%0d ctx=%0d q=%p ref=%p d=%h/%h aux=%h/%h",
                ActivationContextBase, k_q, c, aq[0][c], aq[1][c],
                ad[0][c], ad[1][c], aux[0][c], aux[1][c]);
      end
      cycles++;
      if (wr_q || ar_q) reads++;
    end
  end
endmodule

bind qbs_block_adapter qbs_sram_adapter_checker #(
    .ActivationContextBase(ActivationContextBase)) i_adapter_equivalence (
    .pending_weight_offset(weight_pending_q.offset),
    .pending_activation_offset(activation_pending_q.offset), .*);

module qbs_sram_write_checker (
  input logic clk_i, rst_ni, req_i, we_i,
  input logic [2:0] addr_i,
  input logic [255:0] wdata_i,
  input logic [31:0] be_i
);
  int accesses;
  always @(posedge clk_i) if (rst_ni && req_i) begin
    assert (!$isunknown({we_i, addr_i}));
    if (we_i) begin
      assert (!$isunknown(be_i));
      for (int b = 0; b < 32; b++) if (be_i[b])
        assert (!$isunknown(wdata_i[8*b +: 8]))
          else $fatal(1, "QBS SRAM unknown write byte=%0d addr=%0d", b, addr_i);
    end
    if ($test$plusargs("QBS_SRAM_BUS_TRACE") && accesses < 24)
      $display("QBS SRAM bus %m we=%b addr=%d be=%h data=%h", we_i, addr_i, be_i, wdata_i);
    accesses++;
  end
endmodule

bind qbs_payload_sram qbs_sram_write_checker i_write_checker (.*);
