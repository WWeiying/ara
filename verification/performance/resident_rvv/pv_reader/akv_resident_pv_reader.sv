// SPDX-License-Identifier: Apache-2.0
// Experimental reader of the existing synchronous 256-bit AKV V-row port.
module akv_resident_pv_reader import ara_pkg::*; import rvv_pkg::*; (
  input logic clk_i, rst_ni, cancel_i,
  input logic start_valid_i,
  output logic start_ready_o,
  input logic [6:0] tokens_i,
  input logic [3:0] words_i,
  input logic coefficient_valid_i,
  output logic coefficient_ready_o,
  input logic [31:0] coefficient_i,
  output logic row_read_o,
  output logic [5:0] row_token_o,
  output logic [3:0] row_word_o,
  input logic [255:0] row_data_i,
  output logic stream_valid_o,
  input logic stream_ready_i,
  output logic stream_is_value_o,
  output logic [3:0][63:0] stream_data_o,
  output logic done_valid_o,
  input logic done_ready_i,
  output logic done_error_o,
  output logic busy_o
);
  typedef enum logic [1:0] {Idle, Coefficient, Values, Done} state_t;
  state_t state_q;
  logic [6:0] tokens_q;
  logic [5:0] token_q;
  logic [3:0] words_q, issue_word_q, consumed_word_q;
  logic pending_q, read_q, write_q, error_q;
  logic [1:0] count_q;
  logic [255:0] data_q [2];
  logic pop, push;
  logic [2:0] reserved_after_pop;
  assign start_ready_o = state_q == Idle && !cancel_i;
  assign busy_o = state_q != Idle;
  assign done_valid_o = state_q == Done;
  assign done_error_o = done_valid_o && error_q;
  assign coefficient_ready_o = state_q == Coefficient && !cancel_i && stream_ready_i;
  assign stream_valid_o = !cancel_i && ((state_q == Coefficient && coefficient_valid_i) ||
                                       (state_q == Values && count_q != 0));
  assign stream_is_value_o = state_q == Values;
  assign pop = state_q == Values && stream_valid_o && stream_ready_i;
  assign push = pending_q && !cancel_i;
  // Reserve a FIFO entry for the one-cycle SRAM response before issuing its read.
  assign reserved_after_pop = {1'b0,count_q} + 3'(pending_q) - 3'(pop);
  assign row_read_o = state_q == Values && !cancel_i &&
                      issue_word_q < words_q && reserved_after_pop < 2;
  assign row_token_o = token_q;
  assign row_word_o = issue_word_q;
  always_comb begin
    stream_data_o = '0;
    if (state_q == Coefficient) begin
      for (int lane=0; lane<4; lane++) stream_data_o[lane] = {32'b0, coefficient_i};
    end else begin
      for (int b=0; b<32; b++) begin
        automatic int p = shuffle_index(b, 4, EW16);
        stream_data_o[p/8][8*(p%8)+:8] = data_q[read_q][8*b+:8];
      end
    end
  end
  always_ff @(posedge clk_i) if (push) data_q[write_q] <= row_data_i;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= Idle; tokens_q <= 0; token_q <= 0; words_q <= 0;
      issue_word_q <= 0; consumed_word_q <= 0; pending_q <= 0;
      read_q <= 0; write_q <= 0; count_q <= 0; error_q <= 0;
    end else if (cancel_i && state_q != Idle && state_q != Done) begin
      state_q <= Done; error_q <= 1; pending_q <= 0; count_q <= 0;
    end else begin
      pending_q <= row_read_o;
      if (push) write_q <= !write_q;
      if (pop) begin read_q <= !read_q; consumed_word_q <= consumed_word_q + 1'b1; end
      if (row_read_o) issue_word_q <= issue_word_q + 1'b1;
      case ({push,pop})
        2'b10: count_q <= count_q + 1'b1;
        2'b01: count_q <= count_q - 1'b1;
        default: ;
      endcase
      case (state_q)
        Idle: if (start_valid_i && start_ready_o) begin
          tokens_q <= tokens_i; words_q <= words_i; token_q <= 0;
          read_q <= 0; write_q <= 0; count_q <= 0; pending_q <= 0;
          issue_word_q <= 0; consumed_word_q <= 0;
          error_q <= !(tokens_i inside {[1:64]} && words_i inside {4,6,8});
          state_q <= tokens_i inside {[1:64]} && words_i inside {4,6,8} ? Coefficient : Done;
        end
        Coefficient: if (coefficient_valid_i && coefficient_ready_o) begin
          issue_word_q <= 0; consumed_word_q <= 0; state_q <= Values;
        end
        Values: if (pop && consumed_word_q + 1'b1 == words_q) begin
          if ({1'b0,token_q} + 1'b1 == tokens_q) state_q <= Done;
          else begin token_q <= token_q + 1'b1; state_q <= Coefficient; end
        end
        Done: if (done_ready_i) state_q <= Idle;
        default: state_q <= Idle;
      endcase
    end
  end
  // synthesis translate_off
  always_ff @(posedge clk_i) if (rst_ni && !cancel_i) begin
    assert (count_q <= 2 && {1'b0,count_q}+3'(pending_q) <= 2)
      else $fatal(1,"Resident read credit overflow");
    if (pop && consumed_word_q+1'b1 == words_q)
      assert (count_q == 1 && !pending_q && issue_word_q == words_q)
        else $fatal(1,"Resident token advanced before SRAM drain");
  end
  // synthesis translate_on
endmodule
