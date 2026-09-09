// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Atomically exposes a completed QBS accumulator through Ara's existing LDU
// lane-result ports. "Atomic" here means that no write starts before every
// faulting command read has completed; younger consumers remain completion-
// gated by the sequencer. Legacy commands write full registers; wide M5--M8
// commands update only their active N elements and preserve register tails.
module qbs_commit import qbs_pkg::*; #(
    parameter int unsigned NrLanes = 4,
    parameter int unsigned VLEN = 1024,
    parameter type         vid_t = logic,
    parameter type         vaddr_t = logic
  ) (
    input  logic                     clk_i,
    input  logic                     rst_ni,

    input  logic                     start_valid_i,
    output logic                     start_ready_o,
    input  vid_t                     start_id_i,
    input  logic [4:0]               start_vd_i,
    input  logic [3:0]               start_m_i,
    input  logic [5:0]               start_n_i,

    output logic [3:0]               accumulator_bank_row_o,
    input  logic [7:0]               accumulator_bank_valid_i,
    input  logic [31:0]              accumulator_bank_data_i [8],

    output logic [NrLanes-1:0]       ldu_result_req_o,
    output vid_t [NrLanes-1:0]       ldu_result_id_o,
    output vaddr_t [NrLanes-1:0]     ldu_result_addr_o,
    output logic [63:0]              ldu_result_wdata_o [NrLanes],
    output logic [7:0]               ldu_result_be_o [NrLanes],
    input  logic [NrLanes-1:0]       ldu_result_gnt_i,
    input  logic [NrLanes-1:0]       ldu_result_final_gnt_i,

    output logic                     done_valid_o,
    input  logic                     done_ready_i,
    output logic                     busy_o,
    output logic [31:0]              commit_word_count_o,
    output logic [31:0]              commit_backpressure_cycles_o
  );

  localparam int unsigned LaneWordBytes = 8;
  localparam int unsigned AggregateBytes = NrLanes * LaneWordBytes;
  localparam int unsigned ElementsPerWord = AggregateBytes / 4;
  localparam int unsigned WordsPerRegister = VLEN / 8 / AggregateBytes;
  localparam int unsigned MaxCommitWords =
      QbsMaxResults / ElementsPerWord;
  localparam int unsigned WordIndexWidth =
      MaxCommitWords > 1 ? $clog2(MaxCommitWords) : 1;
  localparam int unsigned RegisterWordWidth =
      WordsPerRegister > 1 ? $clog2(WordsPerRegister) : 1;

  typedef enum logic [1:0] {
    QBS_COMMIT_IDLE,
    QBS_COMMIT_WRITE,
    QBS_COMMIT_DONE
  } qbs_commit_state_e;

  qbs_commit_state_e state_d, state_q;
  vid_t id_d, id_q;
  logic [4:0] vd_d, vd_q;
  logic [3:0] m_d, m_q;
  logic [5:0] n_d, n_q;
  logic [WordIndexWidth-1:0] word_index_d, word_index_q;
  logic [NrLanes-1:0] accepted_d, accepted_q;
  logic [NrLanes-1:0] final_seen_d, final_seen_q;

  logic [2:0] current_context;
  logic [RegisterWordWidth-1:0] current_register_word;
  logic [5:0] current_element_base;
  logic [WordIndexWidth:0] words_per_context;
  logic [WordIndexWidth:0] total_words;
  logic wide_command;
  logic accumulator_word_ready;
  logic [NrLanes-1:0] active_lane_mask;
  logic [NrLanes-1:0] request_fire;
  logic [NrLanes-1:0] accepted_next;
  logic [NrLanes-1:0] final_next;
  logic word_complete;

  assign start_ready_o = state_q == QBS_COMMIT_IDLE;
  assign done_valid_o = state_q == QBS_COMMIT_DONE;
  assign busy_o = state_q != QBS_COMMIT_IDLE;

  always_comb begin
    wide_command = unsigned'(m_q) >= QbsWideMMin;
    words_per_context = (WordIndexWidth+1)'(WordsPerRegister);
    current_context =
        3'(unsigned'(word_index_q) / WordsPerRegister);
    current_register_word =
        RegisterWordWidth'(unsigned'(word_index_q) % WordsPerRegister);
    if (wide_command) begin
      words_per_context = n_q > ElementsPerWord
          ? (WordIndexWidth+1)'(2) : (WordIndexWidth+1)'(1);
      if (n_q > ElementsPerWord) begin
        current_context = 3'(unsigned'(word_index_q) >> 1);
        current_register_word = RegisterWordWidth'(word_index_q[0]);
      end else begin
        current_context = 3'(word_index_q);
        current_register_word = '0;
      end
    end
    current_element_base =
        6'(unsigned'(current_register_word) * ElementsPerWord);
    total_words = (WordIndexWidth+1)'(
        unsigned'(m_q) * unsigned'(words_per_context));
    accumulator_bank_row_o =
        4'(unsigned'(current_context) *
           (wide_command ? (QbsWideMMaxN / ElementsPerWord) :
                           (QbsMaxN / ElementsPerWord)) +
           unsigned'(current_register_word));

    accumulator_word_ready = 1'b1;
    for (int unsigned element = 0; element < ElementsPerWord; element++) begin
      if (unsigned'(current_element_base) + element < unsigned'(n_q))
        accumulator_word_ready &= accumulator_bank_valid_i[element];
    end
  end

  always_comb begin : form_lane_results
    logic [31:0] element_data [ElementsPerWord];
    logic element_active [ElementsPerWord];

    for (int unsigned element = 0; element < ElementsPerWord; element++) begin
      element_active[element] =
          unsigned'(current_element_base) + element < unsigned'(n_q);
      element_data[element] =
          element_active[element]
              ? accumulator_bank_data_i[element] : 32'b0;
    end

    active_lane_mask = '0;
    for (int unsigned lane = 0; lane < NrLanes; lane++) begin
      automatic logic low_active = element_active[lane];
      automatic logic high_active = element_active[lane + NrLanes];
      ldu_result_be_o[lane] = wide_command
          ? {{4{high_active}}, {4{low_active}}} : 8'hff;
      active_lane_mask[lane] = |ldu_result_be_o[lane];
      ldu_result_req_o[lane] = state_q == QBS_COMMIT_WRITE &&
                               accumulator_word_ready &&
                               active_lane_mask[lane] &&
                               !accepted_q[lane];
      ldu_result_id_o[lane] = id_q;
      ldu_result_addr_o[lane] = vaddr_t'(
          unsigned'(vd_q) * WordsPerRegister +
          unsigned'(current_context) * WordsPerRegister +
          unsigned'(current_register_word));
      // EW32's 4-lane shuffle places elements 0..3 in the low lane
      // words and elements 4..7 in the corresponding high lane words.
      ldu_result_wdata_o[lane] = {
        element_data[lane + NrLanes], element_data[lane]
      };
    end
  end

  assign request_fire = ldu_result_req_o & ldu_result_gnt_i;
  assign accepted_next = accepted_q | request_fire;
  assign final_next = final_seen_q |
      (ldu_result_final_gnt_i & (accepted_q | request_fire));
  assign word_complete =
      (accepted_next & active_lane_mask) == active_lane_mask &&
      (final_next & active_lane_mask) == active_lane_mask;

  always_comb begin
    state_d = state_q;
    id_d = id_q;
    vd_d = vd_q;
    m_d = m_q;
    n_d = n_q;
    word_index_d = word_index_q;
    accepted_d = accepted_q;
    final_seen_d = final_seen_q;

    unique case (state_q)
      QBS_COMMIT_IDLE: begin
        if (start_valid_i) begin
          id_d = start_id_i;
          vd_d = start_vd_i;
          m_d = start_m_i;
          n_d = start_n_i;
          word_index_d = '0;
          accepted_d = '0;
          final_seen_d = '0;
          state_d = QBS_COMMIT_WRITE;
        end
      end

      QBS_COMMIT_WRITE: begin
        accepted_d = accepted_next;
        final_seen_d = final_next;
        if (word_complete) begin
          accepted_d = '0;
          final_seen_d = '0;
          if (unsigned'(word_index_q) + 1 == unsigned'(total_words)) begin
            state_d = QBS_COMMIT_DONE;
          end else begin
            word_index_d = word_index_q + 1'b1;
          end
        end
      end

      QBS_COMMIT_DONE: begin
        if (done_ready_i)
          state_d = QBS_COMMIT_IDLE;
      end

      default: state_d = QBS_COMMIT_IDLE;
    endcase
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= QBS_COMMIT_IDLE;
      id_q <= '0;
      vd_q <= '0;
      m_q <= '0;
      n_q <= '0;
      word_index_q <= '0;
      accepted_q <= '0;
      final_seen_q <= '0;
      commit_word_count_o <= '0;
      commit_backpressure_cycles_o <= '0;
    end else begin
      state_q <= state_d;
      id_q <= id_d;
      vd_q <= vd_d;
      m_q <= m_d;
      n_q <= n_d;
      word_index_q <= word_index_d;
      accepted_q <= accepted_d;
      final_seen_q <= final_seen_d;

      if (state_q == QBS_COMMIT_IDLE && start_valid_i) begin
        commit_word_count_o <= '0;
        commit_backpressure_cycles_o <= '0;
      end else begin
        if (state_q == QBS_COMMIT_WRITE &&
            word_complete)
          commit_word_count_o <= commit_word_count_o + 1'b1;
        if (state_q == QBS_COMMIT_WRITE && accumulator_word_ready &&
            |(ldu_result_req_o & ~ldu_result_gnt_i))
          commit_backpressure_cycles_o <=
              commit_backpressure_cycles_o + 1'b1;
      end
    end
  end

`ifndef SYNTHESIS
  initial begin
    assert (NrLanes == 4)
      else $fatal(1, "QBS commit mapping requires four Ara lanes");
    assert (VLEN >= 256 && VLEN <= 1024 && VLEN % 256 == 0)
      else $fatal(1, "QBS commit requires 256..1024-bit VLEN");
    assert (ElementsPerWord == 8)
      else $fatal(1, "QBS accumulator banking expects eight FP32 values/word");
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni) begin
      if (state_q == QBS_COMMIT_IDLE && start_valid_i) begin
        assert (start_m_i inside {[1:QbsMaxM]});
        assert (start_n_i inside {[1:(VLEN/32)]});
        assert (unsigned'(start_m_i) * unsigned'(start_n_i) <=
                QbsMaxResults);
        if (unsigned'(start_m_i) >= QbsWideMMin)
          assert (start_n_i <= QbsWideMMaxN);
      end
      if (state_q == QBS_COMMIT_WRITE && accumulator_word_ready) begin
        for (int unsigned element = 0; element < ElementsPerWord; element++) begin
          if (unsigned'(current_element_base) + element < unsigned'(n_q))
            assert (accumulator_bank_valid_i[element])
              else $fatal(1, "QBS commit observed a missing active result");
        end
      end
      if (done_valid_o)
        assert (commit_word_count_o == unsigned'(total_words))
          else $fatal(1, "QBS commit completed before all active words");
    end
  end
`endif

endmodule : qbs_commit
