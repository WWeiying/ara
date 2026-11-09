// SPDX-License-Identifier: Apache-2.0
// Prototype: six-register, seeds-first source import via existing StA queues.
// The parent owns the queues exclusively and must not flush them mid-command.
module akv_resident_pv_import (
  input logic clk_i, rst_ni,
  input logic start_valid_i,
  output logic start_ready_o,
  input logic [3:0] words_i,
  input logic two_heads_i,
  input logic [6:0] tokens_i,
  input logic cancel_i,
  input logic [3:0] source_valid_i,
  output logic [3:0] source_ready_o,
  input logic [3:0][63:0] source_data_i,
  output logic [3:0] seed_valid_o,
  input logic [3:0] seed_ready_i,
  output logic [3:0][63:0] seed_data_o,
  output logic coefficient_valid_o,
  input logic coefficient_ready_i,
  output logic [31:0] coefficient_o,
  output logic done_valid_o,
  input logic done_ready_i,
  output logic done_error_o,
  output logic busy_o
);
  typedef enum logic [1:0] {Idle, Import, Discard, Done} state_t;
  state_t state_q;
  logic [3:0] words_q;
  logic heads_q, error_q, all_coeff, source_done;
  logic [6:0] tokens_q, sent_q;
  logic [3:0][4:0] word_q;
  logic [2:0] pair_q;
  logic coefficient_fire, pop_group;
  logic [7:0][31:0] pairs;

  assign start_ready_o = state_q == Idle && !cancel_i;
  assign busy_o = state_q != Idle;
  assign done_valid_o = state_q == Done;
  assign done_error_o = done_valid_o && error_q;
  assign seed_data_o = source_data_i;

  // EW16 physical halfword order in each lane is natural {l,l+8,l+4,l+12}.
  // Source queue heads hold all eight interleaved token pairs until their last use.
  for (genvar p = 0; p < 8; p++) begin : gen_pair
    for (genvar h = 0; h < 2; h++) begin : gen_head
      localparam int E = 2*p+h;
      localparam int L = E%4;
      localparam int H = 2*((E/4)%2)+(E/8);
      assign pairs[p][16*h+:16] = source_data_i[L][16*H+:16];
    end
  end
  assign coefficient_o = pairs[pair_q];
  always_comb begin
    all_coeff = &source_valid_i;
    source_done = 1'b1;
    for (int l = 0; l < 4; l++) begin
      all_coeff &= word_q[l] >= 16 && word_q[l] < 24;
      source_done &= word_q[l] == 24;
    end
  end
  assign coefficient_valid_o = state_q == Import && !cancel_i &&
                               sent_q < tokens_q && all_coeff;
  assign coefficient_fire = coefficient_valid_o && coefficient_ready_i;
  assign pop_group = coefficient_fire && (pair_q == 7 || sent_q+1'b1 == tokens_q);

  always_comb begin
    seed_valid_o = '0;
    source_ready_o = '0;
    for (int l = 0; l < 4; l++) begin
      if ((state_q == Import || state_q == Discard) && word_q[l] < 24) begin
        if (cancel_i || state_q == Discard || sent_q == tokens_q)
          source_ready_o[l] = 1'b1;
        else if (word_q[l] < 16) begin
          if ((heads_q || !word_q[l][3]) && {1'b0,word_q[l][2:0]} < words_q) begin
            seed_valid_o[l] = source_valid_i[l];
            source_ready_o[l] = seed_ready_i[l];
          end else source_ready_o[l] = 1'b1;
        end else source_ready_o[l] = pop_group;
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= Idle; words_q <= 0; heads_q <= 0; tokens_q <= 0;
      sent_q <= 0; word_q <= '0; pair_q <= 0; error_q <= 0;
    end else begin
      for (int l = 0; l < 4; l++)
        if (source_valid_i[l] && source_ready_o[l]) word_q[l] <= word_q[l]+1'b1;
      if (coefficient_fire) begin
        sent_q <= sent_q+1'b1;
        pair_q <= pop_group ? 3'b0 : pair_q+1'b1;
      end
      case (state_q)
        Idle: if (start_valid_i && start_ready_o) begin
          words_q <= words_i; heads_q <= two_heads_i; tokens_q <= tokens_i;
          sent_q <= 0; word_q <= '0; pair_q <= 0;
          error_q <= !(words_i inside {4,6,8} && tokens_i inside {[1:64]});
          state_q <= words_i inside {4,6,8} && tokens_i inside {[1:64]} ? Import : Done;
        end
        Import: begin
          if (cancel_i) begin state_q <= Discard; error_q <= 1; end
          else if (source_done && sent_q == tokens_q) state_q <= Done;
        end
        Discard: if (source_done) state_q <= Done;
        Done: if (done_ready_i) state_q <= Idle;
        default: state_q <= Idle;
      endcase
    end
  end
  // synthesis translate_off
  always_ff @(posedge clk_i) if (rst_ni) begin
    for (int l = 0; l < 4; l++)
      assert (word_q[l] <= 24) else $fatal(1,"Resident source over-consumed");
    if (coefficient_valid_o) begin
      for (int l = 0; l < 4; l++)
        assert (word_q[l] == 5'd16+5'(sent_q>>3))
          else $fatal(1,"Resident coefficient lane/group misalignment");
    end
    if (cancel_i || state_q == Discard)
      assert (seed_valid_o == 0 && !coefficient_valid_o)
        else $fatal(1,"Cancelled source reached private computation");
  end
  // synthesis translate_on
endmodule
