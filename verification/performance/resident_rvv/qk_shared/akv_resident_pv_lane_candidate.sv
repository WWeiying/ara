// SPDX-License-Identifier: Apache-2.0
// Isolated, uncompiled replacement draft; compile instead of the production file.
// QK: seed +0, then one F16 query pair and ceil(local_n/4) raw K words per D.
// Caller must exclude inactive lanes and use the per-packet active-lane mask.
// FP32 masks below are semantic bits [1:0]; VMFPU expansion is a later change.
module akv_resident_pv_lane (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic abort_i,
  input  logic cmd_valid_i,
  output logic cmd_ready_o,
  input  logic [5:0] cmd_elements_i,
  input  logic cmd_two_heads_i,
  input  logic [6:0] cmd_tokens_i,
  input  logic [2:0] cmd_rm_i,
  input  logic seed_valid_i,
  output logic seed_ready_o,
  input  logic [63:0] seed_data_i,
  input  logic stream_valid_i,
  output logic stream_ready_o,
  input  logic stream_is_value_i,
  input  logic [63:0] stream_data_i,
  output logic fpu_valid_o,
  input  logic fpu_ready_i,
  output logic [2:0][63:0] fpu_operands_o,
  output logic [3:0] fpu_tag_o,
  output logic [3:0] fpu_mask_o,
  output logic [2:0] fpu_rm_o,
  input  logic fpu_result_valid_i,
  output logic fpu_result_ready_o,
  input  logic [63:0] fpu_result_i,
  input  logic [3:0] fpu_result_tag_i,
  input  logic [4:0] fpu_result_flags_i,
  output logic result_valid_o,
  input  logic result_ready_i,
  output logic [63:0] result_data_o,
  output logic [3:0] result_slot_o,
  output logic [7:0] result_be_o,
  output logic done_valid_o,
  input  logic done_ready_i,
  output logic done_error_o,
  output logic [4:0] done_flags_o,
  output logic busy_o,
  input  logic cmd_qk_i = 1'b0,
  input  logic [7:0] cmd_dimensions_i = 8'd0,
  output logic fpu_fp32_o
);
  typedef enum logic [2:0] {Idle, Seed, Run, Drain, Commit, Done, FaultDrain} state_t;
  state_t state_q;
  logic [3:0] words_q, raw_words_q;
  logic [3:0] tail_mask_q;
  logic two_heads_q, qk_q;
  // The same loop counts tokens in PV and ordered dimensions in QK, including D128.
  logic [7:0] tokens_q;
  logic [2:0] rm_q;
  logic [63:0] accum_q [16];
  logic [15:0] pending_q;
  logic [31:0] coeff_q;
  logic [4:0] flags_q;
  logic error_q, commit_started_q;

  logic [2:0] seed_word_q, word_q, commit_word_q;
  logic seed_head_q, head_q, commit_head_q;
  logic [7:0] token_q;
  logic expect_coeff_q;
  logic [64:0] fifo_q [2];
  logic fifo_read_q, fifo_write_q;
  logic [1:0] fifo_count_q;
  logic [3:0] rx_word_q;
  logic [7:0] rx_token_q;
  logic push, pop, bad_packet, coefficient_fire;
  logic fpu_fire, return_fire, seed_fire, result_fire;
  logic [3:0] slot, seed_slot, commit_slot, returned_mask, commit_mask;
  logic [15:0] query_half, key_low_half, key_high_half;
  logic [3:0] query_lzc, key_low_lzc, key_high_lzc;
  logic [31:0] query_single, key_low_single, key_high_single;
  logic last_head, last_word, raw_word_done;

  function automatic logic [3:0] word_mask(
    input logic [2:0] word_index,
    input logic [3:0] words,
    input logic [3:0] tail_mask,
    input logic fp32
  );
    return ({1'b0, word_index} == words - 1'b1) ? tail_mask :
           (fp32 ? 4'b0011 : 4'b1111);
  endfunction

  function automatic logic [31:0] widen_preserving_nan(
    input logic [15:0] bits,
    input logic [3:0] leading_zeros
  );
    ara_pkg::fp16_t half_value;
    ara_pkg::fp32_t single_value;
    half_value = ara_pkg::fp16_t'(bits);
    single_value = ara_pkg::fp32_from_fp16(half_value, {1'b0, leading_zeros});
    // Internal re-encoding, not a visible conversion: let the FMA observe sNaN.
    if (half_value.e == 5'h1f && half_value.m != '0)
      single_value.m = {half_value.m, 13'b0};
    return single_value;
  endfunction

  assign query_half = head_q ? coeff_q[31:16] : coeff_q[15:0];
  // Native EW16 raw order: consume halfwords {0,2}, then {1,3}.
  assign key_low_half = word_q[0] ? fifo_q[fifo_read_q][31:16] : fifo_q[fifo_read_q][15:0];
  assign key_high_half = word_q[0] ? fifo_q[fifo_read_q][63:48] : fifo_q[fifo_read_q][47:32];
  lzc #(.WIDTH(10), .MODE(1)) i_query_lzc (
    .in_i(query_half[9:0]), .cnt_o(query_lzc), .empty_o()
  );
  lzc #(.WIDTH(10), .MODE(1)) i_key_low_lzc (
    .in_i(key_low_half[9:0]), .cnt_o(key_low_lzc), .empty_o()
  );
  lzc #(.WIDTH(10), .MODE(1)) i_key_high_lzc (
    .in_i(key_high_half[9:0]), .cnt_o(key_high_lzc), .empty_o()
  );
  assign query_single = widen_preserving_nan(query_half, query_lzc);
  assign key_low_single = widen_preserving_nan(key_low_half, key_low_lzc);
  assign key_high_single = widen_preserving_nan(key_high_half, key_high_lzc);

  assign slot = {head_q, word_q};
  assign seed_slot = {seed_head_q, seed_word_q};
  assign commit_slot = {commit_head_q, commit_word_q};
  assign returned_mask = word_mask(fpu_result_tag_i[2:0], words_q, tail_mask_q, qk_q);
  assign commit_mask = word_mask(commit_word_q, words_q, tail_mask_q, qk_q);
  assign cmd_ready_o = state_q == Idle && !abort_i;
  assign busy_o = state_q != Idle;
  assign seed_ready_o = state_q == Seed && !abort_i;
  assign seed_fire = seed_valid_i && seed_ready_o;
  // Keep the original registered FIFO boundary; no FPU-ready path to the source.
  assign stream_ready_o = state_q == Run && !abort_i && rx_token_q < tokens_q && fifo_count_q < 2;
  assign push = stream_valid_i && stream_ready_o;
  assign bad_packet = state_q == Run && fifo_count_q != 0 &&
                      fifo_q[fifo_read_q][64] == expect_coeff_q;
  assign coefficient_fire = state_q == Run && !abort_i && fifo_count_q != 0 &&
                            expect_coeff_q && !bad_packet;
  assign fpu_valid_o = state_q == Run && !abort_i && fifo_count_q != 0 &&
                       !expect_coeff_q && !bad_packet && !pending_q[slot];
  assign fpu_fire = fpu_valid_o && fpu_ready_i;
  assign last_head = !two_heads_q || head_q;
  assign last_word = {1'b0, word_q} == words_q - 1'b1;
  // A QK raw word serves two FP32 words, except a partial final packet.
  assign raw_word_done = !qk_q || word_q[0] || last_word;
  assign pop = coefficient_fire || (fpu_fire && last_head && raw_word_done);
  assign fpu_operands_o[0] = qk_q ? {2{query_single}} :
                            {4{head_q ? coeff_q[31:16] : coeff_q[15:0]}};
  assign fpu_operands_o[1] = qk_q ? {key_high_single, key_low_single} : fifo_q[fifo_read_q][63:0];
  assign fpu_operands_o[2] = accum_q[slot];
  assign fpu_tag_o = slot;
  assign fpu_mask_o = word_mask(word_q, words_q, tail_mask_q, qk_q);
  assign fpu_rm_o = rm_q;
  assign fpu_fp32_o = qk_q;
  assign fpu_result_ready_o = state_q == Run || state_q == Drain || state_q == FaultDrain;
  assign return_fire = fpu_result_valid_i && fpu_result_ready_o;
  assign result_valid_o = state_q == Commit && !abort_i;
  assign result_slot_o = commit_slot;
  assign result_data_o = accum_q[commit_slot];
  assign result_be_o = qk_q ? {{4{commit_mask[1]}}, {4{commit_mask[0]}}} :
                      {{2{commit_mask[3]}}, {2{commit_mask[2]}},
                       {2{commit_mask[1]}}, {2{commit_mask[0]}}};
  assign result_fire = result_valid_o && result_ready_i;
  assign done_valid_o = state_q == Done;
  assign done_error_o = done_valid_o && error_q;
  assign done_flags_o = done_valid_o ? flags_q : '0;

  // One shared accumulator write path; every active QK slot is seeded with +0.
  always_ff @(posedge clk_i) begin
    if (seed_fire) accum_q[seed_slot] <= qk_q ? 64'b0 : seed_data_i;
    if (return_fire) begin
      if (qk_q) begin
        for (int i = 0; i < 2; i++)
          if (returned_mask[i]) accum_q[fpu_result_tag_i][32*i+:32] <= fpu_result_i[32*i+:32];
      end else begin
        for (int i = 0; i < 4; i++)
          if (returned_mask[i]) accum_q[fpu_result_tag_i][16*i+:16] <= fpu_result_i[16*i+:16];
      end
    end
    if (push) fifo_q[fifo_write_q] <= {stream_is_value_i, stream_data_i};
    if (coefficient_fire) coeff_q <= fifo_q[fifo_read_q][31:0];
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= Idle;
      words_q <= '0;
      raw_words_q <= '0;
      tail_mask_q <= '0;
      two_heads_q <= 1'b0;
      qk_q <= 1'b0;
      tokens_q <= '0;
      rm_q <= '0;
      pending_q <= '0;
      flags_q <= '0;
      error_q <= 1'b0;
      commit_started_q <= 1'b0;
      seed_word_q <= '0;
      seed_head_q <= 1'b0;
      word_q <= '0;
      head_q <= 1'b0;
      token_q <= '0;
      expect_coeff_q <= 1'b1;
      commit_word_q <= '0;
      commit_head_q <= 1'b0;
      fifo_read_q <= 1'b0;
      fifo_write_q <= 1'b0;
      fifo_count_q <= '0;
      rx_word_q <= '0;
      rx_token_q <= '0;
    end else begin
      if (push) begin
        fifo_write_q <= !fifo_write_q;
        if (rx_word_q == raw_words_q) begin
          rx_word_q <= '0;
          rx_token_q <= rx_token_q + 1'b1;
        end else rx_word_q <= rx_word_q + 1'b1;
      end
      if (pop) fifo_read_q <= !fifo_read_q;
      case ({push, pop})
        2'b10: fifo_count_q <= fifo_count_q + 1'b1;
        2'b01: fifo_count_q <= fifo_count_q - 1'b1;
        default: ;
      endcase
      if (fpu_fire) pending_q[slot] <= 1'b1;
      if (return_fire) begin
        pending_q[fpu_result_tag_i] <= 1'b0;
        flags_q <= flags_q | fpu_result_flags_i;
      end
      if (result_fire) commit_started_q <= 1'b1;
      case (state_q)
        Idle: if (cmd_valid_i && cmd_ready_o) begin
          words_q <= cmd_qk_i ? ((cmd_elements_i + 6'd1) >> 1) :
                               ((cmd_elements_i + 6'd3) >> 2);
          raw_words_q <= (cmd_elements_i + 6'd3) >> 2;
          if (cmd_qk_i) tail_mask_q <= cmd_elements_i[0] ? 4'b0001 : 4'b0011;
          else begin
            case (cmd_elements_i[1:0])
              2'd1: tail_mask_q <= 4'b0001;
              2'd2: tail_mask_q <= 4'b0011;
              2'd3: tail_mask_q <= 4'b0111;
              default: tail_mask_q <= 4'b1111;
            endcase
          end
          two_heads_q <= cmd_two_heads_i;
          qk_q <= cmd_qk_i;
          tokens_q <= cmd_qk_i ? cmd_dimensions_i : {1'b0, cmd_tokens_i};
          rm_q <= cmd_rm_i;
          pending_q <= '0;
          flags_q <= '0;
          commit_started_q <= 1'b0;
          seed_word_q <= '0;
          seed_head_q <= 1'b0;
          word_q <= '0;
          head_q <= 1'b0;
          token_q <= '0;
          expect_coeff_q <= 1'b1;
          commit_word_q <= '0;
          commit_head_q <= 1'b0;
          fifo_count_q <= '0;
          fifo_read_q <= 1'b0;
          fifo_write_q <= 1'b0;
          rx_word_q <= '0;
          rx_token_q <= '0;
          if (cmd_elements_i == 0 || cmd_rm_i > 4 ||
              (cmd_qk_i ? (cmd_elements_i > 16 ||
                           !(cmd_dimensions_i inside {8'd64, 8'd96, 8'd128})) :
                          (cmd_elements_i > 32 || cmd_tokens_i == 0 || cmd_tokens_i > 64))) begin
            state_q <= Done;
            error_q <= 1'b1;
          end else begin
            state_q <= Seed;
            error_q <= 1'b0;
          end
        end
        Seed: if (seed_fire) begin
          if ({1'b0, seed_word_q} == words_q - 1'b1) begin
            seed_word_q <= '0;
            if (two_heads_q && !seed_head_q) seed_head_q <= 1'b1;
            else state_q <= Run;
          end else seed_word_q <= seed_word_q + 1'b1;
        end
        Run: begin
          if (bad_packet) begin
            error_q <= 1'b1;
            state_q <= FaultDrain;
          end else if (coefficient_fire) expect_coeff_q <= 1'b0;
          else if (fpu_fire) begin
            if (two_heads_q && !head_q) head_q <= 1'b1;
            else begin
              head_q <= 1'b0;
              if ({1'b0, word_q} == words_q - 1'b1) begin
                word_q <= '0;
                expect_coeff_q <= 1'b1;
                token_q <= token_q + 1'b1;
                if (token_q == tokens_q - 1'b1) state_q <= Drain;
              end else word_q <= word_q + 1'b1;
            end
          end
        end
        Drain: if (pending_q == 0) state_q <= Commit;
        Commit: if (result_fire) begin
          if ({1'b0, commit_word_q} == words_q - 1'b1) begin
            commit_word_q <= '0;
            if (two_heads_q && !commit_head_q) commit_head_q <= 1'b1;
            else state_q <= Done;
          end else commit_word_q <= commit_word_q + 1'b1;
        end
        FaultDrain: if (pending_q == 0) state_q <= Done;
        Done: if (done_ready_i) state_q <= Idle;
        default: state_q <= Idle;
      endcase
      if (abort_i && (state_q == Seed || state_q == Run || state_q == Drain ||
                      (state_q == Commit && !commit_started_q))) begin
        error_q <= 1'b1;
        state_q <= FaultDrain;
      end
    end
  end

  // synthesis translate_off
  always_ff @(posedge clk_i) if (rst_ni) begin
    assert (!(abort_i && state_q == Commit && commit_started_q))
      else $fatal(1, "Resident candidate abort after commit authorization");
    assert (fifo_count_q <= 2) else $fatal(1, "Resident candidate ingress overflow");
    if (qk_q && seed_fire)
      assert (seed_data_i == 64'b0) else $fatal(1, "QK seed must be positive FP32 zero");
    if (qk_q && fpu_valid_o)
      assert (fpu_mask_o[3:2] == 0 && fpu_mask_o[1:0] != 0)
        else $fatal(1, "QK semantic FP32 element mask");
    if (return_fire) begin
      assert (pending_q[fpu_result_tag_i]) else $fatal(1, "Unowned resident FPU return");
      assert ((!fpu_result_tag_i[3] || two_heads_q) &&
              {1'b0, fpu_result_tag_i[2:0]} < words_q)
        else $fatal(1, "Resident FPU returned inactive slot");
    end
    if (state_q == Commit || state_q == Done)
      assert (pending_q == 0) else $fatal(1, "Resident candidate completes before drain");
    if (state_q == Drain)
      assert (fifo_count_q == 0 && rx_token_q == tokens_q)
        else $fatal(1, "Resident candidate stream length mismatch");
  end
  // synthesis translate_on
endmodule
