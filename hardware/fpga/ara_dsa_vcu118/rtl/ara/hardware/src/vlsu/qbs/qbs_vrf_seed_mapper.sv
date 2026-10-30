// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Standalone continuation building block, not yet connected to QBS dispatch.
// The owner must reserve StA exclusively and supply four EW32 register words
// per input row. Abort drains this entire owned stream without seeding it.
module qbs_vrf_seed_mapper (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        start_valid_i,
    output logic        start_ready_o,
    input  logic [3:0]  start_m_i,
    input  logic [5:0]  start_n_i,
    input  logic        start_discard_i,
    input  logic        abort_i,

    input  logic [3:0]  lane_valid_i,
    output logic [3:0]  lane_ready_o,
    input  logic [63:0] lane_data_i [4],

    output logic        seed_valid_o,
    input  logic        seed_ready_i,
    output logic [3:0]  seed_row_o,
    output logic [7:0]  seed_mask_o,
    output logic [31:0] seed_data_o [8],

    output logic        done_valid_o,
    input  logic        done_ready_i,
    output logic        done_aborted_o,
    output logic        busy_o
  );

  typedef enum logic [1:0] {IDLE, STREAM, DONE} state_e;
  state_e state_q;
  logic [3:0] m_q;
  logic [5:0] n_q;
  logic [4:0] word_q;
  logic discard_q;
  logic wide, discard, writable, all_valid, consume;
  logic [2:0] context_index;
  logic [1:0] register_word;
  logic [5:0] element_base;

  assign start_ready_o = rst_ni && state_q == IDLE;
  assign busy_o = state_q != IDLE;
  assign done_valid_o = rst_ni && state_q == DONE;
  assign done_aborted_o = discard_q;
  assign wide = m_q >= 5;
  assign discard = discard_q || abort_i;
  assign context_index = word_q[4:2];
  assign register_word = word_q[1:0];
  assign element_base = {1'b0, register_word, 3'b0};
  assign all_valid = &lane_valid_i;

  // Wide-M results occupy two accumulator rows, but still own four VRF
  // words per input. Words beyond active N are drained, never restored.
  assign seed_row_o = wide ? {context_index, register_word[0]} : word_q[3:0];
  for (genvar bank = 0; bank < 8; bank++) begin : gen_banks
    if (bank < 4) assign seed_data_o[bank] = lane_data_i[bank][31:0];
    else assign seed_data_o[bank] = lane_data_i[bank-4][63:32];
    assign seed_mask_o[bank] = (!wide || !register_word[1]) &&
                              unsigned'(element_base) + bank < unsigned'(n_q);
  end
  assign writable = |seed_mask_o;
  assign seed_valid_o = rst_ni && state_q == STREAM && all_valid &&
                        !discard && writable;
  assign consume = rst_ni && state_q == STREAM && all_valid &&
                   (discard || !writable || seed_ready_i);
  assign lane_ready_o = {4{consume}};

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= IDLE;
      m_q <= '0;
      n_q <= '0;
      word_q <= '0;
      discard_q <= 1'b0;
    end else begin
      unique case (state_q)
        IDLE: if (start_valid_i) begin
          state_q <= STREAM;
          m_q <= start_m_i;
          n_q <= start_n_i;
          word_q <= '0;
          discard_q <= start_discard_i || abort_i;
        end
        STREAM: begin
          if (abort_i) discard_q <= 1'b1;
          if (consume) begin
            if ({1'b0, word_q} + 6'd1 == {m_q, 2'b0})
              state_q <= DONE;
            else word_q <= word_q + 1'b1;
          end
        end
        DONE: if (done_ready_i) state_q <= IDLE;
        default: state_q <= IDLE;
      endcase
    end
  end

`ifndef SYNTHESIS
  always_ff @(posedge clk_i) begin
    if (rst_ni) begin
      if (start_valid_i && start_ready_o) begin
        assert (start_m_i inside {[1:8]} && start_n_i inside {[1:32]} &&
                (start_m_i <= 4 || start_n_i <= 16))
          else $fatal(1, "Invalid four-lane VLEN1024 QBS seed shape");
      end
      assert (!(seed_valid_o && (discard || !writable)))
        else $fatal(1, "Discarded VRF data reached accumulator");
      if (|lane_ready_o) begin
        assert (&lane_ready_o && &lane_valid_i)
          else $fatal(1, "QBS seed consumed a partial lane word");
      end
    end
  end
`endif
endmodule : qbs_vrf_seed_mapper
