// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// One explicitly managed Q8_K activation context. Even and odd 128-bit rows
// reside in separate banks, so a four-byte-aligned compact Q8_K beat can span
// two rows without reducing the one-beat-per-cycle fill or replay bandwidth.
module qbs_activation_context import qbs_pkg::*; (
  input  logic                    clk_i,
  input  logic                    rst_ni,

  input  logic                    fill_begin_i,
  input  logic [3:0]              fill_context_id_i,
  input  logic [7:0]              fill_generation_i,
  input  qbs_activation_profile_e fill_profile_i,
  input  qbs_activation_layout_e  fill_layout_i,
  input  logic [2:0]              fill_m_i,
  input  logic [8:0]              fill_k_blocks_i,
  input  logic                    fill_write_valid_i,
  input  logic [7:0]              fill_write_k_block_i,
  input  logic [10:0]             fill_write_offset_i,
  input  logic [127:0]            fill_write_data_i,
  input  logic [15:0]             fill_write_strb_i,
  input  logic                    fill_block_complete_i,
  input  logic [7:0]              fill_complete_k_block_i,
  input  logic                    fill_commit_i,
  input  logic                    fill_abort_i,

  input  logic                    lookup_valid_i,
  input  logic [3:0]              lookup_context_id_i,
  input  logic [7:0]              lookup_generation_i,
  input  qbs_activation_profile_e lookup_profile_i,
  input  qbs_activation_layout_e  lookup_layout_i,
  input  logic [2:0]              lookup_m_i,
  input  logic [8:0]              lookup_k_blocks_i,
  output logic                    lookup_match_o,
  output qbs_validation_error_e   lookup_error_o,

  input  logic                    release_i,

  input  logic                    replay_start_valid_i,
  output logic                    replay_start_ready_o,
  input  logic [7:0]              replay_k_block_i,
  output logic                    replay_data_valid_o,
  input  logic                    replay_data_ready_i,
  output logic [127:0]            replay_data_o,
  output logic [15:0]             replay_strb_o,
  output logic [10:0]             replay_offset_o,
  output logic                    replay_last_o,
  output logic                    replay_done_o,
  output logic                    replay_busy_o,

  output logic                    context_valid_o,
  output logic                    fill_in_progress_o,
  output logic                    fill_ready_to_commit_o
);

  localparam int unsigned BankCount = 2;
  localparam int unsigned BeatBytes = 16;
  localparam int unsigned WordBytes = 4;
  localparam int unsigned BeatWords = BeatBytes / WordBytes;
  localparam int unsigned BlockWords = QbsQ8KBlockBytes / WordBytes;
  localparam int unsigned TotalBytes =
      QbsActivationContextMaxKBlocks * QbsQ8KBlockBytes;
  localparam int unsigned TotalRows = (TotalBytes + BeatBytes - 1) / BeatBytes;
  localparam int unsigned BankDepth = (TotalRows + BankCount - 1) / BankCount;
  localparam int unsigned BankAddrWidth = $clog2(BankDepth);
  localparam int unsigned ReplayBeats =
      (QbsQ8KBlockBytes + BeatBytes - 1) / BeatBytes;
  localparam int unsigned ReplayBeatWidth = $clog2(ReplayBeats);
  localparam int unsigned MacroDepth = 76;
  localparam int unsigned MacroAddrWidth = $clog2(MacroDepth);

  logic context_valid_q;
  logic [3:0] context_id_q;
  logic [7:0] context_generation_q;
  qbs_activation_profile_e context_profile_q;
  qbs_activation_layout_e context_layout_q;
  logic [2:0] context_m_q;
  logic [8:0] context_k_blocks_q;

  logic fill_in_progress_q;
  logic [3:0] fill_context_id_q;
  logic [7:0] fill_generation_q;
  qbs_activation_profile_e fill_profile_q;
  qbs_activation_layout_e fill_layout_q;
  logic [2:0] fill_m_q;
  logic [8:0] fill_k_blocks_q;
  logic [QbsActivationContextMaxKBlocks-1:0] fill_block_complete_q;

  logic [BankCount-1:0] bank_req;
  logic [BankCount-1:0] bank_we;
  logic [BankAddrWidth-1:0] bank_addr [BankCount];
  logic [127:0] bank_wdata [BankCount];
  logic [15:0] bank_be [BankCount];
  logic [127:0] bank_rdata [BankCount];

  logic replay_active_q;
  logic replay_issue_done_q;
  logic [7:0] replay_k_block_q;
  logic [ReplayBeatWidth-1:0] replay_issue_beat_q;
  logic replay_data_valid_q;
  logic replay_low_bank_q;
  logic [1:0] replay_word_rotation_q;
  logic [15:0] replay_strb_q;
  logic [10:0] replay_offset_q;
  logic replay_last_q;
  logic replay_issue;
  logic replay_start_fire;
  logic replay_data_fire;

  assign context_valid_o = context_valid_q;
  assign fill_in_progress_o = fill_in_progress_q;
  assign replay_busy_o = replay_active_q;
  assign replay_start_ready_o = !replay_active_q && !fill_in_progress_q;
  assign replay_start_fire = replay_start_valid_i && replay_start_ready_o;
  assign replay_data_valid_o = replay_data_valid_q;
  assign replay_strb_o = replay_strb_q;
  assign replay_offset_o = replay_offset_q;
  assign replay_last_o = replay_last_q;
  assign replay_data_fire = replay_data_valid_o && replay_data_ready_i;
  assign replay_issue = replay_active_q && !replay_issue_done_q &&
      (!replay_data_valid_q || replay_data_ready_i);

  always_comb begin
    fill_ready_to_commit_o = fill_in_progress_q;
    for (int unsigned block = 0;
         block < QbsActivationContextMaxKBlocks; block++) begin
      if (block < unsigned'(fill_k_blocks_q))
        fill_ready_to_commit_o &= fill_block_complete_q[block];
    end
  end

  always_comb begin
    lookup_match_o = 1'b0;
    lookup_error_o = QBS_VALIDATION_OK;
    if (lookup_valid_i) begin
      if (!context_valid_q || lookup_context_id_i != context_id_q) begin
        lookup_error_o = QBS_VALIDATION_CONTEXT_INVALID;
      end else if (lookup_generation_i != context_generation_q) begin
        lookup_error_o = QBS_VALIDATION_CONTEXT_GENERATION;
      end else if (lookup_profile_i != context_profile_q ||
                   lookup_layout_i != context_layout_q ||
                   lookup_m_i != context_m_q ||
                   lookup_k_blocks_i != context_k_blocks_q) begin
        lookup_error_o = QBS_VALIDATION_CONTEXT_METADATA;
      end else begin
        lookup_match_o = 1'b1;
      end
    end
  end

  always_comb begin : steer_sram
    automatic int unsigned global_word_base;
    automatic int unsigned global_word;
    automatic int unsigned row;
    automatic int unsigned bank;
    automatic int unsigned bank_row;
    automatic int unsigned word_in_row;
    automatic int unsigned replay_word_offset;
    automatic int unsigned replay_valid_words;

    bank_req = '0;
    bank_we = '0;
    for (int unsigned index = 0; index < BankCount; index++) begin
      bank_addr[index] = '0;
      bank_wdata[index] = '0;
      bank_be[index] = '0;
    end

    if (fill_write_valid_i && fill_in_progress_q) begin
      global_word_base = unsigned'(fill_write_k_block_i) * BlockWords +
                         unsigned'(fill_write_offset_i[10:2]);
      for (int unsigned word_lane = 0; word_lane < BeatWords; word_lane++) begin
        if (|fill_write_strb_i[word_lane * WordBytes +: WordBytes]) begin
          global_word = global_word_base + word_lane;
          row = global_word / BeatWords;
          bank = row & (BankCount - 1);
          bank_row = row / BankCount;
          word_in_row = global_word & (BeatWords - 1);
          bank_req[bank] = 1'b1;
          bank_we[bank] = 1'b1;
          bank_addr[bank] = BankAddrWidth'(bank_row);
          bank_wdata[bank][word_in_row * 32 +: 32] =
              fill_write_data_i[word_lane * 32 +: 32];
          bank_be[bank][word_in_row * WordBytes +: WordBytes] =
              fill_write_strb_i[word_lane * WordBytes +: WordBytes];
        end
      end
    end else if (replay_issue) begin
      replay_word_offset = unsigned'(replay_issue_beat_q) * BeatWords;
      replay_valid_words = replay_issue_beat_q == ReplayBeats - 1
          ? BlockWords - replay_word_offset : BeatWords;
      global_word_base = unsigned'(replay_k_block_q) * BlockWords +
                         replay_word_offset;
      row = global_word_base / BeatWords;
      bank = row & (BankCount - 1);
      bank_row = row / BankCount;
      bank_req[bank] = 1'b1;
      bank_addr[bank] = BankAddrWidth'(bank_row);
      word_in_row = global_word_base & (BeatWords - 1);
      if (word_in_row + replay_valid_words > BeatWords) begin
        row++;
        bank = row & (BankCount - 1);
        bank_row = row / BankCount;
        bank_req[bank] = 1'b1;
        bank_addr[bank] = BankAddrWidth'(bank_row);
      end
    end
  end

`ifndef TARGET_SRAM_MC
  for (genvar bank = 0; bank < BankCount; bank++) begin : gen_context_bank
    tc_sram #(
      .NumWords  (BankDepth),
      .DataWidth (128),
      .NumPorts  (1),
      .Latency   (1)
    ) i_context_sram (
      .clk_i,
      .rst_ni,
      .req_i   (bank_req[bank]),
      .we_i    (bank_we[bank]),
      .addr_i  (bank_addr[bank]),
      .wdata_i (bank_wdata[bank]),
      .be_i    (bank_be[bank]),
      .rdata_o (bank_rdata[bank])
    );
  end
`else
  logic [255:0] macro_q [BankCount];
  logic macro_read_half_q [BankCount];

  for (genvar bank = 0; bank < BankCount; bank++) begin : gen_context_bank
    wire macro_req = bank_req[bank] && unsigned'(bank_addr[bank]) < BankDepth;
    wire [MacroAddrWidth-1:0] macro_addr = MacroAddrWidth'(bank_addr[bank] >> 1);
    wire [255:0] macro_bweb;
    // Pack two logical 128-bit rows into one physical word, without changing
    // the two-bank interface or its one-cycle synchronous read.
    for (genvar half = 0; half < 2; half++) begin : gen_half
      for (genvar byte_lane = 0; byte_lane < BeatBytes; byte_lane++) begin : gen_byte
        assign macro_bweb[half*128 + byte_lane*8 +: 8] =
            {8{!(bank_we[bank] && bank_addr[bank][0] == 1'(half) &&
                 bank_be[bank][byte_lane])}};
      end
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        macro_read_half_q[bank] <= 1'b0;
      end else if (macro_req && !bank_we[bank]) begin
        macro_read_half_q[bank] <= bank_addr[bank][0];
      end
    end

    assign bank_rdata[bank] = macro_q[bank]
        [macro_read_half_q[bank] * 128 +: 128];

      TS1N28HPCPUHDSVTB76X256M1SWBSO i_context_sram (
        .SLP   (1'b0),
        .SD    (1'b0),
        .CLK   (clk_i),
        .CEB   (!macro_req),
        .WEB   (!bank_we[bank]),
        .CEBM  (1'b1),
        .WEBM  (1'b1),
        .A     (macro_addr),
        .D     ({2{bank_wdata[bank]}}),
        .BWEB  (macro_bweb),
        .AM    ('0),
        .DM    ('0),
        .BWEBM ('1),
        .BIST  (1'b0),
        .RTSEL (2'b01),
        .WTSEL (2'b00),
        .Q     (macro_q[bank])
      );
  end
`endif

  always_comb begin : reorder_replay_words
    automatic logic [127:0] low_row;
    automatic logic [127:0] high_row;
    automatic int unsigned source_word;
    low_row = bank_rdata[replay_low_bank_q];
    high_row = bank_rdata[!replay_low_bank_q];
    replay_data_o = '0;
    for (int unsigned slot = 0; slot < 4; slot++) begin
      source_word = unsigned'(replay_word_rotation_q) + slot;
      replay_data_o[slot * 32 +: 32] = source_word < 4
          ? low_row[source_word * 32 +: 32]
          : high_row[(source_word - 4) * 32 +: 32];
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      context_valid_q <= 1'b0;
      context_id_q <= '0;
      context_generation_q <= '0;
      context_profile_q <= QBS_ACTIVATION_PROFILE_INVALID;
      context_layout_q <= QBS_ACTIVATION_LAYOUT_INVALID;
      context_m_q <= '0;
      context_k_blocks_q <= '0;
      fill_in_progress_q <= 1'b0;
      fill_context_id_q <= '0;
      fill_generation_q <= '0;
      fill_profile_q <= QBS_ACTIVATION_PROFILE_INVALID;
      fill_layout_q <= QBS_ACTIVATION_LAYOUT_INVALID;
      fill_m_q <= '0;
      fill_k_blocks_q <= '0;
      fill_block_complete_q <= '0;
      replay_active_q <= 1'b0;
      replay_issue_done_q <= 1'b0;
      replay_k_block_q <= '0;
      replay_issue_beat_q <= '0;
      replay_data_valid_q <= 1'b0;
      replay_low_bank_q <= 1'b0;
      replay_word_rotation_q <= '0;
      replay_strb_q <= '0;
      replay_offset_q <= '0;
      replay_last_q <= 1'b0;
      replay_done_o <= 1'b0;
    end else begin
      replay_done_o <= 1'b0;

      if (fill_begin_i) begin
        context_valid_q <= 1'b0;
        fill_in_progress_q <= 1'b1;
        fill_context_id_q <= fill_context_id_i;
        fill_generation_q <= fill_generation_i;
        fill_profile_q <= fill_profile_i;
        fill_layout_q <= fill_layout_i;
        fill_m_q <= fill_m_i;
        fill_k_blocks_q <= fill_k_blocks_i;
        fill_block_complete_q <= '0;
      end

      if (fill_block_complete_i && fill_in_progress_q &&
          unsigned'(fill_complete_k_block_i) <
              QbsActivationContextMaxKBlocks)
        fill_block_complete_q[fill_complete_k_block_i] <= 1'b1;

      if (fill_abort_i)
        fill_in_progress_q <= 1'b0;

      if (fill_commit_i) begin
        context_valid_q <= 1'b1;
        context_id_q <= fill_context_id_q;
        context_generation_q <= fill_generation_q;
        context_profile_q <= fill_profile_q;
        context_layout_q <= fill_layout_q;
        context_m_q <= fill_m_q;
        context_k_blocks_q <= fill_k_blocks_q;
        fill_in_progress_q <= 1'b0;
      end

      if (release_i)
        context_valid_q <= 1'b0;

      if (replay_start_fire) begin
        replay_active_q <= 1'b1;
        replay_issue_done_q <= 1'b0;
        replay_k_block_q <= replay_k_block_i;
        replay_issue_beat_q <= '0;
        replay_data_valid_q <= 1'b0;
      end else begin
        if (replay_issue) begin
          automatic int unsigned global_byte =
              unsigned'(replay_k_block_q) * QbsQ8KBlockBytes +
              unsigned'(replay_issue_beat_q) * BeatBytes;
          automatic int unsigned byte_offset =
              unsigned'(replay_issue_beat_q) * BeatBytes;
          replay_data_valid_q <= 1'b1;
          replay_low_bank_q <= global_byte[4];
          replay_word_rotation_q <= global_byte[3:2];
          replay_offset_q <= 11'(byte_offset);
          replay_last_q <= replay_issue_beat_q == ReplayBeats - 1;
          replay_strb_q <= replay_issue_beat_q == ReplayBeats - 1
              ? 16'h000f : 16'hffff;
          if (replay_issue_beat_q == ReplayBeats - 1)
            replay_issue_done_q <= 1'b1;
          else
            replay_issue_beat_q <= replay_issue_beat_q + 1'b1;
        end else if (replay_data_fire) begin
          replay_data_valid_q <= 1'b0;
        end

        if (replay_data_fire && replay_last_q) begin
          replay_active_q <= 1'b0;
          replay_issue_done_q <= 1'b0;
          replay_done_o <= 1'b1;
        end
      end
    end
  end

`ifndef SYNTHESIS
  initial begin
    assert (QbsActivationContextCount == 1);
    assert (QbsActivationContextMaxM == 1);
    assert (QbsActivationContextMaxKBlocks == 16);
    assert (QbsQ8KBlockBytes % 4 == 0);
    assert ((BankCount & (BankCount - 1)) == 0);
    assert (BankDepth <= 2 * MacroDepth);
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni) begin
      assert (!(fill_write_valid_i && replay_issue))
        else $fatal(1, "QBS context SRAM cannot fill and replay together");
      if (fill_begin_i) begin
        assert (fill_context_id_i == 0 &&
                fill_profile_i == QBS_ACTIVATION_PROFILE_Q8_K &&
                fill_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR &&
                fill_m_i == 1 && fill_k_blocks_i inside {
                    [1:QbsActivationContextMaxKBlocks]});
      end
      if (fill_write_valid_i) begin
        assert (fill_in_progress_q);
        assert (unsigned'(fill_write_k_block_i) <
                unsigned'(fill_k_blocks_q));
        assert (fill_write_offset_i[1:0] == 0);
        for (int unsigned word = 0; word < 4; word++)
          assert (fill_write_strb_i[word * 4 +: 4] inside {4'h0, 4'hf});
      end
      if (fill_commit_i)
        assert (fill_ready_to_commit_o)
          else $fatal(1, "QBS committed an incomplete activation context");
      if (replay_start_valid_i && replay_start_ready_o) begin
        assert (context_valid_q);
        assert (unsigned'(replay_k_block_i) <
                unsigned'(context_k_blocks_q));
      end
      if (release_i)
        assert (context_valid_q);
    end
  end
`endif

endmodule : qbs_activation_context
