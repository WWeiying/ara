// SPDX-License-Identifier: Apache-2.0
// Shared reader of the existing synchronous AKV Q/K/V stores.
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
  output logic busy_o,
  input logic qk_i = 1'b0,
  input logic two_heads_i = 1'b0,
  input logic [7:0] dimensions_i = '0,
  input logic [2:0] query_base_i = '0,
  output logic query_read_o,
  output logic [2:0] query_row_o,
  output logic [3:0] query_word_o,
  input logic [255:0] query_data_i = '0,
  output logic column_start_o,
  output logic [6:0] column_dimension_o,
  output logic [6:0] column_tokens_o,
  input logic column_busy_i = 1'b0,
  input logic column_valid_i = 1'b0,
  output logic [1:0] column_index_o,
  output logic [1:0] column_packet_o,
  input logic [255:0] column_data_i = '0,
  output logic [3:0] stream_active_o
);
  typedef enum logic [3:0] {
    Idle, Coefficient, Values, Done, QueryRead, QueryWait,
    ColumnStart, ColumnWait, QkCoefficient, QkValues, CancelDrain
  } state_t;
  state_t state_q;
  logic [6:0] tokens_q;
  logic [5:0] token_q;
  logic [3:0] words_q, issue_word_q, consumed_word_q;
  logic pending_q, read_q, write_q, error_q;
  logic [1:0] count_q;
  logic [255:0] data_q [2];
  logic qk_q, two_heads_q, query_head_q;
  logic [2:0] query_base_q;
  logic [7:0] dimensions_q;
  logic [6:0] dimension_q;
  logic [1:0] packet_q;
  logic stream_fire, last_packet, last_dimension;
  logic [255:0] raw_data;
  logic [31:0] query_pair;
  logic pop, push;
  logic [2:0] reserved_after_pop;
  assign start_ready_o = state_q == Idle && !cancel_i;
  assign busy_o = state_q != Idle;
  assign done_valid_o = state_q == Done;
  assign done_error_o = done_valid_o && error_q;
  assign coefficient_ready_o = state_q == Coefficient && !cancel_i && stream_ready_i;
  assign stream_valid_o = !cancel_i && ((state_q == Coefficient && coefficient_valid_i) ||
                                       (state_q == Values && count_q != 0) ||
                                       state_q inside {QkCoefficient, QkValues});
  assign stream_is_value_o = state_q inside {Values, QkValues};
  assign stream_fire = stream_valid_o && stream_ready_i;
  assign pop = state_q == Values && stream_valid_o && stream_ready_i;
  assign push = pending_q && !cancel_i;
  // Reserve a FIFO entry for the one-cycle SRAM response before issuing its read.
  assign reserved_after_pop = {1'b0,count_q} + 3'(pending_q) - 3'(pop);
  assign row_read_o = state_q == Values && !cancel_i &&
                      issue_word_q < words_q && reserved_after_pop < 2;
  assign row_token_o = token_q;
  assign row_word_o = issue_word_q;
  assign query_read_o = state_q == QueryRead && !cancel_i && !column_busy_i;
  assign query_row_o = query_base_q + 3'(query_head_q);
  assign query_word_o = {1'b0, dimension_q[6:4]};
  assign column_start_o = state_q == ColumnStart && !cancel_i && !column_busy_i;
  assign column_dimension_o = {dimension_q[6:2], 2'b00};
  assign column_tokens_o = tokens_q;
  assign column_index_o = dimension_q[1:0];
  assign column_packet_o = packet_q;
  assign last_packet = (7'(packet_q) + 7'd1) * 7'd16 >= tokens_q;
  assign last_dimension = {1'b0, dimension_q} + 8'd1 == dimensions_q;
  assign query_pair[15:0] = data_q[0][16*dimension_q[3:0]+:16];
  assign query_pair[31:16] = two_heads_q ? data_q[1][16*dimension_q[3:0]+:16] : 16'b0;
  assign raw_data = qk_q ? column_data_i : data_q[read_q];
  always_comb begin
    stream_data_o = '0;
    for (int lane=0; lane<4; lane++) begin
      stream_active_o[lane] = !qk_q ||
          ((state_q == QkValues ? 7'(packet_q)*7'd16 : 7'd0) + 7'(lane) < tokens_q);
    end
    if (state_q inside {Coefficient, QkCoefficient}) begin
      for (int lane=0; lane<4; lane++)
        stream_data_o[lane] = {32'b0, qk_q ? query_pair : coefficient_i};
    end else begin
      for (int b=0; b<32; b++) begin
        automatic int p = shuffle_index(b, 4, EW16);
        stream_data_o[p/8][8*(p%8)+:8] = raw_data[8*b+:8];
      end
    end
  end
  // PV uses this array as its response FIFO; QK holds one query block per head.
  always_ff @(posedge clk_i) begin
    if (push) data_q[write_q] <= row_data_i;
    if (state_q == QueryWait && !cancel_i) data_q[query_head_q] <= query_data_i;
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= Idle; tokens_q <= 0; token_q <= 0; words_q <= 0;
      issue_word_q <= 0; consumed_word_q <= 0; pending_q <= 0;
      read_q <= 0; write_q <= 0; count_q <= 0; error_q <= 0;
      qk_q <= 0; two_heads_q <= 0; query_head_q <= 0; query_base_q <= 0;
      dimensions_q <= 0; dimension_q <= 0; packet_q <= 0;
    end else if (cancel_i && state_q != Idle && state_q != Done) begin
      // A K gather cannot be cancelled inside the shared SRAM controller.
      state_q <= qk_q && column_busy_i ? CancelDrain : Done;
      error_q <= 1; pending_q <= 0; count_q <= 0;
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
          qk_q <= qk_i; two_heads_q <= two_heads_i; query_head_q <= 0;
          query_base_q <= query_base_i; dimensions_q <= dimensions_i;
          dimension_q <= 0; packet_q <= 0;
          if (qk_i) begin
            error_q <= !(tokens_i inside {[1:64]} && dimensions_i inside {64,96,128} &&
                         ({1'b0,query_base_i} + 4'd1 + 4'(two_heads_i)) <= 8);
            state_q <= tokens_i inside {[1:64]} && dimensions_i inside {64,96,128} &&
                       ({1'b0,query_base_i} + 4'd1 + 4'(two_heads_i)) <= 8 ? QueryRead : Done;
          end else begin
            error_q <= !(tokens_i inside {[1:64]} && words_i inside {4,6,8});
            state_q <= tokens_i inside {[1:64]} && words_i inside {4,6,8} ? Coefficient : Done;
          end
        end
        Coefficient: if (coefficient_valid_i && coefficient_ready_o) begin
          issue_word_q <= 0; consumed_word_q <= 0; state_q <= Values;
        end
        Values: if (pop && consumed_word_q + 1'b1 == words_q) begin
          if ({1'b0,token_q} + 1'b1 == tokens_q) state_q <= Done;
          else begin token_q <= token_q + 1'b1; state_q <= Coefficient; end
        end
        QueryRead: if (query_read_o) state_q <= QueryWait;
        QueryWait: begin
          if (two_heads_q && !query_head_q) begin
            query_head_q <= 1'b1;
            state_q <= QueryRead;
          end else begin
            query_head_q <= 1'b0;
            state_q <= ColumnStart;
          end
        end
        ColumnStart: if (column_start_o) state_q <= ColumnWait;
        ColumnWait: if (column_valid_i && !column_busy_i) state_q <= QkCoefficient;
        QkCoefficient: if (stream_fire) begin packet_q <= 0; state_q <= QkValues; end
        QkValues: if (stream_fire) begin
          if (!last_packet) packet_q <= packet_q + 1'b1;
          else begin
            packet_q <= 0;
            dimension_q <= dimension_q + 1'b1;
            if (last_dimension) state_q <= Done;
            else if (dimension_q[3:0] == 4'hf) state_q <= QueryRead;
            else if (dimension_q[1:0] == 2'b11) state_q <= ColumnStart;
            else state_q <= QkCoefficient;
          end
        end
        CancelDrain: if (!column_busy_i) state_q <= Done;
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
    assert (!(query_read_o && (column_busy_i || column_start_o || row_read_o)))
      else $fatal(1,"Resident Q read overlaps K/V access");
    assert (!(push && state_q == QueryWait))
      else $fatal(1,"Resident reader storage has two owners");
    if (stream_valid_o) assert (stream_active_o != 0)
      else $fatal(1,"Resident reader emitted an empty packet");
  end
  // synthesis translate_on
endmodule
