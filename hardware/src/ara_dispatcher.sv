// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// Ara's dispatcher interfaces Ariane's requests with the vector lanes.
// It also acknowledges instructions back to Ariane, perhaps with a
// response or an error message.

module ara_dispatcher import ara_pkg::*; import rvv_pkg::*; import qbs_pkg::*;
  import akv_pkg::*; #(
    parameter int           unsigned NrLanes            = 0,
    parameter int           unsigned VLEN               = 0,
    parameter type                   ara_req_t          = logic,
    parameter type                   ara_resp_t         = logic,
    parameter type                   accelerator_req_t  = logic,
    parameter type                   accelerator_resp_t = logic,
    // CVA6 configuration
    parameter config_pkg::cva6_cfg_t CVA6Cfg      = cva6_config_pkg::cva6_cfg,
    localparam type                  xlen_t       = logic [CVA6Cfg.XLEN-1:0],
    // Support for floating-point data types
    parameter fpu_support_e          FPUSupport   = FPUSupportHalfSingleDouble,
    // External support for vfrec7, vfrsqrt7
    parameter fpext_support_e        FPExtSupport = FPExtSupportEnable,
    // Support for fixed-point data types
    parameter fixpt_support_e        FixPtSupport = FixedPointEnable,
    // Support for segment memory operations
    parameter seg_support_e          SegSupport   = SegSupportEnable,
    // Dependent parameters: DO NOT CHANGE
    localparam type                  vlen_t       = logic[$clog2(VLEN+1)-1:0],
    localparam int          unsigned VLENB        = VLEN / 8
  ) (
    // Clock and reset
    input  logic                                 clk_i,
    input  logic                                 rst_ni,
    // Interfaces with Ariane
    input  accelerator_req_t                     acc_req_i,
    output accelerator_resp_t                    acc_resp_o,
    // Interface with Ara's backend
    output ara_req_t                             ara_req_o,
    output logic                                 ara_req_valid_o,
    input  logic                                 ara_req_ready_i,
    input  ara_resp_t                            ara_resp_i,
    input  logic                                 ara_resp_valid_i,
    input  logic                                 ara_idle_i,
    input  logic                                 sldu_idle_i,
    output logic                                 sldu_drain_o,
    // Interface with the lanes
    input  logic              [NrLanes-1:0][4:0] fflags_ex_i,
    input  logic              [NrLanes-1:0]      fflags_ex_valid_i,
    // LSU exception-related flush support
    output logic                                 lsu_ex_flush_o,
    input  logic                                 lsu_ex_flush_done_i,
    // Rounding mode is shared between all lanes
    input  logic              [NrLanes-1:0]      vxsat_flag_i,
    output vxrm_t             [NrLanes-1:0]      alu_vxrm_o,
    // Interface with the Vector Store Unit
    output logic                                 core_st_pending_o,
    input  logic                                 load_complete_i,
    input  logic                                 store_complete_i,
    input  logic                                 store_pending_i
  );

  import cf_math_pkg::idx_width;

  `include "common_cells/registers.svh"

  assign core_st_pending_o = acc_req_i.store_pending;

  ////////////
  //  CSRs  //
  ////////////

  vlen_t  csr_vstart_d, csr_vstart_q;
  vlen_t  csr_vl_d, csr_vl_q;
  vtype_t csr_vtype_d, csr_vtype_q;
  vxsat_e csr_vxsat_d, csr_vxsat_q;
  vxrm_t  csr_vxrm_d, csr_vxrm_q;

  `FF(csr_vstart_q, csr_vstart_d, '0)
  `FF(csr_vl_q, csr_vl_d, '0)
  `FF(csr_vtype_q, csr_vtype_d, '{vill: 1'b1, vsew: EW8, vlmul: LMUL_1, default: '0})
  `FF(csr_vxsat_q, csr_vxsat_d, '0)
  `FF(csr_vxrm_q, csr_vxrm_d, '0)
  // Converts between the internal representation of `vtype_t` and the full XLEN-bit CSR.
  function automatic xlen_t xlen_vtype(vtype_t vtype);
    xlen_vtype = {vtype.vill, {CVA6Cfg.XLEN-9{1'b0}}, vtype.vma, vtype.vta, vtype.vsew,
      vtype.vlmul[2:0]};
  endfunction: xlen_vtype

  // Converts between the XLEN-bit vtype CSR and its internal representation
  function automatic vtype_t vtype_xlen(xlen_t xlen);
    vtype_xlen = '{
      vill  : xlen[CVA6Cfg.XLEN-1],
      vma   : xlen[7],
      vta   : xlen[6],
      vsew  : vew_e'(xlen[5:3]),
      vlmul : vlmul_e'(xlen[2:0])
    };
  endfunction : vtype_xlen

  // Calculates next(lmul)
  function automatic vlmul_e next_lmul(vlmul_e lmul);
    unique case (lmul)
      LMUL_1_8: next_lmul = LMUL_1_4;
      LMUL_1_4: next_lmul = LMUL_1_2;
      LMUL_1_2: next_lmul = LMUL_1;
      LMUL_1  : next_lmul = LMUL_2;
      LMUL_2  : next_lmul = LMUL_4;
      LMUL_4  : next_lmul = LMUL_8;
      default : next_lmul = LMUL_RSVD;
    endcase
  endfunction : next_lmul

  // Widening .vx instructions execute at 2*SEW internally. Preserve the architectural
  // scalar rule by truncating rs1 to the source SEW before extending it to the ALU width.
  function automatic elen_t widening_scalar_op(
      xlen_t scalar, vew_e source_eew, logic sign_extend
  );
    elen_t scalar_elen;
    scalar_elen = elen_t'(scalar);
    unique case (source_eew)
      EW8:  widening_scalar_op = sign_extend
                                  ? {{ELEN-8{scalar_elen[7]}}, scalar_elen[7:0]}
                                  : {{ELEN-8{1'b0}}, scalar_elen[7:0]};
      EW16: widening_scalar_op = sign_extend
                                  ? {{ELEN-16{scalar_elen[15]}}, scalar_elen[15:0]}
                                  : {{ELEN-16{1'b0}}, scalar_elen[15:0]};
      EW32: widening_scalar_op = sign_extend
                                  ? {{ELEN-32{scalar_elen[31]}}, scalar_elen[31:0]}
                                  : {{ELEN-32{1'b0}}, scalar_elen[31:0]};
      default: widening_scalar_op = scalar_elen;
    endcase
  endfunction : widening_scalar_op

  function automatic logic mask_result(ara_op_e op);
    mask_result = op inside {
      [VMFEQ:VMFGE], [VMSEQ:VMSGT], [VMADC:VMSBC], [VMSBF:VMSIF],
      [VMANDNOT:VMXNOR]
    };
  endfunction : mask_result

  function automatic logic reduction_result(ara_op_e op);
    reduction_result = op inside {
      [VREDSUM:VWREDSUM], [VFREDUSUM:VFWREDOSUM]
    };
  endfunction : reduction_result

  function automatic logic widening_reduction(ara_op_e op);
    widening_reduction = op inside {
      VWREDSUMU, VWREDSUM, VFWREDUSUM, VFWREDOSUM
    };
  endfunction : widening_reduction

  function automatic logic requires_zero_vstart(ara_op_e op);
    requires_zero_vstart = reduction_result(op) || op inside {
      VCPOP, VFIRST, VMSBF, VMSOF, VMSIF, VIOTA, VCOMPRESS
    };
  endfunction : requires_zero_vstart

  function automatic logic single_register_result(ara_op_e op);
    single_register_result = mask_result(op) || reduction_result(op);
  endfunction : single_register_result

  // Calculates prev(lmul)
  function automatic vlmul_e prev_lmul(vlmul_e lmul);
    unique case (lmul)
      LMUL_1_4: prev_lmul = LMUL_1_8;
      LMUL_1_2: prev_lmul = LMUL_1_4;
      LMUL_1  : prev_lmul = LMUL_1_2;
      LMUL_2  : prev_lmul = LMUL_1;
      LMUL_4  : prev_lmul = LMUL_2;
      LMUL_8  : prev_lmul = LMUL_4;
      default : prev_lmul = LMUL_RSVD;
    endcase
  endfunction : prev_lmul

  // Calculates prev(prev(ew))
  function automatic vew_e prev_prev_ew(vew_e ew);
    unique case (ew)
      EW64: prev_prev_ew    = EW16;
      EW32: prev_prev_ew    = EW8;
      default: prev_prev_ew = EW1024;
    endcase
  endfunction : prev_prev_ew

  /////////////////////////
  //  Backend interface  //
  /////////////////////////

  ara_req_t ara_req, ara_req_d;
  logic     ara_req_valid, ara_req_valid_d;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      ara_req_o       <= '0;
      ara_req_valid_o <= 1'b0;
    end else begin
      if (ara_req_ready_i) begin
        ara_req_o       <= ara_req_d;
        ara_req_valid_o <= ara_req_valid_d;
      end
    end
  end

  /////////////
  //  State  //
  /////////////

  // The backend can either be in normal operation, waiting for Ara to be idle before issuing new
  // operations, or injecting a reshuffling uop.
  // IDLE can happen, for example, once the vlmul has changed.
  // RESHUFFLE can happen when an instruction writes a register with != EEW
  typedef enum logic [3:0] {
    NORMAL_OPERATION,
    WAIT_IDLE,
    WAIT_IDLE_FLUSH,
    RESHUFFLE,
    OVERLAP_PREFIX_FIXUP,
    OVERLAP_WAIT_PREFIX_FIXUP,
    OVERLAP_CAPTURE,
    OVERLAP_WAIT_CAPTURE,
    OVERLAP_ISSUE_ORIGINAL,
    OVERLAP_WAIT_ORIGINAL,
    OVERLAP_FIXUP,
    OVERLAP_WAIT_FIXUP,
    OVERLAP_RESPOND,
    SOURCE_SNAPSHOT_CAPTURE,
    SOURCE_SNAPSHOT_WAIT
  } state_e;
  state_e state_d, state_q, state_qq;
  // state_qq is the previous state signal. Useful to know from which state we come from.

  // Only maintenance reshuffles may drain residual words from the shared,
  // untagged SLDU lane stream. Normal instruction gaps must preserve the
  // reduction selector timing.
  assign sldu_drain_o = state_q == RESHUFFLE && ara_idle_i;

  // We need to memorize the element width used to store each vector on the lanes, so that we are
  // able to deshuffle it when needed.
  rvv_pkg::vew_e [31:0] eew_d, eew_q;
  // eew buffers for reshuffling
  rvv_pkg::vew_e reshuffle_eew_vs1_d, reshuffle_eew_vs1_q;
  rvv_pkg::vew_e reshuffle_eew_vs2_d, reshuffle_eew_vs2_q;
  rvv_pkg::vew_e reshuffle_eew_vd_d, reshuffle_eew_vd_q;
  logic [4:0] reshuffle_vs1_base_d, reshuffle_vs1_base_q;
  logic [4:0] reshuffle_vs2_base_d, reshuffle_vs2_base_q;
  logic [2:0] reshuffle_vs1_limit_d, reshuffle_vs1_limit_q;
  logic [2:0] reshuffle_vs2_limit_d, reshuffle_vs2_limit_q;
  rvv_pkg::vlmul_e reshuffle_lmul_vs1_d, reshuffle_lmul_vs1_q;
  rvv_pkg::vlmul_e reshuffle_lmul_vs2_d, reshuffle_lmul_vs2_q;
  rvv_pkg::vlmul_e reshuffle_lmul_vd_d, reshuffle_lmul_vd_q;
  // If the reg was not written, the content is unknown. No need to reshuffle
  // when writing with != EEW
  logic [31:0] eew_valid_d, eew_valid_q;

  function automatic int unsigned lmul_register_count(vlmul_e lmul);
    unique case (lmul)
      LMUL_2: lmul_register_count = 2;
      LMUL_4: lmul_register_count = 4;
      LMUL_8: lmul_register_count = 8;
      default: lmul_register_count = 1;
    endcase
  endfunction : lmul_register_count

  function automatic int unsigned lmul_element_capacity(
    vlmul_e lmul, vew_e eew
  );
    lmul_element_capacity = VLENB >> unsigned'(eew);
    unique case (lmul)
      LMUL_2  : lmul_element_capacity <<= 1;
      LMUL_4  : lmul_element_capacity <<= 2;
      LMUL_8  : lmul_element_capacity <<= 3;
      LMUL_1_2: lmul_element_capacity >>= 1;
      LMUL_1_4: lmul_element_capacity >>= 2;
      LMUL_1_8: lmul_element_capacity >>= 3;
      default:;
    endcase
  endfunction : lmul_element_capacity

  function automatic vlen_t slidedown_source_start(
    vlen_t vstart, elen_t stride, vlmul_e lmul, vew_e eew
  );
    automatic longint unsigned source_start = unsigned'(vstart) + unsigned'(stride);
    automatic int unsigned capacity = lmul_element_capacity(lmul, eew);
    slidedown_source_start = source_start > capacity ? vlen_t'(capacity)
                                                      : vlen_t'(source_start);
  endfunction : slidedown_source_start

  function automatic vlen_t slidedown_source_end(
    vlen_t vl, elen_t stride, logic use_scalar_op, vlmul_e lmul, vew_e eew
  );
    automatic longint unsigned source_end = unsigned'(vl) + unsigned'(stride);
    automatic int unsigned capacity = lmul_element_capacity(lmul, eew);
    // vslide1down obtains its last destination element from the scalar operand.
    if (use_scalar_op && source_end != 0) source_end -= 1;
    slidedown_source_end = source_end > capacity ? vlen_t'(capacity)
                                                 : vlen_t'(source_end);
  endfunction : slidedown_source_end

  function automatic logic [2:0] lmul_counter_limit(vlmul_e lmul);
    lmul_counter_limit = 3'(lmul_register_count(lmul) - 1);
  endfunction : lmul_counter_limit

  function automatic logic register_in_group(
    logic [4:0] reg_index, logic [4:0] group_base, vlmul_e group_lmul
  );
    register_in_group = unsigned'(reg_index) >= unsigned'(group_base) &&
                        unsigned'(reg_index) <
                          unsigned'(group_base) + lmul_register_count(group_lmul);
  endfunction : register_in_group

  function automatic logic group_needs_reshuffle(
    logic [4:0] base, vlmul_e lmul, vew_e target_eew
  );
    group_needs_reshuffle = 1'b0;
    for (int unsigned i = 0; i < 8; i++) begin
      if (i < lmul_register_count(lmul) && (unsigned'(base) + i) < 32)
        group_needs_reshuffle |= eew_valid_q[base + i] &&
                                 (eew_q[base + i] != target_eew);
    end
  endfunction : group_needs_reshuffle

  function automatic int unsigned segment_register_count(
    logic [2:0] nf, vlmul_e emul
  );
    // nf encodes the number of fields minus one. Fractional-EMUL fields still
    // start in distinct architectural registers.
    segment_register_count = (unsigned'(nf) + 1) * lmul_register_count(emul);
  endfunction : segment_register_count

  function automatic logic register_span_needs_reshuffle(
    logic [4:0] base, int unsigned count, vew_e target_eew
  );
    register_span_needs_reshuffle = 1'b0;
    for (int unsigned i = 0; i < 8; i++) begin
      if (i < count && (unsigned'(base) + i) < 32)
        register_span_needs_reshuffle |= eew_valid_q[base + i] &&
                                         (eew_q[base + i] != target_eew);
    end
  endfunction : register_span_needs_reshuffle

  function automatic int unsigned active_first_register(
    vew_e target_eew, vlen_t vstart
  );
    automatic int unsigned elements_per_register = VLENB >> unsigned'(target_eew);
    active_first_register = unsigned'(vstart) / elements_per_register;
  endfunction : active_first_register

  function automatic int unsigned active_register_count(
    vlmul_e lmul, vew_e target_eew, vlen_t vstart, vlen_t vl
  );
    automatic int unsigned elements_per_register = VLENB >> unsigned'(target_eew);
    automatic int unsigned register_count = lmul_register_count(lmul);
    automatic int unsigned first_register;
    automatic int unsigned last_register;
    active_register_count = 0;
    if (unsigned'(vl) > unsigned'(vstart)) begin
      first_register = unsigned'(vstart) / elements_per_register;
      last_register  = (unsigned'(vl) - 1) / elements_per_register;
      if (first_register < register_count) begin
        if (last_register >= register_count) last_register = register_count - 1;
        active_register_count = last_register - first_register + 1;
      end
    end
  endfunction : active_register_count

  function automatic logic [2:0] active_register_limit(
    vlmul_e lmul, vew_e target_eew, vlen_t vstart, vlen_t vl
  );
    automatic int unsigned count =
        active_register_count(lmul, target_eew, vstart, vl);
    active_register_limit = count == 0 ? '0 : 3'(count - 1);
  endfunction : active_register_limit

  function automatic logic active_group_needs_reshuffle(
    logic [4:0] base, vlmul_e lmul, vew_e target_eew,
    vlen_t vstart, vlen_t vl
  );
    automatic int unsigned first_register = active_first_register(target_eew, vstart);
    automatic int unsigned count =
        active_register_count(lmul, target_eew, vstart, vl);
    active_group_needs_reshuffle = 1'b0;
    for (int unsigned i = 0; i < 8; i++) begin
      if (i < count && (unsigned'(base) + first_register + i) < 32)
        active_group_needs_reshuffle |=
            eew_valid_q[base + first_register + i] &&
            (eew_q[base + first_register + i] != target_eew);
    end
  endfunction : active_group_needs_reshuffle

  function automatic logic active_group_has_mixed_eew(
    logic [4:0] base, vlmul_e lmul, vew_e element_eew,
    vlen_t vstart, vlen_t vl
  );
    automatic int unsigned first_register = active_first_register(element_eew, vstart);
    automatic int unsigned count =
        active_register_count(lmul, element_eew, vstart, vl);
    automatic logic found_reference = 1'b0;
    automatic vew_e reference_eew = EW8;
    active_group_has_mixed_eew = 1'b0;
    for (int unsigned i = 0; i < 8; i++) begin
      if (i < count && (unsigned'(base) + first_register + i) < 32 &&
          eew_valid_q[base + first_register + i]) begin
        if (!found_reference) begin
          found_reference = 1'b1;
          reference_eew = eew_q[base + first_register + i];
        end else begin
          active_group_has_mixed_eew |=
              eew_q[base + first_register + i] != reference_eew;
        end
      end
    end
  endfunction : active_group_has_mixed_eew

  function automatic logic widening_high_overlap(
    logic [4:0] vd, vlmul_e vd_lmul, logic [4:0] vs, vlmul_e vs_lmul
  );
    automatic int unsigned vd_regs = lmul_register_count(vd_lmul);
    automatic int unsigned vs_regs = lmul_register_count(vs_lmul);
    automatic logic integer_source_lmul = vs_lmul inside {LMUL_1, LMUL_2, LMUL_4};
    widening_high_overlap = integer_source_lmul && (vs_regs < vd_regs) &&
                            (unsigned'(vs) == unsigned'(vd) + vd_regs - vs_regs);
  endfunction : widening_high_overlap

  function automatic logic register_groups_overlap(
    logic [4:0] base_a, vlmul_e lmul_a,
    logic [4:0] base_b, vlmul_e lmul_b
  );
    automatic int unsigned end_a = unsigned'(base_a) + lmul_register_count(lmul_a);
    automatic int unsigned end_b = unsigned'(base_b) + lmul_register_count(lmul_b);
    register_groups_overlap = unsigned'(base_a) < end_b &&
                              unsigned'(base_b) < end_a;
  endfunction : register_groups_overlap

  // Save eew information before reshuffling
  rvv_pkg::vew_e eew_old_buffer_d, eew_old_buffer_q, eew_new_buffer_d, eew_new_buffer_q;
  // Helpers to handle reshuffling with LMUL > 1
  logic [2:0] rs_lmul_cnt_d, rs_lmul_cnt_q;
  logic [2:0] rs_lmul_cnt_limit_d, rs_lmul_cnt_limit_q;
  logic rs_mask_request_d, rs_mask_request_q;
  // Save vreg to be reshuffled before reshuffling
  logic [4:0] vs_buffer_d, vs_buffer_q;
  // Keep track of the registers to be reshuffled |vs1|vs2|vd|
  logic [2:0] reshuffle_req_d, reshuffle_req_q;
  logic legal_widen_overlap;
  logic legal_narrow_overlap;
  logic narrow_low_overlap_alias;
  logic legal_reduction_vd_overlap;
  logic overlap_prepared_d, overlap_prepared_q;
  logic overlap_snapshot_valid_d, overlap_snapshot_valid_q;
  logic [2:0] overlap_boundary_reg_d, overlap_boundary_reg_q;
  vlen_t overlap_snapshot_word_d, overlap_snapshot_word_q;
  logic overlap_original_accepted_d, overlap_original_accepted_q;
  logic [4:0] overlap_vd_d, overlap_vd_q;
  vlmul_e overlap_lmul_d, overlap_lmul_q;
  vew_e overlap_target_eew_d, overlap_target_eew_q;
  vlen_t overlap_vl_d, overlap_vl_q;
  vlen_t overlap_vstart_d, overlap_vstart_q;
  vlen_t overlap_prefix_vl_d, overlap_prefix_vl_q;
  logic [2:0] overlap_reg_index_d, overlap_reg_index_q;
  logic [4:0] overlap_current_vd_d, overlap_current_vd_q;
  logic [4:0] overlap_boundary_vd_d, overlap_boundary_vd_q;
  vlen_t overlap_elements_per_reg_d, overlap_elements_per_reg_q;
  vlen_t overlap_reg_first_element_d, overlap_reg_first_element_q;
  vew_e overlap_current_old_eew_d, overlap_current_old_eew_q;
  vew_e overlap_boundary_old_eew_d, overlap_boundary_old_eew_q;
  logic overlap_current_old_eew_valid_d, overlap_current_old_eew_valid_q;
  vew_e [7:0] overlap_old_eew_d, overlap_old_eew_q;
  logic [7:0] overlap_old_eew_valid_d, overlap_old_eew_valid_q;
  logic source_snapshot_valid_d, source_snapshot_valid_q;
  logic [4:0] source_snapshot_vs_d, source_snapshot_vs_q;
  vlmul_e source_snapshot_lmul_d, source_snapshot_lmul_q;
  vew_e source_snapshot_eew_d, source_snapshot_eew_q;
  vlen_t source_snapshot_vl_d, source_snapshot_vl_q;
  logic dual_source_layout_conflict;
  logic dual_source_layout_serialize;
  logic dual_source_snapshot_vs1;
  logic widen_accumulator_layout_conflict;
  logic masked_widen_layout_conflict;
  logic source_snapshot_resolves_widen;
  logic source_snapshot_replays_wide_vd;
  logic source_snapshot_preserves_narrow_vd;
  logic reduction_source_overlap_reshuffle;
  logic indexed_load_groups_overlap;
  logic indexed_load_index_overlap;
  // Segment memory operations end or ongoing?
  logic seg_mem_op_end, pending_seg_mem_op_d, pending_seg_mem_op_q;
  // Easily handle the riscv incoming instruction
  riscv::instruction_t instr;
  assign instr = riscv::instruction_t'(acc_req_i.insn);

`ifdef FOR_VERIFY
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VXSAT_FLOW") &&
        (csr_vxsat_d != csr_vxsat_q || |vxsat_flag_i)) begin
      $display("[ARA_VXSAT_CSR] t=%0t csr=%0b->%0b lane_flags=%b req=%0b/%0b insn=%08h",
               $time, csr_vxsat_q, csr_vxsat_d, vxsat_flag_i,
               acc_req_i.req_valid, acc_req_i.resp_ready, acc_req_i.insn);
    end
  end

  logic [63:0] verify_arch_seq_d, verify_arch_seq_q;
  logic verify_front_active_d, verify_front_active_q;
  logic [63:0] verify_active_arch_seq_d, verify_active_arch_seq_q;
  logic [31:0] verify_active_insn_d, verify_active_insn_q;
  logic [CVA6Cfg.TRANS_ID_BITS-1:0] verify_active_trans_id_d,
                                           verify_active_trans_id_q;
`endif

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q              <= NORMAL_OPERATION;
      state_qq             <= NORMAL_OPERATION;
      eew_q                <= '{default: rvv_pkg::EW8};
      eew_valid_q          <= '0;
      eew_old_buffer_q     <= rvv_pkg::EW8;
      eew_new_buffer_q     <= rvv_pkg::EW8;
      vs_buffer_q          <= '0;
      reshuffle_req_q      <= '0;
      rs_lmul_cnt_q        <= '0;
      rs_lmul_cnt_limit_q  <= '0;
      rs_mask_request_q    <= 1'b0;
      reshuffle_eew_vs1_q  <= rvv_pkg::EW8;
      reshuffle_eew_vs2_q  <= rvv_pkg::EW8;
      reshuffle_eew_vd_q   <= rvv_pkg::EW8;
      reshuffle_vs1_base_q <= '0;
      reshuffle_vs2_base_q <= '0;
      reshuffle_vs1_limit_q <= '0;
      reshuffle_vs2_limit_q <= '0;
      reshuffle_lmul_vs1_q <= rvv_pkg::LMUL_1;
      reshuffle_lmul_vs2_q <= rvv_pkg::LMUL_1;
      reshuffle_lmul_vd_q  <= rvv_pkg::LMUL_1;
      overlap_prepared_q    <= 1'b0;
      overlap_snapshot_valid_q <= 1'b0;
      overlap_boundary_reg_q <= '0;
      overlap_snapshot_word_q <= '0;
      overlap_original_accepted_q <= 1'b0;
      overlap_vd_q          <= '0;
      overlap_lmul_q        <= rvv_pkg::LMUL_1;
      overlap_target_eew_q  <= rvv_pkg::EW8;
      overlap_vl_q          <= '0;
      overlap_vstart_q      <= '0;
      overlap_prefix_vl_q   <= '0;
      overlap_reg_index_q   <= '0;
      overlap_current_vd_q  <= '0;
      overlap_boundary_vd_q <= '0;
      overlap_elements_per_reg_q <= '0;
      overlap_reg_first_element_q <= '0;
      overlap_current_old_eew_q <= rvv_pkg::EW8;
      overlap_boundary_old_eew_q <= rvv_pkg::EW8;
      overlap_current_old_eew_valid_q <= 1'b0;
      overlap_old_eew_q     <= '{default: rvv_pkg::EW8};
      overlap_old_eew_valid_q <= '0;
      source_snapshot_valid_q <= 1'b0;
      source_snapshot_vs_q <= '0;
      source_snapshot_lmul_q <= rvv_pkg::LMUL_1;
      source_snapshot_eew_q <= rvv_pkg::EW8;
      source_snapshot_vl_q <= '0;
      pending_seg_mem_op_q <= 1'b0;
`ifdef FOR_VERIFY
      verify_arch_seq_q        <= '0;
      verify_front_active_q    <= 1'b0;
      verify_active_arch_seq_q <= '0;
      verify_active_insn_q     <= '0;
      verify_active_trans_id_q <= '0;
`endif
    end else begin
      state_q              <= state_d;
      state_qq             <= state_q;
      eew_q                <= eew_d;
      eew_valid_q          <= eew_valid_d;
      eew_old_buffer_q     <= eew_old_buffer_d;
      eew_new_buffer_q     <= eew_new_buffer_d;
      vs_buffer_q          <= vs_buffer_d;
      reshuffle_req_q      <= reshuffle_req_d;
      rs_lmul_cnt_q        <= rs_lmul_cnt_d;
      rs_lmul_cnt_limit_q  <= rs_lmul_cnt_limit_d;
      rs_mask_request_q    <= rs_mask_request_d;
      reshuffle_eew_vs1_q  <= reshuffle_eew_vs1_d;
      reshuffle_eew_vs2_q  <= reshuffle_eew_vs2_d;
      reshuffle_eew_vd_q   <= reshuffle_eew_vd_d;
      reshuffle_vs1_base_q <= reshuffle_vs1_base_d;
      reshuffle_vs2_base_q <= reshuffle_vs2_base_d;
      reshuffle_vs1_limit_q <= reshuffle_vs1_limit_d;
      reshuffle_vs2_limit_q <= reshuffle_vs2_limit_d;
      reshuffle_lmul_vs1_q <= reshuffle_lmul_vs1_d;
      reshuffle_lmul_vs2_q <= reshuffle_lmul_vs2_d;
      reshuffle_lmul_vd_q  <= reshuffle_lmul_vd_d;
      overlap_prepared_q    <= overlap_prepared_d;
      overlap_snapshot_valid_q <= overlap_snapshot_valid_d;
      overlap_boundary_reg_q <= overlap_boundary_reg_d;
      overlap_snapshot_word_q <= overlap_snapshot_word_d;
      overlap_original_accepted_q <= overlap_original_accepted_d;
      overlap_vd_q          <= overlap_vd_d;
      overlap_lmul_q        <= overlap_lmul_d;
      overlap_target_eew_q  <= overlap_target_eew_d;
      overlap_vl_q          <= overlap_vl_d;
      overlap_vstart_q      <= overlap_vstart_d;
      overlap_prefix_vl_q   <= overlap_prefix_vl_d;
      overlap_reg_index_q   <= overlap_reg_index_d;
      overlap_current_vd_q  <= overlap_current_vd_d;
      overlap_boundary_vd_q <= overlap_boundary_vd_d;
      overlap_elements_per_reg_q <= overlap_elements_per_reg_d;
      overlap_reg_first_element_q <= overlap_reg_first_element_d;
      overlap_current_old_eew_q <= overlap_current_old_eew_d;
      overlap_boundary_old_eew_q <= overlap_boundary_old_eew_d;
      overlap_current_old_eew_valid_q <= overlap_current_old_eew_valid_d;
      overlap_old_eew_q     <= overlap_old_eew_d;
      overlap_old_eew_valid_q <= overlap_old_eew_valid_d;
      source_snapshot_valid_q <= source_snapshot_valid_d;
      source_snapshot_vs_q <= source_snapshot_vs_d;
      source_snapshot_lmul_q <= source_snapshot_lmul_d;
      source_snapshot_eew_q <= source_snapshot_eew_d;
      source_snapshot_vl_q <= source_snapshot_vl_d;
      pending_seg_mem_op_q <= pending_seg_mem_op_d;
`ifdef FOR_VERIFY
      verify_arch_seq_q        <= verify_arch_seq_d;
      verify_front_active_q    <= verify_front_active_d;
      verify_active_arch_seq_q <= verify_active_arch_seq_d;
      verify_active_insn_q     <= verify_active_insn_d;
      verify_active_trans_id_q <= verify_active_trans_id_d;
`endif
    end
  end

`ifdef FOR_VERIFY
  longint unsigned debug_reshuffle_idle_cycle_q;

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      debug_reshuffle_idle_cycle_q <= '0;
    end else begin
      debug_reshuffle_idle_cycle_q <= debug_reshuffle_idle_cycle_q + 1'b1;
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_RESHUFFLE_IDLE") &&
        verify_front_active_q &&
        verify_active_insn_q == 32'h49332257 &&
        (debug_reshuffle_idle_cycle_q % 100 == 0)) begin
      $display("[ARA_RESHUFFLE_IDLE] t=%0t state=%0d ara_idle=%0b sldu_idle=%0b req=%0b/%0b pending=%b",
               $time, state_q, ara_idle_i, sldu_idle_i, ara_req_valid,
               ara_req_ready_i, reshuffle_req_q);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_EEW") &&
        ((eew_d[8] != eew_q[8]) || (eew_d[9] != eew_q[9]) ||
         (eew_d[10] != eew_q[10]) || (eew_d[11] != eew_q[11]) ||
         (eew_d[12] != eew_q[12]) || (eew_d[13] != eew_q[13]) ||
         (eew_d[14] != eew_q[14]) || (eew_d[15] != eew_q[15]) ||
         (eew_valid_d[15:8] != eew_valid_q[15:8]))) begin
      $display("[ARA_EEW] t=%0t arch=%0d insn=%h state=%0d in_v/r=%0b/%0b in_op=%0d in_vd=v%0d in_use_vd=%0b in_emul=%0d in_vsew=%0d seg_v=%0b seg_op=%0d seg_vd=v%0d seg_use_vd=%0b seg_emul=%0d seg_vsew=%0d valid=%b->%b eew=%0d%0d%0d%0d_%0d%0d%0d%0d->%0d%0d%0d%0d_%0d%0d%0d%0d",
               $time, verify_active_arch_seq_q, verify_active_insn_q, state_q,
               ara_req_valid, ara_req_ready_i, ara_req.op, ara_req.vd,
               ara_req.use_vd, ara_req.emul, ara_req.vtype.vsew,
               ara_req_valid_d, ara_req_d.op, ara_req_d.vd,
               ara_req_d.use_vd, ara_req_d.emul, ara_req_d.vtype.vsew,
               eew_valid_q[15:8], eew_valid_d[15:8],
               eew_q[8], eew_q[9], eew_q[10], eew_q[11],
               eew_q[12], eew_q[13], eew_q[14], eew_q[15],
               eew_d[8], eew_d[9], eew_d[10], eew_d[11],
               eew_d[12], eew_d[13], eew_d[14], eew_d[15]);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_EEW") &&
        verify_front_active_q &&
        (verify_active_insn_q inside {32'h25c82657, 32'hbc86b257}) &&
        (ara_req_valid || ara_req_valid_d || ara_req_valid_o)) begin
      $display("[ARA_EEW_REQ] t=%0t arch=%0d insn=%h state=%0d ready=%0b in_v=%0b in_op=%0d in_vd=v%0d in_use_vd=%0b in_emul=%0d in_vsew=%0d seg_v=%0b seg_op=%0d seg_vd=v%0d seg_use_vd=%0b seg_emul=%0d seg_vsew=%0d out_v=%0b out_op=%0d out_vd=v%0d out_use_vd=%0b out_emul=%0d out_vsew=%0d eew=%0d%0d%0d%0d_%0d%0d%0d%0d",
               $time, verify_active_arch_seq_q, verify_active_insn_q, state_q,
               ara_req_ready_i, ara_req_valid, ara_req.op, ara_req.vd,
               ara_req.use_vd, ara_req.emul, ara_req.vtype.vsew,
               ara_req_valid_d, ara_req_d.op, ara_req_d.vd,
               ara_req_d.use_vd, ara_req_d.emul, ara_req_d.vtype.vsew,
               ara_req_valid_o, ara_req_o.op, ara_req_o.vd,
               ara_req_o.use_vd, ara_req_o.emul, ara_req_o.vtype.vsew,
               eew_q[8], eew_q[9], eew_q[10], eew_q[11],
               eew_q[12], eew_q[13], eew_q[14], eew_q[15]);
    end
  end

  // Opt-in metadata trace for the mixed-control narrowing failure.  This is
  // intentionally verification-only and does not alter the request path.
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_NARROW_CHAIN") &&
        verify_front_active_q &&
        (verify_active_insn_q inside {
          32'hbe05c057, 32'hb60d3a57, 32'hbc86b257, 32'hb1820c57
        }) &&
        ((state_d != state_q) || (ara_req_valid && ara_req_ready_i))) begin
      $display("[ARA_NARROW_CHAIN] t=%0t insn=%h state=%0d->%0d fire=%b op=%0d vd=v%0d vs2=v%0d emul=%0d eew=%0d->%0d vl=%0d vstart=%0d reshuffle=%b cnt=%0d/%0d buf=v%0d old=%0d new=%0d valid0_7=%b eew0_7=%0d%0d%0d%0d_%0d%0d%0d%0d",
               $time, verify_active_insn_q, state_q, state_d,
               ara_req_valid && ara_req_ready_i, ara_req.op, ara_req.vd,
               ara_req.vs2, ara_req.emul, ara_req.eew_vs2,
               ara_req.vtype.vsew, ara_req.vl, ara_req.vstart,
               reshuffle_req_q, rs_lmul_cnt_q, rs_lmul_cnt_limit_q,
               vs_buffer_q, eew_old_buffer_q, eew_new_buffer_q,
               eew_valid_q[7:0], eew_q[0], eew_q[1], eew_q[2], eew_q[3],
               eew_q[4], eew_q[5], eew_q[6], eew_q[7]);
    end
  end

  // Opt-in trace for a held architectural request that repeatedly injects
  // reshuffle uops. This block is excluded from synthesis builds.
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_RESHUFFLE") &&
        verify_front_active_q &&
        (verify_active_insn_q inside {
          32'hc3090c57, 32'h9f83b457, 32'hf2062857, 32'h3e4a3257,
          32'h3eb345d7, 32'h1ebdab57
        }) &&
        ((state_d != state_q) || (ara_req_valid && ara_req_ready_i))) begin
      $display("[ARA_RESHUFFLE] t=%0t state=%0d->%0d fire=%b op=%0d vd=%0d vs2=%0d vs1=%0d reqs=%b cnt=%0d/%0d mask=%b buf=v%0d old=%0d new=%0d lmul(vd/vs2/vs1)=%0d/%0d/%0d valid0_7=%h eew0_7=%0d%0d%0d%0d_%0d%0d%0d%0d valid16_31=%h eew16_31=%0d%0d%0d%0d_%0d%0d%0d%0d_%0d%0d%0d%0d_%0d%0d%0d%0d",
               $time, state_q, state_d, ara_req_valid && ara_req_ready_i,
               ara_req.op, ara_req.vd, ara_req.vs2, ara_req.vs1,
               reshuffle_req_q, rs_lmul_cnt_q, rs_lmul_cnt_limit_q,
               rs_mask_request_q, vs_buffer_q, eew_old_buffer_q,
               eew_new_buffer_q, reshuffle_lmul_vd_q,
               reshuffle_lmul_vs2_q, reshuffle_lmul_vs1_q,
               eew_valid_q[7:0],
               eew_q[0], eew_q[1], eew_q[2], eew_q[3],
               eew_q[4], eew_q[5], eew_q[6], eew_q[7],
               eew_valid_q[31:16],
               eew_q[16], eew_q[17], eew_q[18], eew_q[19],
               eew_q[20], eew_q[21], eew_q[22], eew_q[23],
               eew_q[24], eew_q[25], eew_q[26], eew_q[27],
               eew_q[28], eew_q[29], eew_q[30], eew_q[31]);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_OVERLAP") &&
        ((state_q != state_d) || (ara_req_valid && ara_req_ready_i)) &&
        (state_q inside {OVERLAP_PREFIX_FIXUP, OVERLAP_WAIT_PREFIX_FIXUP,
                         OVERLAP_CAPTURE, OVERLAP_WAIT_CAPTURE,
                         OVERLAP_ISSUE_ORIGINAL, OVERLAP_WAIT_ORIGINAL,
                         OVERLAP_FIXUP, OVERLAP_WAIT_FIXUP, OVERLAP_RESPOND} ||
         state_d inside {OVERLAP_PREFIX_FIXUP, OVERLAP_WAIT_PREFIX_FIXUP,
                         OVERLAP_CAPTURE, OVERLAP_WAIT_CAPTURE,
                         OVERLAP_ISSUE_ORIGINAL, OVERLAP_WAIT_ORIGINAL,
                         OVERLAP_FIXUP, OVERLAP_WAIT_FIXUP, OVERLAP_RESPOND})) begin
      $display("[ARA_OVERLAP] t=%0t state=%0d->%0d idle=%b req=%b/%b pipe=%b vd=v%0d vs2=v%0d emul=%0d eew=%0d->%0d vl=%0d vstart=%0d idx=%0d old_valid=%b snapshot=%b prepared=%b",
               $time, state_q, state_d, ara_idle_i, ara_req_valid,
               ara_req_ready_i, ara_req_valid_o, ara_req.vd, ara_req.vs2,
               ara_req.emul, ara_req.eew_vs2, ara_req.vtype.vsew,
               ara_req.vl, ara_req.vstart, overlap_reg_index_q,
               overlap_current_old_eew_valid_q,
               overlap_snapshot_valid_q, overlap_prepared_q);
    end
  end

`ifndef SYNTHESIS
  always_ff @(posedge clk_i) begin
    if (rst_ni && state_q inside {OVERLAP_PREFIX_FIXUP, OVERLAP_FIXUP}) begin
      assert (overlap_current_vd_q == overlap_vd_q + overlap_reg_index_q)
        else $fatal(1, "Overlap repair destination context is misaligned");
      assert (overlap_current_old_eew_q == overlap_old_eew_q[overlap_reg_index_q])
        else $fatal(1, "Overlap repair EEW context is misaligned");
      assert (overlap_current_old_eew_valid_q ==
              overlap_old_eew_valid_q[overlap_reg_index_q])
        else $fatal(1, "Overlap repair EEW-valid context is misaligned");
      assert (overlap_reg_first_element_q == vlen_t'(
                  unsigned'(overlap_reg_index_q) *
                  unsigned'(overlap_elements_per_reg_q)))
        else $fatal(1, "Overlap repair element context is misaligned");
    end
  end
`endif

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_LAYOUT428") &&
        verify_front_active_q && verify_active_insn_q == 32'h944be457 &&
        ((state_q != state_d) || ara_req_valid || ara_req_valid_d || ara_req_valid_o)) begin
      $display("[ARA_LAYOUT428] t=%0t state=%0d->%0d req=%b->%b pipe=%b/%b op=%0d vd=v%0d vs2=v%0d eew2=%0d emul=%0d vsew=%0d vl=%0d resh=%b cnt=%0d/%0d buf=v%0d old=%0d new=%0d valid0_15=%h eew0_15=%0d%0d%0d%0d_%0d%0d%0d%0d_%0d%0d%0d%0d_%0d%0d%0d%0d",
               $time, state_q, state_d, ara_req_valid, ara_req_ready_i,
               ara_req_valid_d, ara_req_valid_o, ara_req.op, ara_req.vd,
               ara_req.vs2, ara_req.eew_vs2, ara_req.emul,
               ara_req.vtype.vsew, ara_req.vl, reshuffle_req_q,
               rs_lmul_cnt_q, rs_lmul_cnt_limit_q, vs_buffer_q,
               eew_old_buffer_q, eew_new_buffer_q, eew_valid_q[15:0],
               eew_q[0], eew_q[1], eew_q[2], eew_q[3],
               eew_q[4], eew_q[5], eew_q[6], eew_q[7],
               eew_q[8], eew_q[9], eew_q[10], eew_q[11],
               eew_q[12], eew_q[13], eew_q[14], eew_q[15]);
    end
  end

`endif

  // We need to know if the source operands have a different LMUL constraint than the destination
  // register
  rvv_pkg::vlmul_e lmul_vs2, lmul_vs1;

  // Helper signals to discriminate between config/csr, load/store instructions and the others
  logic is_config, is_vload, is_vstore;
  // Mask memory operations use evl=ceil(vl/8), with vstart measured in bytes.
  logic mask_mem_noop;
  // Whole-register memory-ops / move should be executed even when vl == 0
  logic ignore_zero_vl_check;
  // Helper signals to identify memory operations with vl == 0. They must acknoledge Ariane to update
  // its counters of pending memory operations
  // Ara should tell Ariane when a memory operation is completed, so that it can modify
  // its pending load/store counters.
  // A memory operation can be completed both when it is over and when csr_vl_q == 0. In the latter case,
  // Ara's decoder answers immediately, and this can cause a collision with an answer from Ara's VLSU.
  // To avoid collisions, we give precedence to the VLSU, and we delay the csr_vl_q == 0 memory op
  // completion signal if a collision occurs
  logic load_zero_vl, store_zero_vl;
  // Do not checks vregs validity against current LMUL
  logic skip_lmul_checks;
  // Are we decoding?
  logic is_decoding;
  // Is this an in-lane operation?
  logic in_lane_op;
  // Layout to which the second source group must be normalized. VCOMPRESS
  // carries its packed-mask layout separately and consumes data at SEW.
  rvv_pkg::vew_e vs2_reshuffle_eew;
  vlen_t vs2_reshuffle_vstart, vs2_reshuffle_vl;
  // Gather indices are active only over [vstart, vl), but each of them may
  // address any element in the complete source group up to VLMAX.
  logic reshuffle_full_vs2_group;
  logic indexed_mixed_vs2_layout;

  // If the vslideup offset is greater than csr_vl_q, the vslideup has no effects
  logic null_vslideup;
  // Does the selected reg group for the selected EMUL have same EEW encoding?
  logic is_same_eew;

  // Pipeline the VLSU's load and store complete signals, for timing reasons
  logic load_complete, load_complete_q;
  logic store_complete, store_complete_q;
  logic illegal_insn_load, illegal_insn_store;
  `FF(load_complete_q, load_complete || illegal_insn_load, 1'b0)
  `FF(store_complete_q, store_complete || illegal_insn_store, 1'b0)

  // NP2 Slide support
  logic is_stride_np2;
  logic [idx_width(8*NrLanes)-1:0] sldu_intra_word_byte_offset;
  logic [idx_width(idx_width(8*NrLanes)):0] sldu_popc;

  // The lane operand requester skips complete aggregate words.  The SLDU only
  // permutes the residual byte offset within one NrLanes*ELEN aggregate, so its
  // NP2 decomposition decision must use that same residual offset.
  assign sldu_intra_word_byte_offset =
      ara_req.stride << unsigned'(ara_req.vtype.vsew);

  // Does the residual offset require more than one power-of-two permutation?
  popcount #(
    .INPUT_WIDTH (idx_width(8*NrLanes))
  ) i_np2_stride (
    .data_i    (sldu_intra_word_byte_offset),
    .popcount_o(sldu_popc                 )
  );

  assign is_stride_np2 = sldu_popc > 1;

  // Segment-memory instruction sequencer
  // Decompose the segment memory operations into non-segment memory operations
  // This is a low-impact and low-performance implementation
  logic is_segment_mem_op;
  logic illegal_insn;

  // The handshake signals are just passed-through if the insn is non-segment
  ara_resp_t ara_resp;
  logic ara_resp_valid;

  segment_sequencer #(
    .SegSupport(SegSupport),
    .VLEN      (VLEN      ),
    .ara_req_t (ara_req_t ),
    .ara_resp_t(ara_resp_t)
  ) i_segment_sequencer (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .ara_idle_i(ara_idle_i),
    .is_segment_mem_op_i(is_segment_mem_op),
    .illegal_insn_i(illegal_insn),
    .is_vload_i(is_vload),
    .seg_mem_op_end_o(seg_mem_op_end),
    .load_complete_i(load_complete_i),
    .load_complete_o(load_complete),
    .store_complete_i(store_complete_i),
    .store_complete_o(store_complete),
    .eew_i(eew_q),
    .ara_req_i(ara_req),
    .ara_req_o(ara_req_d),
    .ara_req_valid_i(ara_req_valid),
    .ara_req_valid_o(ara_req_valid_d),
    .ara_req_ready_i(ara_req_ready_i),
    .ara_resp_i(ara_resp_i),
    .ara_resp_o(ara_resp),
    .ara_resp_valid_i(ara_resp_valid_i),
    .ara_resp_valid_o(ara_resp_valid)
  );

  // LSU exception flush FSM
  // Upon exception, Ara should be flushed as soon as no operations older than the store are ongoing.
  // For this reason, we should first wait until Ara is idle. Then, we can flush.
  // Flushes are needed after a faulty memory operation. Even loads need a flush if they access the VRF.
  logic lsu_ex_flush_start, lsu_ex_flush_done, lsu_ex_flush_done_q;
  typedef enum logic [1:0] {
    LSU_FLUSH_IDLE,
    LSU_FLUSH,
    LSU_FLUSH_WAIT,
    LSU_FLUSH_DONE
  } lsu_ex_flush_fsm_e;
  lsu_ex_flush_fsm_e lsu_ex_state_d, lsu_ex_state_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      lsu_ex_state_q <= LSU_FLUSH_IDLE;
      lsu_ex_flush_done_q  <= 1'b0;
    end else begin
      lsu_ex_state_q <= lsu_ex_state_d;
      lsu_ex_flush_done_q  <= lsu_ex_flush_done_i;
    end
  end

  always_comb begin : i_lsu_ex_flush_fsm
    lsu_ex_state_d = lsu_ex_state_q;
    lsu_ex_flush_o = 1'b0;
    lsu_ex_flush_done = 1'b0;

    case (lsu_ex_state_q)
      LSU_FLUSH_IDLE: begin
        if (lsu_ex_flush_start)
          lsu_ex_state_d = LSU_FLUSH;
      end
      LSU_FLUSH: begin
        lsu_ex_flush_o = 1'b1;
          lsu_ex_state_d = LSU_FLUSH_WAIT;
      end
      LSU_FLUSH_WAIT: begin
        if (lsu_ex_flush_done_q)
          lsu_ex_state_d = LSU_FLUSH_DONE;
      end
      LSU_FLUSH_DONE: begin
        lsu_ex_flush_done = 1'b1;
        lsu_ex_state_d = LSU_FLUSH_IDLE;
      end
    endcase
  end

  ///////////////
  //  Decoder  //
  ///////////////

  elen_t vfmvfs_result;

  always_comb begin: p_decoder
    // Default values
    csr_vstart_d     = csr_vstart_q;
    csr_vl_d         = csr_vl_q;
    csr_vtype_d      = csr_vtype_q;
    state_d      = state_q;
    eew_d        = eew_q;
    eew_valid_d  = eew_valid_q;
    lmul_vs2     = csr_vtype_q.vlmul;
    lmul_vs1     = csr_vtype_q.vlmul;

`ifdef FOR_VERIFY
    verify_arch_seq_d        = verify_arch_seq_q;
    verify_front_active_d    = verify_front_active_q;
    verify_active_arch_seq_d = verify_active_arch_seq_q;
    verify_active_insn_d     = verify_active_insn_q;
    verify_active_trans_id_d = verify_active_trans_id_q;
    if (acc_req_i.req_valid && !verify_front_active_q) begin
      verify_front_active_d    = 1'b1;
      verify_active_arch_seq_d = verify_arch_seq_q;
      verify_active_insn_d     = acc_req_i.insn;
      verify_active_trans_id_d = acc_req_i.trans_id;
    end
`endif

    reshuffle_req_d     = reshuffle_req_q;
    eew_old_buffer_d    = eew_old_buffer_q;
    eew_new_buffer_d    = eew_new_buffer_q;
    vs_buffer_d         = vs_buffer_q;
    reshuffle_eew_vs1_d = reshuffle_eew_vs1_q;
    reshuffle_eew_vs2_d = reshuffle_eew_vs2_q;
    reshuffle_eew_vd_d  = reshuffle_eew_vd_q;
    reshuffle_vs1_base_d = reshuffle_vs1_base_q;
    reshuffle_vs2_base_d = reshuffle_vs2_base_q;
    reshuffle_vs1_limit_d = reshuffle_vs1_limit_q;
    reshuffle_vs2_limit_d = reshuffle_vs2_limit_q;
    reshuffle_lmul_vs1_d = reshuffle_lmul_vs1_q;
    reshuffle_lmul_vs2_d = reshuffle_lmul_vs2_q;
    reshuffle_lmul_vd_d  = reshuffle_lmul_vd_q;
    legal_widen_overlap = 1'b0;
    legal_narrow_overlap = 1'b0;
    narrow_low_overlap_alias = 1'b0;
    legal_reduction_vd_overlap = 1'b0;
    overlap_prepared_d = overlap_prepared_q;
    overlap_snapshot_valid_d = overlap_snapshot_valid_q;
    overlap_boundary_reg_d = overlap_boundary_reg_q;
    overlap_snapshot_word_d = overlap_snapshot_word_q;
    overlap_original_accepted_d = overlap_original_accepted_q;
    overlap_vd_d = overlap_vd_q;
    overlap_lmul_d = overlap_lmul_q;
    overlap_target_eew_d = overlap_target_eew_q;
    overlap_vl_d = overlap_vl_q;
    overlap_vstart_d = overlap_vstart_q;
    overlap_prefix_vl_d = overlap_prefix_vl_q;
    overlap_reg_index_d = overlap_reg_index_q;
    overlap_current_vd_d = overlap_current_vd_q;
    overlap_boundary_vd_d = overlap_boundary_vd_q;
    overlap_elements_per_reg_d = overlap_elements_per_reg_q;
    overlap_reg_first_element_d = overlap_reg_first_element_q;
    overlap_current_old_eew_d = overlap_current_old_eew_q;
    overlap_boundary_old_eew_d = overlap_boundary_old_eew_q;
    overlap_current_old_eew_valid_d = overlap_current_old_eew_valid_q;
    overlap_old_eew_d = overlap_old_eew_q;
    overlap_old_eew_valid_d = overlap_old_eew_valid_q;
    source_snapshot_valid_d = source_snapshot_valid_q;
    source_snapshot_vs_d = source_snapshot_vs_q;
    source_snapshot_lmul_d = source_snapshot_lmul_q;
    source_snapshot_eew_d = source_snapshot_eew_q;
    source_snapshot_vl_d = source_snapshot_vl_q;
    dual_source_layout_conflict = 1'b0;
    dual_source_layout_serialize = 1'b0;
    dual_source_snapshot_vs1 = 1'b0;
    widen_accumulator_layout_conflict = 1'b0;
    masked_widen_layout_conflict = 1'b0;
    source_snapshot_resolves_widen = 1'b0;
    source_snapshot_replays_wide_vd = 1'b0;
    source_snapshot_preserves_narrow_vd = 1'b0;
    reduction_source_overlap_reshuffle = 1'b0;
    indexed_load_groups_overlap = 1'b0;
    indexed_load_index_overlap = 1'b0;

    pending_seg_mem_op_d = pending_seg_mem_op_q;

    rs_lmul_cnt_d       = '0;
    rs_lmul_cnt_limit_d = '0;
    rs_mask_request_d   = 1'b0;

    illegal_insn = 1'b0;
    illegal_insn_load  = 1'b0;
    illegal_insn_store = 1'b0;
    csr_vxsat_d      = csr_vxsat_q;
    csr_vxrm_d       = csr_vxrm_q;

    is_vload      = 1'b0;
    is_vstore     = 1'b0;
    mask_mem_noop = 1'b0;
    load_zero_vl  = 1'b0;
    store_zero_vl = 1'b0;

    skip_lmul_checks     = 1'b0;

    lsu_ex_flush_start = 1'b0;

    null_vslideup = 1'b0;

    vfmvfs_result = ara_resp_i.resp;

    is_decoding     = 1'b0;
    in_lane_op      = 1'b0;

    is_segment_mem_op = 1'b0;

    acc_resp_o       = '{
      trans_id      : acc_req_i.trans_id,
      load_complete : load_zero_vl | load_complete_q,
      store_complete: store_zero_vl | store_complete_q,
      store_pending : store_pending_i,
      fflags_valid  : |fflags_ex_valid_i,
      default       : '0
    };
    acc_resp_o.req_ready  = 1'b0;
    acc_resp_o.resp_valid = 1'b0;

    // fflags
    for (int lane = 0; lane < NrLanes; lane++) acc_resp_o.fflags |= fflags_ex_i[lane];

    ara_req = '{
      vl           : csr_vl_q,
      vstart       : csr_vstart_q,
      vtype        : csr_vtype_q,
      emul         : csr_vtype_q.vlmul,
      eew_vs1      : csr_vtype_q.vsew,
      old_eew_vs1  : csr_vtype_q.vsew,
      eew_vs2      : csr_vtype_q.vsew,
      old_eew_vs2  : csr_vtype_q.vsew,
      eew_vd_op    : csr_vtype_q.vsew,
      eew_vmask    : eew_q[VMASK],
      cvt_resize   : CVT_SAME,
      fp_rm          : fpnew_pkg::RNE,
      op             : VADD,
      conversion_vs1 : OpQueueConversionNone,
      conversion_vs2 : OpQueueConversionNone,
`ifdef FOR_VERIFY
      verify_arch_seq : verify_active_arch_seq_d,
      verify_arch_insn: verify_active_insn_d,
      verify_trans_id : verify_active_trans_id_d,
`endif
      default      : '0
    };
    ara_req_valid = 1'b0;
    vs2_reshuffle_eew = csr_vtype_q.vsew;
    vs2_reshuffle_vstart = csr_vstart_q;
    vs2_reshuffle_vl = csr_vl_q;
    reshuffle_full_vs2_group = 1'b0;
    indexed_mixed_vs2_layout = 1'b0;

    is_config            = 1'b0;
    ignore_zero_vl_check = 1'b0;

    // Saturation in any lane will raise vxsat flag
    csr_vxsat_d |= |vxsat_flag_i;
    // Fixed-point rounding mode is applied to all lanes
    for (int lane = 0; lane < NrLanes; lane++) alu_vxrm_o[lane] = csr_vxrm_q;
    // Rounding mode is shared between all lanes
    for (int lane = 0; lane < NrLanes; lane++) acc_resp_o.fflags |= fflags_ex_i[lane];
    // Special states
    case (state_q)
      // Is Ara idle?
      WAIT_IDLE: begin
        if (!ara_req_valid_o && ara_idle_i) state_d = NORMAL_OPERATION;
      end

      // Wait for idle and then flush the stu-related pipes.
      // This operation is not IPC critical.
      WAIT_IDLE_FLUSH: begin
        if ((lsu_ex_state_q == LSU_FLUSH_IDLE) && ara_idle_i) begin
          // Start the flush FSM
          lsu_ex_flush_start = 1'b1;
        end
        // Get back to normal operation once the flush is over
        if (lsu_ex_state_q == LSU_FLUSH_DONE) begin
          state_d = NORMAL_OPERATION;
        end
      end

      OVERLAP_PREFIX_FIXUP: begin
        automatic logic [3:0] reg_count =
            4'(lmul_register_count(overlap_lmul_q));
        automatic vlen_t preserved_elements;
        automatic logic needs_fixup;

        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;

        if (overlap_prefix_vl_q <= overlap_reg_first_element_q)
          preserved_elements = '0;
        else if (overlap_prefix_vl_q >=
                 overlap_reg_first_element_q + overlap_elements_per_reg_q)
          preserved_elements = overlap_elements_per_reg_q;
        else
          preserved_elements = overlap_prefix_vl_q - overlap_reg_first_element_q;

        needs_fixup = preserved_elements != 0 &&
                      overlap_current_old_eew_valid_q &&
                      overlap_current_old_eew_q != overlap_target_eew_q;

        if (needs_fixup) begin
          // Re-encode only a destination prefix known not to contain an
          // overlapping source. This covers preserved narrowing elements below
          // vstart and a widening accumulator below the high source group.
          ara_req_valid         = ara_idle_i;
          ara_req.emul          = LMUL_1;
          ara_req.vstart        = '0;
          ara_req.vs2           = overlap_current_vd_q;
          ara_req.eew_vs2       = overlap_current_old_eew_q;
          ara_req.use_vs2       = 1'b1;
          ara_req.vd            = overlap_current_vd_q;
          ara_req.use_vd        = 1'b1;
          ara_req.op            = ara_pkg::VSLIDEDOWN;
          ara_req.stride        = '0;
          ara_req.use_scalar_op = 1'b0;
          ara_req.vm            = 1'b1;
          ara_req.vtype.vsew    = overlap_target_eew_q;
          ara_req.vl            = preserved_elements;
          ara_req.scale_vl      = 1'b1;
        end

        if (!needs_fixup || (ara_idle_i && ara_req_ready_i)) begin
          if ({1'b0, overlap_reg_index_q} + 1'b1 == reg_count) begin
            overlap_reg_index_d = '0;
            overlap_current_vd_d = overlap_vd_q;
            overlap_reg_first_element_d = '0;
            overlap_current_old_eew_d = overlap_old_eew_q[0];
            overlap_current_old_eew_valid_d = overlap_old_eew_valid_q[0];
            state_d = OVERLAP_WAIT_PREFIX_FIXUP;
          end else begin
            overlap_reg_index_d = overlap_reg_index_q + 1'b1;
            overlap_current_vd_d = overlap_current_vd_q + 1'b1;
            overlap_reg_first_element_d = overlap_reg_first_element_q +
                overlap_elements_per_reg_q;
            overlap_current_old_eew_d =
                overlap_old_eew_q[overlap_reg_index_q + 1'b1];
            overlap_current_old_eew_valid_d =
                overlap_old_eew_valid_q[overlap_reg_index_q + 1'b1];
          end
        end
      end

      OVERLAP_WAIT_PREFIX_FIXUP: begin
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;
        if (!ara_req_valid_o && ara_idle_i)
          state_d = overlap_snapshot_valid_q ? OVERLAP_CAPTURE
                                             : OVERLAP_ISSUE_ORIGINAL;
      end

      OVERLAP_CAPTURE: begin
        // Capture one aggregate VRF word before an overlapping widening
        // operation overwrites bytes that still encode undisturbed tail data.
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;

        // The regular scoreboard records an LMUL group by its base register.
        // A boundary register inside that group therefore cannot rely on a
        // per-register RAW check against an older group write.  Capture only
        // after all older Ara operations have drained.
        ara_req_valid             = ara_idle_i;
        ara_req.emul              = LMUL_1;
        ara_req.vstart            = '0;
        ara_req.vs2               = overlap_boundary_vd_q;
        ara_req.eew_vs2           = overlap_boundary_old_eew_q;
        ara_req.use_vs2           = 1'b1;
        ara_req.vd                = overlap_boundary_vd_q;
        ara_req.use_vd            = 1'b0;
        ara_req.op                = ara_pkg::VSLIDEDOWN;
        ara_req.stride            = '0;
        ara_req.use_scalar_op     = 1'b0;
        ara_req.vm                = 1'b1;
        // Run the normal reshuffle datapath during capture and retain the
        // selected word already encoded in the destination EEW layout.
        ara_req.vtype.vsew        = overlap_target_eew_q;
        ara_req.vl                = overlap_elements_per_reg_q;
        ara_req.scale_vl          = 1'b1;
        ara_req.overlap_capture   = 1'b1;
        ara_req.overlap_snapshot_word = overlap_snapshot_word_q;

        if (ara_idle_i && ara_req_ready_i)
          state_d = OVERLAP_WAIT_CAPTURE;
      end

      OVERLAP_WAIT_CAPTURE: begin
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;
        if (!ara_req_valid_o && ara_idle_i)
          state_d = OVERLAP_ISSUE_ORIGINAL;
      end

      // The CVXIF request is still pending.  Returning state_d to NORMAL lets
      // the common decoder issue that exact architectural request this cycle.
      OVERLAP_ISSUE_ORIGINAL: begin
        state_d = NORMAL_OPERATION;
      end

      OVERLAP_WAIT_ORIGINAL: begin
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;

        if (ara_req_valid_o && ara_req_ready_i)
          overlap_original_accepted_d = 1'b1;

        if (overlap_original_accepted_q && !ara_req_valid_o && ara_idle_i) begin
          overlap_reg_index_d = '0;
          overlap_current_vd_d = overlap_vd_q;
          overlap_reg_first_element_d = '0;
          overlap_current_old_eew_d = overlap_old_eew_q[0];
          overlap_current_old_eew_valid_d = overlap_old_eew_valid_q[0];
          state_d = OVERLAP_FIXUP;
        end
      end

      OVERLAP_FIXUP: begin
        automatic logic [3:0] reg_count =
            4'(lmul_register_count(overlap_lmul_q));
        automatic vlen_t active_elements;
        automatic logic needs_fixup;

        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;

        if (overlap_vl_q <= overlap_reg_first_element_q)
          active_elements = '0;
        else if (overlap_vl_q >=
                 overlap_reg_first_element_q + overlap_elements_per_reg_q)
          active_elements = overlap_elements_per_reg_q;
        else
          active_elements = overlap_vl_q - overlap_reg_first_element_q;

        needs_fixup = active_elements < overlap_elements_per_reg_q &&
                      overlap_current_old_eew_valid_q &&
                      overlap_current_old_eew_q != overlap_target_eew_q;

        if (needs_fixup) begin
          // Re-encode only destination elements that the widening operation did
          // not overwrite. vstart marks the first untouched element in this
          // architectural register; the SLDU keeps lower result bytes intact.
          ara_req_valid         = 1'b1;
          ara_req.emul          = LMUL_1;
          ara_req.vstart        = active_elements;
          ara_req.vs2           = overlap_current_vd_q;
          ara_req.eew_vs2       = overlap_current_old_eew_q;
          ara_req.use_vs2       = 1'b1;
          ara_req.vd            = overlap_current_vd_q;
          ara_req.use_vd        = 1'b1;
          ara_req.op            = ara_pkg::VSLIDEDOWN;
          ara_req.stride        = '0;
          ara_req.use_scalar_op = 1'b0;
          ara_req.vm            = 1'b1;
          ara_req.vtype.vsew    = overlap_target_eew_q;
          ara_req.vl            = overlap_elements_per_reg_q;
          ara_req.scale_vl      = 1'b1;
          ara_req.overlap_use_snapshot = overlap_snapshot_valid_q &&
              overlap_reg_index_q == overlap_boundary_reg_q;
          ara_req.overlap_snapshot_word = overlap_snapshot_word_q;
        end

        if (!needs_fixup || ara_req_ready_i) begin
          eew_d[overlap_current_vd_q] = overlap_target_eew_q;
          eew_valid_d[overlap_current_vd_q] = 1'b1;
          if ({1'b0, overlap_reg_index_q} + 1'b1 == reg_count) begin
            state_d = OVERLAP_WAIT_FIXUP;
          end else begin
            overlap_reg_index_d = overlap_reg_index_q + 1'b1;
            overlap_current_vd_d = overlap_current_vd_q + 1'b1;
            overlap_reg_first_element_d = overlap_reg_first_element_q +
                overlap_elements_per_reg_q;
            overlap_current_old_eew_d =
                overlap_old_eew_q[overlap_reg_index_q + 1'b1];
            overlap_current_old_eew_valid_d =
                overlap_old_eew_valid_q[overlap_reg_index_q + 1'b1];
          end
        end
      end

      OVERLAP_WAIT_FIXUP: begin
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;
        if (!ara_req_valid_o && ara_idle_i)
          state_d = OVERLAP_RESPOND;
      end

      OVERLAP_RESPOND: begin
        if (acc_req_i.req_valid && acc_req_i.resp_ready) begin
          acc_resp_o.req_ready  = 1'b1;
          acc_resp_o.resp_valid = 1'b1;
          overlap_prepared_d = 1'b0;
          overlap_snapshot_valid_d = 1'b0;
          overlap_original_accepted_d = 1'b0;
          overlap_prefix_vl_d = '0;
          source_snapshot_valid_d = 1'b0;
          state_d = NORMAL_OPERATION;
        end
      end

      SOURCE_SNAPSHOT_CAPTURE: begin
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;

        // Read the source in its current narrow layout without writing an
        // architectural destination. Each lane retains its raw VRF words.
        ara_req_valid             = ara_idle_i;
        ara_req.emul              = source_snapshot_lmul_q;
        ara_req.vstart            = '0;
        ara_req.vs2               = source_snapshot_vs_q;
        ara_req.eew_vs2           = source_snapshot_eew_q;
        ara_req.use_vs2           = 1'b1;
        ara_req.use_vd            = 1'b0;
        ara_req.op                = ara_pkg::VSLIDEDOWN;
        ara_req.stride            = '0;
        ara_req.use_scalar_op     = 1'b0;
        ara_req.vm                = 1'b1;
        ara_req.vtype.vsew        = source_snapshot_eew_q;
        ara_req.vtype.vlmul       = source_snapshot_lmul_q;
        ara_req.vl                = source_snapshot_vl_q;
        ara_req.scale_vl          = 1'b0;
        ara_req.overlap_capture   = 1'b1;
        ara_req.source_snapshot_capture = 1'b1;

        if (ara_idle_i && ara_req_ready_i)
          state_d = SOURCE_SNAPSHOT_WAIT;
      end

      SOURCE_SNAPSHOT_WAIT: begin
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;
        if (!ara_req_valid_o && ara_idle_i) begin
          source_snapshot_valid_d = 1'b1;
          state_d = NORMAL_OPERATION;
        end
      end

      // Inject a reshuffle instruction
      RESHUFFLE: begin
        // Instruction is of one of the RVV types
        automatic rvv_instruction_t insn = rvv_instruction_t'(instr.instr);

        // Stall the interface, wait for the backend to accept the injected uop
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;

        // Handle LMUL > 1
        rs_lmul_cnt_d       = rs_lmul_cnt_q;
        rs_lmul_cnt_limit_d = rs_lmul_cnt_limit_q;
        rs_mask_request_d   = 1'b0;

        // Every single reshuffle request refers to LMUL == 1
        ara_req.emul = LMUL_1;

        // vstart is always 0 for a reshuffle
        ara_req.vstart = '0;

        // These generate a reshuffle request to Ara's backend
        // When LMUL > 1, not all the regs that compose a large
        // register should always be reshuffled
        // A reshuffle reads and rewrites an architectural register in a new
        // physical EEW layout. Start it only after the older shared SLDU
        // stream has drained, so its untagged per-lane operands cannot be
        // interleaved with a preceding reduction or slide stream.
        ara_req_valid         = ~rs_mask_request_q & ara_idle_i & sldu_idle_i;
        ara_req.use_scalar_op = 1'b1;
        ara_req.vs2           = vs_buffer_q;
        ara_req.eew_vs2       = eew_old_buffer_q;
        ara_req.use_vs2       = 1'b1;
        ara_req.vd            = vs_buffer_q;
        ara_req.use_vd        = 1'b1;
        ara_req.op            = ara_pkg::VSLIDEDOWN;
        ara_req.stride        = '0;
        ara_req.use_scalar_op = 1'b0;
        // Unmasked: reshuffle everything
        ara_req.vm            = 1'b1;
        // Shuffle the whole reg (vl refers to current vsew)
        ara_req.vtype.vsew    = eew_new_buffer_q;
        // Always reshuffle one vreg at a time
        ara_req.vl            = VLENB >> ara_req.vtype.vsew;
        // Vl refers to current system vsew but operand requesters
        // will fetch from a register with a different eew
        ara_req.scale_vl      = 1'b1;

        // Backend ready - Decide what to do next. A masked reshuffle has no
        // request to handshake, so skip it independently of backend readiness.
        if (rs_mask_request_q ||
            (ara_idle_i && sldu_idle_i && ara_req_ready_i)) begin
          // Register completely reshuffled
          if (rs_lmul_cnt_q == rs_lmul_cnt_limit_q) begin
            rs_lmul_cnt_d = 0;

            // Delete the already processed vector register from the notebook -> |vs1|vs2|vd|
            unique casez (reshuffle_req_q)
              3'b??1: reshuffle_req_d = {reshuffle_req_q[2:1], 1'b0};
              3'b?10: reshuffle_req_d = {reshuffle_req_q[2  ], 2'b0};
              3'b100: reshuffle_req_d =                        3'b0 ;
              default:;
            endcase

            // Prepare the information to reshuffle the vector registers during the next cycles
            // Reshuffle in the following order: vd, v2, v1. The order is arbitrary.
            // If we are here, vd has been already reshuffled.
            unique casez (reshuffle_req_d)
              3'b?10: begin
                eew_old_buffer_d = eew_q[reshuffle_vs2_base_q];
                eew_new_buffer_d = reshuffle_eew_vs2_q;
                vs_buffer_d      = reshuffle_vs2_base_q;
                rs_lmul_cnt_limit_d = reshuffle_vs2_limit_q;
              end
              3'b100: begin
                eew_old_buffer_d = eew_q[reshuffle_vs1_base_q];
                eew_new_buffer_d = reshuffle_eew_vs1_q;
                vs_buffer_d      = reshuffle_vs1_base_q;
                rs_lmul_cnt_limit_d = reshuffle_vs1_limit_q;
              end
              default:;
            endcase

            // Source and destination active intervals can partially overlap,
            // notably for an in-place vslidedown. Keep both interval requests
            // so registers touched only by one side are not lost, but do not
            // reshuffle an overlapping physical register twice. eew_q already
            // reflects older completed registers; the second term forwards the
            // conversion accepted in this cycle for the interval boundary.
            if (reshuffle_req_d != '0)
              rs_mask_request_d =
                  (eew_old_buffer_d == eew_new_buffer_d) ||
                  ((vs_buffer_d == vs_buffer_q) &&
                   (eew_new_buffer_d == eew_new_buffer_q));

            if (reshuffle_req_d == 3'b0) begin
              // EEW metadata describes a complete physical register. Do not
              // expose the updated tag to the held architectural request until
              // the final reshuffle write has reached the VRF, even when only
              // one LMUL_1 register was converted.
              state_d = WAIT_IDLE;
            end
          // The register is not completely reshuffled (LMUL > 1)
          end else begin
            // Count up
            rs_lmul_cnt_d = rs_lmul_cnt_q + 1;

            // Prepare the information to reshuffle the vector registers during the next cycles
            // Since LMUL > 1, we should go on and check if the next register needs a reshuffle
            // at all.
            unique casez (reshuffle_req_d)
              3'b??1: begin
                vs_buffer_d      = vs_buffer_q + 1;
                eew_old_buffer_d = eew_q[vs_buffer_d];
                eew_new_buffer_d = reshuffle_eew_vd_q;
              end
              3'b?10: begin
                vs_buffer_d      = vs_buffer_q + 1;
                eew_old_buffer_d = eew_q[vs_buffer_d];
                eew_new_buffer_d = reshuffle_eew_vs2_q;
              end
              3'b100: begin
                vs_buffer_d      = vs_buffer_q + 1;
                eew_old_buffer_d = eew_q[vs_buffer_d];
                eew_new_buffer_d = reshuffle_eew_vs1_q;
              end
              default:;
            endcase

            // Mask the next request if we don't need to reshuffle the next reg
            if (eew_new_buffer_d == eew_old_buffer_d) rs_mask_request_d = 1'b1;
          end
        end
      end
    endcase

    if (state_d == NORMAL_OPERATION && state_q != RESHUFFLE &&
        state_q != OVERLAP_RESPOND && state_q != SOURCE_SNAPSHOT_WAIT) begin
      if (acc_req_i.req_valid && ara_req_ready_i && acc_req_i.resp_ready) begin
        // Decoding
        is_decoding = 1'b1;
        // Acknowledge the request
        acc_resp_o.req_ready = 1'b1;

        // Decode the instructions based on their opcode
        unique case (instr.itype.opcode)
          //////////////////////////////////////
          //  Vector Arithmetic instructions  //
          //////////////////////////////////////

          riscv::OpcodeVec: begin
            // Instruction is of one of the RVV types
            automatic rvv_instruction_t insn = rvv_instruction_t'(instr.instr);

            // These (mostly) always respond at the same cycle
            acc_resp_o.resp_valid = 1'b1;

            // Decode based on their func3 field
            unique case (insn.varith_type.func3)
              // Configuration instructions
              OPCFG: begin: opcfg
                // These can be acknowledged regardless of the state of Ara
                // NOTE: unless there is a pending fault-only first vector load
                is_config       = 1'b1;

                // Update vtype
                if (insn.vsetvli_type.func1 == 1'b0) begin // vsetvli
                  csr_vtype_d = vtype_xlen(xlen_t'(insn.vsetvli_type.zimm11));
                end else if (insn.vsetivli_type.func2 == 2'b11) begin // vsetivli
                  csr_vtype_d = vtype_xlen(xlen_t'(insn.vsetivli_type.zimm10));
                end else if (insn.vsetvl_type.func7 == 7'b100_0000) begin // vsetvl
                  csr_vtype_d = vtype_xlen(xlen_t'(acc_req_i.rs2[7:0]));
                end else
                  illegal_insn = 1'b1;

                // Check whether the updated vtype makes sense
                if ((csr_vtype_d.vsew > rvv_pkg::vew_e'($clog2(ELENB))) || // SEW <= ELEN
                    (csr_vtype_d.vlmul == LMUL_RSVD) ||                    // reserved value
                    // LMUL >= SEW/ELEN
                    (signed'($clog2(ELENB)) + signed'(csr_vtype_d.vlmul) < signed'(csr_vtype_d.vsew))) begin
                  csr_vtype_d = '{vill: 1'b1, vsew: EW8, vlmul: LMUL_1, default: '0};
                  csr_vl_d    = '0;
                end

                // Update the vector length
                else begin
                  // Maximum vector length. VLMAX = LMUL * VLEN / SEW.
                  automatic int unsigned vlmax = VLENB >> csr_vtype_d.vsew;
                  unique case (csr_vtype_d.vlmul)
                    LMUL_1  : vlmax <<= 0;
                    LMUL_2  : vlmax <<= 1;
                    LMUL_4  : vlmax <<= 2;
                    LMUL_8  : vlmax <<= 3;
                    // Fractional LMUL
                    LMUL_1_2: vlmax >>= 1;
                    LMUL_1_4: vlmax >>= 2;
                    LMUL_1_8: vlmax >>= 3;
                    default:;
                  endcase

                  if (insn.vsetivli_type.func2 == 2'b11) begin // vsetivli
                    // vsetivli follows the same AVL/VLMAX constraints as vsetvli.
                    csr_vl_d = (vlen_t'(insn.vsetivli_type.uimm5) > vlmax) ?
                      vlen_t'(vlmax) : vlen_t'(insn.vsetivli_type.uimm5);
                  end else begin // vsetvl || vsetvli
                    if (insn.vsetvl_type.rs1 == '0 && insn.vsetvl_type.rd == '0) begin
                      // Do not update the vector length
                      csr_vl_d = csr_vl_q;
                    end else if (insn.vsetvl_type.rs1 == '0 && insn.vsetvl_type.rd != '0) begin
                      // Set the vector length to vlmax
                      csr_vl_d = vlmax;
                    end else begin
                      // Normal stripmining
                      csr_vl_d = ((|acc_req_i.rs1[$bits(acc_req_i.rs1)-1:$bits(csr_vl_d)]) ||
                        (vlen_t'(acc_req_i.rs1) > vlmax)) ? vlmax : vlen_t'(acc_req_i.rs1);
                    end
                  end
                end

                // Return the new vl
                acc_resp_o.result = csr_vl_d;

                // If the vtype has changed, wait for the backend before issuing any new instructions.
                // This is to avoid hazards on implicit register labels when LMUL_old > LMUL_new
                // and both the LMULs are greater then LMUL_1 (i.e., lmul[2] == 1'b0)
                // Checking only lmul_q is a trick: we want to stall only if both lmuls have
                // zero MSB. If lmul_q has zero MSB, it's greater than lmul_d only if also
                // lmul_d has zero MSB since the slice comparison is intrinsically unsigned
                if (!csr_vtype_q.vlmul[2] && (csr_vtype_d.vlmul[2:0] < csr_vtype_q.vlmul[2:0]))
                  state_d = WAIT_IDLE;
              end

              OPIVV: begin: opivv
                // These generate a request to Ara's backend
                ara_req.vs1     = insn.varith_type.rs1;
                ara_req.use_vs1 = 1'b1;
                ara_req.vs2     = insn.varith_type.rs2;
                ara_req.use_vs2 = 1'b1;
                ara_req.vd      = insn.varith_type.rd;
                ara_req.use_vd  = 1'b1;
                ara_req.vm      = insn.varith_type.vm;
                ara_req_valid   = 1'b1;

                // Decode based on the func6 field
                unique case (insn.varith_type.func6)
                  6'b000000: ara_req.op = ara_pkg::VADD;
                  6'b000010: ara_req.op = ara_pkg::VSUB;
                  6'b000100: ara_req.op = ara_pkg::VMINU;
                  6'b000101: ara_req.op = ara_pkg::VMIN;
                  6'b000110: ara_req.op = ara_pkg::VMAXU;
                  6'b000111: ara_req.op = ara_pkg::VMAX;
                  6'b001001: ara_req.op = ara_pkg::VAND;
                  6'b001010: ara_req.op = ara_pkg::VOR;
                  6'b001011: ara_req.op = ara_pkg::VXOR;
                  6'b001100: begin
                    ara_req.op = ara_pkg::VRGATHER;
                    ara_req.eew_vs2 = eew_q[ara_req.vs1];
                    // The MASKU will ask for elements from vs2 through the MaskB opqueue
                    // and deshuffle them with eew_vd_op encoding
                    ara_req.eew_vd_op = eew_q[ara_req.vs2];
                    // When data and indices alias, both architectural views use
                    // SEW. Normalize the group once and let both request paths
                    // consume that layout; retaining two historical EEW views
                    // would require replay support on the ad-hoc MaskB requester.
                    if (ara_req.vs1 == ara_req.vs2) begin
                      ara_req.eew_vs2   = csr_vtype_q.vsew;
                      ara_req.eew_vd_op = csr_vtype_q.vsew;
                    end
                  end
                  6'b001110: begin // VRGATHEREI16
                    ara_req.op      = ara_pkg::VRGATHEREI16;
                    ara_req.eew_vs1 = EW16;
                    // The index vector has EEW=16 independently of SEW, so its
                    // EMUL is LMUL * 16 / SEW.
                    unique case (csr_vtype_q.vsew)
                      EW8:  lmul_vs1 = next_lmul(csr_vtype_q.vlmul);
                      EW16: lmul_vs1 = csr_vtype_q.vlmul;
                      EW32: lmul_vs1 = prev_lmul(csr_vtype_q.vlmul);
                      EW64: lmul_vs1 = prev_lmul(prev_lmul(csr_vtype_q.vlmul));
                      default: lmul_vs1 = LMUL_RSVD;
                    endcase
                    // This allows the MASKU to deshuffle vs1 correctly since it gets deshuffled with eew_vs2
                    ara_req.eew_vs2 = eew_q[ara_req.vs1];
                    // The MASKU will ask for elements from vs2 through the MaskB opqueue
                    // and deshuffle them with eew_vd_op encoding
                    ara_req.eew_vd_op = eew_q[ara_req.vs2];
                  end
                  6'b010000: begin
                    ara_req.op = ara_pkg::VADC;

                    // Encoding corresponding to unmasked operations are reserved
                    if (insn.varith_type.vm) illegal_insn = 1'b1;

                    // An illegal instruction is raised if the destination vector is v0
                    if (insn.varith_type.rd == 5'b0) illegal_insn = 1'b1;
                  end
                  6'b010001: begin
                    ara_req.op        = ara_pkg::VMADC;

                    if (register_in_group(insn.varith_type.rd, insn.varith_type.rs1,
                                          ara_req.emul) ||
                        register_in_group(insn.varith_type.rd, insn.varith_type.rs2,
                                          ara_req.emul))
                      illegal_insn = 1'b1;
                  end
                  6'b010010: begin
                    ara_req.op = ara_pkg::VSBC;
                    // Encoding corresponding to unmasked operations are reserved
                    if (insn.varith_type.vm) illegal_insn         = 1'b1;
                    // An illegal instruction is raised if the destination vector is v0
                    if (insn.varith_type.rd == 5'b0) illegal_insn = 1'b1;
                  end
                  6'b010011: begin
                    ara_req.op        = ara_pkg::VMSBC;

                    if (register_in_group(insn.varith_type.rd, insn.varith_type.rs1,
                                          ara_req.emul) ||
                        register_in_group(insn.varith_type.rd, insn.varith_type.rs2,
                                          ara_req.emul))
                      illegal_insn = 1'b1;
                  end
                  6'b011000: begin
                    ara_req.op         = ara_pkg::VMSEQ;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011001: begin
                    ara_req.op        = ara_pkg::VMSNE;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011010: begin
                    ara_req.op        = ara_pkg::VMSLTU;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011011: begin
                    ara_req.op        = ara_pkg::VMSLT;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011100: begin
                    ara_req.op        = ara_pkg::VMSLEU;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011101: begin
                    ara_req.op        = ara_pkg::VMSLE;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b010111: begin
                    ara_req.op      = ara_pkg::VMERGE;
                    ara_req.use_vs2 = !insn.varith_type.vm; // vmv.v.v does not use vs2
                    // With a normal vmv.v.v, copy input EEW to output when the
                    // architectural active byte count is exactly representable
                    // in that layout. Otherwise a wider raw copy would either
                    // drop a partial final element or overwrite undisturbed tail
                    // bytes; fall back to the architectural SEW and reshuffle.
                    if (insn.varith_type.vm &&
                        (((csr_vl_q << csr_vtype_q.vsew[1:0]) &
                          ((1 << eew_q[ara_req.vs1][1:0]) - 1)) == 0)) begin
                      ara_req.eew_vs1    = eew_q[ara_req.vs1];
                      ara_req.vtype.vsew = eew_q[ara_req.vs1];
                      ara_req.vl         = (csr_vl_q << csr_vtype_q.vsew[1:0]) >> ara_req.eew_vs1[1:0];
                    end
                  end
                  6'b100000: ara_req.op = ara_pkg::VSADDU;
                  6'b100001: ara_req.op = ara_pkg::VSADD;
                  6'b100010: ara_req.op = ara_pkg::VSSUBU;
                  6'b100011: ara_req.op = ara_pkg::VSSUB;
                  6'b100101: ara_req.op = ara_pkg::VSLL;
                  6'b100111: ara_req.op = ara_pkg::VSMUL;
                  6'b101000: ara_req.op = ara_pkg::VSRL;
                  6'b101010: ara_req.op = ara_pkg::VSSRL;
                  6'b101011: ara_req.op = ara_pkg::VSSRA;
                  6'b101001: ara_req.op = ara_pkg::VSRA;
                  6'b101100: begin
                    ara_req.op             = ara_pkg::VNSRL;
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);

                    // Check whether the EEW is not too wide.
                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;

                    // Check whether we can access vs2
                    unique case (ara_req.emul.next())
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  6'b101101: begin
                    ara_req.op             = ara_pkg::VNSRA;
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);

                    // Check whether the EEW is not too wide.
                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;

                    // Check whether we can access vs2
                    unique case (ara_req.emul.next())
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  6'b101110: begin
                    ara_req.op             = ara_pkg::VNCLIPU;
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    lmul_vs2               = next_lmul(csr_vtype_q.vlmul);

                    // A narrowing source is twice as wide as the destination.
                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;

                    unique case (ara_req.emul.next())
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  6'b101111: begin
                    ara_req.op             = ara_pkg::VNCLIP;
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    lmul_vs2               = next_lmul(csr_vtype_q.vlmul);

                    // A narrowing source is twice as wide as the destination.
                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;

                    unique case (ara_req.emul.next())
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  // Reductions encode in cvt_resize the neutral value bits
                  // CVT_WIDE is 2'b00 (hack to save wires)
                  6'b110000: begin
                    ara_req.op = ara_pkg::VWREDSUMU;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.eew_vs1        = csr_vtype_q.vsew.next();
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueReductionZExt;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110001: begin
                    ara_req.op = ara_pkg::VWREDSUM;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.eew_vs1        = csr_vtype_q.vsew.next();
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueReductionZExt;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  default: illegal_insn = 1'b1;
                endcase

                // Reduction seeds and results are scalar vector-register operands.
                // Only vs2 follows the data LMUL.
                if (reduction_result(ara_req.op)) lmul_vs1 = LMUL_1;

                // Instructions with an integer LMUL have extra constraints on the registers they can
                // access. The constraints can be different for each architectural operand.
                unique case (ara_req.emul)
                  LMUL_2: if (!single_register_result(ara_req.op) &&
                        (insn.varith_type.rd & 5'b00001) != 5'b00000) illegal_insn = ara_req.use_vd;
                  LMUL_4: if (!single_register_result(ara_req.op) &&
                        (insn.varith_type.rd & 5'b00011) != 5'b00000) illegal_insn = ara_req.use_vd;
                  LMUL_8: if (!single_register_result(ara_req.op) &&
                        (insn.varith_type.rd & 5'b00111) != 5'b00000) illegal_insn = ara_req.use_vd;
                  LMUL_RSVD: illegal_insn = 1'b1;
                  default:;
                endcase
                unique case (lmul_vs2)
                  LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                  LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                  LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                  LMUL_RSVD: illegal_insn = 1'b1;
                  default:;
                endcase
                unique case (lmul_vs1)
                  LMUL_2: if ((insn.varith_type.rs1 & 5'b00001) != 5'b00000) illegal_insn |= ara_req.use_vs1;
                  LMUL_4: if ((insn.varith_type.rs1 & 5'b00011) != 5'b00000) illegal_insn |= ara_req.use_vs1;
                  LMUL_8: if ((insn.varith_type.rs1 & 5'b00111) != 5'b00000) illegal_insn |= ara_req.use_vs1;
                  LMUL_RSVD: illegal_insn = 1'b1;
                  default:;
                endcase

                // Instruction is invalid if the vtype is invalid
                if (csr_vtype_q.vill) illegal_insn = 1'b1;
              end

              OPIVX: begin: opivx
                // These generate a request to Ara's backend
                ara_req.scalar_op     = acc_req_i.rs1;
                ara_req.use_scalar_op = 1'b1;
                ara_req.vs2           = insn.varith_type.rs2;
                ara_req.use_vs2       = 1'b1;
                ara_req.vd            = insn.varith_type.rd;
                ara_req.use_vd        = 1'b1;
                ara_req.vm            = insn.varith_type.vm;
                ara_req.is_stride_np2 = is_stride_np2;
                ara_req_valid         = 1'b1;

                // Decode based on the func6 field
                unique case (insn.varith_type.func6)
                  6'b000000: ara_req.op = ara_pkg::VADD;
                  6'b000010: ara_req.op = ara_pkg::VSUB;
                  6'b000011: ara_req.op = ara_pkg::VRSUB;
                  6'b000100: ara_req.op = ara_pkg::VMINU;
                  6'b000101: ara_req.op = ara_pkg::VMIN;
                  6'b000110: ara_req.op = ara_pkg::VMAXU;
                  6'b000111: ara_req.op = ara_pkg::VMAX;
                  6'b001001: ara_req.op = ara_pkg::VAND;
                  6'b001010: ara_req.op = ara_pkg::VOR;
                  6'b001011: ara_req.op = ara_pkg::VXOR;
                  6'b001100: begin
                    ara_req.op = ara_pkg::VRGATHER;
                    // The MASKU will ask for elements from vs2 through the MaskB opqueue
                    // and deshuffle them with eew_vd_op encoding
                    ara_req.eew_vd_op = eew_q[ara_req.vs2];
                  end
                  6'b001110: begin
                    ara_req.op            = ara_pkg::VSLIDEUP;
                    ara_req.stride        = acc_req_i.rs1;
                    ara_req.eew_vs2       = csr_vtype_q.vsew;
                    // Encode vslideup/vslide1up on the use_scalar_op field
                    ara_req.use_scalar_op = 1'b0;
                    // Vl refers to current system vsew, but operand requesters
                    // will fetch bytes from a vreg with a different eew
                    // i.e., request will need reshuffling
                    ara_req.scale_vl      = 1'b1;
                    // If stride > vl, the vslideup has no effects
                    if (|ara_req.stride[$bits(ara_req.stride)-1:$bits(csr_vl_q)] ||
                      (vlen_t'(ara_req.stride) >= csr_vl_q)) null_vslideup = 1'b1;
                  end
                  6'b001111: begin
                    ara_req.op            = ara_pkg::VSLIDEDOWN;
                    ara_req.stride        = acc_req_i.rs1;
                    ara_req.eew_vs2       = csr_vtype_q.vsew;
                    // Encode vslidedown/vslide1down on the use_scalar_op field
                    ara_req.use_scalar_op = 1'b0;
                    // Request will need reshuffling
                    ara_req.scale_vl      = 1'b1;
                  end
                  6'b010000: begin
                    ara_req.op = ara_pkg::VADC;

                    // Encoding corresponding to unmasked operations are reserved
                    if (insn.varith_type.vm) illegal_insn = 1'b1;

                    // An illegal instruction is raised if the destination vector is v0
                    if (insn.varith_type.rd == 5'b0) illegal_insn = 1'b1;
                  end
                  6'b010001: begin
                    ara_req.op        = ara_pkg::VMADC;

                    if (register_in_group(insn.varith_type.rd, insn.varith_type.rs2,
                                          ara_req.emul))
                      illegal_insn = 1'b1;
                  end
                  6'b010010: begin
                    ara_req.op = ara_pkg::VSBC;

                    // Encoding corresponding to unmasked operations are reserved
                    if (insn.varith_type.vm) illegal_insn = 1'b1;

                    // An illegal instruction is raised if the destination vector is v0
                    if (insn.varith_type.rd == 5'b0) illegal_insn = 1'b1;
                  end
                  6'b010011: begin
                    ara_req.op        = ara_pkg::VMSBC;

                    if (register_in_group(insn.varith_type.rd, insn.varith_type.rs2,
                                          ara_req.emul))
                      illegal_insn = 1'b1;
                  end
                  6'b011000: begin
                    ara_req.op         = ara_pkg::VMSEQ;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011001: begin
                    ara_req.op        = ara_pkg::VMSNE;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011010: begin
                    ara_req.op        = ara_pkg::VMSLTU;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011011: begin
                    ara_req.op        = ara_pkg::VMSLT;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011100: begin
                    ara_req.op        = ara_pkg::VMSLEU;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011101: begin
                    ara_req.op        = ara_pkg::VMSLE;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011110: begin
                    ara_req.op        = ara_pkg::VMSGTU;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011111: begin
                    ara_req.op        = ara_pkg::VMSGT;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b010111: begin
                    ara_req.op      = ara_pkg::VMERGE;
                    ara_req.use_vs2 = !insn.varith_type.vm; // vmv.v.x does not use vs2
                  end
                  6'b100000: ara_req.op = ara_pkg::VSADDU;
                  6'b100001: ara_req.op = ara_pkg::VSADD;
                  6'b100010: ara_req.op = ara_pkg::VSSUBU;
                  6'b100011: ara_req.op = ara_pkg::VSSUB;
                  6'b100101: ara_req.op = ara_pkg::VSLL;
                  6'b100111: ara_req.op = ara_pkg::VSMUL;
                  6'b101000: ara_req.op = ara_pkg::VSRL;
                  6'b101010: ara_req.op = ara_pkg::VSSRL;
                  6'b101011: ara_req.op = ara_pkg::VSSRA;
                  6'b101001: ara_req.op = ara_pkg::VSRA;
                  6'b101100: begin
                    ara_req.op             = ara_pkg::VNSRL;
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);

                    // Check whether the EEW is not too wide.
                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;

                    // Check whether we can access vs2
                    unique case (ara_req.emul.next())
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  6'b101101: begin
                    ara_req.op             = ara_pkg::VNSRA;
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);

                    // Check whether the EEW is not too wide.
                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;

                    // Check whether we can access vs2
                    unique case (ara_req.emul.next())
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  6'b101110: begin
                    ara_req.op      = ara_pkg::VNCLIPU;
                    ara_req.eew_vs2 = csr_vtype_q.vsew.next();
                    lmul_vs2        = next_lmul(csr_vtype_q.vlmul);

                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;
                    unique case (lmul_vs2)
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  6'b101111: begin
                    ara_req.op      = ara_pkg::VNCLIP;
                    ara_req.eew_vs2 = csr_vtype_q.vsew.next();
                    lmul_vs2        = next_lmul(csr_vtype_q.vlmul);

                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;
                    unique case (lmul_vs2)
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  default: illegal_insn = 1'b1;
                endcase

                // Instructions with an integer LMUL have extra constraints on the registers they can
                // access.
                unique case (ara_req.emul)
                  LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000 ||
                        (!mask_result(ara_req.op) &&
                         (insn.varith_type.rd & 5'b00001) != 5'b00000)) illegal_insn = 1'b1;
                  LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000 ||
                        (!mask_result(ara_req.op) &&
                         (insn.varith_type.rd & 5'b00011) != 5'b00000)) illegal_insn = 1'b1;
                  LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000 ||
                        (!mask_result(ara_req.op) &&
                         (insn.varith_type.rd & 5'b00111) != 5'b00000)) illegal_insn = 1'b1;
                  default:;
                endcase

                // Instruction is invalid if the vtype is invalid
                if (csr_vtype_q.vill) illegal_insn = 1'b1;
              end

              OPIVI: begin: opivi
                // These generate a request to Ara's backend
                // Sign-extend this by default.
                // Instructions that need the immediate to be zero-extended
                // (vrgather, shifts, clips, slides) should do overwrite this.
                ara_req.scalar_op     = {{ELEN{insn.varith_type.rs1[19]}}, insn.varith_type.rs1};
                ara_req.use_scalar_op = 1'b1;
                ara_req.vs2           = insn.varith_type.rs2;
                ara_req.use_vs2       = 1'b1;
                ara_req.vd            = insn.varith_type.rd;
                ara_req.use_vd        = 1'b1;
                ara_req.vm            = insn.varith_type.vm;
                ara_req.is_stride_np2 = is_stride_np2;
                ara_req_valid         = 1'b1;

                // Decode based on the func6 field
                unique case (insn.varith_type.func6)
                  6'b000000: ara_req.op = ara_pkg::VADD;
                  6'b000011: ara_req.op = ara_pkg::VRSUB;
                  6'b001001: ara_req.op = ara_pkg::VAND;
                  6'b001010: ara_req.op = ara_pkg::VOR;
                  6'b001011: ara_req.op = ara_pkg::VXOR;
                  6'b001100: begin
                    ara_req.op = ara_pkg::VRGATHER;
                    // The VI form carries an unsigned 5-bit index.
                    ara_req.scalar_op = elen_t'(insn.varith_type.rs1);
                    // The MASKU will ask for elements from vs2 through the MaskB opqueue
                    // and deshuffle them with eew_vd_op encoding
                    ara_req.eew_vd_op = eew_q[ara_req.vs2];
                  end
                  6'b001110: begin
                    ara_req.op            = ara_pkg::VSLIDEUP;
                    // VSLIDE*.VI uses an unsigned 5-bit offset, unlike signed
                    // arithmetic immediates decoded by the common VI path.
                    ara_req.stride        = elen_t'(insn.varith_type.rs1);
                    ara_req.eew_vs2       = csr_vtype_q.vsew;
                    // Encode vslideup/vslide1up on the use_scalar_op field
                    ara_req.use_scalar_op = 1'b0;
                    // Request will need reshuffling
                    ara_req.scale_vl      = 1'b1;
                    // If stride > vl, the vslideup has no effects
                    if (|ara_req.stride[$bits(ara_req.stride)-1:$bits(csr_vl_q)] ||
                      (vlen_t'(ara_req.stride) >= csr_vl_q)) null_vslideup = 1'b1;
                  end
                  6'b001111: begin
                    ara_req.op            = ara_pkg::VSLIDEDOWN;
                    ara_req.stride        = elen_t'(insn.varith_type.rs1);
                    ara_req.eew_vs2       = csr_vtype_q.vsew;
                    // Encode vslidedown/vslide1down on the use_scalar_op field
                    ara_req.use_scalar_op = 1'b0;
                    // Request will need reshuffling
                    ara_req.scale_vl      = 1'b1;
                  end
                  6'b010000: begin
                    ara_req.op = ara_pkg::VADC;

                    // Encoding corresponding to unmasked operations are reserved
                    if (insn.varith_type.vm) illegal_insn = 1'b1;

                    // An illegal instruction is raised if the destination vector is v0
                    if (insn.varith_type.rd == 5'b0) illegal_insn = 1'b1;
                  end
                  6'b010001: begin
                    ara_req.op        = ara_pkg::VMADC;

                    if (register_in_group(insn.varith_type.rd, insn.varith_type.rs2,
                                          ara_req.emul))
                      illegal_insn = 1'b1;
                  end
                  6'b011000: begin
                    ara_req.op         = ara_pkg::VMSEQ;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011001: begin
                    ara_req.op        = ara_pkg::VMSNE;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011100: begin
                    ara_req.op        = ara_pkg::VMSLEU;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011101: begin
                    ara_req.op        = ara_pkg::VMSLE;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011110: begin
                    ara_req.op        = ara_pkg::VMSGTU;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011111: begin
                    ara_req.op        = ara_pkg::VMSGT;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs1    = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = csr_vtype_q.vsew;
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b010111: begin
                    ara_req.op      = ara_pkg::VMERGE;
                    ara_req.use_vs2 = !insn.varith_type.vm; // vmv.v.i does not use vs2
                  end
                  6'b100000: ara_req.op = ara_pkg::VSADDU;
                  6'b100001: ara_req.op = ara_pkg::VSADD;
                  6'b100101: ara_req.op = ara_pkg::VSLL;
                  6'b100111: begin // vmv<nr>r.v
                    automatic int unsigned vlmax;
                    // Execute also if vl == 0
                    ignore_zero_vl_check = 1'b1;
                    // The number of elements depends on the EEW we will consider
                    vlmax = VLENB >> eew_q[insn.varith_type.rs2];
                    // Rescale the maximum vector length depending on how many
                    // registers we should copy (VLMAX = simm[2:0] * VLEN / SEW).
                    unique case (insn.varith_type.rs1[17:15])
                      3'd0 : begin
                        vlmax <<= 0;
                        ara_req.emul = LMUL_1;
                      end
                      3'd1 : begin
                        vlmax <<= 1;
                        ara_req.emul = LMUL_2;
                      end
                      3'd3 : begin
                        vlmax <<= 2;
                        ara_req.emul = LMUL_4;
                      end
                      3'd7 : begin
                        vlmax <<= 3;
                        ara_req.emul = LMUL_8;
                      end
                      default: begin
                        // Trigger an error for the reserved simm values
                        illegal_insn = 1'b1;
                      end
                    endcase
                    // From here on, the only difference with a vmv.v.v is that the vector reg index
                    // is in rs2. For the rest,, pretend to be a vmv.v.v
                    ara_req.op            = ara_pkg::VMERGE;
                    ara_req.use_scalar_op = 1'b0;
                    ara_req.use_vs1       = 1'b1;
                    ara_req.use_vs2       = 1'b0;
                    ara_req.vs1           = insn.varith_type.rs2;
                    ara_req.eew_vs1       = eew_q[insn.varith_type.rs2];
                    // The source group is selected by the whole-register move
                    // encoding, independently of the current vtype LMUL. Use the
                    // complete group when normalizing mixed per-register layouts.
                    lmul_vs1              = ara_req.emul;
                    // Copy the encoding information to the new register
                    ara_req.vtype.vsew    = eew_q[insn.varith_type.rs2];
                    ara_req.vl            = vlmax; // whole register move
                  end
                  6'b101000: ara_req.op = ara_pkg::VSRL;
                  6'b101001: ara_req.op = ara_pkg::VSRA;
                  6'b101010: ara_req.op = ara_pkg::VSSRL;
                  6'b101011: ara_req.op = ara_pkg::VSSRA;
                  6'b101100: begin
                    ara_req.op             = ara_pkg::VNSRL;
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);

                    // Check whether the EEW is not too wide.
                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;

                    // Check whether we can access vs2
                    unique case (ara_req.emul.next())
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  6'b101101: begin
                    ara_req.op             = ara_pkg::VNSRA;
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);

                    // Check whether the EEW is not too wide.
                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;

                    // Check whether we can access vs2
                    unique case (ara_req.emul.next())
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  6'b101110: begin
                    ara_req.op      = ara_pkg::VNCLIPU;
                    ara_req.eew_vs2 = csr_vtype_q.vsew.next();
                    lmul_vs2        = next_lmul(csr_vtype_q.vlmul);

                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;
                    unique case (lmul_vs2)
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  6'b101111: begin
                    ara_req.op      = ara_pkg::VNCLIP;
                    ara_req.eew_vs2 = csr_vtype_q.vsew.next();
                    lmul_vs2        = next_lmul(csr_vtype_q.vlmul);

                    if (int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;
                    unique case (lmul_vs2)
                      LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn = 1'b1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end
                  default: illegal_insn = 1'b1;
                endcase

                // Shift and narrowing shift amounts are encoded as uimm5.
                // Keep arithmetic and comparison immediates sign-extended.
                if (ara_req.op inside {
                      VSLL, VSRL, VSRA, VSSRL, VSSRA,
                      VNSRL, VNSRA, VNCLIP, VNCLIPU
                    })
                  ara_req.scalar_op = elen_t'(insn.varith_type.rs1);

                // Instructions with an integer LMUL have extra constraints on the registers they can
                // access.
                unique case (ara_req.emul)
                  LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000 ||
                        (!mask_result(ara_req.op) &&
                         (insn.varith_type.rd & 5'b00001) != 5'b00000)) illegal_insn = 1'b1;
                  LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000 ||
                        (!mask_result(ara_req.op) &&
                         (insn.varith_type.rd & 5'b00011) != 5'b00000)) illegal_insn = 1'b1;
                  LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000 ||
                        (!mask_result(ara_req.op) &&
                         (insn.varith_type.rd & 5'b00111) != 5'b00000)) illegal_insn = 1'b1;
                  default:;
                endcase

                // Instruction is invalid if the vtype is invalid
                if (csr_vtype_q.vill) illegal_insn = 1'b1;
              end

              OPMVV: begin: opmvv
                // These generate a request to Ara's backend
                ara_req.vs1     = insn.varith_type.rs1;
                ara_req.use_vs1 = 1'b1;
                ara_req.vs2     = insn.varith_type.rs2;
                ara_req.use_vs2 = 1'b1;
                ara_req.vd      = insn.varith_type.rd;
                ara_req.use_vd  = 1'b1;
                ara_req.vm      = insn.varith_type.vm;
                ara_req_valid   = 1'b1;

                // Ordinary OPMVV instructions write a full data-vector group.
                // Single-register mask/reduction results are narrowed below
                // after the operation has been decoded.
                ara_req.emul = csr_vtype_q.vlmul;

                // Decode based on the func6 field
                unique case (insn.varith_type.func6)
                  // Encode, for each reduction, the bits of the neutral
                  // value of each operation
                  6'b000000: begin
                    ara_req.op             = ara_pkg::VREDSUM;
                    ara_req.conversion_vs1 = OpQueueReductionZExt;
                    ara_req.cvt_resize     = resize_e'(2'b00);
                  end
                  6'b000001: begin
                    ara_req.op             = ara_pkg::VREDAND;
                    ara_req.conversion_vs1 = OpQueueReductionZExt;
                    ara_req.cvt_resize     = resize_e'(2'b11);
                  end
                  6'b000010: begin
                    ara_req.op             = ara_pkg::VREDOR;
                    ara_req.conversion_vs1 = OpQueueReductionZExt;
                    ara_req.cvt_resize     = resize_e'(2'b00);
                  end
                  6'b000011: begin
                    ara_req.op             = ara_pkg::VREDXOR;
                    ara_req.conversion_vs1 = OpQueueReductionZExt;
                    ara_req.cvt_resize     = resize_e'(2'b00);
                  end
                  6'b000100: begin
                    ara_req.op             = ara_pkg::VREDMINU;
                    ara_req.conversion_vs1 = OpQueueReductionZExt;
                    ara_req.cvt_resize     = resize_e'(2'b11);
                  end
                  6'b000101: begin
                    ara_req.op             = ara_pkg::VREDMIN;
                    ara_req.conversion_vs1 = OpQueueReductionZExt;
                    ara_req.cvt_resize     = resize_e'(2'b01);
                  end
                  6'b000110: begin
                    ara_req.op             = ara_pkg::VREDMAXU;
                    ara_req.conversion_vs1 = OpQueueReductionZExt;
                    ara_req.cvt_resize     = resize_e'(2'b00);
                  end
                  6'b000111: begin
                    ara_req.op             = ara_pkg::VREDMAX;
                    ara_req.conversion_vs1 = OpQueueReductionZExt;
                    ara_req.cvt_resize     = resize_e'(2'b10);
                  end
                  6'b010000: begin // VWXUNARY0
                    // vmv.x.s
                    // Stall the interface until we get the result
                    acc_resp_o.req_ready  = 1'b0;
                    acc_resp_o.resp_valid = 1'b0;

                    case (insn.varith_type.rs1)
                      5'b00000: begin
                        ara_req.op      = ara_pkg::VMVXS;
                        ara_req.use_vs1 = 1'b0;
                        ara_req.vl      = 1;
                      end
                      5'b10000: begin
                        ara_req.op      = ara_pkg::VCPOP;
                        ara_req.eew_vs2 = eew_q[ara_req.vs2];
                      end
                      5'b10001: begin
                        ara_req.op      = ara_pkg::VFIRST;
                        ara_req.eew_vs2 = eew_q[ara_req.vs2];
                      end
                      default :;
                    endcase

                    ara_req.use_vd     = 1'b0;
                    ara_req.vstart     = '0;
                    skip_lmul_checks     = 1'b1;
                    ignore_zero_vl_check = 1'b1;

                    // Sign extend operands
                    unique case (csr_vtype_q.vsew)
                      EW8: begin
                        ara_req.conversion_vs2 = OpQueueConversionSExt8;
                      end
                      EW16: begin
                        ara_req.conversion_vs2 = OpQueueConversionSExt4;
                      end
                      EW32: begin
                        ara_req.conversion_vs2 = OpQueueConversionSExt2;
                      end
                      default:;
                    endcase

                    // Wait until the back-end answers to acknowledge those instructions
                    if ( ara_resp_valid ) begin
                      acc_resp_o.req_ready  = 1'b1;
                      acc_resp_o.resp_valid = 1'b1;
                      acc_resp_o.result     = ara_resp.resp;
                      acc_resp_o.exception  = ara_resp.exception;
                      ara_req_valid       = 1'b0;
                    end
                  end
                  6'b010100: begin
                    // VMSBF, -OF, -IF, require bit-level masking
                    // vd is fetched for correct mask undisturbed
                    ara_req.use_vs1    = 1'b0;
                    ara_req.use_vd_op  = 1'b1;
                    ara_req.eew_vs2    = eew_q[ara_req.vs2]; // Force reshuffle
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    case (insn.varith_type.rs1)
                      5'b00001: begin
                        ara_req.op = ara_pkg::VMSBF;
                        // This is a mask-to-mask operation, vsew does not have any meaning
                        // So, avoid reshuffling
                        ara_req.vtype.vsew = eew_q[ara_req.vd];
                      end
                      5'b00010: begin
                        ara_req.op = ara_pkg::VMSOF;
                        // This is a mask-to-mask operation, vsew does not have any meaning
                        // So, avoid reshuffling
                        ara_req.vtype.vsew = eew_q[ara_req.vd];
                      end
                      5'b00011: begin
                        ara_req.op = ara_pkg::VMSIF;
                        // This is a mask-to-mask operation, vsew does not have any meaning
                        // So, avoid reshuffling
                        ara_req.vtype.vsew = eew_q[ara_req.vd];
                      end
                      5'b10000: begin
                        ara_req.op = ara_pkg::VIOTA;
                        // VIOTA writes a regular data-vector group.  Its mask
                        // source is constrained to LMUL1 separately below.
                        ara_req.emul = csr_vtype_q.vlmul;
                        ara_req.use_vd_op  = 1'b0;
                      end
                      5'b10001: begin
                        ara_req.op = ara_pkg::VID;
                        // VID writes a regular data-vector group, not a mask.
                        ara_req.emul = csr_vtype_q.vlmul;
                        ara_req.use_vd_op  = 1'b0;
                        ara_req.use_vs2 = 1'b0;
                      end
                    endcase
                  end
                  6'b001000: ara_req.op = ara_pkg::VAADDU;
                  6'b001001: ara_req.op = ara_pkg::VAADD;
                  6'b001010: ara_req.op = ara_pkg::VASUBU;
                  6'b001011: ara_req.op = ara_pkg::VASUB;
                  6'b010111: begin
                    ara_req.op = ara_pkg::VCOMPRESS;
                    // MASKU reads vs1 as packed mask bits, but the register can
                    // have been produced at any EEW.  Its historical EEW is
                    // carried in eew_vs2 for masku_operands' deshuffle path.
                    ara_req.eew_vs2 = eew_q[ara_req.vs1];
                    // VCOMPRESS's indexed MaskB reads span the complete data
                    // source group. Normalize that group to SEW before issue,
                    // then use the normalized layout in MASKU.
                    ara_req.eew_vd_op = csr_vtype_q.vsew;
                    // Encoding corresponding to unmasked operations are reserved
                    if (!insn.varith_type.vm) illegal_insn = 1'b1;
                  end
                  6'b011000: begin
                    ara_req.op         = ara_pkg::VMANDNOT;
                    // The source operands should have the same byte encoding
                    // Minimize reshuffling on mask operations
                    ara_req.eew_vs1    = eew_q[ara_req.vs1];
                    ara_req.eew_vs2    = eew_q[ara_req.vs1]; // Force reshuffle
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011001: begin
                    ara_req.op         = ara_pkg::VMAND;
                    ara_req.eew_vs1    = eew_q[ara_req.vs1];
                    ara_req.eew_vs2    = eew_q[ara_req.vs1]; // Force reshuffle
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011010: begin
                    ara_req.op         = ara_pkg::VMOR;
                    ara_req.eew_vs1    = eew_q[ara_req.vs1];
                    ara_req.eew_vs2    = eew_q[ara_req.vs1]; // Force reshuffle
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011011: begin
                    ara_req.op         = ara_pkg::VMXOR;
                    ara_req.eew_vs1    = eew_q[ara_req.vs1];
                    ara_req.eew_vs2    = eew_q[ara_req.vs1]; // Force reshuffle
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011100: begin
                    ara_req.op         = ara_pkg::VMORNOT;
                    ara_req.eew_vs1    = eew_q[ara_req.vs1];
                    ara_req.eew_vs2    = eew_q[ara_req.vs1]; // Force reshuffle
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011101: begin
                    ara_req.op         = ara_pkg::VMNAND;
                    ara_req.eew_vs1    = eew_q[ara_req.vs1];
                    ara_req.eew_vs2    = eew_q[ara_req.vs1]; // Force reshuffle
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011110: begin
                    ara_req.op         = ara_pkg::VMNOR;
                    ara_req.eew_vs1    = eew_q[ara_req.vs1];
                    ara_req.eew_vs2    = eew_q[ara_req.vs1]; // Force reshuffle
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b011111: begin
                    ara_req.op         = ara_pkg::VMXNOR;
                    ara_req.eew_vs1    = eew_q[ara_req.vs1];
                    ara_req.eew_vs2    = eew_q[ara_req.vs1]; // Force reshuffle
                    ara_req.eew_vd_op  = eew_q[ara_req.vd];
                    ara_req.vtype.vsew = eew_q[ara_req.vd];
                  end
                  6'b010010: begin // VXUNARY0
                    // These instructions do not use vs1
                    ara_req.use_vs1    = 1'b0;
                    // They are always encoded as ADDs with zero.
                    ara_req.op            = ara_pkg::VADD;
                    ara_req.use_scalar_op = 1'b1;
                    ara_req.scalar_op     = '0;

                    case (insn.varith_type.rs1)
                      5'b00010: begin // VZEXT.VF8
                        ara_req.conversion_vs2 = OpQueueConversionZExt8;
                        ara_req.eew_vs2        = rvv_pkg::EW8;
                        ara_req.cvt_resize     = CVT_WIDE;
                        ara_req.emul           = csr_vtype_q.vlmul;
                        lmul_vs2               = prev_lmul(prev_lmul(prev_lmul(csr_vtype_q.vlmul)));

                        // Invalid conversion
                        if (int'(csr_vtype_q.vsew) < int'(EW64) ||
                            int'(csr_vtype_q.vlmul) inside {LMUL_1_2, LMUL_1_4, LMUL_1_8})
                          illegal_insn = 1'b1;
                      end
                      5'b00011: begin // VSEXT.VF8
                        ara_req.conversion_vs2 = OpQueueConversionSExt8;
                        ara_req.eew_vs2        = rvv_pkg::EW8;
                        ara_req.cvt_resize     = CVT_WIDE;
                        ara_req.emul           = csr_vtype_q.vlmul;
                        lmul_vs2               = prev_lmul(prev_lmul(prev_lmul(csr_vtype_q.vlmul)));

                        // Invalid conversion
                        if (int'(csr_vtype_q.vsew) < int'(EW64) ||
                            int'(csr_vtype_q.vlmul) inside {LMUL_1_2, LMUL_1_4, LMUL_1_8})
                          illegal_insn = 1'b1;
                      end
                      5'b00100: begin // VZEXT.VF4
                        ara_req.conversion_vs2 = OpQueueConversionZExt4;
                        ara_req.eew_vs2        = prev_prev_ew(csr_vtype_q.vsew);
                        ara_req.cvt_resize     = CVT_WIDE;
                        ara_req.emul           = csr_vtype_q.vlmul;
                        lmul_vs2               = prev_lmul(prev_lmul(csr_vtype_q.vlmul));

                        // Invalid conversion
                        if (int'(csr_vtype_q.vsew) < int'(EW32) ||
                            int'(csr_vtype_q.vlmul) inside {LMUL_1_4, LMUL_1_8}) illegal_insn = 1'b1;
                      end
                      5'b00101: begin // VSEXT.VF4
                        ara_req.conversion_vs2 = OpQueueConversionSExt4;
                        ara_req.eew_vs2        = prev_prev_ew(csr_vtype_q.vsew);
                        ara_req.cvt_resize     = CVT_WIDE;
                        ara_req.emul           = csr_vtype_q.vlmul;
                        lmul_vs2               = prev_lmul(prev_lmul(csr_vtype_q.vlmul));

                        // Invalid conversion
                        if (int'(csr_vtype_q.vsew) < int'(EW32) ||
                            int'(csr_vtype_q.vlmul) inside {LMUL_1_4, LMUL_1_8}) illegal_insn = 1'b1;
                      end
                      5'b00110: begin // VZEXT.VF2
                        ara_req.conversion_vs2 = OpQueueConversionZExt2;
                        ara_req.eew_vs2        = csr_vtype_q.vsew.prev();
                        ara_req.cvt_resize     = CVT_WIDE;
                        ara_req.emul           = csr_vtype_q.vlmul;
                        lmul_vs2               = prev_lmul(csr_vtype_q.vlmul);

                        // Invalid conversion
                        if (int'(csr_vtype_q.vsew) < int'(EW16) || int'(csr_vtype_q.vlmul) inside {LMUL_1_8})
                          illegal_insn = 1'b1;
                      end
                      5'b00111: begin // VSEXT.VF2
                        ara_req.conversion_vs2 = OpQueueConversionSExt2;
                        ara_req.eew_vs2        = csr_vtype_q.vsew.prev();
                        ara_req.cvt_resize     = CVT_WIDE;
                        ara_req.emul           = csr_vtype_q.vlmul;
                        lmul_vs2               = prev_lmul(csr_vtype_q.vlmul);

                        // Invalid conversion
                        if (int'(csr_vtype_q.vsew) < int'(EW16) || int'(csr_vtype_q.vlmul) inside {LMUL_1_8})
                          illegal_insn = 1'b1;
                      end
                      default: illegal_insn = 1'b1;
                    endcase
                  end
                  // Divide instructions
                  6'b100000: ara_req.op = ara_pkg::VDIVU;
                  6'b100001: ara_req.op = ara_pkg::VDIV;
                  6'b100010: ara_req.op = ara_pkg::VREMU;
                  6'b100011: ara_req.op = ara_pkg::VREM;
                  // Multiply instructions
                  6'b100100: ara_req.op = ara_pkg::VMULHU;
                  6'b100101: ara_req.op = ara_pkg::VMUL;
                  6'b100110: ara_req.op = ara_pkg::VMULHSU;
                  6'b100111: ara_req.op = ara_pkg::VMULH;
                  // Multiply-Add instructions
                  // vd is also used as a source operand
                  6'b101001: begin
                    ara_req.op             = ara_pkg::VMADD;
                    ara_req.use_vd_op      = 1'b1;
                    // Swap "vs2" and "vd" since "vs2" is the addend and "vd" is the multiplicand
                    ara_req.swap_vs2_vd_op = 1'b1;
                  end
                  6'b101011: begin
                    ara_req.op             = ara_pkg::VNMSUB;
                    ara_req.use_vd_op      = 1'b1;
                    ara_req.swap_vs2_vd_op = 1'b1;
                  end
                  6'b101101: begin
                    ara_req.op        = ara_pkg::VMACC;
                    ara_req.use_vd_op = 1'b1;
                  end
                  6'b101111: begin
                    ara_req.op        = ara_pkg::VNMSAC;
                    ara_req.use_vd_op = 1'b1;
                  end
                  // Widening instructions
                  6'b110000: begin // VWADDU
                    ara_req.op             = ara_pkg::VADD;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110001: begin // VWADD
                    ara_req.op             = ara_pkg::VADD;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110010: begin // VWSUBU
                    ara_req.op             = ara_pkg::VSUB;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110011: begin // VWSUB
                    ara_req.op             = ara_pkg::VSUB;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110100: begin // VWADDU.W
                    ara_req.op             = ara_pkg::VADD;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110101: begin // VWADD.W
                    ara_req.op             = ara_pkg::VADD;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110110: begin // VWSUBU.W
                    ara_req.op             = ara_pkg::VSUB;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110111: begin // VWSUB.W
                    ara_req.op             = ara_pkg::VSUB;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111000: begin // VWMULU
                    ara_req.op             = ara_pkg::VMUL;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111010: begin // VWMULSU
                    ara_req.op             = ara_pkg::VMUL;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111011: begin // VWMUL
                    ara_req.op             = ara_pkg::VMUL;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111100: begin // VWMACCU
                    ara_req.op             = ara_pkg::VMACC;
                    ara_req.use_vd_op      = 1'b1;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111101: begin // VWMACC
                    ara_req.op             = ara_pkg::VMACC;
                    ara_req.use_vd_op      = 1'b1;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111111: begin // VWMACCSU
                    ara_req.op             = ara_pkg::VMACC;
                    ara_req.use_vd_op      = 1'b1;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  default: illegal_insn = 1'b1;
                endcase

                // Mask and reduction results occupy one architectural register
                // even though their data sources may use the current LMUL.
                if (single_register_result(ara_req.op) ||
                    ara_req.op inside {VMVXS, VCPOP, VFIRST}) begin
                  ara_req.emul = LMUL_1;
                end

                // Mask logical operands and result each occupy one architectural mask register,
                // independently of the data LMUL selected in vtype.
                if (ara_req.op inside {[VMANDNOT:VMXNOR]}) begin
                  lmul_vs1 = LMUL_1;
                  lmul_vs2 = LMUL_1;
                  // Preserve each source's own physical VRF layout. MASKU
                  // deshuffles the two packed-mask operands independently.
                  ara_req.eew_vs1 = eew_q[ara_req.vs1];
                  ara_req.eew_vs2 = eew_q[ara_req.vs2];
                  // Mask logical instructions preserve elements below vstart and, with
                  // tail-undisturbed policy, all elements at or above vl.
                  if ((csr_vstart_q != '0) || !csr_vtype_q.vta)
                    ara_req.use_vd_op = 1'b1;
                end

                // Mask operands always occupy one architectural register,
                // independently of the data LMUL selected in vtype.
                if (ara_req.op inside {[VMSBF:VMSIF], VIOTA}) lmul_vs2 = LMUL_1;
                if (ara_req.op == VCOMPRESS) lmul_vs1 = LMUL_1;

                // A reduction's vs1 seed and vd result each occupy one architectural register.
                // Only vs2 follows the current vector LMUL.
                if (reduction_result(ara_req.op)) lmul_vs1 = LMUL_1;

                // Instructions with an integer LMUL have extra constraints on the registers they can
                // access. These constraints can be different for the two source operands and the
                // destination register.
                if (!skip_lmul_checks) begin
                  unique case (ara_req.emul)
                    LMUL_2: if (!single_register_result(ara_req.op) &&
                          (insn.varith_type.rd & 5'b00001) != 5'b00000) illegal_insn = ara_req.use_vd;
                    LMUL_4: if (!single_register_result(ara_req.op) &&
                          (insn.varith_type.rd & 5'b00011) != 5'b00000) illegal_insn = ara_req.use_vd;
                    LMUL_8: if (!single_register_result(ara_req.op) &&
                          (insn.varith_type.rd & 5'b00111) != 5'b00000) illegal_insn = ara_req.use_vd;
                    default:;
                  endcase
                  unique case (lmul_vs2)
                    LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                    LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                    LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                    default:;
                  endcase
                  unique case (lmul_vs1)
                    LMUL_2: if ((insn.varith_type.rs1 & 5'b00001) != 5'b00000) illegal_insn |= ara_req.use_vs1;
                    LMUL_4: if ((insn.varith_type.rs1 & 5'b00011) != 5'b00000) illegal_insn |= ara_req.use_vs1;
                    LMUL_8: if ((insn.varith_type.rs1 & 5'b00111) != 5'b00000) illegal_insn |= ara_req.use_vs1;
                    default:;
                  endcase
                end

                // Ara cannot support instructions who operates on more than 64 bits.
                if (int'(ara_req.vtype.vsew) > int'(EW64)) illegal_insn = 1'b1;

                // Instruction is invalid if the vtype is invalid
                if (csr_vtype_q.vill) illegal_insn = 1'b1;
              end

              OPMVX: begin: opmvx
                // These generate a request to Ara's backend
                ara_req.scalar_op     = acc_req_i.rs1;
                ara_req.use_scalar_op = 1'b1;
                ara_req.vs2           = insn.varith_type.rs2;
                ara_req.use_vs2       = 1'b1;
                ara_req.vd            = insn.varith_type.rd;
                ara_req.use_vd        = 1'b1;
                ara_req.vm            = insn.varith_type.vm;
                ara_req.is_stride_np2 = is_stride_np2;
                ara_req_valid         = 1'b1;

                // Decode based on the func6 field
                unique case (insn.varith_type.func6)
                  6'b001000: ara_req.op = ara_pkg::VAADDU;
                  6'b001001: ara_req.op = ara_pkg::VAADD;
                  6'b001010: ara_req.op = ara_pkg::VASUBU;
                  6'b001011: ara_req.op = ara_pkg::VASUB;
                  // Slides
                  6'b001110: begin // vslide1up
                    ara_req.op      = ara_pkg::VSLIDEUP;
                    ara_req.stride  = 1;
                    ara_req.eew_vs2 = csr_vtype_q.vsew;
                    // Request will need reshuffling
                    ara_req.scale_vl = 1'b1;
                  end
                  6'b001111: begin // vslide1down
                    ara_req.op      = ara_pkg::VSLIDEDOWN;
                    ara_req.stride  = 1;
                    ara_req.eew_vs2 = csr_vtype_q.vsew;
                    // Request will need reshuffling
                    ara_req.scale_vl = 1'b1;
                  end
                  6'b010000: begin // VRXUNARY0
                    // vmv.s.x
                    ara_req.op      = ara_pkg::VMVSX;
                    ara_req.use_vs2 = 1'b0;
                    ara_req.vl      = |csr_vl_q ? 1 : '0;
                    // This instruction ignores LMUL checks
                    skip_lmul_checks  = 1'b1;
                  end
                  // Divide instructions
                  6'b100000: ara_req.op = ara_pkg::VDIVU;
                  6'b100001: ara_req.op = ara_pkg::VDIV;
                  6'b100010: ara_req.op = ara_pkg::VREMU;
                  6'b100011: ara_req.op = ara_pkg::VREM;
                  // Multiply instructions
                  6'b100100: ara_req.op = ara_pkg::VMULHU;
                  6'b100101: ara_req.op = ara_pkg::VMUL;
                  6'b100110: ara_req.op = ara_pkg::VMULHSU;
                  6'b100111: ara_req.op = ara_pkg::VMULH;
                  // Multiply-Add instructions
                  // vd is also used as a source operand
                  6'b101001: begin
                    ara_req.op             = ara_pkg::VMADD;
                    ara_req.use_vd_op      = 1'b1;
                    // Swap "vs2" and "vd" since "vs2" is the addend and "vd" is the multiplicand
                    ara_req.swap_vs2_vd_op = 1'b1;
                  end
                  6'b101011: begin
                    ara_req.op             = ara_pkg::VNMSUB;
                    ara_req.use_vd_op      = 1'b1;
                    ara_req.swap_vs2_vd_op = 1'b1;
                  end
                  6'b101101: begin
                    ara_req.op        = ara_pkg::VMACC;
                    ara_req.use_vd_op = 1'b1;
                  end
                  6'b101111: begin
                    ara_req.op        = ara_pkg::VNMSAC;
                    ara_req.use_vd_op = 1'b1;
                  end
                  // Widening instructions
                  6'b110000: begin // VWADDU
                    ara_req.op             = ara_pkg::VADD;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110001: begin // VWADD
                    ara_req.op             = ara_pkg::VADD;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110010: begin // VWSUBU
                    ara_req.op             = ara_pkg::VSUB;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110011: begin // VWSUB
                    ara_req.op             = ara_pkg::VSUB;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110100: begin // VWADDU.W
                    ara_req.op             = ara_pkg::VADD;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110101: begin // VWADD.W
                    ara_req.op             = ara_pkg::VADD;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110110: begin // VWSUBU.W
                    ara_req.op             = ara_pkg::VSUB;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b110111: begin // VWSUB.W
                    ara_req.op             = ara_pkg::VSUB;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111000: begin // VWMULU
                    ara_req.op             = ara_pkg::VMUL;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111010: begin // VWMULSU
                    ara_req.op             = ara_pkg::VMUL;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111011: begin // VWMUL
                    ara_req.op             = ara_pkg::VMUL;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111100: begin // VWMACCU
                    ara_req.op             = ara_pkg::VMACC;
                    ara_req.use_vd_op      = 1'b1;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111101: begin // VWMACC
                    ara_req.op             = ara_pkg::VMACC;
                    ara_req.use_vd_op      = 1'b1;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111110: begin // VWMACCUS
                    ara_req.op             = ara_pkg::VMACC;
                    ara_req.use_vd_op      = 1'b1;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionZExt2;
                    ara_req.conversion_vs2 = OpQueueConversionSExt2;
                    ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  6'b111111: begin // VWMACCSU
                    ara_req.op             = ara_pkg::VMACC;
                    ara_req.use_vd_op      = 1'b1;
                    ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                    ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                    ara_req.conversion_vs1 = OpQueueConversionSExt2;
                    ara_req.conversion_vs2 = OpQueueConversionZExt2;
                    ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    ara_req.cvt_resize     = CVT_WIDE;
                  end
                  default: illegal_insn = 1'b1;
                endcase

                // conversion_vs1 describes the narrow scalar operand for widening .vx forms.
                // The VALU sees the widened destination SEW, so perform this conversion before
                // the request leaves the dispatcher instead of letting the VALU truncate at 2*SEW.
                if (ara_req.conversion_vs1 inside {
                      OpQueueConversionZExt2, OpQueueConversionSExt2
                    }) begin
                  ara_req.scalar_op = widening_scalar_op(
                    acc_req_i.rs1,
                    csr_vtype_q.vsew,
                    ara_req.conversion_vs1 == OpQueueConversionSExt2
                  );
                end

                // Instructions with an integer LMUL have extra constraints on the registers they can
                // access. The constraints can be different for the two source operands and the
                // destination register.
                if (!skip_lmul_checks) begin
                  unique case (ara_req.emul)
                    LMUL_2: if ((insn.varith_type.rd & 5'b00001) != 5'b00000) illegal_insn = ara_req.use_vd;
                    LMUL_4: if ((insn.varith_type.rd & 5'b00011) != 5'b00000) illegal_insn = ara_req.use_vd;
                    LMUL_8: if ((insn.varith_type.rd & 5'b00111) != 5'b00000) illegal_insn = ara_req.use_vd;
                    default:;
                  endcase
                  unique case (lmul_vs2)
                    LMUL_2: if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                    LMUL_4: if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                    LMUL_8: if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                    default:;
                  endcase
                end

                // Ara cannot support instructions who operates on more than 64 bits.
                if (int'(ara_req.vtype.vsew) > int'(EW64)) illegal_insn = 1'b1;

                // Instruction is invalid if the vtype is invalid
                if (csr_vtype_q.vill) illegal_insn = 1'b1;
              end

              OPFVV: begin: opfvv
                if (FPUSupport != FPUSupportNone) begin
                  // These generate a request to Ara's backend
                  ara_req.vs1     = insn.varith_type.rs1;
                  ara_req.use_vs1 = 1'b1;
                  ara_req.vs2     = insn.varith_type.rs2;
                  ara_req.use_vs2 = 1'b1;
                  ara_req.vd      = insn.varith_type.rd;
                  ara_req.use_vd  = 1'b1;
                  ara_req.vm      = insn.varith_type.vm;
                  ara_req.fp_rm   = acc_req_i.frm;
                  ara_req_valid   = 1'b1;

                  // Decode based on the func6 field
                  unique case (insn.varith_type.func6)
                    // VFP Addition
                    6'b000000: begin
                      ara_req.op             = ara_pkg::VFADD;
                      // When performing a floating-point add/sub, fpnew adds the second and the third
                      // operand. Send the first operand (vs2) to the third result queue.
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b000001: begin
                      ara_req.op             = ara_pkg::VFREDUSUM;
                      ara_req.conversion_vs1 = OpQueueReductionZExt;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.cvt_resize     = resize_e'(2'b00);
                    end
                    6'b000010: begin
                      ara_req.op             = ara_pkg::VFSUB;
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b000011: begin
                      ara_req.op             = ara_pkg::VFREDOSUM;
                      ara_req.conversion_vs1 = OpQueueReductionZExt;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.cvt_resize     = resize_e'(2'b00);
                    end
                    6'b000100: ara_req.op = ara_pkg::VFMIN;
                    6'b000101: begin
                      ara_req.op             = ara_pkg::VFREDMIN;
                      ara_req.conversion_vs1 = OpQueueReductionZExt;
                      ara_req.cvt_resize     = resize_e'(2'b01);
                    end
                    6'b000110: ara_req.op = ara_pkg::VFMAX;
                    6'b000111: begin
                      ara_req.op             = ara_pkg::VFREDMAX;
                      ara_req.conversion_vs1 = OpQueueReductionZExt;
                      ara_req.cvt_resize     = resize_e'(2'b10);
                    end
                    6'b001000: ara_req.op = ara_pkg::VFSGNJ;
                    6'b001001: ara_req.op = ara_pkg::VFSGNJN;
                    6'b001010: ara_req.op = ara_pkg::VFSGNJX;
                    6'b010000: begin // VWFUNARY0
                      // vmv.f.s
                      // Stall the interface until we get the result
                      acc_resp_o.req_ready  = 1'b0;
                      acc_resp_o.resp_valid = 1'b0;

                      ara_req.op         = ara_pkg::VFMVFS;
                      ara_req.use_vs1    = 1'b0;
                      ara_req.use_vd     = 1'b0;
                      ara_req.vl         = 1;
                      ara_req.vstart     = '0;
                      skip_lmul_checks     = 1'b1;
                      ignore_zero_vl_check = 1'b1;

                      // Zero-extend operands
                      unique case (csr_vtype_q.vsew)
                        EW16: begin
                          ara_req.conversion_vs2 = OpQueueConversionZExt4;
                        end
                        EW32: begin
                          ara_req.conversion_vs2 = OpQueueConversionZExt2;
                        end
                        default:;
                      endcase

                      // NaN-box the result if needed
                      unique case (csr_vtype_q.vsew)
                        EW16: begin
                          vfmvfs_result[63:16] = '1;
                          vfmvfs_result[15:0]  = ara_resp.resp[15:0];
                        end
                        EW32: begin
                          vfmvfs_result[63:32] = '1;
                          vfmvfs_result[31:0]  = ara_resp.resp[31:0];
                        end
                        default: vfmvfs_result = ara_resp.resp;
                      endcase

                      // Wait until the back-end answers to acknowledge those instructions
                      if (ara_resp_valid) begin
                        acc_resp_o.req_ready  = 1'b1;
                        acc_resp_o.resp_valid = 1'b1;
                        acc_resp_o.result     = vfmvfs_result;
                        acc_resp_o.exception  = ara_resp.exception;
                        ara_req_valid       = 1'b0;
                      end
                    end
                    6'b011000: begin
                      ara_req.op = ara_pkg::VMFEQ;
                      ara_req.use_vd_op  = 1'b1;
                      ara_req.eew_vs1    = csr_vtype_q.vsew;
                      ara_req.eew_vs2    = csr_vtype_q.vsew;
                      ara_req.eew_vd_op  = eew_q[ara_req.vd];
                      ara_req.vtype.vsew = eew_q[ara_req.vd];
                    end
                    6'b011001: begin
                      ara_req.op = ara_pkg::VMFLE;
                      ara_req.use_vd_op  = 1'b1;
                      ara_req.eew_vs1    = csr_vtype_q.vsew;
                      ara_req.eew_vs2    = csr_vtype_q.vsew;
                      ara_req.eew_vd_op  = eew_q[ara_req.vd];
                      ara_req.vtype.vsew = eew_q[ara_req.vd];
                    end
                    6'b011011: begin
                      ara_req.op = ara_pkg::VMFLT;
                      ara_req.use_vd_op  = 1'b1;
                      ara_req.eew_vs1    = csr_vtype_q.vsew;
                      ara_req.eew_vs2    = csr_vtype_q.vsew;
                      ara_req.eew_vd_op  = eew_q[ara_req.vd];
                      ara_req.vtype.vsew = eew_q[ara_req.vd];
                    end
                    6'b011100: begin
                      ara_req.op = ara_pkg::VMFNE;
                      ara_req.use_vd_op  = 1'b1;
                      ara_req.eew_vs1    = csr_vtype_q.vsew;
                      ara_req.eew_vs2    = csr_vtype_q.vsew;
                      ara_req.eew_vd_op  = eew_q[ara_req.vd];
                      ara_req.vtype.vsew = eew_q[ara_req.vd];
                    end
                    6'b010010: begin // VFUNARY0
                      // These instructions do not use vs1
                      ara_req.use_vs1    = 1'b0;

                      case (insn.varith_type.rs1)
                        5'b00000: ara_req.op = VFCVTXUF;
                        5'b00001: ara_req.op = VFCVTXF;
                        5'b00010: ara_req.op = VFCVTFXU;
                        5'b00011: ara_req.op = VFCVTFX;
                        5'b00110: ara_req.op = VFCVTRTZXUF;
                        5'b00111: ara_req.op = VFCVTRTZXF;
                        5'b01000: begin // Widening VFCVTXUF
                          ara_req.op             = VFCVTXUF;
                          ara_req.cvt_resize     = CVT_WIDE;
                          ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                          ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                          ara_req.conversion_vs2 = OpQueueAdjustFPCvt;
                        end
                        5'b01001: begin // Widening VFCVTXF
                          ara_req.op             = VFCVTXF;
                          ara_req.cvt_resize     = CVT_WIDE;
                          ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                          ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                          ara_req.conversion_vs2 = OpQueueAdjustFPCvt;
                        end
                        5'b01010: begin // Widening VFCVTFXU
                          ara_req.op             = VFCVTFXU;
                          ara_req.cvt_resize     = CVT_WIDE;
                          ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                          ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                          ara_req.conversion_vs2 = OpQueueAdjustFPCvt;
                        end
                        5'b01011: begin // Widening VFCVTFX
                          ara_req.op             = VFCVTFX;
                          ara_req.cvt_resize     = CVT_WIDE;
                          ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                          ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                          ara_req.conversion_vs2 = OpQueueAdjustFPCvt;
                        end
                        5'b01100: begin // Widening VFCVTFF
                          ara_req.op             = VFCVTFF;
                          ara_req.cvt_resize     = CVT_WIDE;
                          ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                          ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                          ara_req.conversion_vs2 = OpQueueAdjustFPCvt;
                        end
                        5'b01110: begin // Widening VFCVTRTZXUF
                          ara_req.op             = VFCVTRTZXUF;
                          ara_req.cvt_resize     = CVT_WIDE;
                          ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                          ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                          ara_req.conversion_vs2 = OpQueueAdjustFPCvt;
                        end
                        5'b01111: begin // Widening VFCVTRTZXF
                          ara_req.op             = VFCVTRTZXF;
                          ara_req.cvt_resize     = CVT_WIDE;
                          ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                          ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                          ara_req.conversion_vs2 = OpQueueAdjustFPCvt;
                        end
                        5'b10000: begin // Narrowing VFCVTXUF
                          ara_req.op             = VFCVTXUF;
                          ara_req.cvt_resize     = CVT_NARROW;
                          ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                        end
                        5'b10001: begin // Narrowing VFCVTXF
                          ara_req.op             = VFCVTXF;
                          ara_req.cvt_resize     = CVT_NARROW;
                          ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                        end
                        5'b10010: begin // Narrowing VFCVTFXU
                          ara_req.op             = VFCVTFXU;
                          ara_req.cvt_resize     = CVT_NARROW;
                          ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                        end
                        5'b10011: begin // Narrowing VFCVTFX
                          ara_req.op             = VFCVTFX;
                          ara_req.cvt_resize     = CVT_NARROW;
                          ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                        end
                        5'b10100: begin // Narrowing VFCVTFF
                          ara_req.op             = VFCVTFF;
                          ara_req.cvt_resize     = CVT_NARROW;
                          ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                        end
                        5'b10101: begin // Narrowing VFNCVTRODFF
                          ara_req.op             = VFNCVTRODFF;
                          ara_req.cvt_resize     = CVT_NARROW;
                          ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                        end
                        5'b10110: begin // Narrowing VFCVTRTZXUF
                          ara_req.op             = VFCVTRTZXUF;
                          ara_req.cvt_resize     = CVT_NARROW;
                          ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                        end
                        5'b10111: begin // Narrowing VFCVTRTZXF
                          ara_req.op             = VFCVTRTZXF;
                          ara_req.cvt_resize     = CVT_NARROW;
                          ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                        end
                        default: begin
                          // Trigger an error
                          illegal_insn = 1'b1;
                        end
                      endcase
                      // Narrowing conversions consume a 2*SEW source group.
                      // Its EMUL is therefore twice the destination LMUL even
                      // though ara_req.emul continues to describe the result.
                      if (ara_req.cvt_resize == CVT_NARROW)
                        lmul_vs2 = next_lmul(csr_vtype_q.vlmul);
                    end
                    6'b010011: begin // VFUNARY1
                    // These instructions do not use vs1
                    ara_req.use_vs1    = 1'b0;

                    unique case (insn.varith_type.rs1)
                      5'b00000: ara_req.op = ara_pkg::VFSQRT;
                      5'b00100: ara_req.op = ara_pkg::VFRSQRT7;
                      5'b00101: ara_req.op = ara_pkg::VFREC7;
                      5'b10000: ara_req.op = ara_pkg::VFCLASS;
                      default : illegal_insn = 1'b1;
                    endcase

                    end
                    6'b100000: ara_req.op = ara_pkg::VFDIV;
                    6'b100100: ara_req.op = ara_pkg::VFMUL;
                    6'b101000: begin
                      ara_req.op             = ara_pkg::VFMADD;
                      ara_req.use_vd_op      = 1'b1;
                      // Swap "vs2" and "vd" since "vs2" is the addend and "vd" is the multiplicand
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b101001: begin
                      ara_req.op             = ara_pkg::VFNMADD;
                      ara_req.use_vd_op      = 1'b1;
                      // Swap "vs2" and "vd" since "vs2" is the addend and "vd" is the multiplicand
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b101010: begin
                      ara_req.op             = ara_pkg::VFMSUB;
                      ara_req.use_vd_op      = 1'b1;
                      // Swap "vs2" and "vd" since "vs2" is the addend and "vd" is the multiplicand
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b101011: begin
                      ara_req.op             = ara_pkg::VFNMSUB;
                      ara_req.use_vd_op      = 1'b1;
                      // Swap "vs2" and "vd" since "vs2" is the addend and "vd" is the multiplicand
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b101100: begin
                      ara_req.op        = ara_pkg::VFMACC;
                      ara_req.use_vd_op = 1'b1;
                    end
                    6'b101101: begin
                      ara_req.op        = ara_pkg::VFNMACC;
                      ara_req.use_vd_op = 1'b1;
                    end
                    6'b101110: begin
                      ara_req.op        = ara_pkg::VFMSAC;
                      ara_req.use_vd_op = 1'b1;
                    end
                    6'b101111: begin
                      ara_req.op        = ara_pkg::VFNMSAC;
                      ara_req.use_vd_op = 1'b1;
                    end
                    6'b110000: begin // VFWADD
                      ara_req.op             = ara_pkg::VFADD;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueConversionWideFP2;
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                    end
                    6'b110001: begin // VFWREDUSUM
                      ara_req.op             = ara_pkg::VFWREDUSUM;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueReductionZExt;
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.eew_vs1        = csr_vtype_q.vsew.next();
                      ara_req.cvt_resize     = resize_e'(2'b00);
                    end
                    6'b110010: begin // VFWSUB
                      ara_req.op             = ara_pkg::VFSUB;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueConversionWideFP2;
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                    end
                    6'b110011: begin // VFWREDOSUM
                      ara_req.op             = ara_pkg::VFWREDOSUM;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueReductionZExt;
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.eew_vs1        = csr_vtype_q.vsew.next();
                      ara_req.cvt_resize     = resize_e'(2'b00);
                    end
                    6'b110100: begin // VFWADD.W
                      ara_req.op             = ara_pkg::VFADD;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueConversionWideFP2;
                    end
                    6'b110110: begin // VFWSUB.W
                      ara_req.op             = ara_pkg::VFSUB;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueConversionWideFP2;
                    end
                    6'b111000: begin // VFWMUL
                      ara_req.op             = ara_pkg::VFMUL;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueConversionWideFP2;
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                    end
                    6'b111100: begin // VFWMACC
                      ara_req.op             = ara_pkg::VFMACC;
                      ara_req.use_vd_op      = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueConversionWideFP2;
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    end
                    6'b111101: begin // VFWNMACC
                      ara_req.op             = ara_pkg::VFNMACC;
                      ara_req.use_vd_op      = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueConversionWideFP2;
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    end
                    6'b111110: begin // VFWMSAC
                      ara_req.op             = ara_pkg::VFMSAC;
                      ara_req.use_vd_op      = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueConversionWideFP2;
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    end
                    6'b111111: begin // VFWNMSAC
                      ara_req.op             = ara_pkg::VFNMSAC;
                      ara_req.use_vd_op      = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs1 = OpQueueConversionWideFP2;
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    end
                    default: illegal_insn = 1'b1;
                  endcase

                  // Reduction seeds and results are scalar vector-register operands.
                  // Only vs2 follows the data LMUL.
                  if (reduction_result(ara_req.op)) lmul_vs1 = LMUL_1;

                  // Instructions with an integer LMUL have extra constraints on the registers they
                  // can access. The constraints can be different for the two source operands and the
                  // destination register.
                  if (!skip_lmul_checks) begin
                    unique case (ara_req.emul)
                      LMUL_2   : if (!single_register_result(ara_req.op) &&
                        (insn.varith_type.rd & 5'b00001) != 5'b00000) illegal_insn = ara_req.use_vd;
                      LMUL_4   : if (!single_register_result(ara_req.op) &&
                        (insn.varith_type.rd & 5'b00011) != 5'b00000) illegal_insn = ara_req.use_vd;
                      LMUL_8   : if (!single_register_result(ara_req.op) &&
                        (insn.varith_type.rd & 5'b00111) != 5'b00000) illegal_insn = ara_req.use_vd;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                    unique case (lmul_vs2)
                      LMUL_2   : if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                      LMUL_4   : if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                      LMUL_8   : if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                    unique case (lmul_vs1)
                      LMUL_2   : if ((insn.varith_type.rs1 & 5'b00001) != 5'b00000) illegal_insn |= ara_req.use_vs1;
                      LMUL_4   : if ((insn.varith_type.rs1 & 5'b00011) != 5'b00000) illegal_insn |= ara_req.use_vs1;
                      LMUL_8   : if ((insn.varith_type.rs1 & 5'b00111) != 5'b00000) illegal_insn |= ara_req.use_vs1;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end

                  // Ara can support 8-bit float, 16-bit float, 32-bit float, 64-bit float.
                  // Ara cannot support instructions who operates on more than 64 bits.
                  unique case (FPUSupport)
                    FPUSupportAll: if (int'(csr_vtype_q.vsew) > int'(EW64) || int'(ara_req.eew_vs2) > int'(EW64))
                          illegal_insn = 1'b1;
                    FPUSupportHalfSingleDouble: if (int'(csr_vtype_q.vsew) < int'(EW16) ||
                          int'(csr_vtype_q.vsew) > int'(EW64) || int'(ara_req.eew_vs2) > int'(EW64))
                          illegal_insn = 1'b1;
                    FPUSupportHalfSingle: if (int'(csr_vtype_q.vsew) < int'(EW16) ||
                          int'(csr_vtype_q.vsew) > int'(EW32) || int'(ara_req.eew_vs2) > int'(EW32))
                          illegal_insn = 1'b1;
                    FPUSupportSingleDouble: if (int'(csr_vtype_q.vsew) < int'(EW32) ||
                          int'(csr_vtype_q.vsew) > int'(EW64) || int'(ara_req.eew_vs2) > int'(EW64))
                          illegal_insn = 1'b1;
                    FPUSupportHalf: if (int'(csr_vtype_q.vsew) != int'(EW16) || int'(ara_req.eew_vs2) > int'(EW16))
                          illegal_insn = 1'b1;
                    FPUSupportSingle: if (int'(csr_vtype_q.vsew) != int'(EW32) || int'(ara_req.eew_vs2) > int'(EW32))
                        illegal_insn = 1'b1;
                    FPUSupportDouble: if (int'(csr_vtype_q.vsew) != int'(EW64) || int'(ara_req.eew_vs2) > int'(EW64))
                        illegal_insn = 1'b1;
                    default: illegal_insn = 1'b1; // Unsupported configuration
                  endcase

                  // Instruction is invalid if the vtype is invalid
                  if (csr_vtype_q.vill) illegal_insn = 1'b1;
                end else illegal_insn = 1'b1; // Vector FP instructions are disabled
              end

              OPFVF: begin: opfvf
                if (FPUSupport != FPUSupportNone) begin
                  // These generate a request to Ara's backend
                  ara_req.scalar_op     = acc_req_i.rs1;
                  ara_req.use_scalar_op = 1'b1;
                  ara_req.vs2           = insn.varith_type.rs2;
                  ara_req.use_vs2       = 1'b1;
                  ara_req.vd            = insn.varith_type.rd;
                  ara_req.use_vd        = 1'b1;
                  ara_req.vm            = insn.varith_type.vm;
                  ara_req.is_stride_np2 = is_stride_np2;
                  ara_req.fp_rm         = acc_req_i.frm;
                  ara_req_valid         = 1'b1;

                  // Decode based on the func6 field
                  unique case (insn.varith_type.func6)
                    6'b000000: begin
                      ara_req.op             = ara_pkg::VFADD;
                      // When performing a floating-point add/sub, fpnew adds the second and the third
                      // operand
                      // So, send the first operand (vs2) to the third result queue
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b000010: begin
                      ara_req.op             = ara_pkg::VFSUB;
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b000100: ara_req.op = ara_pkg::VFMIN;
                    6'b000110: ara_req.op = ara_pkg::VFMAX;
                    6'b001000: ara_req.op = ara_pkg::VFSGNJ;
                    6'b001001: ara_req.op = ara_pkg::VFSGNJN;
                    6'b001010: ara_req.op = ara_pkg::VFSGNJX;
                    6'b001110: begin // vfslide1up
                      ara_req.op     = ara_pkg::VSLIDEUP;
                      ara_req.stride = 1;
                    ara_req.eew_vs2  = csr_vtype_q.vsew;
                    // Request will need reshuffling
                    ara_req.scale_vl = 1'b1;
                    end
                    6'b001111: begin // vfslide1down
                      ara_req.op     = ara_pkg::VSLIDEDOWN;
                      ara_req.stride = 1;
                    ara_req.eew_vs2  = csr_vtype_q.vsew;
                    // Request will need reshuffling
                    ara_req.scale_vl = 1'b1;
                    end
                    6'b010000: begin // VRFUNARY0
                      // vmv.s.f
                      ara_req.op      = ara_pkg::VFMVSF;
                      ara_req.use_vs2 = 1'b0;
                      ara_req.vl      = |csr_vl_q ? 1 : '0;
                      // This instruction ignores LMUL checks
                      skip_lmul_checks  = 1'b1;
                    end
                    6'b010111: ara_req.op = ara_pkg::VMERGE;
                    6'b011000: begin
                      ara_req.op = ara_pkg::VMFEQ;
                      ara_req.use_vd_op  = 1'b1;
                      ara_req.eew_vs1    = csr_vtype_q.vsew;
                      ara_req.eew_vs2    = csr_vtype_q.vsew;
                      ara_req.eew_vd_op  = eew_q[ara_req.vd];
                      ara_req.vtype.vsew = eew_q[ara_req.vd];
                    end
                    6'b011001: begin
                      ara_req.op = ara_pkg::VMFLE;
                      ara_req.use_vd_op  = 1'b1;
                      ara_req.eew_vs1    = csr_vtype_q.vsew;
                      ara_req.eew_vs2    = csr_vtype_q.vsew;
                      ara_req.eew_vd_op  = eew_q[ara_req.vd];
                      ara_req.vtype.vsew = eew_q[ara_req.vd];
                    end
                    6'b011011: begin
                      ara_req.op = ara_pkg::VMFLT;
                      ara_req.use_vd_op  = 1'b1;
                      ara_req.eew_vs1    = csr_vtype_q.vsew;
                      ara_req.eew_vs2    = csr_vtype_q.vsew;
                      ara_req.eew_vd_op  = eew_q[ara_req.vd];
                      ara_req.vtype.vsew = eew_q[ara_req.vd];
                    end
                    6'b011100: begin
                      ara_req.op = ara_pkg::VMFNE;
                      ara_req.use_vd_op  = 1'b1;
                      ara_req.eew_vs1    = csr_vtype_q.vsew;
                      ara_req.eew_vs2    = csr_vtype_q.vsew;
                      ara_req.eew_vd_op  = eew_q[ara_req.vd];
                      ara_req.vtype.vsew = eew_q[ara_req.vd];
                    end
                    6'b011101: begin
                      ara_req.op = ara_pkg::VMFGT;
                      ara_req.use_vd_op  = 1'b1;
                      ara_req.eew_vs1    = csr_vtype_q.vsew;
                      ara_req.eew_vs2    = csr_vtype_q.vsew;
                      ara_req.eew_vd_op  = eew_q[ara_req.vd];
                      ara_req.vtype.vsew = eew_q[ara_req.vd];
                    end
                    6'b011111: begin
                      ara_req.op = ara_pkg::VMFGE;
                      ara_req.use_vd_op  = 1'b1;
                      ara_req.eew_vs1    = csr_vtype_q.vsew;
                      ara_req.eew_vs2    = csr_vtype_q.vsew;
                      ara_req.eew_vd_op  = eew_q[ara_req.vd];
                      ara_req.vtype.vsew = eew_q[ara_req.vd];
                    end
                    6'b100100: ara_req.op = ara_pkg::VFMUL;
                    6'b100000: ara_req.op = ara_pkg::VFDIV;
                    6'b100001: ara_req.op = ara_pkg::VFRDIV;
                    6'b100111: begin
                      ara_req.op             = ara_pkg::VFRSUB;
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b101000: begin
                      ara_req.op             = ara_pkg::VFMADD;
                      ara_req.use_vd_op      = 1'b1;
                      // Swap "vs2" and "vd" since "vs2" is the addend and "vd" is the multiplicand
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b101001: begin
                      ara_req.op             = ara_pkg::VFNMADD;
                      ara_req.use_vd_op      = 1'b1;
                      // Swap "vs2" and "vd" since "vs2" is the addend and "vd" is the multiplicand
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b101010: begin
                      ara_req.op             = ara_pkg::VFMSUB;
                      ara_req.use_vd_op      = 1'b1;
                      // Swap "vs2" and "vd" since "vs2" is the addend and "vd" is the multiplicand
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b101011: begin
                      ara_req.op             = ara_pkg::VFNMSUB;
                      ara_req.use_vd_op      = 1'b1;
                      // Swap "vs2" and "vd" since "vs2" is the addend and "vd" is the multiplicand
                      ara_req.swap_vs2_vd_op = 1'b1;
                    end
                    6'b101100: begin
                      ara_req.op        = ara_pkg::VFMACC;
                      ara_req.use_vd_op = 1'b1;
                    end
                    6'b101101: begin
                      ara_req.op        = ara_pkg::VFNMACC;
                      ara_req.use_vd_op = 1'b1;
                    end
                    6'b101110: begin
                      ara_req.op        = ara_pkg::VFMSAC;
                      ara_req.use_vd_op = 1'b1;
                    end
                    6'b101111: begin
                      ara_req.op        = ara_pkg::VFNMSAC;
                      ara_req.use_vd_op = 1'b1;
                    end
                    6'b110000: begin // VFWADD
                      ara_req.op             = ara_pkg::VFADD;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.wide_fp_imm    = 1'b1;
                    end
                    6'b110010: begin // VFWSUB
                      ara_req.op             = ara_pkg::VFSUB;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.wide_fp_imm    = 1'b1;
                    end
                    6'b110100: begin // VFWADD.W
                      ara_req.op             = ara_pkg::VFADD;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                      ara_req.wide_fp_imm    = 1'b1;
                    end
                    6'b110110: begin // VFWSUB.W
                      ara_req.op             = ara_pkg::VFSUB;
                      ara_req.swap_vs2_vd_op = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      lmul_vs2                 = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.eew_vs2        = csr_vtype_q.vsew.next();
                      ara_req.wide_fp_imm    = 1'b1;
                    end
                    6'b111000: begin // VFWMUL
                      ara_req.op             = ara_pkg::VFMUL;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.wide_fp_imm    = 1'b1;
                    end
                    6'b111100: begin // VFWMACC
                      ara_req.op             = ara_pkg::VFMACC;
                      ara_req.use_vd_op      = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.wide_fp_imm    = 1'b1;
                      ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    end
                    6'b111101: begin // VFWNMACC
                      ara_req.op             = ara_pkg::VFNMACC;
                      ara_req.use_vd_op      = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.wide_fp_imm    = 1'b1;
                      ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    end
                    6'b111110: begin // VFWMSAC
                      ara_req.op             = ara_pkg::VFMSAC;
                      ara_req.use_vd_op      = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.wide_fp_imm    = 1'b1;
                      ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    end
                    6'b111111: begin // VFWNMSAC
                      ara_req.op             = ara_pkg::VFNMSAC;
                      ara_req.use_vd_op      = 1'b1;
                      ara_req.emul           = next_lmul(csr_vtype_q.vlmul);
                      ara_req.vtype.vsew     = csr_vtype_q.vsew.next();
                      ara_req.conversion_vs2 = OpQueueConversionWideFP2;
                      ara_req.wide_fp_imm    = 1'b1;
                      ara_req.eew_vd_op      = csr_vtype_q.vsew.next();
                    end
                    default: illegal_insn = 1'b1;
                  endcase

                  // Check if the FP scalar operand is NaN-boxed. If not, replace it with a NaN.
                  case (csr_vtype_q.vsew)
                    EW16: if (~(&acc_req_i.rs1[63:16])) ara_req.scalar_op = 64'h0000000000007e00;
                    EW32: if (~(&acc_req_i.rs1[63:32])) ara_req.scalar_op = 64'h000000007fc00000;
                  endcase

                  // Instructions with an integer LMUL have extra constraints on the registers they
                  // can access. The constraints can be different for the two source operands and the
                  // destination register.
                  if (!skip_lmul_checks) begin
                    unique case (ara_req.emul)
                      LMUL_2   : if (!mask_result(ara_req.op) &&
                        (insn.varith_type.rd & 5'b00001) != 5'b00000) illegal_insn = ara_req.use_vd;
                      LMUL_4   : if (!mask_result(ara_req.op) &&
                        (insn.varith_type.rd & 5'b00011) != 5'b00000) illegal_insn = ara_req.use_vd;
                      LMUL_8   : if (!mask_result(ara_req.op) &&
                        (insn.varith_type.rd & 5'b00111) != 5'b00000) illegal_insn = ara_req.use_vd;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                    unique case (lmul_vs2)
                      LMUL_2   : if ((insn.varith_type.rs2 & 5'b00001) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                      LMUL_4   : if ((insn.varith_type.rs2 & 5'b00011) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                      LMUL_8   : if ((insn.varith_type.rs2 & 5'b00111) != 5'b00000) illegal_insn |= ara_req.use_vs2;
                      LMUL_RSVD: illegal_insn = 1'b1;
                      default:;
                    endcase
                  end

                  // Ara can support 16-bit float, 32-bit float, 64-bit float.
                  // Ara cannot support instructions who operates on more than 64 bits.
                  unique case (FPUSupport)
                    FPUSupportAll: if (int'(csr_vtype_q.vsew) > int'(EW64)) illegal_insn = 1'b1;
                    FPUSupportHalfSingleDouble: if (int'(csr_vtype_q.vsew) < int'(EW16) ||
                          int'(csr_vtype_q.vsew) > int'(EW64)) illegal_insn = 1'b1;
                    FPUSupportHalfSingle: if (int'(csr_vtype_q.vsew) < int'(EW16) ||
                          int'(csr_vtype_q.vsew) > int'(EW32)) illegal_insn = 1'b1;
                    FPUSupportSingleDouble: if (int'(csr_vtype_q.vsew) < int'(EW32) ||
                          int'(csr_vtype_q.vsew) > int'(EW64)) illegal_insn = 1'b1;
                    FPUSupportHalf: if (int'(csr_vtype_q.vsew) != int'(EW16)) illegal_insn = 1'b1;
                    FPUSupportSingle: if (int'(csr_vtype_q.vsew) != int'(EW32))
                        illegal_insn = 1'b1;
                    FPUSupportDouble: if (int'(csr_vtype_q.vsew) != int'(EW64))
                        illegal_insn = 1'b1;
                    default: illegal_insn = 1'b1; // Unsupported configuration
                  endcase

                  // Instruction is invalid if the vtype is invalid
                  if (csr_vtype_q.vill) illegal_insn = 1'b1;
                end else illegal_insn = 1'b1; // Vector FP instructions are disabled
              end
            endcase
          end

          ////////////////////
          //  Vector Loads  //
          ////////////////////

          riscv::OpcodeLoadFp: begin
            // Instruction is of one of the RVV types
            automatic rvv_instruction_t insn = rvv_instruction_t'(instr.instr);

            // The instruction is a load
            is_vload = 1'b1;

            // Wait before acknowledging this instruction
            acc_resp_o.req_ready = 1'b0;

            // These generate a request to Ara's backend
            ara_req.vd        = insn.vmem_type.rd;
            ara_req.use_vd    = 1'b1;
            ara_req.vm        = insn.vmem_type.vm;
            ara_req.scalar_op = acc_req_i.rs1;
            ara_req.nf        = insn.vmem_type.nf;
            ara_req_valid     = 1'b1;

            // Decode the element width
            // Indexed memory operations follow a different rule
            unique case ({insn.vmem_type.mew, insn.vmem_type.width})
              4'b0000: begin
                  if (insn.vmem_type.mop != 2'b01 && insn.vmem_type.mop != 2'b11) begin
                    ara_req.vtype.vsew = EW8;
                  end else begin
                    ara_req.vtype.vsew = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = EW8;
                    ara_req.scale_vl   = 1'b1;
                  end
              end
              4'b0101: begin
                  if (insn.vmem_type.mop != 2'b01 && insn.vmem_type.mop != 2'b11) begin
                    ara_req.vtype.vsew = EW16;
                  end else begin
                    ara_req.vtype.vsew = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = EW16;
                    ara_req.scale_vl   = 1'b1;
                  end
              end
              4'b0110: begin
                  if (insn.vmem_type.mop != 2'b01 && insn.vmem_type.mop != 2'b11) begin
                    ara_req.vtype.vsew = EW32;
                  end else begin
                    ara_req.vtype.vsew = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = EW32;
                    ara_req.scale_vl   = 1'b1;
                  end
              end
              4'b0111: begin
                  if (insn.vmem_type.mop != 2'b01 && insn.vmem_type.mop != 2'b11) begin
                    ara_req.vtype.vsew = EW64;
                  end else begin
                    ara_req.vtype.vsew = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = EW64;
                    ara_req.scale_vl   = 1'b1;
                  end
              end
              default: begin // Invalid. Element is too wide, or encoding is non-existant.
                acc_resp_o.req_ready  = 1'b1;
                acc_resp_o.resp_valid = 1'b1;
                illegal_insn          = 1'b1;
                ara_req_valid       = 1'b0;
              end
            endcase

            // Decode the addressing mode
            unique case (insn.vmem_type.mop)
              2'b00: begin
                ara_req.op = VLE;

                // Decode the lumop field
                case (insn.vmem_type.rs2)
                  5'b00000:;      // Unit-strided
                  5'b01000:;      // Unit-strided, whole registers
                  5'b01011: begin // Unit-strided, mask load, EEW=1
                    // We operate ceil(vl/8) bytes
                    ara_req.vl         = (csr_vl_q >> 3) + |csr_vl_q[2:0];
                    ara_req.vtype.vsew = EW8;
                    mask_mem_noop      = csr_vstart_q >= ara_req.vl;
                  end
                  5'b10000: begin // Unit-strided, fault-only first
                    ara_req.fault_only_first = 1'b1;
                  end
                  default: begin // Reserved
                    illegal_insn_load     = 1'b1;
                  end
                endcase
              end
              2'b10: begin
                ara_req.op     = VLSE;
                ara_req.stride = acc_req_i.rs2;
              end
              2'b01, // Indexed-unordered
              2'b11: begin // Indexed-ordered
                ara_req.op      = VLXE;
                // These also read vs2
                ara_req.vs2     = insn.vmem_type.rs2;
                ara_req.use_vs2 = 1'b1;
                ara_req.old_eew_vs2 = eew_q[insn.vmem_type.rs2 +
                    active_first_register(ara_req.eew_vs2, ara_req.vstart)];
                lmul_vs2 = vlmul_e'(csr_vtype_q.vlmul +
                    (ara_req.eew_vs2 - csr_vtype_q.vsew));
              end
              default:;
            endcase

            // For memory operations: EMUL = LMUL * (EEW / SEW)
            // EEW is encoded in the instruction
            ara_req.emul = vlmul_e'(csr_vtype_q.vlmul + (ara_req.vtype.vsew - csr_vtype_q.vsew));

            // Mask loads transfer ceil(vl/8) bytes to one architectural mask
            // register. Their EMUL is fixed at one, independently of vtype.
            if (insn.vmem_type.mop == 2'b00 && insn.vmem_type.rs2 == 5'b01011)
              ara_req.emul = LMUL_1;

            // Exception if EMUL > 8 or < 1/8.  Mask memory operations have
            // architecturally fixed EMUL=1, so the generic EEW/SEW-derived
            // sign-transition check does not apply to them.
            if (!(insn.vmem_type.mop == 2'b00 && insn.vmem_type.rs2 == 5'b01011)) begin
              unique case ({csr_vtype_q.vlmul[2], ara_req.emul[2]})
                // The new emul is lower than the previous lmul
                2'b01: begin
                  // But the new eew is greater than vsew
                  if (signed'(ara_req.vtype.vsew - csr_vtype_q.vsew) > 0) begin
                    illegal_insn_load = 1'b1;
                  end
                end
                // The new emul is greater than the previous lmul
                2'b10: begin
                  // But the new eew is lower than vsew
                  if (signed'(ara_req.vtype.vsew - csr_vtype_q.vsew) < 0) begin
                    illegal_insn_load = 1'b1;
                  end
                end
                default:;
              endcase
            end

            // Instructions with an integer LMUL have extra constraints on the registers they can
            // access.
            unique case (ara_req.emul)
              LMUL_2: if ((insn.varith_type.rd & 5'b00001) != 5'b00000) begin
                illegal_insn_load     = 1'b1;
              end
              LMUL_4: if ((insn.varith_type.rd & 5'b00011) != 5'b00000) begin
                illegal_insn_load     = 1'b1;
              end
              LMUL_8: if ((insn.varith_type.rd & 5'b00111) != 5'b00000) begin
                illegal_insn_load     = 1'b1;
              end
              LMUL_RSVD: begin
                illegal_insn_load     = 1'b1;
              end
              default:;
            endcase

            // Check for segment loads
            if (ara_req.nf != 3'b000 &&
                !(insn.vmem_type.mop == 2'b00 &&
                  insn.vmem_type.rs2 == 5'b01000)) begin
              if (pending_seg_mem_op_q) begin
                // This is a segment load instruction
                is_segment_mem_op = 1'b1;
                // Remove pending segment mem op when over
                if (seg_mem_op_end) pending_seg_mem_op_d = 1'b0;
              end else begin
                // Wait for idle not to mess with load/store_complete_i
                // since the segment sequencer filters these signals
                ara_req_valid = 1'b0;
                pending_seg_mem_op_d = 1'b1;
                state_d = WAIT_IDLE;
              end
              // nf encodes NFIELDS-1. Each fractional-EMUL field starts in a
              // distinct register; integer EMUL fields occupy EMUL registers.
              if (segment_register_count(ara_req.nf, ara_req.emul) > 8)
                illegal_insn = 1'b1;
              if (unsigned'(ara_req.vd) +
                    segment_register_count(ara_req.nf, ara_req.emul) > 32)
                illegal_insn = 1'b1;
            end

            // Vector whole register loads overwrite all the other decoding information.
            if (ara_req.op == VLE && insn.vmem_type.rs2 == 5'b01000) begin
              // Execute also if vl == 0
              ignore_zero_vl_check = 1'b1;
              // The LMUL value is kept in the instruction itself
              illegal_insn_load     = 1'b0;
              ara_req_valid  = 1'b1;

              // VLSU moves whole-register transfers as a byte stream. vstart
              // is architecturally expressed in elements of the encoded EEW,
              // so convert it before replacing that EEW with EW8.
              ara_req.vstart = csr_vstart_q << unsigned'(ara_req.vtype.vsew);

              // Maximum vector length. VLMAX = nf * VLEN / EW8.
              ara_req.vtype.vsew = EW8;
              unique case (insn.vmem_type.nf)
                3'd0: begin
                  ara_req.vl = VLENB << 0;
                  ara_req.emul = LMUL_1;
                end
                3'd1: begin
                  ara_req.vl = VLENB << 1;
                  ara_req.emul = LMUL_2;
                end
                3'd3:  begin
                  ara_req.vl = VLENB << 2;
                  ara_req.emul = LMUL_4;
                end
                3'd7:  begin
                  ara_req.vl = VLENB << 3;
                  ara_req.emul = LMUL_8;
                end
                default: begin
                  // Trigger an error for the reserved simm values
                  illegal_insn_load = 1'b1;
                end
              endcase

              // A restarted whole-register transfer with vstart >= evl has
              // no active body. Resolve it without entering VLSU, where the
              // byte-count subtraction would otherwise underflow.
              if (ara_req.vstart >= ara_req.vl) begin
                mask_mem_noop = 1'b1;
                ignore_zero_vl_check = 1'b0;
              end
            end

            // Wait until the back-end answers to acknowledge those instructions
            if ( ara_resp_valid ) begin
              acc_resp_o.req_ready  = 1'b1;
              acc_resp_o.resp_valid = 1'b1;
              acc_resp_o.exception  = ara_resp.exception;
              ara_req_valid       = 1'b0;
              // In case of exception, modify vstart or vl, depending if the insn
              // was a fault-only-first
              if (ara_resp.fof_exception) begin
                csr_vl_d = ara_resp.exception_vstart;
                // Mask exception if we had a fault-only-first with exception on
                // idx > 0
                acc_resp_o.exception.valid = 1'b0;
                // Flush if mask reg was involved in the fof operation
                if (!ara_req.vm) begin
                  state_d = WAIT_IDLE_FLUSH;
                end
              end else if (ara_resp.exception.valid) begin
                csr_vstart_d = ara_resp.exception_vstart;
                // If this load has VRF source operands, flush everything
                if (!ara_req.vm || ara_req.use_vs2) begin
                  state_d = WAIT_IDLE_FLUSH;
                end
              end
            end
          end

          /////////////////////
          //  Vector Stores  //
          /////////////////////

          // Vector stores encode:
          //  - The target EEW in ara_req.vtype.vsew
          //  - The requested source layout in ara_req.eew_vs1
          //  - The first active source register's current layout in old_eew_vs1
          // The current vector length refers to the target EEW!
          // Uniform source groups can be streamed in their existing layout.
          // Restarted and segmented stores may normalize active registers first.

          riscv::OpcodeStoreFp: begin
            // Instruction is of one of the RVV types
            automatic rvv_instruction_t insn = rvv_instruction_t'(instr.instr);

            // The instruction is a store
            is_vstore = 1'b1;

            // Wait before acknowledging this instruction
            acc_resp_o.req_ready = 1'b0;

            // vl depends on the EEW encoded in the instruction. Operand
            // requesters initially refer to the source's physical layout;
            // maintenance reshuffles, when required below, update that tag
            // before the architectural request is replayed.
            ara_req.scale_vl = 1'b1;

            // These generate a request to Ara's backend
            ara_req.vs1       = insn.vmem_type.rd; // vs3 is encoded in the same position as rd
            ara_req.use_vs1   = 1'b1;
            ara_req.old_eew_vs1 = eew_q[insn.vmem_type.rd];
            ara_req.vm        = insn.vmem_type.vm;
            ara_req.scalar_op = acc_req_i.rs1;
            ara_req.nf        = insn.vmem_type.nf;
            ara_req_valid     = 1'b1;

            // Decode the element width
            // Indexed memory operations follow a different rule
            unique case ({insn.vmem_type.mew, insn.vmem_type.width})
              4'b0000: begin
                  if (insn.vmem_type.mop != 2'b01 && insn.vmem_type.mop != 2'b11) begin
                    ara_req.vtype.vsew = EW8; // ara_req.vtype.vsew is the target EEW!
                  end else begin
                    ara_req.vtype.vsew = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = EW8;
                  end
              end
              4'b0101: begin
                  if (insn.vmem_type.mop != 2'b01 && insn.vmem_type.mop != 2'b11) begin
                    ara_req.vtype.vsew = EW16;
                  end else begin
                    ara_req.vtype.vsew = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = EW16;
                  end
              end
              4'b0110: begin
                  if (insn.vmem_type.mop != 2'b01 && insn.vmem_type.mop != 2'b11) begin
                    ara_req.vtype.vsew = EW32;
                  end else begin
                    ara_req.vtype.vsew = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = EW32;
                  end
              end
              4'b0111: begin
                  if (insn.vmem_type.mop != 2'b01 && insn.vmem_type.mop != 2'b11) begin
                    ara_req.vtype.vsew = EW64;
                  end else begin
                    ara_req.vtype.vsew = csr_vtype_q.vsew;
                    ara_req.eew_vs2    = EW64;
                  end
              end
              default: begin // Invalid. Element is too wide, or encoding is non-existant.
                illegal_insn  = 1'b1;
              end
            endcase

            // Decode the addressing mode
            unique case (insn.vmem_type.mop)
              2'b00: begin
                ara_req.op = VSE;

                // Decode the sumop field
                unique case (insn.vmem_type.rs2)
                  5'b00000:;     // Unit-strided
                  5'b01000:;     // Unit-strided, whole registers
                  5'b01011: begin // Unit-strided, mask store, EEW=1
                    // We operate ceil(vl/8) bytes
                    ara_req.vl         = (csr_vl_q >> 3) + |csr_vl_q[2:0];
                    ara_req.vtype.vsew = EW8;
                    mask_mem_noop      = csr_vstart_q >= ara_req.vl;
                  end
                  default: begin // Reserved
                    illegal_insn_store    = 1'b1;
                  end
                endcase
              end
              2'b10: begin
                ara_req.op     = VSSE;
                ara_req.stride = acc_req_i.rs2;
              end
              2'b01, // Indexed-unordered
              2'b11: begin // Indexed-orderd
                ara_req.op      = VSXE;
                // These also read vs2
                ara_req.vs2     = insn.vmem_type.rs2;
                ara_req.use_vs2 = 1'b1;
                ara_req.old_eew_vs2 = eew_q[insn.vmem_type.rs2 +
                    active_first_register(ara_req.eew_vs2, ara_req.vstart)];
                lmul_vs2 = vlmul_e'(csr_vtype_q.vlmul +
                    (ara_req.eew_vs2 - csr_vtype_q.vsew));
              end
              default:;
            endcase

            // For memory operations: EMUL = LMUL * (EEW / SEW)
            // EEW is encoded in the instruction
            ara_req.emul = vlmul_e'(csr_vtype_q.vlmul + (ara_req.vtype.vsew - csr_vtype_q.vsew));

            // Mask stores transfer ceil(vl/8) bytes from one architectural
            // mask register. Their EMUL is fixed at one, independently of vtype.
            if (insn.vmem_type.mop == 2'b00 && insn.vmem_type.rs2 == 5'b01011)
              ara_req.emul = LMUL_1;

            // Exception if EMUL > 8 or < 1/8.  Mask memory operations have
            // architecturally fixed EMUL=1, so the generic EEW/SEW-derived
            // sign-transition check does not apply to them.
            if (!(insn.vmem_type.mop == 2'b00 && insn.vmem_type.rs2 == 5'b01011)) begin
              unique case ({csr_vtype_q.vlmul[2], ara_req.emul[2]})
                // The new emul is lower than the previous lmul
                2'b01: begin
                  // But the new eew is greater than vsew
                  if (signed'(ara_req.vtype.vsew - csr_vtype_q.vsew) > 0) begin
                    illegal_insn_store = 1'b1;
                  end
                end
                // The new emul is greater than the previous lmul
                2'b10: begin
                  // But the new eew is lower than vsew
                  if (signed'(ara_req.vtype.vsew - csr_vtype_q.vsew) < 0) begin
                    illegal_insn_store = 1'b1;
                  end
                end
                default:;
              endcase
            end

            // Instructions with an integer LMUL have extra constraints on the registers they can
            // access.
            unique case (ara_req.emul)
              LMUL_2: if ((insn.varith_type.rd & 5'b00001) != 5'b00000) begin
                illegal_insn_store     = 1'b1;
              end
              LMUL_4: if ((insn.varith_type.rd & 5'b00011) != 5'b00000) begin
                illegal_insn_store    = 1'b1;
              end
              LMUL_8: if ((insn.varith_type.rd & 5'b00111) != 5'b00000) begin
                illegal_insn_store    = 1'b1;
              end
              LMUL_RSVD: begin
                illegal_insn_store    = 1'b1;
              end
              default:;
            endcase

            // Check for segment stores
            if (ara_req.nf != 3'b000 &&
                !(insn.vmem_type.mop == 2'b00 &&
                  insn.vmem_type.rs2 == 5'b01000)) begin
              if (pending_seg_mem_op_q) begin
                // This is a segment store instruction
                is_segment_mem_op = 1'b1;
                // Remove pending segment mem op when over
                if (seg_mem_op_end) pending_seg_mem_op_d = 1'b0;
              end else begin
                // Wait for idle not to mess with load/store_complete_i
                // since the segment sequencer filters these signals
                ara_req_valid = 1'b0;
                pending_seg_mem_op_d = 1'b1;
                state_d = WAIT_IDLE;
              end
              if (segment_register_count(ara_req.nf, ara_req.emul) > 8)
                illegal_insn = 1'b1;
              if (unsigned'(ara_req.vd) +
                    segment_register_count(ara_req.nf, ara_req.emul) > 32)
                illegal_insn = 1'b1;
            end

            // Vector whole register stores are encoded as stores of length VLENB, length
            // multiplier LMUL_1 and element width EW8. They overwrite all this decoding.
            if (ara_req.op == VSE && insn.vmem_type.rs2 == 5'b01000) begin
              // Execute also if vl == 0
              ignore_zero_vl_check = 1'b1;
              illegal_insn_store    = 1'b0;

              // Match VSTU's byte-stream representation while retaining the
              // architectural EEW interpretation of vstart.
              ara_req.vstart = csr_vstart_q << unsigned'(ara_req.vtype.vsew);

              // Maximum vector length. VLMAX = nf * VLEN / EW8.
              ara_req.vtype.vsew = EW8;
              unique case (insn.vmem_type.nf)
                3'd0: begin
                  ara_req.vl = VLENB << 0;
                  ara_req.emul = LMUL_1;
                end
                3'd1: begin
                  ara_req.vl = VLENB << 1;
                  ara_req.emul = LMUL_2;
                end
                3'd3:  begin
                  ara_req.vl = VLENB << 2;
                  ara_req.emul = LMUL_4;
                end
                3'd7:  begin
                  ara_req.vl = VLENB << 3;
                  ara_req.emul = LMUL_8;
                end
                default: begin
                  // Trigger an error for the reserved simm values
                  illegal_insn_store = 1'b1;
                end
              endcase

              if (ara_req.vstart >= ara_req.vl) begin
                mask_mem_noop = 1'b1;
                ignore_zero_vl_check = 1'b0;
              end

              acc_resp_o.req_ready  = 1'b0;
              acc_resp_o.resp_valid = 1'b0;
              ara_req_valid  = 1'b1;
            end

            // Wait until the back-end answers to acknowledge those instructions
            if ( ara_resp_valid ) begin
              acc_resp_o.req_ready  = 1'b1;
              acc_resp_o.resp_valid = 1'b1;
              acc_resp_o.exception  = ara_resp.exception;
              ara_req_valid       = 1'b0;
              // In case of exception, modify vstart and wait until the previous
              // operations are over. Then, flush.
              if ( ara_resp.exception.valid ) begin
                csr_vstart_d = ara_resp.exception_vstart;
                state_d = WAIT_IDLE_FLUSH;
              end
            end
            ara_req.eew_vs1 = ara_req.vtype.vsew; // This is the new vs1 EEW
            // VSTU consumes one physical-layout tag for the active byte stream.
            // With nonzero vstart, the group head may be inactive and may retain
            // a different EEW from the registers that actually supply data.
            begin
              automatic int unsigned first_active_register =
                  active_first_register(ara_req.vtype.vsew, ara_req.vstart);
              if (unsigned'(ara_req.vs1) + first_active_register < 32)
                ara_req.old_eew_vs1 =
                    eew_q[ara_req.vs1 + first_active_register];
            end
          end

          ////////////////////////////
          //  CSR Reads and Writes  //
          ////////////////////////////

          riscv::OpcodeSystem: begin
            // CSR ops have semantic dependency from vector instrucitons.
            // Therefore, Ara must be idle before performing any CSR operation.
            // Stall if there is any pending vector instruction
            // NOTE: This is overconstraining. Not all CSR ops actually need to stall if a vector instruction is pending.
            //       E.g., CSR vl is never updated by instructions past ara_dispatcher, except for "unit-stride fault-only-first loads". Reading vl would be safe otherwise.
            //       E.g., CSR vlenb is a design-constant parameter, reading is always safe.
            //       E.g., CSRs vxrm and vxsat have no influence on-non fixed-point instructions, it could be read and written safely when no fixed-point operation is running.
            //       By better analyzing the spec, more of optimizations of such can be made. For the sake of simplicity, the current implementation treats CSR ops as one block.
            // Just always go to WAIT_IDLE for at least one cycle (if there is a vinsn before the CSR one, it can be that ara_idle_i is still deasserted when the CSR is here).
            if (state_qq != WAIT_IDLE) begin
              state_d = WAIT_IDLE;
              acc_resp_o.req_ready = 1'b0;
              is_config = 1'b1;
            end else begin
              // These always respond at the same cycle
              acc_resp_o.resp_valid = 1'b1;
              is_config        = 1'b1;

              unique case (instr.itype.funct3)
                3'b001: begin // csrrw
                  // Decode the CSR.
                  case (riscv::csr_addr_t'(instr.itype.imm))
                    // Only vstart can be written with CSR instructions.
                    riscv::CSR_VSTART: begin
                      csr_vstart_d          = acc_req_i.rs1;
                      acc_resp_o.result = csr_vstart_q;
                    end
                    riscv::CSR_VXRM: begin
                      csr_vxrm_d            = vxrm_t'(acc_req_i.rs1[1:0]);
                      acc_resp_o.result = vlen_t'(csr_vxrm_q);
                    end
                    riscv::CSR_VXSAT: begin
                      csr_vxsat_d           = vxsat_e'(acc_req_i.rs1[0]);
                      acc_resp_o.result = vlen_t'(csr_vxsat_q);
                    end
                    riscv::CSR_VCSR: begin
                      csr_vxrm_d            = vxrm_t'(  acc_req_i.rs1[2:1] );
                      csr_vxsat_d           = vxsat_e'( acc_req_i.rs1[0]   );
                      acc_resp_o.result = vlen_t'(  { csr_vxrm_q, csr_vxsat_q } );
                    end
                    default: illegal_insn = 1'b1;
                  endcase
                end
                3'b010: begin // csrrs
                  // Decode the CSR.
                  case (riscv::csr_addr_t'(instr.itype.imm))
                    riscv::CSR_VSTART: begin
                      csr_vstart_d          = csr_vstart_q | vlen_t'(acc_req_i.rs1);
                      acc_resp_o.result = csr_vstart_q;
                    end
                    riscv::CSR_VTYPE: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = xlen_vtype(csr_vtype_q);
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VL: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = csr_vl_q;
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VLENB: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = VLENB;
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VXRM: begin
                      csr_vxrm_d            = csr_vxrm_q | vxrm_t'(acc_req_i.rs1[1:0]);
                      acc_resp_o.result = vlen_t'(csr_vxrm_q);
                    end
                    riscv::CSR_VXSAT: begin
                      csr_vxsat_d           = csr_vxsat_q | vxsat_e'(acc_req_i.rs1[0]);
                      acc_resp_o.result = vlen_t'(csr_vxsat_q);
                    end
                    riscv::CSR_VCSR: begin
                      csr_vxrm_d            = csr_vxrm_q  | vxrm_t'(acc_req_i.rs1[2:1]);
                      csr_vxsat_d           = csr_vxsat_q | vxsat_e'(acc_req_i.rs1[0]);
                      acc_resp_o.result = vlen_t'(  { csr_vxrm_q, csr_vxsat_q } );
                    end
                    default: illegal_insn = 1'b1;
                  endcase
                end
                3'b011: begin // csrrc
                  // Decode the CSR.
                  case (riscv::csr_addr_t'(instr.itype.imm))
                    riscv::CSR_VSTART: begin
                      csr_vstart_d          = csr_vstart_q & ~vlen_t'(acc_req_i.rs1);
                      acc_resp_o.result = csr_vstart_q;
                    end
                    riscv::CSR_VTYPE: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = xlen_vtype(csr_vtype_q);
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VL: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = csr_vl_q;
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VLENB: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = VLENB;
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VXSAT: begin
                      csr_vxsat_d           = csr_vxsat_q & ~vxsat_e'(acc_req_i.rs1[0]);
                      acc_resp_o.result = csr_vxsat_q;
                    end
                    riscv::CSR_VXRM: begin
                      csr_vxrm_d           = csr_vxrm_q & ~vxrm_t'(acc_req_i.rs1[1:0]);
                      acc_resp_o.result = csr_vxrm_q;
                    end
                    riscv::CSR_VCSR: begin
                      csr_vxrm_d            = csr_vxrm_q  & ~vxrm_t'(acc_req_i.rs1[2:1]);
                      csr_vxsat_d           = csr_vxsat_q & ~vxsat_e'(acc_req_i.rs1[0]);
                      acc_resp_o.result = vlen_t'(  { csr_vxrm_q, csr_vxsat_q } );
                    end
                    default: illegal_insn = 1'b1;
                  endcase
                end
                3'b101: begin // csrrwi
                  // Decode the CSR.
                  case (riscv::csr_addr_t'(instr.itype.imm))
                    // Only vstart can be written with CSR instructions.
                    riscv::CSR_VSTART: begin
                      csr_vstart_d          = vlen_t'(acc_req_i.rs1);
                      acc_resp_o.result = csr_vstart_q;
                    end
                    riscv::CSR_VXRM: begin
                      csr_vxrm_d            = vxrm_t'(acc_req_i.rs1[1:0]);
                      acc_resp_o.result = vlen_t'(csr_vxrm_q);
                    end
                    riscv::CSR_VXSAT: begin
                      csr_vxsat_d           = acc_req_i.rs1[0];
                      acc_resp_o.result = csr_vxsat_q;
                    end
                    riscv::CSR_VCSR: begin
                      // logic [19:15] rs1; So, LSB is [15]
                      csr_vxrm_d            = vxrm_t'(acc_req_i.rs1[2:1]);
                      csr_vxsat_d           = vxsat_e'(acc_req_i.rs1[0]);
                      acc_resp_o.result = vlen_t'({csr_vxrm_q, csr_vxsat_q});
                    end
                    default: illegal_insn = 1'b1;
                  endcase
                end
                3'b110: begin // csrrsi
                  // Decode the CSR.
                  case (riscv::csr_addr_t'(instr.itype.imm))
                    riscv::CSR_VSTART: begin
                      csr_vstart_d          = csr_vstart_q | vlen_t'(acc_req_i.rs1);
                      acc_resp_o.result = csr_vstart_q;
                    end
                    riscv::CSR_VTYPE: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = xlen_vtype(csr_vtype_q);
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VL: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = csr_vl_q;
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VLENB: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = VLENB;
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VXSAT: begin
                      // logic [19:15] rs1; So, LSB is [15]
                      csr_vxsat_d           = csr_vxsat_q | vxsat_e'(acc_req_i.rs1[0]);
                      acc_resp_o.result = csr_vxsat_q;
                    end
                    riscv::CSR_VXRM: begin
                      // logic [19:15] rs1; So, LSB is [15]
                      csr_vxrm_d           = csr_vxrm_q | vxrm_t'(acc_req_i.rs1[1:0]);
                      acc_resp_o.result = csr_vxrm_q;
                    end
                    riscv::CSR_VCSR: begin
                      // logic [19:15] rs1; So, LSB is [15]
                      csr_vxrm_d            = csr_vxrm_q  |  vxrm_t'(acc_req_i.rs1[2:1]);
                      csr_vxsat_d           = csr_vxsat_q | vxsat_e'(acc_req_i.rs1[0]);
                      acc_resp_o.result = { csr_vxrm_q,  csr_vxsat_q };
                    end
                    default: illegal_insn = 1'b1;
                  endcase
                end
                3'b111: begin // csrrci
                  // Decode the CSR.
                  unique case (riscv::csr_addr_t'(instr.itype.imm))
                    riscv::CSR_VSTART: begin
                      csr_vstart_d          = csr_vstart_q & ~vlen_t'(acc_req_i.rs1);
                      acc_resp_o.result = csr_vstart_q;
                    end
                    riscv::CSR_VTYPE: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = xlen_vtype(csr_vtype_q);
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VL: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = csr_vl_q;
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VLENB: begin
                      // Only reads are allowed
                      if (instr.itype.rs1 == '0) acc_resp_o.result = VLENB;
                      else illegal_insn = 1'b1;
                    end
                    riscv::CSR_VXSAT: begin
                      csr_vxsat_d           = csr_vxsat_q & ~vxsat_e'(acc_req_i.rs1[0]);
                      acc_resp_o.result = csr_vxsat_q;
                    end
                    riscv::CSR_VXRM: begin
                      csr_vxrm_d           = csr_vxrm_q & ~vxrm_t'(acc_req_i.rs1[1:0]);
                      acc_resp_o.result = csr_vxrm_q;
                    end
                    riscv::CSR_VCSR: begin
                      // logic [19:15] rs1; So, LSB is [15]
                      csr_vxrm_d           = csr_vxrm_q  &  ~vxrm_t'(acc_req_i.rs1[2:1]);
                      csr_vxsat_d          = csr_vxsat_q & ~vxsat_e'(acc_req_i.rs1[0]);
                      acc_resp_o.result = { csr_vxrm_q,  csr_vxsat_q };
                    end
                    default: illegal_insn= 1'b1;
                  endcase
                end
                default: begin
                  // Trigger an illegal instruction
                  illegal_insn = 1'b1;
                end
              endcase // instr.itype.funct3
            end
          end

          //////////////////////////////////////
          //  QBS and AKV custom instructions //
          //////////////////////////////////////
          QbsOpcodeCustom2: begin : custom2
            automatic logic is_qbexec;
            automatic logic is_qbinfo;
            automatic logic is_akvfill;
            automatic logic is_akvload;
            automatic logic is_akvinfo;
            automatic logic is_akvrelease;
            automatic logic [6:0] qbs_funct7;
            automatic logic [6:0] akv_funct7;
            automatic int unsigned qbs_m;
            automatic int unsigned qbs_destination_regs;
            automatic int unsigned akv_head_dim;
            automatic logic akv_implementation_supported;

            is_qbexec = instr.rtype.funct3 == QbsQbexecFunct3;
            is_qbinfo = instr.rtype.funct3 == QbsQbinfoFunct3;
            is_akvfill = instr.rtype.funct3 == AkvFillFunct3;
            is_akvload = instr.rtype.funct3 == AkvLoadFunct3;
            is_akvinfo = instr.rtype.funct3 == AkvInfoFunct3;
            is_akvrelease = instr.rtype.funct3 == AkvReleaseFunct3;
            qbs_funct7 = 7'(instr.rtype.funct7);
            akv_funct7 = 7'(instr.rtype.funct7);
            qbs_m = unsigned'(qbs_funct7[1:0]) + 1;
            qbs_destination_regs = qbs_m == 1 ? 1 : (qbs_m == 2 ? 2 : 4);
            akv_head_dim = akv_funct7[0] ? 128 : 64;
            akv_implementation_supported =
                AkvEnable && NrLanes == 4 && VLEN == 1024;

            if (is_qbinfo) begin
              if (!QbsEnable)
                illegal_insn = 1'b1;
              // qbinfo has no hidden state and does not enter the sequencer.
              // funct7 and rs2 are reserved in ABI version 1.
              acc_resp_o.resp_valid = 1'b1;
              acc_resp_o.result = xlen_t'(
                  qbs_capability_word(64'(acc_req_i.rs1), VLEN));
              if (instr.rtype.funct7 != '0 || instr.rtype.rs2 != '0)
                illegal_insn = 1'b1;
            end else if (is_qbexec) begin
              if (!QbsEnable)
                illegal_insn = 1'b1;
              // The blocking command is accounted as an accelerator load until
              // its atomic VRF commit or terminal exception.
              // Keep the CVA6 request resident until ara_resp_valid. This is the
              // same request/response contract used by ordinary vector loads;
              // accepting it here would discard the transaction identity before
              // the blocking QBS command can return its terminal response.
              acc_resp_o.req_ready = 1'b0;
              acc_resp_o.resp_valid = 1'b0;
              is_vload = 1'b1;
              ignore_zero_vl_check = 1'b1;
              ara_req_valid = 1'b1;
              ara_req.op = VQBEXEC;
              ara_req.scalar_op = acc_req_i.rs1;
              ara_req.stride = acc_req_i.rs2;
              ara_req.use_scalar_op = 1'b0;
              ara_req.vd = instr.rtype.rd;
              ara_req.use_vd = 1'b1;
              ara_req.vm = 1'b1;
              ara_req.vtype.vsew = EW32;
              ara_req.eew_vd_op = EW32;
              ara_req.vstart = '0;
              ara_req.vl = vlen_t'(qbs_m * (VLEN / 32));
              // QBS numerical-contract v1 is independent of the dynamic frm CSR.
              ara_req.fp_rm = fpnew_pkg::roundmode_e'(QbsNumericalRoundingMode);
              unique case (qbs_m)
                1: ara_req.emul = LMUL_1;
                2: ara_req.emul = LMUL_2;
                default: ara_req.emul = LMUL_4;
              endcase

              // These checks are intentionally in front of descriptor fetch:
              // destination reservation cannot depend on unread memory.
              if (qbs_funct7[6:2] != '0 ||
                  (unsigned'(instr.rtype.rd) % qbs_destination_regs) != 0 ||
                  unsigned'(instr.rtype.rd) + qbs_destination_regs > 32 ||
                  csr_vstart_q != '0 || !acc_req_i.acc_cons_en ||
                  acc_req_i.rs1[QbsDescriptorAlignmentLog2-1:0] != '0 ||
                  acc_req_i.rs2[QbsActivationBaseAlignmentLog2-1:0] != '0)
                illegal_insn = 1'b1;

              // QBS owns the VLSU memory and result interfaces for the complete
              // command, so issue it only after all older Ara work has drained.
              if (!ara_idle_i) begin
                ara_req_valid = 1'b0;
                acc_resp_o.req_ready = 1'b0;
                state_d = WAIT_IDLE;
              end

              if (ara_resp_valid) begin
                ara_req_valid = 1'b0;
                acc_resp_o.req_ready = 1'b1;
                acc_resp_o.resp_valid = 1'b1;
                acc_resp_o.exception = ara_resp.exception;
                acc_resp_o.fflags |= ara_resp.fflags;
                acc_resp_o.fflags_valid |= ara_resp.fflags_valid;
              end
            end else if (is_akvinfo) begin
              if (!akv_implementation_supported)
                illegal_insn = 1'b1;
              acc_resp_o.resp_valid = 1'b1;
              acc_resp_o.result = xlen_t'(akv_capability_word(
                  64'(acc_req_i.rs1), akv_implementation_supported));
              if (akv_funct7 != '0 || instr.rtype.rs2 != '0)
                illegal_insn = 1'b1;
            end else if (is_akvfill) begin
              acc_resp_o.req_ready = 1'b0;
              acc_resp_o.resp_valid = 1'b0;
              is_vload = 1'b1;
              ignore_zero_vl_check = 1'b1;
              ara_req_valid = 1'b1;
              ara_req.op = VAKVFILL;
              ara_req.scalar_op = acc_req_i.rs1;
              ara_req.stride = acc_req_i.rs2;
              ara_req.use_scalar_op = 1'b0;
              ara_req.akv_refill = akv_funct7[0];
              ara_req.vm = 1'b1;
              ara_req.vtype = '{vill: 1'b0, vma: 1'b1, vta: 1'b1,
                                vsew: EW16, vlmul: LMUL_1};
              ara_req.emul = LMUL_1;
              ara_req.vstart = '0;
              ara_req.vl = vlen_t'(1);

              if (!akv_implementation_supported ||
                  akv_funct7[6:1] != '0 || instr.rtype.rd != '0 ||
                  (akv_funct7[0] && instr.rtype.rs1 != '0) ||
                  (!akv_funct7[0] &&
                   acc_req_i.rs1[AkvDescriptorAlignmentLog2-1:0] != '0) ||
                  csr_vstart_q != '0 || !acc_req_i.acc_cons_en)
                illegal_insn = 1'b1;

              // Fill and refill replace hidden state and may fault, so they
              // begin only after all older vector work has drained.
              if (!ara_idle_i) begin
                ara_req_valid = 1'b0;
                acc_resp_o.req_ready = 1'b0;
                state_d = WAIT_IDLE;
              end

              if (ara_resp_valid) begin
                ara_req_valid = 1'b0;
                acc_resp_o.req_ready = 1'b1;
                acc_resp_o.resp_valid = 1'b1;
                acc_resp_o.exception = ara_resp.exception;
              end
            end else if (is_akvload) begin
              acc_resp_o.req_ready = 1'b0;
              acc_resp_o.resp_valid = 1'b0;
              is_vload = 1'b1;
              ignore_zero_vl_check = 1'b1;
              ara_req_valid = 1'b1;
              ara_req.op = VAKVLOAD;
              ara_req.scalar_op = acc_req_i.rs1;
              ara_req.use_scalar_op = 1'b0;
              ara_req.vd = instr.rtype.rd;
              ara_req.use_vd = 1'b1;
              ara_req.vm = 1'b1;
              ara_req.vtype = '{vill: 1'b0, vma: 1'b1, vta: 1'b1,
                                vsew: EW16,
                                vlmul: akv_funct7[0] ? LMUL_2 : LMUL_1};
              ara_req.eew_vd_op = EW16;
              ara_req.vstart = '0;
              ara_req.vl = vlen_t'(akv_head_dim);
              ara_req.emul = akv_funct7[0] ? LMUL_2 : LMUL_1;

              if (!akv_implementation_supported ||
                  akv_funct7[6:1] != '0 || instr.rtype.rs2 != '0 ||
                  (akv_funct7[0] &&
                   (instr.rtype.rd[7] || instr.rtype.rd > 5'd30)) ||
                  csr_vstart_q != '0 || !acc_req_i.acc_cons_en)
                illegal_insn = 1'b1;

              if (ara_resp_valid) begin
                ara_req_valid = 1'b0;
                acc_resp_o.req_ready = 1'b1;
                acc_resp_o.resp_valid = 1'b1;
                acc_resp_o.exception = ara_resp.exception;
              end
            end else if (is_akvrelease) begin
              acc_resp_o.req_ready = 1'b0;
              acc_resp_o.resp_valid = 1'b0;
              is_vload = 1'b1;
              ignore_zero_vl_check = 1'b1;
              ara_req_valid = 1'b1;
              ara_req.op = VAKVRELEASE;
              ara_req.vm = 1'b1;
              ara_req.vtype = '{vill: 1'b0, vma: 1'b1, vta: 1'b1,
                                vsew: EW16, vlmul: LMUL_1};
              ara_req.emul = LMUL_1;
              ara_req.vstart = '0;
              ara_req.vl = vlen_t'(1);

              if (!akv_implementation_supported || akv_funct7 != '0 ||
                  instr.rtype.rd != '0 || instr.rtype.rs1 != '0 ||
                  instr.rtype.rs2 != '0 || csr_vstart_q != '0 ||
                  !acc_req_i.acc_cons_en)
                illegal_insn = 1'b1;

              if (!ara_idle_i) begin
                ara_req_valid = 1'b0;
                acc_resp_o.req_ready = 1'b0;
                state_d = WAIT_IDLE;
              end

              if (ara_resp_valid) begin
                ara_req_valid = 1'b0;
                acc_resp_o.req_ready = 1'b1;
                acc_resp_o.resp_valid = 1'b1;
                acc_resp_o.exception = ara_resp.exception;
              end
            end else begin
              illegal_insn = 1'b1;
            end
          end

          default: begin
            // Trigger an illegal instruction
            illegal_insn = 1'b1;
          end
        endcase
      end

      // VMADC/VMSBC are not predicated operations: their vm bit selects the
      // carry/borrow input.  They nevertheless need the old mask destination
      // to preserve elements before vstart and tails under undisturbed policy.
      // Other mask-result operations request vd in their individual decode
      // paths because they also need mask-undisturbed merging.
      if (ara_req_valid && (ara_req.op inside {[VMADC:VMSBC]}) &&
          ((csr_vstart_q != '0) || !csr_vtype_q.vta)) begin
        ara_req.use_vd_op = 1'b1;
      end

      // Spike executes widening reductions whose scalar seed aliases the
      // narrow source group, although RVV 1.0 classifies a source register
      // used at two EEWs as reserved. Support that compatibility case through
      // the source snapshot path below; all ordinary overlap checks remain.

      // Check that we have fixed-point support if requested
      // vxsat and vxrm are always accessible anyway
      if (ara_req_valid && (ara_req.op inside {[VSADDU:VNCLIPU], VSMUL}) && (FixPtSupport == FixedPointDisable))
        illegal_insn = 1'b1;

      // Check that we have we have vfrec7, vfrsqrt7
      if (ara_req_valid && (ara_req.op inside {VFREC7, VFRSQRT7}) && (FPExtSupport == FPExtSupportDisable))
        illegal_insn = 1'b1;

      // RVV requires these non-restartable operations to begin at element 0.
      // Check the architectural CSR because some decode paths normalize the
      // internal request's vstart before sending it to the backend.
      if (ara_req_valid && (csr_vstart_q != '0) && requires_zero_vstart(ara_req.op))
        illegal_insn = 1'b1;

      // Raise an illegal instruction exception
      if ( illegal_insn || illegal_insn_load || illegal_insn_store ) begin
        // CVA6 classifies accelerator memory operations before Ara performs
        // the complete RVV legality check.  Balance that dispatched-memory
        // accounting even when a generic legality rule rejects the request.
        // Otherwise a following scalar memory operation can wait forever for
        // a vector load/store that never entered the VLSU.
        if (is_vload)  illegal_insn_load  = 1'b1;
        if (is_vstore) illegal_insn_store = 1'b1;

        // Segment requests reserve the segment sequencer while waiting for Ara
        // to become idle.  An illegal request never emits seg_mem_op_end, so
        // release that reservation together with the exception response.
        if ((is_vload || is_vstore) && ara_req.nf != '0)
          pending_seg_mem_op_d = 1'b0;

        ara_req_valid            = 1'b0;
        acc_resp_o.req_ready       = 1'b1;
        acc_resp_o.resp_valid      = 1'b1;
        acc_resp_o.exception.valid = 1'b1;
        acc_resp_o.exception.cause = riscv::ILLEGAL_INSTR;
        acc_resp_o.exception.tval  = instr;
      end

      // Check if we need to reshuffle our vector registers involved in the operation
      // This operation is costly when occurs, so avoid it if possible
      reshuffle_full_vs2_group = ara_req.op inside {VRGATHER, VRGATHEREI16};
      vs2_reshuffle_eew =
          ara_req.op inside {VCOMPRESS, VRGATHER, VRGATHEREI16}
              ? ara_req.vtype.vsew : ara_req.eew_vs2;
      vs2_reshuffle_vstart = ara_req.vstart;
      vs2_reshuffle_vl = ara_req.vl;
      if (ara_req.op == VSLIDEDOWN) begin
        vs2_reshuffle_vstart = slidedown_source_start(
            ara_req.vstart, ara_req.stride, lmul_vs2, vs2_reshuffle_eew);
        vs2_reshuffle_vl = slidedown_source_end(
            ara_req.vl, ara_req.stride, ara_req.use_scalar_op,
            lmul_vs2, vs2_reshuffle_eew);
      end
      indexed_mixed_vs2_layout = ara_req.op inside {VLXE, VSXE} &&
          active_group_has_mixed_eew(
              ara_req.vs2, lmul_vs2, ara_req.eew_vs2,
              ara_req.vstart, ara_req.vl);
      // An architectural no-op must be acknowledged before any layout
      // maintenance is started. In particular, a zero-length source snapshot
      // would enter the SLDU without an operand beat and could never retire.
      if (ara_req_valid && !acc_resp_o.exception.valid &&
          !(((csr_vstart_q >= csr_vl_q) || mask_mem_noop || null_vslideup) &&
            !is_config && !ignore_zero_vl_check)) begin
        automatic rvv_instruction_t insn = rvv_instruction_t'(instr.instr);

        // Is the instruction an in-lane one and could it be subject to reshuffling?
        in_lane_op = ara_req.op inside {[VADD:VMERGE]} || ara_req.op inside {[VREDSUM:VMSBC]} ||
                     ara_req.op inside {[VMANDNOT:VMXNOR]} || ara_req.op inside {[VMVXS:VSLIDEDOWN]} ||
                     ara_req.op inside {VRGATHER, VRGATHEREI16};
        // Annotate which registers need a reshuffle -> |vs1|vs2|vd|
        // Optimization: reshuffle vs1 and vs2 only if the operation is strictly in-lane
        // Optimization: reshuffle vd only if we are not overwriting the whole vector register!
        // During a vstore, if vstart > 0, reshuffle immediately not to complicate operand fetch stage
        // During a vstore with EMUL > 1, reshuffle immediately if the register group's EEW is not the
        // same for every reg.
        reshuffle_req_d = {
          ara_req.use_vs1 &&
            (is_segment_mem_op && is_vstore
                ? register_span_needs_reshuffle(
                    ara_req.vs1,
                    segment_register_count(ara_req.nf, ara_req.emul),
                    ara_req.eew_vs1)
                : active_group_needs_reshuffle(
                    ara_req.vs1, is_vstore ? ara_req.emul : lmul_vs1,
                    ara_req.eew_vs1, ara_req.vstart, ara_req.vl)) &&
            (in_lane_op ||
             (is_vstore && (is_segment_mem_op ||
                            (csr_vstart_q != '0) || !is_same_eew))),
          ara_req.use_vs2 &&
            (reshuffle_full_vs2_group
                 ? group_needs_reshuffle(ara_req.vs2, lmul_vs2,
                                         vs2_reshuffle_eew)
                 : active_group_needs_reshuffle(
                       ara_req.vs2, lmul_vs2, vs2_reshuffle_eew,
                       vs2_reshuffle_vstart, vs2_reshuffle_vl)) &&
            (in_lane_op || ara_req.op == VCOMPRESS ||
             indexed_mixed_vs2_layout),
          ara_req.use_vd && ara_req.op != VQBEXEC &&
            (is_segment_mem_op && is_vload
                ? register_span_needs_reshuffle(
                    ara_req.vd,
                    segment_register_count(ara_req.nf, ara_req.emul),
                    ara_req.vtype.vsew)
                : active_group_needs_reshuffle(
                    ara_req.vd,
                    single_register_result(ara_req.op) ? LMUL_1 : ara_req.emul,
                    ara_req.vtype.vsew, ara_req.vstart, ara_req.vl)) &&
            // A full active destination can skip preservation only for a pure
            // overwrite. Accumulate and other read-modify-write operations
            // must first expose every old-vd register in the requested layout.
            !(!ara_req.use_vd_op && !reduction_result(ara_req.op) &&
              ara_req.op != VCOMPRESS && ara_req.op != VSLIDEUP && ara_req.vm &&
              ara_req.vstart == 0 &&
              (ara_req.vl == ((VLENB << ara_req.emul[1:0]) >> ara_req.vtype.vsew)))};

        // An indexed load may start writing vd before AddrGen has consumed the
        // complete index group.  If those groups overlap, retain the index
        // source after any required layout normalization and replay it for the
        // whole address-generation phase.
        indexed_load_groups_overlap = ara_req.op == VLXE &&
            ara_req.use_vd && ara_req.use_vs2 &&
            register_groups_overlap(ara_req.vd, ara_req.emul,
                                    ara_req.vs2, lmul_vs2);
        // Normalize the overlapping index source before touching vd.  The
        // generic vd-first reshuffle order would otherwise destroy the source
        // view before it can be retained.
        if (indexed_load_groups_overlap && !source_snapshot_valid_q &&
            reshuffle_req_d[1])
          reshuffle_req_d[0] = 1'b0;
        indexed_load_index_overlap = indexed_load_groups_overlap &&
            !reshuffle_req_d[1];

`ifdef FOR_VERIFY
        if ($test$plusargs("ARA_DEBUG_RESHUFFLE") &&
            verify_active_insn_q == 32'h3e4a3257) begin
          $display("[ARA_RESHUFFLE_DECODE] t=%0t vd=v%0d emul=%0d vsew=%0d vl=%0d vstart=%0d first=%0d count=%0d need_vd=%0b req=%b eew_v4_7=%0d/%0d/%0d/%0d valid=%b",
                   $time, ara_req.vd, ara_req.emul, ara_req.vtype.vsew,
                   ara_req.vl, ara_req.vstart,
                   active_first_register(ara_req.vtype.vsew, ara_req.vstart),
                   active_register_count(ara_req.emul, ara_req.vtype.vsew,
                                         ara_req.vstart, ara_req.vl),
                   active_group_needs_reshuffle(
                       ara_req.vd, ara_req.emul, ara_req.vtype.vsew,
                       ara_req.vstart, ara_req.vl),
                   reshuffle_req_d, eew_q[4], eew_q[5], eew_q[6], eew_q[7],
                   eew_valid_q[7:4]);
        end
`endif

        // A widening .wv-style instruction can read one physical register
        // group through two different EEW/LMUL views. If one view is already
        // encoded correctly and converting the other would destroy it, retain
        // the correct view before any in-place reshuffle.
        dual_source_layout_serialize = ara_req.use_vs1 && ara_req.use_vs2 &&
            ara_req.eew_vs1 != vs2_reshuffle_eew &&
            register_groups_overlap(ara_req.vs1, lmul_vs1,
                                    ara_req.vs2, lmul_vs2) &&
            reshuffle_req_d[2] && reshuffle_req_d[1] &&
            (!ara_req.use_vd ||
             (!register_groups_overlap(
                  ara_req.vd,
                  single_register_result(ara_req.op) ? LMUL_1 : ara_req.emul,
                  ara_req.vs1, lmul_vs1) &&
              !register_groups_overlap(
                  ara_req.vd,
                  single_register_result(ara_req.op) ? LMUL_1 : ara_req.emul,
                  ara_req.vs2, lmul_vs2)));

        dual_source_layout_conflict = ara_req.use_vs1 && ara_req.use_vs2 &&
            ara_req.eew_vs1 != vs2_reshuffle_eew &&
            register_groups_overlap(ara_req.vs1, lmul_vs1,
                                    ara_req.vs2, lmul_vs2) &&
            !dual_source_layout_serialize &&
            ((!reshuffle_req_d[2] && reshuffle_req_d[1]) ||
             (reshuffle_req_d[2] && !reshuffle_req_d[1]));
        // Preserve which source view is already readable before destination
        // deduplication and overlap handling mutate reshuffle_req_d below.
        dual_source_snapshot_vs1 = dual_source_layout_conflict &&
            !reshuffle_req_d[2] && reshuffle_req_d[1];

        // Two overlapping source views cannot be normalized in one in-place
        // reshuffle batch: converting the second view would destroy the first
        // before the source-snapshot logic can retain it. Normalize vs2 first,
        // return through WAIT_IDLE, then re-decode and snapshot that complete
        // view before converting vs1. Destination-overlap cases remain on the
        // existing conservative overlap paths.
        if (dual_source_layout_serialize)
          reshuffle_req_d[2] = 1'b0;

        // A widening accumulate can legally overlap a narrow source with the
        // high part of its wide destination. The bytes in that overlap are two
        // simultaneous architectural views: a narrow multiplicand and a wide
        // old destination operand. Preserve the already-correct narrow view
        // before normalizing the complete accumulator group.
        widen_accumulator_layout_conflict = ara_req.use_vd && ara_req.use_vd_op &&
            reshuffle_req_d[0] && !single_register_result(ara_req.op) &&
            unsigned'(ara_req.vtype.vsew) > unsigned'(csr_vtype_q.vsew) &&
            ((ara_req.use_vs1 && !reshuffle_req_d[2] &&
              unsigned'(ara_req.eew_vs1) < unsigned'(ara_req.vtype.vsew) &&
              widening_high_overlap(ara_req.vd, ara_req.emul,
                                    ara_req.vs1, lmul_vs1)) ||
             (ara_req.use_vs2 && !reshuffle_req_d[1] &&
              unsigned'(vs2_reshuffle_eew) < unsigned'(ara_req.vtype.vsew) &&
              widening_high_overlap(ara_req.vd, ara_req.emul,
                                    ara_req.vs2, lmul_vs2)));

        // A masked widening write cannot leave the inactive destination bytes
        // in a narrow layout. If a narrow source overlaps the high destination
        // registers, retain that source before normalizing the complete old
        // destination into the wide layout.
        masked_widen_layout_conflict = ara_req.use_vd && !ara_req.vm &&
            reshuffle_req_d[0] && !single_register_result(ara_req.op) &&
            unsigned'(ara_req.vtype.vsew) > unsigned'(csr_vtype_q.vsew) &&
            ((ara_req.use_vs1 && !reshuffle_req_d[2] &&
              unsigned'(ara_req.eew_vs1) < unsigned'(ara_req.vtype.vsew) &&
              widening_high_overlap(ara_req.vd, ara_req.emul,
                                    ara_req.vs1, lmul_vs1)) ||
             (ara_req.use_vs2 && !reshuffle_req_d[1] &&
              unsigned'(vs2_reshuffle_eew) < unsigned'(ara_req.vtype.vsew) &&
              widening_high_overlap(ara_req.vd, ara_req.emul,
                                    ara_req.vs2, lmul_vs2)));

        source_snapshot_resolves_widen = source_snapshot_valid_q &&
            ara_req.use_vd &&
            unsigned'(ara_req.vtype.vsew) > unsigned'(csr_vtype_q.vsew) &&
            ((ara_req.use_vs1 && ara_req.vs1 == source_snapshot_vs_q &&
              ara_req.eew_vs1 == source_snapshot_eew_q &&
              lmul_vs1 == source_snapshot_lmul_q) ||
             (ara_req.use_vs2 && ara_req.vs2 == source_snapshot_vs_q &&
              vs2_reshuffle_eew == source_snapshot_eew_q &&
              lmul_vs2 == source_snapshot_lmul_q));

        // A .wv operation may use the complete destination group as its wide
        // source while a narrow source aliases the destination's high half.
        // When that wide source is replayed from the snapshot, normalizing vd
        // before issue would destroy the physical narrow-source view and make
        // the two layouts alternate forever. Keep the narrow view in the VRF;
        // the overlap path repairs vd after the original operation consumes it.
        source_snapshot_replays_wide_vd = source_snapshot_valid_q &&
            ara_req.use_vd &&
            ((ara_req.use_vs1 && ara_req.vs1 == ara_req.vd &&
              ara_req.vs1 == source_snapshot_vs_q &&
              ara_req.eew_vs1 == ara_req.vtype.vsew &&
              ara_req.eew_vs1 == source_snapshot_eew_q &&
              lmul_vs1 == ara_req.emul &&
              lmul_vs1 == source_snapshot_lmul_q) ||
             (ara_req.use_vs2 && ara_req.vs2 == ara_req.vd &&
              ara_req.vs2 == source_snapshot_vs_q &&
              vs2_reshuffle_eew == ara_req.vtype.vsew &&
              vs2_reshuffle_eew == source_snapshot_eew_q &&
              lmul_vs2 == ara_req.emul &&
              lmul_vs2 == source_snapshot_lmul_q));

`ifdef FOR_VERIFY
        if ($test$plusargs("ARA_DEBUG_SOURCE_SNAPSHOT") &&
            (dual_source_layout_conflict || source_snapshot_valid_q))
          $display("[ARA_SOURCE_DISPATCH] t=%0t insn=%h conflict=%0b valid=%0b req=%b vs1=v%0d/e%0d/l%0d vs2=v%0d/e%0d/l%0d",
                   $time, instr.instr, dual_source_layout_conflict,
                   source_snapshot_valid_q, reshuffle_req_d,
                   ara_req.vs1, ara_req.eew_vs1, lmul_vs1,
                   ara_req.vs2, vs2_reshuffle_eew, lmul_vs2);
`endif

        if (source_snapshot_valid_q) begin
          // A masked narrowing overlap preserves old vd in its narrow layout.
          // If vs1 aliases vd, that same snapshot is also the instruction's
          // narrow shift-amount view while the physical group remains in the
          // wide vs2 layout. Reads precede the corresponding in-order result
          // merge, so the preserve shadow can safely serve both roles.
          if (ara_req.use_vs1 && ara_req.vs1 == source_snapshot_vs_q &&
              ara_req.eew_vs1 == source_snapshot_eew_q &&
              lmul_vs1 == source_snapshot_lmul_q) begin
            ara_req.source_snapshot_replay_vs1 = 1'b1;
            // VRGATHEREI16 sends vs1 through the ALU into MASKU, whose
            // deshuffler uses eew_vs2 for that stream. Replay retains the
            // captured physical layout even if the aliased data view was
            // subsequently normalized to SEW.
            if (ara_req.op == VRGATHEREI16)
              ara_req.eew_vs2 = source_snapshot_eew_q;
            reshuffle_req_d[2] = 1'b0;
          end
          if (ara_req.use_vs2 && ara_req.vs2 == source_snapshot_vs_q &&
              vs2_reshuffle_eew == source_snapshot_eew_q &&
              lmul_vs2 == source_snapshot_lmul_q) begin
            ara_req.source_snapshot_replay_vs2 = 1'b1;
            // An overlapping indexed load may normalize vd after capturing
            // its index source.  The current EEW notebook then describes vd,
            // not the retained source bytes; AddrGen must deshuffle replayed
            // offsets using the snapshot's original physical layout.
            if (ara_req.op == VLXE)
              ara_req.old_eew_vs2 = source_snapshot_eew_q;
            // Gather/compress fetch vs2 through the ad-hoc MaskB path, whose
            // deshuffler uses eew_vd_op. A replay returns bytes in the saved
            // physical layout even if the aliased register has since been
            // reshuffled for another source view.
            if (ara_req.op inside {VRGATHER, VRGATHEREI16, VCOMPRESS})
              ara_req.eew_vd_op = source_snapshot_eew_q;
            reshuffle_req_d[1] = 1'b0;
          end
        end

        // In this exact narrowing alias, the replayed narrow vs1 is also the
        // architectural old vd while vs2 consumes the wider view of the same
        // group. The VALU can merge prestart/masked-off bytes from that stable
        // snapshot; modifying the prefix in the VRF before capture would
        // corrupt the wide source view.
        source_snapshot_preserves_narrow_vd =
            ara_req.source_snapshot_replay_vs1 &&
            ara_req.use_vd && ara_req.use_vs1 && ara_req.use_vs2 &&
            ara_req.vd == ara_req.vs1 && ara_req.vd == ara_req.vs2 &&
            ara_req.eew_vs1 == ara_req.vtype.vsew &&
            unsigned'(vs2_reshuffle_eew) > unsigned'(ara_req.vtype.vsew) &&
            ara_req.op inside {VNSRL, VNSRA, VNCLIP, VNCLIPU};

        // A full-length destination normally needs no preservation reshuffle. If
        // it aliases a source with the same EEW and effective LMUL, however, the
        // old group is still an input and must be converted before it is read.
        // Merge that conversion into the destination request before eliminating
        // duplicate requests for the same physical register group.
        if (ara_req.use_vd && ara_req.use_vs1 &&
            (ara_req.vs1 == ara_req.vd) &&
            (ara_req.eew_vs1 == ara_req.vtype.vsew) &&
            ((is_vstore ? ara_req.emul : lmul_vs1) ==
             (single_register_result(ara_req.op) ? LMUL_1 : ara_req.emul))) begin
          reshuffle_req_d[0] |= reshuffle_req_d[2];
        end
        if (ara_req.use_vd && ara_req.use_vs2 &&
            (ara_req.vs2 == ara_req.vd) &&
            (vs2_reshuffle_eew == ara_req.vtype.vsew) &&
            (lmul_vs2 ==
             (single_register_result(ara_req.op) ? LMUL_1 : ara_req.emul)) &&
            ara_req.op != VSLIDEDOWN) begin
          reshuffle_req_d[0] |= reshuffle_req_d[1];
        end
        // A narrowing destination may legally alias its double-width source.
        // When their EEWs differ, the source conversion is not a duplicate of
        // the destination conversion: keep it so the wide source is put in the
        // layout expected by the narrowing operation.  A later decode then
        // uses the overlap repair path to restore the destination layout.
        narrow_low_overlap_alias =
            (ara_req.cvt_resize == CVT_NARROW ||
             ara_req.op inside {VNSRL, VNSRA, VNCLIP, VNCLIPU}) &&
            ara_req.use_vd && ara_req.use_vs2 &&
            unsigned'(ara_req.vtype.vsew) < unsigned'(vs2_reshuffle_eew) &&
            ara_req.vd == ara_req.vs2;

        // A scalar reduction result may be placed anywhere in its vs2 source
        // group. Source and destination reshuffles are not duplicates when
        // their EEWs differ: normalize the source before it is read, then defer
        // the overlapping destination conversion to the repair path.
        reduction_source_overlap_reshuffle = reduction_result(ara_req.op) &&
            register_in_group(ara_req.vd, ara_req.vs2, lmul_vs2) &&
            reshuffle_req_d[1];

        // Mask out duplicate requests for the same architectural operand.
        reshuffle_req_d &= {
          (!ara_req.use_vs2 ||
           (ara_req.vs1 != ara_req.vs2) ||
           ara_req.source_snapshot_replay_vs2) &&
              (!ara_req.use_vd ||
              (ara_req.vs1 != ara_req.vd)),
          !ara_req.use_vd || (ara_req.vs2 != ara_req.vd) ||
              ara_req.op == VSLIDEDOWN || narrow_low_overlap_alias ||
              reduction_source_overlap_reshuffle,
          1'b1};

        // A widening reduction may legally place its single-register result
        // inside the narrow vs2 source group.  The source group must retain its
        // narrow layout until the reduction consumes it.  If vd needs a wider
        // layout, defer that conversion to the overlap-repair path so vd[0] is
        // written first and the remaining elements follow the active tail
        // policy without corrupting the source.
        legal_reduction_vd_overlap = widening_reduction(ara_req.op) &&
            register_in_group(ara_req.vd, ara_req.vs2, lmul_vs2) &&
            reshuffle_req_d[0];
        if (legal_reduction_vd_overlap) begin
          reshuffle_req_d[0] = 1'b0;
        end

        // A legal widening source may alias the high-numbered part of the wider
        // destination group.  Those registers cannot simultaneously carry the
        // narrow source and wide destination layouts before the operation.  Keep
        // the source layout and let the widening read-before-write protocol
        // consume it before the overlapping destination part is overwritten.
        // Integer widening operations tag cvt_resize as CVT_WIDE, while FP
        // widening arithmetic widens its operands in the operand queues and
        // deliberately leaves cvt_resize at CVT_SAME.  Classify the overlap
        // from the architectural destination EEW instead of that datapath-
        // specific field.  Reductions are excluded because their destination
        // occupies only one architectural register.
        legal_widen_overlap = ara_req.use_vd &&
            !single_register_result(ara_req.op) &&
            unsigned'(ara_req.vtype.vsew) > unsigned'(csr_vtype_q.vsew) &&
            ((ara_req.use_vs1 &&
              unsigned'(ara_req.eew_vs1) < unsigned'(ara_req.vtype.vsew) &&
              widening_high_overlap(ara_req.vd, ara_req.emul,
                                    ara_req.vs1, lmul_vs1)) ||
             (ara_req.use_vs2 &&
              unsigned'(vs2_reshuffle_eew) < unsigned'(ara_req.vtype.vsew) &&
              widening_high_overlap(ara_req.vd, ara_req.emul,
                                    ara_req.vs2, lmul_vs2)));
        if (legal_widen_overlap &&
            (!source_snapshot_resolves_widen ||
             source_snapshot_replays_wide_vd)) begin
          reshuffle_req_d[0] = 1'b0;
        end

        // A legal narrowing destination may alias the low-numbered part of
        // its double-width source group.  Reshuffling a partially preserved
        // destination before the instruction would also reshuffle and corrupt
        // that source.  Defer destination-tail conversion to the overlap
        // fixup path after the narrowing operation has consumed the source.
        legal_narrow_overlap = narrow_low_overlap_alias && reshuffle_req_d[0] &&
            !ara_req.source_snapshot_replay_vs2;
        if (legal_narrow_overlap) begin
          reshuffle_req_d[0] = 1'b0;
        end
`ifdef FOR_VERIFY
        if ($test$plusargs("ARA_DEBUG_FIXED") && ara_req.op == VSSRL &&
            ara_req.emul == LMUL_4) begin
          $display("[ARA_EEW] t=%0t vs1=v%0d need=%0d have=%0d/%0d/%0d/%0d valid=%b vs2=v%0d need=%0d have=%0d/%0d/%0d/%0d valid=%b req=%b",
                   $time, ara_req.vs1, ara_req.eew_vs1,
                   eew_q[ara_req.vs1], eew_q[ara_req.vs1 + 1],
                   eew_q[ara_req.vs1 + 2], eew_q[ara_req.vs1 + 3],
                   eew_valid_q[ara_req.vs1 +: 4], ara_req.vs2,
                   ara_req.eew_vs2, eew_q[ara_req.vs2],
                   eew_q[ara_req.vs2 + 1], eew_q[ara_req.vs2 + 2],
                   eew_q[ara_req.vs2 + 3], eew_valid_q[ara_req.vs2 +: 4],
                   reshuffle_req_d);
        end
`endif

        // Prepare the information to reshuffle the vector registers during the next cycles
        // Reshuffle in the following order: vd, v2, v1. The order is arbitrary.
        unique casez (reshuffle_req_d)
          3'b??1: begin
            automatic int unsigned first_register =
                is_segment_mem_op && is_vload ? 0 :
                active_first_register(ara_req.vtype.vsew, ara_req.vstart);
            eew_old_buffer_d = eew_q[ara_req.vd + first_register];
            eew_new_buffer_d = ara_req.vtype.vsew;
            vs_buffer_d      = ara_req.vd + first_register;
          end
          3'b?10: begin
            automatic int unsigned first_register =
                reshuffle_full_vs2_group ? 0 :
                active_first_register(vs2_reshuffle_eew, vs2_reshuffle_vstart);
            eew_old_buffer_d = eew_q[ara_req.vs2 + first_register];
            eew_new_buffer_d = vs2_reshuffle_eew;
            vs_buffer_d      = ara_req.vs2 + first_register;
          end
          3'b100: begin
            automatic int unsigned first_register =
                is_segment_mem_op && is_vstore ? 0 :
                active_first_register(ara_req.eew_vs1, ara_req.vstart);
            eew_old_buffer_d = eew_q[ara_req.vs1 + first_register];
            eew_new_buffer_d = ara_req.eew_vs1;
            vs_buffer_d      = ara_req.vs1 + first_register;
          end
          default:;
        endcase
      end

      // Reshuffle if at least one of the three registers needs a reshuffle
      if (legal_narrow_overlap && !reshuffle_req_d[1] &&
          !source_snapshot_valid_q) begin
        // The wide source is already in its requested layout, but converting
        // the overlapping destination in place would destroy it. Capture the
        // active source, normalize the old destination to the narrow layout,
        // then replay the captured source into the narrowing operation. This
        // also leaves mask-disabled destination bytes in the correct layout.
        ara_req_valid         = 1'b0;
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;
        source_snapshot_vs_d = ara_req.vs2;
        source_snapshot_lmul_d = lmul_vs2;
        source_snapshot_eew_d = vs2_reshuffle_eew;
        source_snapshot_vl_d = ara_req.vl;
        state_d = SOURCE_SNAPSHOT_CAPTURE;
      end else if ((dual_source_layout_conflict || widen_accumulator_layout_conflict ||
           masked_widen_layout_conflict || indexed_load_index_overlap) &&
          !source_snapshot_valid_q) begin
        // Keep the CVXIF request pending while a source-only uop drains the
        // currently valid view into the lane-local snapshot.
        ara_req_valid         = 1'b0;
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;
        if ((dual_source_layout_conflict && dual_source_snapshot_vs1) ||
            ((widen_accumulator_layout_conflict || masked_widen_layout_conflict) &&
             ara_req.use_vs1 &&
             !reshuffle_req_d[2] &&
             widening_high_overlap(ara_req.vd, ara_req.emul,
                                   ara_req.vs1, lmul_vs1))) begin
          source_snapshot_vs_d = ara_req.vs1;
          source_snapshot_lmul_d = lmul_vs1;
          source_snapshot_eew_d = ara_req.eew_vs1;
          source_snapshot_vl_d = ara_req.vl;
        end else begin
          source_snapshot_vs_d = ara_req.vs2;
          source_snapshot_lmul_d = lmul_vs2;
          source_snapshot_eew_d = vs2_reshuffle_eew;
          // Gather indices may legally select any element below VLMAX, not
          // only an element below the current VL.  When the data view is the
          // source retained across an aliased index reshuffle, capture the
          // complete data group so every in-range index can be replayed.
          source_snapshot_vl_d = ara_req.op inside {VRGATHER, VRGATHEREI16}
              ? vlen_t'(lmul_element_capacity(lmul_vs2, vs2_reshuffle_eew))
              : ara_req.vl;
        end
        state_d = SOURCE_SNAPSHOT_CAPTURE;
      end else if (|reshuffle_req_d) begin
        // Instruction is of one of the RVV types
        automatic rvv_instruction_t insn = rvv_instruction_t'(instr.instr);

        // Stall the interface, and inject a reshuffling instruction
        acc_resp_o.req_ready  = 1'b0;
        acc_resp_o.resp_valid = 1'b0;
        ara_req_valid  = 1'b0;

        // Each operand can have a different effective LMUL.
        unique casez (reshuffle_req_d)
          3'b??1: rs_lmul_cnt_limit_d = is_segment_mem_op && is_vload
              ? 3'(segment_register_count(ara_req.nf, ara_req.emul) - 1)
              : active_register_limit(
                  single_register_result(ara_req.op) ? LMUL_1 : ara_req.emul,
                  ara_req.vtype.vsew, ara_req.vstart, ara_req.vl);
          3'b?10: rs_lmul_cnt_limit_d = active_register_limit(
            lmul_vs2, vs2_reshuffle_eew,
            reshuffle_full_vs2_group ? vlen_t'(0) : vs2_reshuffle_vstart,
            reshuffle_full_vs2_group
                ? vlen_t'((VLENB * lmul_register_count(lmul_vs2)) >>
                          unsigned'(vs2_reshuffle_eew))
                : vs2_reshuffle_vl);
          3'b100: rs_lmul_cnt_limit_d = is_segment_mem_op && is_vstore
              ? 3'(segment_register_count(ara_req.nf, ara_req.emul) - 1)
              : active_register_limit(
                  is_vstore ? ara_req.emul : lmul_vs1,
                  ara_req.eew_vs1, ara_req.vstart, ara_req.vl);
          default: rs_lmul_cnt_limit_d = '0;
        endcase

        // Save info for next reshuffles
        reshuffle_eew_vs1_d = ara_req.eew_vs1;
        reshuffle_eew_vs2_d = vs2_reshuffle_eew;
        reshuffle_eew_vd_d  = ara_req.vtype.vsew;
        reshuffle_vs1_base_d = ara_req.vs1 +
            (is_segment_mem_op && is_vstore ? 0 :
             active_first_register(ara_req.eew_vs1, ara_req.vstart));
        reshuffle_vs2_base_d = ara_req.vs2 +
            (reshuffle_full_vs2_group ? 0 :
             active_first_register(vs2_reshuffle_eew, vs2_reshuffle_vstart));
        reshuffle_vs1_limit_d = is_segment_mem_op && is_vstore
            ? 3'(segment_register_count(ara_req.nf, ara_req.emul) - 1)
            : active_register_limit(
                is_vstore ? ara_req.emul : lmul_vs1,
                ara_req.eew_vs1, ara_req.vstart, ara_req.vl);
        reshuffle_vs2_limit_d = active_register_limit(
            lmul_vs2, vs2_reshuffle_eew,
            reshuffle_full_vs2_group ? vlen_t'(0) : vs2_reshuffle_vstart,
            reshuffle_full_vs2_group
                ? vlen_t'((VLENB * lmul_register_count(lmul_vs2)) >>
                          unsigned'(vs2_reshuffle_eew))
                : vs2_reshuffle_vl);
        reshuffle_lmul_vs1_d = is_vstore ? ara_req.emul : lmul_vs1;
        reshuffle_lmul_vs2_d = lmul_vs2;
        reshuffle_lmul_vd_d  = single_register_result(ara_req.op) ? LMUL_1 : ara_req.emul;

        // Reshuffle
        state_d = RESHUFFLE;
      end else if ((ara_req.vstart < ara_req.vl) &&
                   ((legal_widen_overlap &&
                     (!source_snapshot_resolves_widen ||
                      source_snapshot_replays_wide_vd)) ||
                    legal_narrow_overlap || legal_reduction_vd_overlap) &&
                   ara_req_valid && ara_req_ready_i) begin
        if (!overlap_prepared_q) begin
          automatic vlen_t repair_vl = legal_reduction_vd_overlap
              ? vlen_t'(1) : ara_req.vl;
          automatic int unsigned elements_per_reg =
              VLENB >> unsigned'(ara_req.vtype.vsew);
          automatic int unsigned boundary_reg =
              unsigned'(repair_vl) / elements_per_reg;
          automatic int unsigned active_in_boundary =
              unsigned'(repair_vl) % elements_per_reg;
          automatic int unsigned active_bytes =
              active_in_boundary << unsigned'(ara_req.vtype.vsew);
          automatic int unsigned overlap_source_base;
          automatic int unsigned overlap_start_element;
          automatic logic snapshot_needed;

          // Hold the architectural request while the internal capture is
          // issued.  A snapshot is needed only when the active/tail boundary
          // cuts an aggregate lane word; whole tail words survive the original
          // read-before-write widening operation and can be read back later.
          ara_req_valid         = 1'b0;
          acc_resp_o.req_ready  = 1'b0;
          acc_resp_o.resp_valid = 1'b0;

          overlap_prepared_d   = 1'b1;
          overlap_vd_d         = ara_req.vd;
          overlap_lmul_d       = single_register_result(ara_req.op)
              ? LMUL_1 : ara_req.emul;
          overlap_target_eew_d = ara_req.vtype.vsew;
          overlap_vl_d         = repair_vl;
          overlap_vstart_d     = ara_req.vstart;
          overlap_prefix_vl_d  = legal_narrow_overlap &&
              !source_snapshot_preserves_narrow_vd ? ara_req.vstart : '0;
          overlap_reg_index_d  = '0;
          overlap_current_vd_d = ara_req.vd;
          overlap_elements_per_reg_d = vlen_t'(elements_per_reg);
          overlap_reg_first_element_d = '0;
          overlap_current_old_eew_d = eew_q[ara_req.vd];
          overlap_current_old_eew_valid_d = eew_valid_q[ara_req.vd];
          for (int unsigned i = 0; i < 8; i++) begin
            if (i < lmul_register_count(
                    single_register_result(ara_req.op) ? LMUL_1 : ara_req.emul) &&
                (unsigned'(ara_req.vd) + i) < 32) begin
              overlap_old_eew_d[i] = eew_q[ara_req.vd + i];
              overlap_old_eew_valid_d[i] = eew_valid_q[ara_req.vd + i];
            end else begin
              overlap_old_eew_d[i] = rvv_pkg::EW8;
              overlap_old_eew_valid_d[i] = 1'b0;
            end
          end

          snapshot_needed = 1'b0;
          if (boundary_reg < lmul_register_count(
                  single_register_result(ara_req.op) ? LMUL_1 : ara_req.emul) &&
              (unsigned'(ara_req.vd) + boundary_reg) < 32 &&
              active_in_boundary != 0) begin
            snapshot_needed = eew_valid_q[ara_req.vd + boundary_reg] &&
                eew_q[ara_req.vd + boundary_reg] != ara_req.vtype.vsew &&
                (active_bytes % (NrLanes * 8)) != 0;
          end
          overlap_snapshot_valid_d = snapshot_needed;
          overlap_boundary_reg_d = 3'(boundary_reg);
          overlap_boundary_vd_d = ara_req.vd + 5'(boundary_reg);
          overlap_boundary_old_eew_d = rvv_pkg::EW8;
          if (snapshot_needed)
            overlap_boundary_old_eew_d = eew_q[ara_req.vd + boundary_reg];
          overlap_snapshot_word_d = vlen_t'(active_bytes / (NrLanes * 8));

          // Widening MACs also read vd as a wide accumulator. If their active
          // destination lies completely below the overlapping high source
          // group, convert that safe prefix before issuing the operation.
          if (legal_widen_overlap && ara_req.use_vd_op) begin
            overlap_source_base = 32;
            if (ara_req.use_vs1 &&
                widening_high_overlap(ara_req.vd, ara_req.emul,
                                      ara_req.vs1, lmul_vs1))
              overlap_source_base = unsigned'(ara_req.vs1);
            if (ara_req.use_vs2 &&
                widening_high_overlap(ara_req.vd, ara_req.emul,
                                      ara_req.vs2, lmul_vs2) &&
                unsigned'(ara_req.vs2) < overlap_source_base)
              overlap_source_base = unsigned'(ara_req.vs2);

            overlap_start_element =
                (overlap_source_base - unsigned'(ara_req.vd)) * elements_per_reg;
            if (unsigned'(ara_req.vl) <= overlap_start_element)
              overlap_prefix_vl_d = ara_req.vl;
          end

          if (overlap_prefix_vl_d != '0)
            state_d = OVERLAP_PREFIX_FIXUP;
          else
            state_d = snapshot_needed ? OVERLAP_CAPTURE : OVERLAP_ISSUE_ORIGINAL;
        end else begin
          // The boundary snapshot, when required, is now stable in the SLDU.
          // Issue the original operation and keep CVXIF stalled until all tail
          // repair uops have completed.
          state_d = OVERLAP_WAIT_ORIGINAL;
          acc_resp_o.req_ready  = 1'b0;
          acc_resp_o.resp_valid = 1'b0;
          overlap_prepared_d = 1'b0;
          overlap_original_accepted_d = 1'b0;
        end
      end


      if (ara_req_valid && ara_req_ready_i &&
          (ara_req.source_snapshot_replay_vs1 ||
           ara_req.source_snapshot_replay_vs2)) begin
        source_snapshot_valid_d = 1'b0;
      end
    end

    // Update only registers intersecting the architectural active interval.
    // Complete prefix/tail registers are not rewritten and must retain both
    // their physical layout and their per-register EEW metadata.
    if (ara_req_valid_d && ara_req_d.use_vd && ara_req_ready_i &&
        state_q != OVERLAP_PREFIX_FIXUP) begin
      automatic vlmul_e destination_lmul = single_register_result(ara_req_d.op)
          ? LMUL_1 : ara_req_d.emul;
      automatic int unsigned first_register = active_first_register(
          ara_req_d.vtype.vsew, ara_req_d.vstart);
      automatic int unsigned register_count = active_register_count(
          destination_lmul, ara_req_d.vtype.vsew, ara_req_d.vstart, ara_req_d.vl);
      for (int unsigned i = 0; i < 8; i++) begin
        if (i < register_count &&
            (unsigned'(ara_req_d.vd) + first_register + i) < 32) begin
          eew_d[ara_req_d.vd + first_register + i]       = ara_req_d.vtype.vsew;
          eew_valid_d[ara_req_d.vd + first_register + i] = 1'b1;
        end
      end
    end

    // Any valid non-config instruction is a NOP if vl == 0, with some exceptions,
    // e.g. whole vector memory operations / whole vector register move
    if (is_decoding && (csr_vstart_q >= csr_vl_q || mask_mem_noop || null_vslideup) && !is_config &&
      !ignore_zero_vl_check && !acc_resp_o.exception.valid) begin
      // If we are acknowledging a memory operation, we must tell Ariane that the memory
      // operation was resolved (to decrement its pending load/store counter)
      // This can collide with the same signal from the vector load/store unit, so we must
      // delay the zero_vl acknowledge by 1 cycle
      acc_resp_o.req_ready  = ~((is_vload & load_complete_q) | (is_vstore & store_complete_q));
      acc_resp_o.resp_valid = ~((is_vload & load_complete_q) | (is_vstore & store_complete_q));
      ara_req_valid  = 1'b0;
      load_zero_vl     = is_vload;
      store_zero_vl    = is_vstore;
    end

    // Reset vstart to zero for successful vector instructions
    // Corner cases:
    // * vstart exception reporting, e.g., VLSU, is handled above
    // * CSR operations are not considered vector instructions
    if ( acc_resp_o.resp_valid
          & !acc_resp_o.exception.valid
          & (instr.itype.opcode != riscv::OpcodeSystem)
        ) begin
      csr_vstart_d = '0;
    end

    acc_resp_o.load_complete  = load_zero_vl  | load_complete_q;
    acc_resp_o.store_complete = store_zero_vl | store_complete_q;

    // The token must change at every new instruction
    ara_req.token = (ara_req_valid_o && ara_req_ready_i) ? ~ara_req_o.token : ara_req_o.token;
`ifdef FOR_VERIFY
    if (acc_req_i.req_valid && acc_resp_o.req_ready) begin
      verify_front_active_d = 1'b0;
      verify_arch_seq_d     = verify_active_arch_seq_d + 1;
    end
`endif
  end: p_decoder

`ifdef FOR_VERIFY
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VFMVFS9") &&
        is_decoding && instr.instr == 32'h429014d7) begin
      $display("[ARA_VFMVFS9_DISPATCH] t=%0t state=%0d req=%0b/%0b op=%0d vs1=v%0d/%0b/e%0d/l%0d have=%0b/e%0d vs2=v%0d/%0b/e%0d/l%0d have=%0b/e%0d vl=%0d in_lane=%0b need=%0b/%0b reshuffle=%b",
               $time, state_q, ara_req_valid, ara_req_ready_i, ara_req.op,
               ara_req.vs1, ara_req.use_vs1, ara_req.eew_vs1, lmul_vs1,
               eew_valid_q[ara_req.vs1], eew_q[ara_req.vs1],
               ara_req.vs2, ara_req.use_vs2, vs2_reshuffle_eew, lmul_vs2,
               eew_valid_q[ara_req.vs2], eew_q[ara_req.vs2], ara_req.vl,
               in_lane_op,
               active_group_needs_reshuffle(ara_req.vs1, lmul_vs1,
                                            ara_req.eew_vs1,
                                            ara_req.vstart, ara_req.vl),
               active_group_needs_reshuffle(ara_req.vs2, lmul_vs2,
                                            vs2_reshuffle_eew,
                                            ara_req.vstart, ara_req.vl),
               reshuffle_req_d);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VCOMPRESS415") &&
        is_decoding && instr.instr == 32'h5f412857) begin
      $display("[ARA_VCOMPRESS415_DISPATCH] t=%0t state=%0d op=%0d valid=%0b use_vs1=%0b vs1=v%0d lmul_vs1=%0d eew_vs1=%0d tracked_valid=%0b tracked_eew=%0d in_lane=%0b need=%0b req_d=%b vd=v%0d vs2=v%0d",
               $time, state_q, ara_req.op, ara_req_valid, ara_req.use_vs1,
               ara_req.vs1, lmul_vs1, ara_req.eew_vs1,
               eew_valid_q[ara_req.vs1], eew_q[ara_req.vs1], in_lane_op,
               active_group_needs_reshuffle(ara_req.vs1, lmul_vs1,
                                            ara_req.eew_vs1,
                                            ara_req.vstart, ara_req.vl),
               reshuffle_req_d, ara_req.vd, ara_req.vs2);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("ARA_DEBUG_VMUL402") &&
        ara_req_valid_o && ara_req_ready_i &&
        ara_req_o.verify_arch_insn == 32'h96c6e457)
      $display("[ARA_VMUL402_DISPATCH] t=%0t op=%0d vd=v%0d vs2=v%0d vl=%0d sew=%0d use_scalar=%0b scalar=%h token=%0b",
               $time, ara_req_o.op, ara_req_o.vd, ara_req_o.vs2,
               ara_req_o.vl, ara_req_o.vtype.vsew,
               ara_req_o.use_scalar_op, ara_req_o.scalar_op,
               ara_req_o.token);
  end
`endif

  // Check if register groups have all their registers with the same EEW encoding
  always_comb begin
    logic [15:0] same_eew_m2;
    logic [7:0]  same_eew_m4;
    logic [3:0]  same_eew_m8;
    logic [3:0]  same_eew_by_lmul;

    // LMUL = 2: group of 2 registers
    for (int i = 0; i < 16; i++) begin
      same_eew_m2[i] = (eew_q[2*i] == eew_q[2*i+1]);
    end

    // LMUL = 4: group of 4 registers (2 LMUL=2 groups + mid-pair check)
    for (int i = 0; i < 8; i++) begin
      same_eew_m4[i] = (eew_q[4*i+1] == eew_q[4*i+2]) &&
                       (same_eew_m2[2*i] && same_eew_m2[2*i+1]);
    end

    // LMUL = 8: group of 8 registers (2 LMUL=4 groups + mid-pair check)
    for (int i = 0; i < 4; i++) begin
      same_eew_m8[i] = (eew_q[8*i+3] == eew_q[8*i+4]) &&
                       (same_eew_m4[2*i] && same_eew_m4[2*i+1]);
    end

    // Final selection per LMUL
    same_eew_by_lmul[LMUL_1] = 1'b1; // always same EEW with 1 register
    same_eew_by_lmul[LMUL_2] = same_eew_m2[ara_req.vs1[4:1]];
    same_eew_by_lmul[LMUL_4] = same_eew_m4[ara_req.vs1[4:2]];
    same_eew_by_lmul[LMUL_8] = same_eew_m8[ara_req.vs1[4:3]];

    // If EMUL is fractional (emul[2] == 1), EEW is considered uniform
    is_same_eew = same_eew_by_lmul[ara_req.emul[1:0]] | ara_req.emul[2];
  end

endmodule : ara_dispatcher
