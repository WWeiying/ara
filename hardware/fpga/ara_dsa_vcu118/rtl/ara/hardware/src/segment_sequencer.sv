// Copyright 2024 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matteo Perotti <mperotti@iis.ee.ethz.ch>
// Description: break down segment memory operations into scalar
// memory operations. This is extremely bad in terms of IPC, but
// it has low-impact on the physical implementation.

module segment_sequencer import ara_pkg::*; import rvv_pkg::*; #(
    parameter bit          SegSupport = 1'b0,
    parameter int unsigned VLEN       = 0,
    parameter type         ara_req_t  = logic,
    parameter type         ara_resp_t = logic
  ) (
    // Clock and reset
    input  logic      clk_i,
    input  logic      rst_ni,
    input  logic      ara_idle_i,
    // Enable the segment sequencer?
    input  logic      is_segment_mem_op_i,
    input  logic      illegal_insn_i,
    input  logic      is_vload_i,
    output logic      seg_mem_op_end_o,
    input  logic      load_complete_i,
    output logic      load_complete_o,
    input  logic      store_complete_i,
    output logic      store_complete_o,
    input  vew_e [31:0] eew_i,
    // Ara frontend - backend info and handshakes
    input  ara_req_t  ara_req_i,
    output ara_req_t  ara_req_o,
    input  logic      ara_req_valid_i,
    output logic      ara_req_valid_o,
    input  logic      ara_req_ready_i,
    input  ara_resp_t ara_resp_i,
    output ara_resp_t ara_resp_o,
    input  logic      ara_resp_valid_i,
    output logic      ara_resp_valid_o
  );

  import cf_math_pkg::idx_width;

  if (SegSupport == SegSupportEnable) begin : gen_segment_support

    localparam int unsigned VLENB = VLEN > 0 ? VLEN / 8 : 1;

    logic ara_resp_valid_d, ara_resp_valid_q;
    ara_resp_t ara_resp_d, ara_resp_q;
    logic is_vload_d, is_vload_q;
    logic [$bits(ara_req_i.vstart):0] next_vstart_cnt;
    logic [2:0] nf_d, nf_q;

    typedef enum logic [1:0] {
      IDLE,
      SEGMENT_MICRO_OPS,
      SEGMENT_MICRO_OPS_WAIT_END,
      SEGMENT_MICRO_OPS_END
    } state_e;
    state_e state_d, state_q;

    // Track the elements within each segment
    logic new_seg_mem_op;
    logic segment_cnt_en, segment_cnt_clear;
    logic [$bits(ara_req_i.nf)-1:0] segment_cnt_q;
    logic [4:0] segment_reg_offset;
    int unsigned segment_source_reg_index;

    always_comb begin
      unique case (ara_req_i.emul)
        LMUL_2: segment_reg_offset = 5'(segment_cnt_q << 1);
        LMUL_4: segment_reg_offset = 5'(segment_cnt_q << 2);
        LMUL_8: segment_reg_offset = 5'(segment_cnt_q << 3);
        default: segment_reg_offset = 5'(segment_cnt_q);
      endcase
    end

    counter #(
      .WIDTH($bits(ara_req_i.nf)),
      .STICKY_OVERFLOW(1'b0)
    ) i_segment_cnt (
      .clk_i,
      .rst_ni,
      .clear_i(segment_cnt_clear),
      .en_i(segment_cnt_en),
      .load_i(1'b0),
      .down_i(1'b0),
      .d_i('0),
      .q_o(segment_cnt_q),
      .overflow_o( /* Unused */ )
    );
    assign segment_cnt_clear = (state_q == SEGMENT_MICRO_OPS_END)
                             | ((state_q != IDLE) & segment_cnt_en & (segment_cnt_q == nf_q));

    // Track the number of segments
    logic vstart_cnt_en, vstart_cnt_clear;
    logic [$bits(ara_req_i.vstart)-1:0] vstart_cnt_q;

    counter #(
      .WIDTH($bits(ara_req_i.vstart)),
      .STICKY_OVERFLOW(1'b0)
    ) i_vstart_cnt (
      .clk_i,
      .rst_ni,
      .clear_i( vstart_cnt_clear ),
      .en_i(vstart_cnt_en),
      .load_i(new_seg_mem_op),
      .down_i(1'b0),
      .d_i(ara_req_i.vstart),
      .q_o(vstart_cnt_q),
      .overflow_o( /* Unused */ )
    );
    // Change destination vector index when all the fields of the segment have been processed
    assign vstart_cnt_en = segment_cnt_en & (segment_cnt_q == nf_q);
    assign vstart_cnt_clear = (state_q == SEGMENT_MICRO_OPS_END);

    // Next vstart count
    assign next_vstart_cnt = vstart_cnt_q + 1;

    always_comb begin
      automatic int unsigned active_element;
      automatic int unsigned element_reg_offset;

      active_element = state_q == IDLE
          ? unsigned'(ara_req_i.vstart) : unsigned'(vstart_cnt_q);
      element_reg_offset =
          (active_element << unsigned'(ara_req_i.eew_vs1)) / VLENB;
      segment_source_reg_index = unsigned'(ara_req_i.vs1) +
          unsigned'(segment_reg_offset) + element_reg_offset;
    end

    always_comb begin
      state_d = state_q;

      // Pass through
      ara_req_o        = ara_req_i;
      ara_req_valid_o  = ara_req_valid_i;
      ara_resp_o       = ara_resp_i;
      ara_resp_valid_o = ara_resp_valid_i;
      // Block load/store_complete
      load_complete_o  = 1'b0;
      store_complete_o = 1'b0;

      ara_resp_d       = ara_resp_q;
      ara_resp_valid_d = ara_resp_valid_q;
      is_vload_d       = is_vload_q;
      nf_d             = nf_q;

      seg_mem_op_end_o = 1'b0;

      // Don't count up by default
      new_seg_mem_op = 1'b0;
      segment_cnt_en = 1'b0;

      // Low-perf Moore's FSM
      unique case (state_q)
        IDLE: begin
          // Pass-through
          load_complete_o  = load_complete_i;
          store_complete_o = store_complete_i;
          if (is_segment_mem_op_i && !is_vload_i &&
              segment_source_reg_index < 32)
            ara_req_o.old_eew_vs1 = eew_i[segment_source_reg_index];
          // Start only when the segment request itself is transferred. During
          // pre-request reshuffles the decoder can already identify the held
          // architectural instruction as a segment operation while suppressing
          // ara_req_valid_i; advancing here would drop field zero.
          if (ara_req_valid_i && ara_req_ready_i &&
              is_segment_mem_op_i && !illegal_insn_i) begin
            nf_d       = ara_req_i.nf;
            is_vload_d = is_vload_i;
            // Set-up sequencing
            new_seg_mem_op = 1'b1;
            // Set up the first micro operation
            // The first micro-op covers exactly the architectural element at
            // vstart.  Using vl=1 only works when vstart is zero and otherwise
            // creates an empty internal request with vl <= vstart.
            ara_req_o.vl = ara_req_i.vstart + 1'b1;
            // Field zero must use the same strided representation as every
            // later unit-segment micro-op. With nonzero vstart, passing the
            // original VLE/VSE through would address base + vstart*EEW instead
            // of base + vstart*(nf+1)*EEW.
            if (ara_req_i.op == VLE || ara_req_i.op == VSE) begin
              ara_req_o.op = is_vload_i ? VLSE : VSSE;
              ara_req_o.stride = is_vload_i
                               ? (ara_req_i.nf + 1) << ara_req_i.vtype.vsew
                               : (ara_req_i.nf + 1) << ara_req_i.eew_vs1;
            end
            // Pass to the next field if the previous micro op finished
            segment_cnt_en = 1'b1;
            // Start sequencing
            state_d    = SEGMENT_MICRO_OPS;
          end
        end
        SEGMENT_MICRO_OPS: begin
          // Manipulate the memory micro request in advance
          ara_req_o.vl        = next_vstart_cnt;
          ara_req_o.vstart    = vstart_cnt_q;
          ara_req_o.vs1       = ara_req_i.vs1 + segment_reg_offset;
          ara_req_o.vd        = ara_req_i.vd  + segment_reg_offset;
          if (!is_vload_q && segment_source_reg_index < 32)
            ara_req_o.old_eew_vs1 = eew_i[segment_source_reg_index];

          ara_req_o.scalar_op = is_vload_q           // todo: relax timing here
                              ? ara_req_i.scalar_op + (segment_cnt_q << ara_req_i.vtype.vsew)
                              : ara_req_i.scalar_op + (segment_cnt_q << ara_req_i.eew_vs1);
          // If segment unit-stride, the segments are actually separated by (#field << eew) bytes
          if (ara_req_i.op == VLE || ara_req_i.op == VSE) begin
            ara_req_o.op = is_vload_q
                         ? VLSE
                         : VSSE;
            ara_req_o.stride = is_vload_q
                             ? (ara_req_i.nf + 1) << ara_req_i.vtype.vsew
                             : (ara_req_i.nf + 1) << ara_req_i.eew_vs1;
          end

          // Don't answer CVA6 yet
          ara_resp_valid_o = 1'b0;

          // Pass to the next field if the previous micro op finished
          if (ara_req_valid_i && ara_req_ready_i) begin
            segment_cnt_en = 1'b1;
          end

          // Wait for an answer from Ara's backend
          if (ara_resp_valid_i) begin            // If exception, stop the execution
            if (ara_resp_i.exception.valid) begin
            // If no exception, continue with the micro ops
            end else begin
              // If over - stop in the next cycle
              if (segment_cnt_clear && (next_vstart_cnt == ara_req_i.vl)) begin
                // Sample the last answer
                ara_resp_d       = ara_resp_i;
                is_vload_d       = is_vload_i;
                state_d = SEGMENT_MICRO_OPS_WAIT_END;
              end
            end
          end
        end
        SEGMENT_MICRO_OPS_WAIT_END: begin
          // Don't answer CVA6 yet
          ara_resp_valid_o = 1'b0;
          // Stop injecting micro instructions
          ara_req_valid_o  = 1'b0;
          // Wait for idle to give the final load/store_complete
          if (ara_idle_i && ara_req_ready_i) begin
            state_d = SEGMENT_MICRO_OPS_END;
          end
        end
        SEGMENT_MICRO_OPS_END: begin
          ara_resp_o       = ara_resp_q;
          seg_mem_op_end_o = 1'b1;
          ara_resp_valid_o = 1'b1;
          load_complete_o  = is_vload_q;
          store_complete_o = ~is_vload_q;
          state_d = IDLE;
        end
        default:;
      endcase
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        state_q          <= IDLE;
        nf_q             <= '0;
        is_vload_q       <= 1'b0;
        ara_resp_q       <= '0;
        ara_resp_valid_q <= '0;
      end else begin
        state_q          <= state_d;
        nf_q             <= nf_d;
        is_vload_q       <= is_vload_d;
        ara_resp_q       <= ara_resp_d;
      end
    end

`ifdef FOR_VERIFY
    always_ff @(posedge clk_i) begin
      if (rst_ni && $test$plusargs("ARA_DEBUG_SEGMENT") &&
          (is_segment_mem_op_i || state_q != IDLE)) begin
        $display("[ARA_SEGMENT] t=%0t state=%0d->%0d in=%0b/%0b seg=%0b cnt=%0d nf=%0d clear=%0b in_arch=%0d in_vd=v%0d in_emul=%0d in_vl=%0d in_vs=%0d in_tok=%0b out=%0b out_arch=%0d out_vd=v%0d out_emul=%0d out_vl=%0d out_vs=%0d out_tok=%0b",
                 $time, state_q, state_d, ara_req_valid_i, ara_req_ready_i,
                 is_segment_mem_op_i, segment_cnt_q, nf_q, segment_cnt_clear,
                 ara_req_i.verify_arch_seq, ara_req_i.vd, ara_req_i.emul,
                 ara_req_i.vl, ara_req_i.vstart, ara_req_i.token,
                 ara_req_valid_o, ara_req_o.verify_arch_seq, ara_req_o.vd,
                 ara_req_o.emul, ara_req_o.vl, ara_req_o.vstart,
                 ara_req_o.token);
      end
      if (rst_ni && state_q == IDLE && state_d != IDLE) begin
        assert (ara_req_valid_i && ara_req_ready_i)
          else $error("segment sequencer started without a request handshake");
      end
    end
`endif
  end else begin : gen_no_segment_support
    // No segment micro-ops here
    assign seg_mem_op_end_o = 1'b0;
    // Pass through if segment support is disabled
    assign load_complete_o  = load_complete_i;
    assign store_complete_o = store_complete_i;
    assign ara_req_o        = ara_req_i;
    assign ara_req_valid_o  = ara_req_valid_i;
    assign ara_resp_o       = ara_resp_i;
    assign ara_resp_valid_o = ara_resp_valid_i;
  end

endmodule
