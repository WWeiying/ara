// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// One explicitly managed activation context. Adjacent 128-bit rows reside in
// different banks, allowing compact blocks to cross rows at one beat/cycle.
// ExtendedShapes is opt-in until descriptor/runtime admission is integrated.
module qbs_activation_context import qbs_pkg::*; #(
  parameter bit ExtendedShapes = 1'b0
) (
  input  logic                    clk_i,
  input  logic                    rst_ni,

  input  logic                    fill_begin_i,
  input  logic [3:0]              fill_context_id_i,
  input  logic [7:0]              fill_generation_i,
  input  qbs_activation_profile_e fill_profile_i,
  input  qbs_activation_layout_e  fill_layout_i,
  input  logic [(ExtendedShapes ? 4 : 3)-1:0] fill_m_i,
  input  logic [8:0]              fill_k_blocks_i,
  input  logic                    fill_write_valid_i,
  input  logic [7:0]              fill_write_k_block_i,
  input  logic [(ExtendedShapes ? 12 : 11)-1:0] fill_write_offset_i,
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
  input  logic [(ExtendedShapes ? 4 : 3)-1:0] lookup_m_i,
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
  output logic [(ExtendedShapes ? 12 : 11)-1:0] replay_offset_o,
  output logic                    replay_last_o,
  output logic                    replay_done_o,
  output logic                    replay_busy_o,

  output logic                    context_valid_o,
  output logic                    fill_in_progress_o,
  output logic                    fill_ready_to_commit_o
);

  localparam int unsigned BankCount = 2;
  localparam int unsigned BeatBytes = 16;
  localparam int unsigned MWidth = ExtendedShapes ? 4 : 3;
  localparam int unsigned OffsetWidth = ExtendedShapes ? 12 : 11;
  localparam int unsigned WordBytes = ExtendedShapes ? 2 : 4;
  localparam int unsigned WordBits = WordBytes * 8;
  localparam int unsigned WordByteShift = $clog2(WordBytes);
  localparam int unsigned BeatWords = BeatBytes / WordBytes;
  localparam int unsigned RotationWidth = $clog2(BeatWords);
  localparam int unsigned MaxBlocks = ExtendedShapes ? 32 : 16;
  // Do not grow SRAM when more shapes or block tags become legal.
  localparam int unsigned TotalBytes = 16 * QbsQ8KBlockBytes;
  localparam int unsigned MaxPayloadBytes =
      (ExtendedShapes ? 8 : 1) * QbsQ8KBlockBytes;
  localparam int unsigned PayloadWidth = $clog2(MaxPayloadBytes + 1);
  localparam int unsigned TotalRows = (TotalBytes + BeatBytes - 1) / BeatBytes;
  localparam int unsigned BankDepth = (TotalRows + BankCount - 1) / BankCount;
  localparam int unsigned BankAddrWidth = $clog2(BankDepth);
  localparam int unsigned ReplayBeats =
      (MaxPayloadBytes + BeatBytes - 1) / BeatBytes;
  localparam int unsigned ReplayBeatWidth = $clog2(ReplayBeats);
  localparam int unsigned MacroDepth = 76;
  localparam int unsigned MacroAddrWidth = $clog2(MacroDepth);

  logic context_valid_q;
  logic [3:0] context_id_q;
  logic [7:0] context_generation_q;
  qbs_activation_profile_e context_profile_q;
  qbs_activation_layout_e context_layout_q;
  logic [MWidth-1:0] context_m_q;
  logic [8:0] context_k_blocks_q;
  logic [PayloadWidth-1:0] context_payload_bytes_q, fill_payload_bytes_q;
  logic [PayloadWidth-1:0] context_payload_bytes;

  logic fill_in_progress_q;
  logic [3:0] fill_context_id_q;
  logic [7:0] fill_generation_q;
  qbs_activation_profile_e fill_profile_q;
  qbs_activation_layout_e fill_layout_q;
  logic [MWidth-1:0] fill_m_q;
  logic [8:0] fill_k_blocks_q;
  logic [MaxBlocks-1:0] fill_block_complete_q;

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
  logic [RotationWidth-1:0] replay_word_rotation_q;
  logic [15:0] replay_strb_q;
  logic [OffsetWidth-1:0] replay_offset_q;
  logic replay_last_q;
  logic replay_issue;
  logic replay_start_fire;
  logic replay_data_fire;

  function automatic logic [PayloadWidth-1:0] payload_bytes(
      input qbs_activation_profile_e profile,
      input qbs_activation_layout_e layout);
    logic [PayloadWidth-1:0] bytes_per_row;
    if (!ExtendedShapes) return PayloadWidth'(QbsQ8KBlockBytes);
    bytes_per_row = profile == QBS_ACTIVATION_PROFILE_Q8_0
        ? PayloadWidth'(QbsQ8_0BlockBytes) : PayloadWidth'(QbsQ8KBlockBytes);
    case (layout)
      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED: return bytes_per_row << 2;
      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED: return bytes_per_row << 3;
      default: return bytes_per_row;
    endcase
  endfunction

  // Constant multipliers and layout shifts avoid a variable block-size multiply
  // on the SRAM address path. Thirteen bits cover every admitted byte address.
  function automatic logic [12:0] block_byte_offset(
      input logic [7:0] block_index,
      input qbs_activation_profile_e profile,
      input qbs_activation_layout_e layout);
    logic [12:0] offset;
    offset = ExtendedShapes && profile == QBS_ACTIVATION_PROFILE_Q8_0
        ? 13'(block_index) * 13'(QbsQ8_0BlockBytes)
        : 13'(block_index) * 13'(QbsQ8KBlockBytes);
    if (ExtendedShapes) begin
      case (layout)
        QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED: offset = offset << 2;
        QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED: offset = offset << 3;
        default: ;
      endcase
    end
    return offset;
  endfunction

  assign context_payload_bytes = ExtendedShapes ? context_payload_bytes_q :
      PayloadWidth'(QbsQ8KBlockBytes);

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
         block < MaxBlocks; block++) begin
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
      global_word_base = (unsigned'(block_byte_offset(fill_write_k_block_i,
          fill_profile_q, fill_layout_q)) + unsigned'(fill_write_offset_i)) >> WordByteShift;
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
          bank_wdata[bank][word_in_row * WordBits +: WordBits] =
              fill_write_data_i[word_lane * WordBits +: WordBits];
          bank_be[bank][word_in_row * WordBytes +: WordBytes] =
              fill_write_strb_i[word_lane * WordBytes +: WordBytes];
        end
      end
    end else if (replay_issue) begin
      replay_word_offset = unsigned'(replay_issue_beat_q) * BeatWords;
      replay_valid_words = unsigned'(context_payload_bytes) / WordBytes - replay_word_offset;
      if (replay_valid_words > BeatWords) replay_valid_words = BeatWords;
      global_word_base = (unsigned'(block_byte_offset(replay_k_block_q,
          context_profile_q, context_layout_q)) >> WordByteShift) + replay_word_offset;
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
    for (int unsigned slot = 0; slot < BeatWords; slot++) begin
      source_word = unsigned'(replay_word_rotation_q) + slot;
      replay_data_o[slot * WordBits +: WordBits] = source_word < BeatWords
          ? low_row[source_word * WordBits +: WordBits]
          : high_row[(source_word - BeatWords) * WordBits +: WordBits];
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
      context_payload_bytes_q <= '0;
      fill_payload_bytes_q <= '0;
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
        fill_payload_bytes_q <= payload_bytes(fill_profile_i, fill_layout_i);
        fill_block_complete_q <= '0;
      end

      if (fill_block_complete_i && fill_in_progress_q &&
          unsigned'(fill_complete_k_block_i) <
              MaxBlocks)
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
        context_payload_bytes_q <= fill_payload_bytes_q;
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
              unsigned'(block_byte_offset(replay_k_block_q,
                  context_profile_q, context_layout_q)) +
              unsigned'(replay_issue_beat_q) * BeatBytes;
          automatic int unsigned byte_offset =
              unsigned'(replay_issue_beat_q) * BeatBytes;
          replay_data_valid_q <= 1'b1;
          replay_low_bank_q <= global_byte[4];
          replay_word_rotation_q <= RotationWidth'(global_byte >> WordByteShift);
          replay_offset_q <= OffsetWidth'(byte_offset);
          replay_last_q <= byte_offset + BeatBytes >= unsigned'(context_payload_bytes);
          for (int byte_lane = 0; byte_lane < BeatBytes; byte_lane++)
            replay_strb_q[byte_lane] <= byte_offset + byte_lane < unsigned'(context_payload_bytes);
          if (byte_offset + BeatBytes >= unsigned'(context_payload_bytes))
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
        assert (!replay_active_q && !fill_in_progress_q);
        assert (fill_context_id_i == 0 && fill_k_blocks_i inside {[1:MaxBlocks]});
        if (ExtendedShapes) begin
          assert (fill_profile_i inside {QBS_ACTIVATION_PROFILE_Q8_K,
                                        QBS_ACTIVATION_PROFILE_Q8_0});
          assert ((fill_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR && fill_m_i == 1) ||
                  (fill_layout_i == QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED && fill_m_i == 4) ||
                  (fill_layout_i == QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED &&
                   fill_m_i inside {[5:8]}));
          assert (unsigned'(payload_bytes(fill_profile_i, fill_layout_i)) *
                  unsigned'(fill_k_blocks_i) <= TotalBytes);
        end else begin
          assert (fill_profile_i == QBS_ACTIVATION_PROFILE_Q8_K &&
                  fill_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR && fill_m_i == 1);
        end
      end
      if (fill_write_valid_i) begin
        assert (fill_in_progress_q);
        assert (unsigned'(fill_write_k_block_i) <
                unsigned'(fill_k_blocks_q));
        assert ((unsigned'(fill_write_offset_i) % WordBytes) == 0);
        for (int unsigned word = 0; word < BeatWords; word++)
          assert (fill_write_strb_i[word * WordBytes +: WordBytes] inside
                  {WordBytes'('0), WordBytes'('1)});
        for (int unsigned byte_lane = 0; byte_lane < BeatBytes; byte_lane++)
          if (fill_write_strb_i[byte_lane])
            assert (unsigned'(fill_write_offset_i) + byte_lane <
                    unsigned'(fill_payload_bytes_q));
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
