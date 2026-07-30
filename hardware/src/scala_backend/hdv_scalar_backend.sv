// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Minimal CVA6-style scalar backend for HDV.  HDV already owns fetch, packet
// formation, and scalar/vector splitting, so this block keeps only the pieces
// needed behind HEU: an architectural X/FP register context, a small RV64
// decoder/ALU/branch path, a CSR-cycle stub, and a vector operand service.

module hdv_scalar_backend
  import ariane_pkg::*;
#(
  parameter int unsigned XLEN     = 64,
  parameter int unsigned NumSlots = 8,
  parameter int unsigned ScalarIssueWidth = 3,
  parameter int unsigned SimpleAluIssueWidth = 2,
  parameter int unsigned AxiDataWidth = 64,
  parameter int unsigned VectorVlenBytes = 0,
  parameter logic [XLEN-1:0] InitialRa  = '0,
  parameter logic [XLEN-1:0] InitialA0  = '0,
  parameter logic [XLEN-1:0] InitialA1  = '0,
  parameter logic [XLEN-1:0] InitialA2  = '0,
  parameter logic [XLEN-1:0] InitialA3  = '0,
  parameter logic [XLEN-1:0] InitialA4  = '0,
  parameter logic [XLEN-1:0] InitialA5  = '0,
  parameter logic [XLEN-1:0] InitialA6  = '0,
  parameter logic [XLEN-1:0] InitialA7  = '0,
  parameter logic [XLEN-1:0] InitialFa0 = '0,
  parameter bit TreatRetAsTaskExit   = 1'b1,
  // TreatEbreakAsTaskExit: when 1, the EBREAK instruction (0x00100073) is
  // recognised as the end of an HDV task, decoupling task-completion from
  // the ordinary scalar return convention.  Set to 0 if the task body uses
  // ebreak for debug purposes and task-end is signalled by ret only.
  parameter bit TreatEbreakAsTaskExit = 1'b1,
  parameter config_pkg::cva6_cfg_t CVA6Cfg = cva6_config_pkg::cva6_cfg,
  parameter type addr_t = logic [XLEN-1:0],
  parameter type axi_req_t = logic,
  parameter type axi_resp_t = logic
) (
  input  logic                         clk_i,
  input  logic                         rst_ni,
  input  logic                         flush_i,

  input  logic                         scalar_valid_i,
  output logic                         scalar_ready_o,
  input  logic [NumSlots-1:0]          scalar_insn_valid_i,
  input  logic [NumSlots-1:0][31:0]    scalar_insn_i,
  input  logic [NumSlots-1:0]          scalar_insn_is_32b_i,
  input  addr_t [NumSlots-1:0]         scalar_insn_pc_i,
  output logic                         scalar_ep_done_o,
  output logic [31:0]                  scalar_pending_gpr_read_mask_o,
  output logic [31:0]                  scalar_pending_gpr_write_mask_o,
  output logic [31:0]                  scalar_pending_fpr_read_mask_o,
  output logic [31:0]                  scalar_pending_fpr_write_mask_o,
  // Asserted while the active scalar EP still has an unexecuted or in-flight
  // memory-ordering operation. Loads remain pending through their R response;
  // stores remain pending through their B response.
  output logic                         scalar_mem_order_pending_o,
  output logic                         scalar_error_o,

  output logic                         redirect_valid_o,
  output addr_t                        redirect_pc_o,
  output logic                         branch_resolved_valid_o,
  output logic                         branch_taken_o,
  output addr_t                        branch_pc_o,
  output addr_t                        branch_target_o,
  // branch_backward_o: asserted (together with branch_resolved_valid_o) when
  // the resolved branch target is numerically less than the branch PC, i.e.
  // it is a backward branch.  hdv_top uses this for loop-exit signalling
  // without needing to compare addresses itself.
  output logic                         branch_backward_o,
  output logic                         task_complete_o,

  input  logic                         vec_operand_req_valid_i,
  output logic                         vec_operand_req_ready_o,
  input  logic [4:0]                   vec_rs1_addr_i,
  input  logic [4:0]                   vec_rs2_addr_i,
  input  logic [4:0]                   vec_frs1_addr_i,
  output logic [XLEN-1:0]              vec_rs1_data_o,
  output logic [XLEN-1:0]              vec_rs2_data_o,
  output logic [XLEN-1:0]              vec_frs1_data_o,

  input  logic                         vec_wb_valid_i,
  input  logic [4:0]                   vec_wb_rd_i,
  input  logic [XLEN-1:0]              vec_wb_data_i,
  input  logic                         vec_wb_is_fpr_i,
  input  logic                         vec_wb_is_vset_i,

  // In-flight vset (rd!=x0) hazard hints, one per outstanding vector EP.  A
  // scalar that reads either destination must wait for the corresponding VL
  // writeback.
  input  logic [1:0]                   vec_vset_inflight_valid_i,
  input  logic [1:0][4:0]              vec_vset_inflight_rd_i,
  input  logic                         vec_store_inflight_i,

  output axi_req_t                     scalar_axi_req_o,
  input  axi_resp_t                    scalar_axi_resp_i
);

  localparam int unsigned EffectiveSimpleAluIssueWidth =
      (SimpleAluIssueWidth < ScalarIssueWidth) ? SimpleAluIssueWidth : ScalarIssueWidth;
  localparam int unsigned SlotIdxWidth =
      (NumSlots > 1) ? $clog2(NumSlots) : 1;

  typedef enum logic [3:0] {
    IDLE      = 4'd0,
    EXECUTE   = 4'd1,
    WAIT_MULT = 4'd2,
    WAIT_FPU  = 4'd3,
    LSU_AR    = 4'd4,
    LSU_R     = 4'd5,
    LSU_AW    = 4'd6,
    LSU_W     = 4'd7,
    LSU_B     = 4'd8,
    DONE      = 4'd9,
    REDIRECT  = 4'd10,
    COMPLEX_ISSUE = 4'd11,
    COMPLEX_EXEC  = 4'd12
  } state_e;

  localparam type branchpredict_sbe_t = struct packed {
    cf_t                     cf;
    logic [CVA6Cfg.VLEN-1:0] predict_address;
  };

  localparam type exception_t = struct packed {
    logic [CVA6Cfg.XLEN-1:0] cause;
    logic [CVA6Cfg.XLEN-1:0] tval;
    logic [CVA6Cfg.GPLEN-1:0] tval2;
    logic [31:0] tinst;
    logic gva;
    logic valid;
  };

  localparam type scoreboard_entry_t = struct packed {
    logic [CVA6Cfg.VLEN-1:0] pc;
    logic [CVA6Cfg.TRANS_ID_BITS-1:0] trans_id;
    fu_t fu;
    fu_op op;
    logic [REG_ADDR_SIZE-1:0] rs1;
    logic [REG_ADDR_SIZE-1:0] rs2;
    logic [REG_ADDR_SIZE-1:0] rd;
    logic [CVA6Cfg.XLEN-1:0] result;
    logic valid;
    logic use_imm;
    logic use_zimm;
    logic use_pc;
    exception_t ex;
    branchpredict_sbe_t bp;
    logic is_compressed;
    logic is_macro_instr;
    logic is_last_macro_instr;
    logic is_double_rd_macro_instr;
    logic vfp;
    logic is_zcmt;
  };

  localparam type bp_resolve_t = struct packed {
    logic                    valid;
    logic [CVA6Cfg.VLEN-1:0] pc;
    logic [CVA6Cfg.VLEN-1:0] target_address;
    logic                    is_mispredict;
    logic                    is_taken;
    cf_t                     cf_type;
  };

  localparam type irq_ctrl_t = struct packed {
    logic [CVA6Cfg.XLEN-1:0] mie;
    logic [CVA6Cfg.XLEN-1:0] mip;
    logic [CVA6Cfg.XLEN-1:0] mideleg;
    logic [CVA6Cfg.XLEN-1:0] hideleg;
    logic [CVA6Cfg.XLEN-1:0] hgeie;
    logic [5:0]              vgein;
    logic                    sie;
    logic                    global_enable;
  };

  localparam type fu_data_t = struct packed {
    fu_t                              fu;
    fu_op                             operation;
    logic [CVA6Cfg.XLEN-1:0]          operand_a;
    logic [CVA6Cfg.XLEN-1:0]          operand_b;
    logic [CVA6Cfg.XLEN-1:0]          imm;
    logic [CVA6Cfg.TRANS_ID_BITS-1:0] trans_id;
  };

  localparam type interrupts_t = struct packed {
    logic [CVA6Cfg.XLEN-1:0] S_SW;
    logic [CVA6Cfg.XLEN-1:0] VS_SW;
    logic [CVA6Cfg.XLEN-1:0] M_SW;
    logic [CVA6Cfg.XLEN-1:0] S_TIMER;
    logic [CVA6Cfg.XLEN-1:0] VS_TIMER;
    logic [CVA6Cfg.XLEN-1:0] M_TIMER;
    logic [CVA6Cfg.XLEN-1:0] S_EXT;
    logic [CVA6Cfg.XLEN-1:0] VS_EXT;
    logic [CVA6Cfg.XLEN-1:0] M_EXT;
    logic [CVA6Cfg.XLEN-1:0] HS_EXT;
  };

  localparam interrupts_t HDV_INTERRUPTS = '{
    S_SW:     (1 << (CVA6Cfg.XLEN - 1)) | CVA6Cfg.XLEN'(riscv::IRQ_S_SOFT),
    VS_SW:    (1 << (CVA6Cfg.XLEN - 1)) | CVA6Cfg.XLEN'(riscv::IRQ_VS_SOFT),
    M_SW:     (1 << (CVA6Cfg.XLEN - 1)) | CVA6Cfg.XLEN'(riscv::IRQ_M_SOFT),
    S_TIMER:  (1 << (CVA6Cfg.XLEN - 1)) | CVA6Cfg.XLEN'(riscv::IRQ_S_TIMER),
    VS_TIMER: (1 << (CVA6Cfg.XLEN - 1)) | CVA6Cfg.XLEN'(riscv::IRQ_VS_TIMER),
    M_TIMER:  (1 << (CVA6Cfg.XLEN - 1)) | CVA6Cfg.XLEN'(riscv::IRQ_M_TIMER),
    S_EXT:    (1 << (CVA6Cfg.XLEN - 1)) | CVA6Cfg.XLEN'(riscv::IRQ_S_EXT),
    VS_EXT:   (1 << (CVA6Cfg.XLEN - 1)) | CVA6Cfg.XLEN'(riscv::IRQ_VS_EXT),
    M_EXT:    (1 << (CVA6Cfg.XLEN - 1)) | CVA6Cfg.XLEN'(riscv::IRQ_M_EXT),
    HS_EXT:   (1 << (CVA6Cfg.XLEN - 1)) | CVA6Cfg.XLEN'(riscv::IRQ_HS_EXT)
  };

  state_e state_d, state_q;

  logic [NumSlots-1:0]       insn_valid_d, insn_valid_q;
  logic [NumSlots-1:0][31:0] insn_d, insn_q;
  logic [NumSlots-1:0]       insn_is_32b_d, insn_is_32b_q;
  addr_t [NumSlots-1:0]      insn_pc_d, insn_pc_q;
  logic [NumSlots-1:0]       remaining_slots;
  logic [31:0] pending_gpr_read_mask_d;
  logic [31:0] pending_gpr_write_mask_d;
  logic [31:0] pending_fpr_read_mask_d;
  logic [31:0] pending_fpr_write_mask_d;
  logic        scalar_mem_order_pending_d, scalar_mem_order_pending_q;
  logic        scalar_mem_release_forbidden_d, scalar_mem_release_forbidden_q;
  logic        scalar_input_has_mem_order;
  logic        scalar_input_has_nonreleasable_order;
  logic        scalar_remaining_releasable_mem;
  logic        scalar_remaining_nonreleasable_order;
  logic        scalar_mem_inflight_d;

  logic [XLEN-1:0] xrf_d [32];
  logic [XLEN-1:0] xrf_q [32];
  logic [XLEN-1:0] frf_d [32];
  logic [XLEN-1:0] frf_q [32];
  logic [63:0] cycle_d, cycle_q;
  logic [XLEN-1:0] csr_vl_d, csr_vl_q;
  logic [XLEN-1:0] csr_vtype_d, csr_vtype_q;
  logic [2:0]      csr_frm_d, csr_frm_q;

  logic [SlotIdxWidth-1:0] curr_slot_idx;
  logic       curr_slot_found;
  logic [31:0] curr_insn;
  logic        curr_is_32b;
  addr_t       curr_pc;
  logic [15:0] curr_cinsn;
  logic [SlotIdxWidth-1:0] serial_slot_idx;
  logic        serial_slot_found;
  logic [31:0] serial_insn;
  logic        serial_is_32b;
  logic [31:0] serial_dec_instr;
  logic        serial_illegal_compressed;
  logic [31:0] serial_decoder_instr;

  logic [31:0] cva6_dec_instr;
  logic        cva6_illegal_compressed;
  logic        cva6_is_macro_instr;
  logic        cva6_is_compressed;
  logic        cva6_is_zcmt_instr;
  logic [31:0] cva6_decoder_instr;
  scoreboard_entry_t cva6_decoded;
  logic [31:0] cva6_orig_instr;
  logic        cva6_is_control_flow;
  fu_data_t    cva6_fu_data;
  logic [XLEN-1:0] cva6_operand_a;
  logic [XLEN-1:0] cva6_operand_b;
  logic [XLEN-1:0] cva6_alu_result;
  logic            cva6_alu_branch_res;
  logic [XLEN-1:0] cva6_mult_result;
  logic            cva6_mult_valid;
  logic            cva6_mult_ready;
  logic [CVA6Cfg.TRANS_ID_BITS-1:0] cva6_mult_trans_id;
  logic [CVA6Cfg.FLen-1:0]          cva6_fpu_result;
  logic                             cva6_fpu_valid;
  logic                             cva6_fpu_ready;
  logic [CVA6Cfg.TRANS_ID_BITS-1:0] cva6_fpu_trans_id;
  exception_t                       cva6_fpu_exception;
  logic [CVA6Cfg.VLEN-1:0] cva6_branch_result;
  bp_resolve_t             cva6_resolved_branch;
  logic                    cva6_resolve_branch;
  exception_t              cva6_branch_exception;
  logic                    fast_branch_valid;
  logic                    fast_branch_taken;
  addr_t                   fast_branch_target;
  logic                    fast_task_exit;

  // Non-simple scalar instructions cross a registered issue boundary before
  // entering the execution units.  Besides shortening the execution path,
  // keeping the decoded metadata here makes completion independent of the
  // live priority encoder while the instruction is in flight.
  logic              issue_valid_d, issue_valid_q;
  logic [SlotIdxWidth-1:0] issue_slot_idx_d, issue_slot_idx_q;
  logic [31:0]       issue_insn_d, issue_insn_q;
  logic              issue_is_32b_d, issue_is_32b_q;
  addr_t             issue_pc_d, issue_pc_q;
  logic [31:0]       issue_decoder_instr_d, issue_decoder_instr_q;
  scoreboard_entry_t issue_decoded_d, issue_decoded_q;
  fu_data_t          issue_fu_data_d, issue_fu_data_q;
  logic              issue_mult_ready_d, issue_mult_ready_q;

  logic              exec_slot_found;
  addr_t             exec_pc;
  logic [31:0]       exec_decoder_instr;
  scoreboard_entry_t exec_decoded;
  fu_data_t          exec_fu_data;
  fu_data_t          issue_operand_fu_data;
  logic [XLEN-1:0]   issue_operand_a;
  logic [XLEN-1:0]   issue_operand_b;
  logic [XLEN-1:0]   issue_operand_c;
  logic              scalar_mult_issue;
  logic              cva6_mult_issue;
  logic              local_mul_issue;
  logic              local_mul_valid;
  logic [XLEN-1:0]   local_mul_result;
  logic              scalar_mult_valid;
  logic [XLEN-1:0]   scalar_mult_result;

  // The stock CVA6 multiplier performs a full XLEN x XLEN multiply between
  // issue_fu_data_q and its result register.  Split ordinary integer
  // multiplication into smaller partial products and a registered adder tree.
  // The active RVB=0 configuration instantiates only the serial divider for
  // non-local MULT operations.  An RVB build retains the CVA6 unit for CLMUL.
  localparam int unsigned MulHalfW = XLEN / 2;
  localparam int unsigned MulCrossW = XLEN + 2;
  localparam int unsigned MulAccumW = 2 * XLEN + 2;
  logic                    local_mul_s1_valid_q;
  logic                    local_mul_s2_valid_q;
  fu_op                    local_mul_s1_op_q;
  fu_op                    local_mul_s2_op_q;
  logic [XLEN-1:0]         local_mul_ll_d, local_mul_ll_q;
  logic signed [MulCrossW-1:0]
                           local_mul_hl_d, local_mul_hl_q;
  logic signed [MulCrossW-1:0]
                           local_mul_lh_d, local_mul_lh_q;
  logic signed [MulCrossW-1:0]
                           local_mul_hh_d, local_mul_hh_q;
  logic signed [MulAccumW-1:0]
                           local_mul_pair_lo_d, local_mul_pair_lo_q;
  logic signed [MulAccumW-1:0]
                           local_mul_pair_hi_d, local_mul_pair_hi_q;
  logic signed [MulAccumW-1:0] local_mul_product;

  logic [4:0]  rs1_addr;
  logic [4:0]  rs2_addr;
  logic [XLEN-1:0] rs1_data;
  logic [XLEN-1:0] rs2_data;
  logic [XLEN-1:0] rs3_data;
  axi_req_t scalar_axi_req;

  logic wb_en;
  logic wb_is_fpr;
  logic [4:0] wb_addr;
  logic [XLEN-1:0] wb_data;
  logic unsupported;
  logic branch_resolved;
  logic branch_taken;
  addr_t branch_target;
  logic redirect_pending_d, redirect_pending_q;
  addr_t redirect_pc_d, redirect_pc_q;
  logic error_seen_d, error_seen_q;
  logic task_complete_pending_d, task_complete_pending_q;

  logic branch_resolved_pulse_d, branch_resolved_pulse_q;
  logic branch_taken_d, branch_taken_q;
  addr_t branch_pc_d, branch_pc_q;
  addr_t branch_target_d, branch_target_q;
  logic branch_backward_d, branch_backward_q;
  logic lsu_is_load;
  addr_t lsu_addr;
  logic [1:0] lsu_size;
  logic lsu_misaligned;
  logic [AxiDataWidth-1:0] lsu_store_data;
  logic [(AxiDataWidth/8)-1:0] lsu_store_strb;
  logic [XLEN-1:0] lsu_load_data;
  logic lsu_resp_error;
  logic lsu_is_fp;
  logic live_lsu_misaligned;
  logic issue_lsu_misaligned;
  logic serial_lsu_supported;
  logic serial_lsu_encoding_valid;
  logic serial_load_base_raw;
  logic [4:0] serial_lsu_rd;
  logic [4:0] serial_lsu_rs2;
  logic fpu_issue;
  logic fpu_writes_fpr;
  logic fpu_writes_xrf;
  logic csr_write;
  logic [11:0] csr_addr;
  logic [XLEN-1:0] csr_rdata;
  logic [XLEN-1:0] csr_wdata;
  logic [XLEN-1:0] csr_wmask;
  logic csr_supported;
  logic csr_op_supported;
  logic csr_addr_supported;
  logic hdv_task_ret;
  logic hdv_task_ebreak;
  logic branch_backward;  // combinational: resolved && target < pc

  typedef struct packed {
    logic             valid;
    logic             wb_en;
    logic [4:0]       rd;
    logic [XLEN-1:0]  result;
  } simple_alu_dec_t;

  logic [NumSlots-1:0]       simple_batch_mask;
  logic [NumSlots-1:0]       simple_class_valid;
  logic [NumSlots-1:0]       simple_batch_wb_en;
  logic [NumSlots-1:0][4:0]  simple_batch_rd;
  logic [NumSlots-1:0][XLEN-1:0] simple_batch_result;
  logic [NumSlots-1:0][XLEN-1:0] simple_lane_result;
  logic                      simple_batch_valid;
  logic [31:0]               simple_batch_write_mask;
  logic [31:0]               curr_int_read_mask;
  logic                      complex_simple_raw_stall;
  logic                      complex_prefix_ready;

  // ── Pipelined (non-blocking) scalar load queue ─────────────────────────────
  // The original LSU blocks one load per EP (IDLE->EXECUTE->LSU_AR->LSU_R), so a
  // GEMM iteration's 4 A-loads serialize at full AXI round-trip latency.  This
  // queue lets a single EP issue several load ARs back-to-back (same AXI id => R
  // returns in order) and collect the R responses into FRF/XRF as they arrive,
  // pipelining the round-trips.  The state (repurposed LSU_AR) stays until every
  // outstanding R has drained, so a dependent vfmacc reading the loaded fa (in a
  // later EP, gated by scalar_ep_done) still observes the written value.
  localparam int unsigned LdQDepth = 4;
  localparam int unsigned LdQPtrW  = (LdQDepth > 1) ? $clog2(LdQDepth) : 1;
  localparam int unsigned ByteOffW = $clog2(AxiDataWidth/8);
  logic [LdQDepth-1:0][4:0]          ldq_rd_q, ldq_rd_d;
  logic [LdQDepth-1:0]               ldq_is_fpr_q, ldq_is_fpr_d;
  logic [LdQDepth-1:0][ByteOffW-1:0] ldq_off_q, ldq_off_d;
  logic [LdQDepth-1:0][2:0]          ldq_ext_q, ldq_ext_d;
  logic [LdQPtrW-1:0]                ldq_head_q, ldq_head_d;
  logic [LdQPtrW-1:0]                ldq_tail_q, ldq_tail_d;
  logic [LdQPtrW:0]                  ldq_count_q, ldq_count_d;
  localparam logic [LdQPtrW:0]       LdQDepthC = LdQDepth;
  logic                             ldq_full, ldq_empty;
  logic                             ld_ar_valid, ld_ar_fire, ld_r_fire;
  logic                             ld_req_enter, ld_req_capture;
  logic                             ld_req_valid_d, ld_req_valid_q;
  addr_t                            ld_req_addr_d, ld_req_addr_q;
  logic [1:0]                       ld_req_size_d, ld_req_size_q;
  logic [4:0]                       ld_req_rd_d, ld_req_rd_q;
  logic                             ld_req_is_fpr_d, ld_req_is_fpr_q;
  logic [ByteOffW-1:0]              ld_req_off_d, ld_req_off_q;
  logic [2:0]                       ld_req_ext_d, ld_req_ext_q;
  addr_t                            live_lsu_addr;
  logic [1:0]                       live_lsu_size;
  logic [2:0]                       live_lsu_ext;
  logic                             live_lsu_is_fpr;
  logic                             curr_is_load;
  logic [2:0]                        curr_ld_ext;
  logic [XLEN-1:0]                   ldq_pop_data;
  logic                             ldq_pop_err;

  function automatic logic [XLEN-1:0] ld_extend(input logic [AxiDataWidth-1:0] data,
                                                input logic [ByteOffW-1:0]      off,
                                                input logic [2:0]               ext);
    logic [AxiDataWidth-1:0] raw;
    raw = data >> (8 * off);
    unique case (ext)
      3'd0: ld_extend = {{(XLEN-8){raw[7]}},   raw[7:0]};
      3'd1: ld_extend = {{(XLEN-8){1'b0}},     raw[7:0]};
      3'd2: ld_extend = {{(XLEN-16){raw[15]}}, raw[15:0]};
      3'd3: ld_extend = {{(XLEN-16){1'b0}},    raw[15:0]};
      3'd4: ld_extend = {{(XLEN-32){raw[31]}}, raw[31:0]};
      3'd5: ld_extend = {{(XLEN-32){1'b0}},    raw[31:0]};
      3'd6: ld_extend = {{(XLEN-32){1'b1}},    raw[31:0]};
      default: ld_extend = raw[XLEN-1:0];
    endcase
  endfunction

  function automatic logic addr_is_misaligned(input addr_t addr,
                                               input logic [1:0] size);
    unique case (size)
      2'b11: addr_is_misaligned = |addr[2:0];
      2'b10: addr_is_misaligned = |addr[1:0];
      2'b01: addr_is_misaligned = addr[0];
      default: addr_is_misaligned = 1'b0;
    endcase
  endfunction

  function automatic logic is_local_mul_op(input fu_op operation);
    is_local_mul_op = operation inside {MUL, MULH, MULHU, MULHSU, MULW};
  endfunction

  function automatic logic [XLEN-1:0] sext32(input logic [31:0] value);
    sext32 = {{(XLEN-32){value[31]}}, value};
  endfunction

  function automatic simple_alu_dec_t decode_simple_alu(
    input logic             is_32b,
    input logic [31:0]      insn,
    input addr_t            pc,
    input logic [XLEN-1:0]  rs1_value,
    input logic [XLEN-1:0]  rs2_value
  );
    automatic simple_alu_dec_t dec;
    automatic logic [6:0] opcode;
    automatic logic [2:0] funct3;
    automatic logic [6:0] funct7;
    automatic logic [4:0] rd;
    automatic logic [XLEN-1:0] imm_i;
    automatic logic [XLEN-1:0] imm_u;
    automatic logic [31:0] word_result;

    dec = '0;
    opcode = insn[6:0];
    funct3 = insn[14:12];
    funct7 = insn[31:25];
    rd = insn[11:7];
    imm_i = {{(XLEN-12){insn[31]}}, insn[31:20]};
    imm_u = {{(XLEN-32){insn[31]}}, insn[31:12], 12'b0};
    word_result = '0;

    if (is_32b) begin
      unique case (opcode)
        7'b0110111: begin // LUI
          dec.valid  = 1'b1;
          dec.wb_en  = 1'b1;
          dec.result = imm_u;
        end

        7'b0010111: begin // AUIPC
          dec.valid  = 1'b1;
          dec.wb_en  = 1'b1;
          dec.result = addr_t'(pc + addr_t'(imm_u));
        end

        7'b0010011: begin // OP-IMM
          dec.valid = 1'b1;
          dec.wb_en = 1'b1;
          unique case (funct3)
            3'b000: dec.result = rs1_value + imm_i; // ADDI
            3'b010: dec.result = {{(XLEN-1){1'b0}}, ($signed(rs1_value) < $signed(imm_i))}; // SLTI
            3'b011: dec.result = {{(XLEN-1){1'b0}}, (rs1_value < imm_i)}; // SLTIU
            3'b100: dec.result = rs1_value ^ imm_i; // XORI
            3'b110: dec.result = rs1_value | imm_i; // ORI
            3'b111: dec.result = rs1_value & imm_i; // ANDI
            3'b001: begin // SLLI
              dec.valid  = (funct7 == 7'b0000000);
              dec.result = rs1_value << insn[25:20];
            end
            3'b101: begin
              dec.valid = (funct7 == 7'b0000000) || (funct7 == 7'b0100000);
              if (funct7 == 7'b0100000) begin
                dec.result = XLEN'($signed(rs1_value) >>> insn[25:20]); // SRAI
              end else begin
                dec.result = rs1_value >> insn[25:20]; // SRLI
              end
            end
            default: dec.valid = 1'b0;
          endcase
        end

        7'b0011011: begin // OP-IMM-32
          dec.valid = 1'b1;
          dec.wb_en = 1'b1;
          unique case (funct3)
            3'b000: begin // ADDIW
              word_result = rs1_value[31:0] + imm_i[31:0];
              dec.result = sext32(word_result);
            end
            3'b001: begin // SLLIW
              dec.valid = (insn[31:25] == 7'b0000000);
              word_result = rs1_value[31:0] << insn[24:20];
              dec.result = sext32(word_result);
            end
            3'b101: begin
              dec.valid = (insn[31:25] == 7'b0000000) || (insn[31:25] == 7'b0100000);
              if (insn[31:25] == 7'b0100000) begin
                word_result = $signed(rs1_value[31:0]) >>> insn[24:20]; // SRAIW
              end else begin
                word_result = rs1_value[31:0] >> insn[24:20]; // SRLIW
              end
              dec.result = sext32(word_result);
            end
            default: dec.valid = 1'b0;
          endcase
        end

        7'b0110011: begin // OP
          dec.wb_en = 1'b1;
          unique case (funct3)
            3'b000: begin
              dec.valid = (funct7 == 7'b0000000) || (funct7 == 7'b0100000);
              dec.result = (funct7 == 7'b0100000) ? (rs1_value - rs2_value) :
                                                     (rs1_value + rs2_value); // SUB/ADD
            end
            3'b001: begin
              dec.valid = (funct7 == 7'b0000000);
              dec.result = rs1_value << rs2_value[5:0]; // SLL
            end
            3'b010: begin
              dec.valid = (funct7 == 7'b0000000);
              dec.result = {{(XLEN-1){1'b0}}, ($signed(rs1_value) < $signed(rs2_value))}; // SLT
            end
            3'b011: begin
              dec.valid = (funct7 == 7'b0000000);
              dec.result = {{(XLEN-1){1'b0}}, (rs1_value < rs2_value)}; // SLTU
            end
            3'b100: begin
              dec.valid = (funct7 == 7'b0000000);
              dec.result = rs1_value ^ rs2_value; // XOR
            end
            3'b101: begin
              dec.valid = (funct7 == 7'b0000000) || (funct7 == 7'b0100000);
              dec.result = (funct7 == 7'b0100000) ? XLEN'($signed(rs1_value) >>> rs2_value[5:0]) :
                                                     (rs1_value >> rs2_value[5:0]); // SRA/SRL
            end
            3'b110: begin
              dec.valid = (funct7 == 7'b0000000);
              dec.result = rs1_value | rs2_value; // OR
            end
            3'b111: begin
              dec.valid = (funct7 == 7'b0000000);
              dec.result = rs1_value & rs2_value; // AND
            end
            default: dec.valid = 1'b0;
          endcase
        end

        7'b0111011: begin // OP-32
          dec.wb_en = 1'b1;
          unique case (funct3)
            3'b000: begin // ADDW/SUBW
              dec.valid = (funct7 == 7'b0000000) || (funct7 == 7'b0100000);
              word_result = (funct7 == 7'b0100000) ? (rs1_value[31:0] - rs2_value[31:0]) :
                                                     (rs1_value[31:0] + rs2_value[31:0]);
              dec.result = sext32(word_result);
            end
            3'b001: begin // SLLW
              dec.valid = (funct7 == 7'b0000000);
              word_result = rs1_value[31:0] << rs2_value[4:0];
              dec.result = sext32(word_result);
            end
            3'b101: begin
              dec.valid = (funct7 == 7'b0000000) || (funct7 == 7'b0100000);
              if (funct7 == 7'b0100000) begin
                word_result = $signed(rs1_value[31:0]) >>> rs2_value[4:0]; // SRAW
              end else begin
                word_result = rs1_value[31:0] >> rs2_value[4:0]; // SRLW
              end
              dec.result = sext32(word_result);
            end
            default: dec.valid = 1'b0;
          endcase
        end

        default: dec.valid = 1'b0;
      endcase
    end

    dec.rd = rd;
    if (rd == 5'd0) begin
      dec.wb_en = 1'b0;
    end
    return dec;
  endfunction

  // Keep the simple-lane classifier independent of the 64-bit result datapath.
  // The complex decoder can then select the first intrinsically non-simple slot
  // without waiting for the simple batch's prefix hazard scan to finish.
  function automatic logic simple_alu_encoding_valid(input logic        is_32b,
                                                      input logic [31:0] insn);
    automatic logic [6:0] opcode;
    automatic logic [2:0] funct3;
    automatic logic [6:0] funct7;
    begin
      opcode = insn[6:0];
      funct3 = insn[14:12];
      funct7 = insn[31:25];
      simple_alu_encoding_valid = 1'b0;

      if (is_32b) begin
        unique case (opcode)
          7'b0110111, // LUI
          7'b0010111: // AUIPC
            simple_alu_encoding_valid = 1'b1;

          7'b0010011: begin // OP-IMM
            unique case (funct3)
              3'b000, 3'b010, 3'b011, 3'b100, 3'b110, 3'b111:
                simple_alu_encoding_valid = 1'b1;
              3'b001:
                simple_alu_encoding_valid = (funct7 == 7'b0000000);
              3'b101:
                simple_alu_encoding_valid = (funct7 == 7'b0000000) ||
                                            (funct7 == 7'b0100000);
              default: ;
            endcase
          end

          7'b0011011: begin // OP-IMM-32
            unique case (funct3)
              3'b000:
                simple_alu_encoding_valid = 1'b1;
              3'b001:
                simple_alu_encoding_valid = (funct7 == 7'b0000000);
              3'b101:
                simple_alu_encoding_valid = (funct7 == 7'b0000000) ||
                                            (funct7 == 7'b0100000);
              default: ;
            endcase
          end

          7'b0110011: begin // OP
            unique case (funct3)
              3'b000, 3'b101:
                simple_alu_encoding_valid = (funct7 == 7'b0000000) ||
                                            (funct7 == 7'b0100000);
              3'b001, 3'b010, 3'b011, 3'b100, 3'b110, 3'b111:
                simple_alu_encoding_valid = (funct7 == 7'b0000000);
              default: ;
            endcase
          end

          7'b0111011: begin // OP-32
            unique case (funct3)
              3'b000, 3'b101:
                simple_alu_encoding_valid = (funct7 == 7'b0000000) ||
                                            (funct7 == 7'b0100000);
              3'b001:
                simple_alu_encoding_valid = (funct7 == 7'b0000000);
              default: ;
            endcase
          end

          default: ;
        endcase
      end
    end
  endfunction

  function automatic logic [31:0] simple_alu_read_mask(input logic        is_32b,
                                                       input logic [31:0] insn);
    automatic logic [31:0] mask;
    automatic logic [6:0] opcode;
    begin
      mask = '0;
      opcode = insn[6:0];
      if (is_32b) begin
        unique case (opcode)
          7'b0010011,
          7'b0011011: begin // OP-IMM / OP-IMM-32
            if (insn[19:15] != 5'd0) mask[insn[19:15]] = 1'b1;
          end
          7'b0110011,
          7'b0111011: begin // OP / OP-32
            if (insn[19:15] != 5'd0) mask[insn[19:15]] = 1'b1;
            if (insn[24:20] != 5'd0) mask[insn[24:20]] = 1'b1;
          end
          default: mask = '0; // LUI/AUIPC read no GPRs.
        endcase
      end
      simple_alu_read_mask = mask;
    end
  endfunction

  function automatic logic scalar_opfp_writes_gpr(input logic [31:0] insn);
    begin
      unique case (insn[31:27])
        5'b10100, // FEQ/FLT/FLE
        5'b11000, // FCVT integer <- floating point
        5'b11100: // FMV.X.* / FCLASS
          scalar_opfp_writes_gpr = 1'b1;
        default:
          scalar_opfp_writes_gpr = 1'b0;
      endcase
    end
  endfunction

  function automatic logic scalar_32b_writes_gpr(input logic [31:0] insn);
    automatic logic [6:0] opcode;
    begin
      opcode = insn[6:0];
      unique case (opcode)
        7'b0110111, // LUI
        7'b0010111, // AUIPC
        7'b1101111, // JAL
        7'b1100111, // JALR
        7'b0000011, // LOAD
        7'b0010011, // OP-IMM
        7'b0011011, // OP-IMM-32
        7'b0110011, // OP
        7'b0111011, // OP-32
        7'b0101111, // AMO
        7'b1110011: // SYSTEM/CSR
          scalar_32b_writes_gpr = 1'b1;
        7'b1010011:
          scalar_32b_writes_gpr = scalar_opfp_writes_gpr(insn);
        default:
          scalar_32b_writes_gpr = 1'b0;
      endcase
    end
  endfunction

  function automatic logic [31:0] scalar_write_mask_conservative(input logic        is_32b,
                                                                 input logic [31:0] insn);
    automatic logic [31:0] mask;
    automatic logic [4:0] rd;
    begin
      mask = '0;
      rd = insn[11:7];
      if (!is_32b) begin
        // Do not speculate across an unexpanded compressed instruction.
        mask = 32'hffff_ffff;
      end else if ((rd != 5'd0) && scalar_32b_writes_gpr(insn)) begin
        mask[rd] = 1'b1;
      end
      scalar_write_mask_conservative = mask;
    end
  endfunction

  function automatic logic scalar_order_barrier(input logic        is_32b,
                                                input logic [31:0] insn);
    automatic logic [6:0] opcode;
    begin
      opcode = insn[6:0];
      scalar_order_barrier = !is_32b ||
                             (opcode == 7'b1100011) || // BRANCH
                             (opcode == 7'b1101111) || // JAL
                             (opcode == 7'b1100111) || // JALR
                             (opcode == 7'b0001111) || // FENCE
                             (opcode == 7'b1110011);   // CSR/SYSTEM
    end
  endfunction

  function automatic logic [31:0] pending_gpr_read_mask(input logic        is_32b,
                                                        input logic [31:0] insn);
    automatic logic [31:0] mask;
    automatic logic [6:0] opcode;
    automatic logic [2:0] funct3;
    begin
      mask = '0;
      opcode = insn[6:0];
      funct3 = insn[14:12];
      if (!is_32b) begin
        mask = 32'hffff_ffff;
      end else begin
        unique case (opcode)
          7'b1100111,
          7'b0000011,
          7'b0000111,
          7'b0010011,
          7'b0011011: begin
            if (insn[19:15] != 5'd0) mask[insn[19:15]] = 1'b1;
          end
          7'b1100011,
          7'b0100011,
          7'b0110011,
          7'b0111011,
          7'b0101111: begin
            if (insn[19:15] != 5'd0) mask[insn[19:15]] = 1'b1;
            if (insn[24:20] != 5'd0) mask[insn[24:20]] = 1'b1;
          end
          7'b0100111,
          7'b1010011: begin
            if (insn[19:15] != 5'd0) mask[insn[19:15]] = 1'b1;
          end
          7'b1110011: begin
            if ((funct3 inside {3'b001, 3'b010, 3'b011}) &&
                (insn[19:15] != 5'd0)) begin
              mask[insn[19:15]] = 1'b1;
            end
          end
          default: mask = '0;
        endcase
      end
      pending_gpr_read_mask = mask;
    end
  endfunction

  function automatic logic [31:0] pending_gpr_write_mask(input logic        is_32b,
                                                         input logic [31:0] insn);
    automatic logic [31:0] mask;
    automatic logic [4:0] rd;
    begin
      mask = '0;
      rd = insn[11:7];
      if (!is_32b) begin
        mask = 32'hffff_ffff;
      end else if ((rd != 5'd0) && scalar_32b_writes_gpr(insn)) begin
        mask[rd] = 1'b1;
      end
      pending_gpr_write_mask = mask;
    end
  endfunction

  function automatic logic [31:0] pending_fpr_read_mask(input logic        is_32b,
                                                        input logic [31:0] insn);
    automatic logic [31:0] mask;
    automatic logic [6:0] opcode;
    begin
      mask = '0;
      opcode = insn[6:0];
      if (!is_32b) begin
        mask = 32'hffff_ffff;
      end else begin
        unique case (opcode)
          7'b0100111: mask[insn[24:20]] = 1'b1;
          7'b1010011: begin
            mask[insn[19:15]] = 1'b1;
            mask[insn[24:20]] = 1'b1;
          end
          7'b1000011,
          7'b1000111,
          7'b1001011,
          7'b1001111: begin
            mask[insn[19:15]] = 1'b1;
            mask[insn[24:20]] = 1'b1;
            mask[insn[31:27]] = 1'b1;
          end
          default: mask = '0;
        endcase
      end
      pending_fpr_read_mask = mask;
    end
  endfunction

  function automatic logic [31:0] pending_fpr_write_mask(input logic        is_32b,
                                                         input logic [31:0] insn);
    automatic logic [31:0] mask;
    automatic logic [6:0] opcode;
    automatic logic [2:0] funct3;
    begin
      mask = '0;
      opcode = insn[6:0];
      funct3 = insn[14:12];
      if (!is_32b) begin
        mask = 32'hffff_ffff;
      end else begin
        unique case (opcode)
          7'b0000111: begin
            if (funct3 inside {3'b010, 3'b011}) begin
              mask[insn[11:7]] = 1'b1;
            end
          end
          7'b1010011: begin
            if (!scalar_opfp_writes_gpr(insn)) begin
              mask[insn[11:7]] = 1'b1;
            end
          end
          7'b1000011,
          7'b1000111,
          7'b1001011,
          7'b1001111: mask[insn[11:7]] = 1'b1;
          default: mask = '0;
        endcase
      end
      pending_fpr_write_mask = mask;
    end
  endfunction

  function automatic logic is_releasable_scalar_mem_op(input logic        is_32b,
                                                        input logic [31:0] insn);
    automatic logic [6:0] opcode;
    automatic logic [2:0] funct3;
    begin
      opcode = insn[6:0];
      funct3 = insn[14:12];
      is_releasable_scalar_mem_op = is_32b &&
          ((opcode == 7'b0000011) ||  // integer load
           (opcode == 7'b0100011) ||  // integer store
           (opcode == 7'b0000111 && (funct3 inside {3'b010, 3'b011})) || // FLW/FLD
           (opcode == 7'b0100111 && (funct3 inside {3'b010, 3'b011})));  // FSW/FSD
    end
  endfunction

  function automatic logic is_nonreleasable_scalar_order_op(input logic        is_32b,
                                                             input logic [31:0] insn);
    automatic logic [6:0] opcode;
    begin
      opcode = insn[6:0];
      // Keep compressed instructions and architectural ordering/system
      // operations as EP-wide boundaries. Their completion/exception semantics
      // are intentionally not speculated across by this optimization.
      is_nonreleasable_scalar_order_op = !is_32b ||
          (opcode == 7'b0001111) ||  // FENCE/FENCE.I
          (opcode == 7'b0101111) ||  // AMO
          (opcode == 7'b1110011);    // SYSTEM/CSR
    end
  endfunction

  always_comb begin : p_scalar_mem_order_summary
    scalar_input_has_mem_order = 1'b0;
    scalar_input_has_nonreleasable_order = 1'b0;
    scalar_remaining_releasable_mem = 1'b0;
    scalar_remaining_nonreleasable_order = 1'b0;

    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (scalar_insn_valid_i[i]) begin
        scalar_input_has_mem_order |=
            is_releasable_scalar_mem_op(scalar_insn_is_32b_i[i],
                                        scalar_insn_i[i]) |
            is_nonreleasable_scalar_order_op(scalar_insn_is_32b_i[i],
                                              scalar_insn_i[i]);
        scalar_input_has_nonreleasable_order |=
            is_nonreleasable_scalar_order_op(scalar_insn_is_32b_i[i],
                                              scalar_insn_i[i]);
      end
      if (insn_valid_d[i]) begin
        scalar_remaining_releasable_mem |=
            is_releasable_scalar_mem_op(insn_is_32b_d[i], insn_d[i]);
        scalar_remaining_nonreleasable_order |=
            is_nonreleasable_scalar_order_op(insn_is_32b_d[i], insn_d[i]);
      end
    end

    scalar_mem_inflight_d = ld_req_valid_d || (ldq_count_d != '0) ||
        (state_d inside {LSU_AR, LSU_R, LSU_AW, LSU_W, LSU_B});
  end

  // These are next-state summaries.  HEU registers them into its existing
  // current-EP masks; they never feed its issue gate combinationally.
  assign scalar_pending_gpr_read_mask_o = pending_gpr_read_mask_d;
  assign scalar_pending_gpr_write_mask_o = pending_gpr_write_mask_d;
  assign scalar_pending_fpr_read_mask_o = pending_fpr_read_mask_d;
  assign scalar_pending_fpr_write_mask_o = pending_fpr_write_mask_d;
  assign scalar_mem_order_pending_o = scalar_mem_order_pending_d;

  always_comb begin : p_simple_predecode
    automatic simple_alu_dec_t dec;
    automatic logic [XLEN-1:0] lane_rs1;
    automatic logic [XLEN-1:0] lane_rs2;

    simple_class_valid = '0;
    simple_lane_result = '0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      simple_class_valid[i] = simple_alu_encoding_valid(insn_is_32b_q[i], insn_q[i]);
      lane_rs1 = (insn_q[i][19:15] == 5'd0) ? '0 : xrf_q[insn_q[i][19:15]];
      lane_rs2 = (insn_q[i][24:20] == 5'd0) ? '0 : xrf_q[insn_q[i][24:20]];
      dec = decode_simple_alu(insn_is_32b_q[i], insn_q[i], insn_pc_q[i], lane_rs1, lane_rs2);
      simple_lane_result[i] = dec.result;
    end
  end

  // Select the first intrinsically non-simple instruction independently from
  // the simple batch result and prefix-hazard chain.  complex_prefix_ready below
  // prevents it from being captured until every older valid simple slot was
  // actually consumed, preserving the original in-order semantics.
  always_comb begin : p_find_execute_slot
    curr_slot_found = 1'b0;
    curr_slot_idx   = '0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (insn_valid_q[i] && !simple_class_valid[i] && !curr_slot_found) begin
        curr_slot_found = 1'b1;
        curr_slot_idx   = SlotIdxWidth'(i);
      end
    end
  end

  always_comb begin : p_find_serial_slot
    serial_slot_found = 1'b0;
    serial_slot_idx   = '0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (insn_valid_q[i] && !serial_slot_found) begin
        serial_slot_found = 1'b1;
        serial_slot_idx   = SlotIdxWidth'(i);
      end
    end
  end

  assign curr_insn   = insn_q[curr_slot_idx];
  assign curr_is_32b = insn_is_32b_q[curr_slot_idx];
  assign curr_pc     = insn_pc_q[curr_slot_idx];
  assign curr_cinsn  = curr_insn[15:0];
  assign serial_insn   = insn_q[serial_slot_idx];
  assign serial_is_32b = insn_is_32b_q[serial_slot_idx];

  // Conditional branches dominate the scalar complex-instruction traffic in
  // HDV loops.  Decode them directly from the registered packet so they retain
  // the original one-cycle execution behavior.  Less common complex classes
  // still use the registered CVA6 decode stage below to break the long generic
  // decode/execute path.
  always_comb begin : p_fast_branch
    automatic logic [XLEN-1:0] lhs;
    automatic logic [XLEN-1:0] rhs;
    automatic logic [XLEN-1:0] branch_imm;

    lhs = (curr_insn[19:15] == 5'd0) ? '0 : xrf_q[curr_insn[19:15]];
    rhs = (curr_insn[24:20] == 5'd0) ? '0 : xrf_q[curr_insn[24:20]];
    branch_imm = {{(XLEN-13){curr_insn[31]}}, curr_insn[31], curr_insn[7],
                  curr_insn[30:25], curr_insn[11:8], 1'b0};

    fast_branch_valid = curr_slot_found && curr_is_32b &&
                        (curr_insn[6:0] == 7'b1100011);
    fast_branch_taken = 1'b0;
    unique case (curr_insn[14:12])
      3'b000: fast_branch_taken = (lhs == rhs);                    // BEQ
      3'b001: fast_branch_taken = (lhs != rhs);                    // BNE
      3'b100: fast_branch_taken = ($signed(lhs) < $signed(rhs));   // BLT
      3'b101: fast_branch_taken = ($signed(lhs) >= $signed(rhs));  // BGE
      3'b110: fast_branch_taken = (lhs < rhs);                     // BLTU
      3'b111: fast_branch_taken = (lhs >= rhs);                    // BGEU
      default: fast_branch_valid = 1'b0;
    endcase

    fast_branch_target = fast_branch_taken ? addr_t'(curr_pc + branch_imm) :
                                             addr_t'(curr_pc + XLEN'(4));
    fast_task_exit = curr_slot_found && curr_is_32b &&
                     ((TreatRetAsTaskExit && (curr_insn == 32'h00008067)) ||
                      (TreatEbreakAsTaskExit && (curr_insn == 32'h00100073)));
  end

  always_comb begin : p_simple_batch
    automatic int unsigned issued;
    automatic logic stop_scan;
    automatic logic [31:0] used_rd;
    automatic logic [31:0] prior_read_mask;
    automatic logic [31:0] prior_write_mask;
    automatic logic [31:0] read_mask;
    automatic logic [31:0] write_mask;
    automatic logic lane_vset_hazard_stall;
    automatic logic lane_order_hazard;
    automatic logic lane_wb_en;
    automatic logic [4:0] lane_rd;

    simple_batch_mask   = '0;
    simple_batch_wb_en  = '0;
    simple_batch_rd     = '0;
    simple_batch_result = '0;
    simple_batch_write_mask = '0;
    issued              = 0;
    stop_scan           = 1'b0;
    used_rd             = '0;
    prior_read_mask      = '0;
    prior_write_mask     = '0;

    for (int unsigned i = 0; i < NumSlots; i++) begin
      lane_rd = insn_q[i][11:7];
      lane_wb_en = simple_class_valid[i] && (lane_rd != 5'd0);
      read_mask = simple_alu_read_mask(insn_is_32b_q[i], insn_q[i]);
      write_mask = scalar_write_mask_conservative(insn_is_32b_q[i], insn_q[i]);
      lane_vset_hazard_stall = 1'b0;
      for (int unsigned v = 0; v < 2; v++) begin
        if (vec_vset_inflight_valid_i[v] &&
            (vec_vset_inflight_rd_i[v] != 5'd0)) begin
          lane_vset_hazard_stall |=
              read_mask[vec_vset_inflight_rd_i[v]] ||
              write_mask[vec_vset_inflight_rd_i[v]];
        end
      end
      lane_order_hazard = ((read_mask & prior_write_mask) != 32'b0) ||
                          ((write_mask & prior_write_mask) != 32'b0) ||
                          ((write_mask & prior_read_mask) != 32'b0);

      if (insn_valid_q[i] && !stop_scan) begin
        if ((issued < EffectiveSimpleAluIssueWidth) && simple_class_valid[i] &&
            !lane_vset_hazard_stall &&
            !lane_order_hazard &&
            (!lane_wb_en || !used_rd[lane_rd])) begin
          simple_batch_mask[i]   = 1'b1;
          simple_batch_wb_en[i]  = lane_wb_en;
          simple_batch_rd[i]     = lane_rd;
          simple_batch_result[i] = simple_lane_result[i];
          if (lane_wb_en) begin
            used_rd[lane_rd] = 1'b1;
            simple_batch_write_mask[lane_rd] = 1'b1;
          end
          issued++;
        end else if ((issued >= EffectiveSimpleAluIssueWidth) ||
                     (simple_class_valid[i] && lane_vset_hazard_stall) ||
                     (simple_class_valid[i] && lane_order_hazard) ||
                     (lane_wb_en && used_rd[lane_rd])) begin
          stop_scan = 1'b1;
        end

        prior_read_mask |=
          pending_gpr_read_mask(insn_is_32b_q[i], insn_q[i]);
        prior_write_mask |= write_mask;
        if (!simple_class_valid[i] &&
            scalar_order_barrier(insn_is_32b_q[i], insn_q[i])) begin
          stop_scan = 1'b1;
        end
      end
    end

    simple_batch_valid = |simple_batch_mask;
  end

  always_comb begin : p_complex_prefix_ready
    complex_prefix_ready = curr_slot_found;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      if ((i < curr_slot_idx) && insn_valid_q[i] && !simple_batch_mask[i]) begin
        complex_prefix_ready = 1'b0;
      end
    end
  end

  always_comb begin : p_complex_read_hazard
    curr_int_read_mask = '0;
    if (curr_slot_found) begin
      if (!(CVA6Cfg.FpPresent && ariane_pkg::is_rs1_fpr(cva6_decoded.op)) &&
          !cva6_decoded.use_zimm &&
          (rs1_addr != 5'd0)) begin
        curr_int_read_mask[rs1_addr] = 1'b1;
      end
      if (!(CVA6Cfg.FpPresent && ariane_pkg::is_rs2_fpr(cva6_decoded.op)) &&
          (rs2_addr != 5'd0)) begin
        curr_int_read_mask[rs2_addr] = 1'b1;
      end
    end
    complex_simple_raw_stall = curr_slot_found &&
                               ((curr_int_read_mask & simple_batch_write_mask) != 32'b0);
  end

  compressed_decoder #(
    .CVA6Cfg(CVA6Cfg)
  ) i_compressed_decoder (
    .instr_i          (curr_insn),
    .instr_o          (cva6_dec_instr),
    .illegal_instr_o  (cva6_illegal_compressed),
    .is_macro_instr_o (cva6_is_macro_instr),
    .is_compressed_o  (cva6_is_compressed),
    .is_zcmt_instr_o  (cva6_is_zcmt_instr)
  );

  compressed_decoder #(
    .CVA6Cfg(CVA6Cfg)
  ) i_serial_compressed_decoder (
    .instr_i          (serial_insn),
    .instr_o          (serial_dec_instr),
    .illegal_instr_o  (serial_illegal_compressed),
    .is_macro_instr_o (),
    .is_compressed_o  (),
    .is_zcmt_instr_o  ()
  );

  assign cva6_decoder_instr = curr_is_32b ? curr_insn : cva6_dec_instr;
  assign serial_decoder_instr = serial_is_32b ? serial_insn : serial_dec_instr;

  decoder #(
    .CVA6Cfg(CVA6Cfg),
    .branchpredict_sbe_t(branchpredict_sbe_t),
    .exception_t(exception_t),
    .irq_ctrl_t(irq_ctrl_t),
    .scoreboard_entry_t(scoreboard_entry_t),
    .interrupts_t(interrupts_t),
    .INTERRUPTS(HDV_INTERRUPTS)
  ) i_decoder (
    .debug_req_i                  (1'b0),
    .pc_i                         (curr_pc[CVA6Cfg.VLEN-1:0]),
    .is_compressed_i              (!curr_is_32b && cva6_is_compressed),
    .compressed_instr_i           (curr_cinsn),
    .is_illegal_i                 (!curr_is_32b && cva6_illegal_compressed),
    .instruction_i                (cva6_decoder_instr),
    .is_macro_instr_i             (!curr_is_32b && cva6_is_macro_instr),
    .is_last_macro_instr_i        (1'b0),
    .is_double_rd_macro_instr_i   (1'b0),
    .is_zcmt_i                    (!curr_is_32b && cva6_is_zcmt_instr),
    .jump_address_i               ('0),
    .branch_predict_i             ('0),
    .ex_i                         ('0),
    .irq_i                        (2'b00),
    .irq_ctrl_i                   ('0),
    .clic_mode_i                  (1'b0),
    .clic_irq_req_i               (1'b0),
    .clic_irq_cause_i             ('0),
    .priv_lvl_i                   (riscv::PRIV_LVL_M),
    .v_i                          (1'b0),
    .debug_mode_i                 (1'b0),
    .fs_i                         (riscv::Dirty),
    .vfs_i                        (riscv::Dirty),
    .frm_i                        (3'b000),
    .vs_i                         (riscv::Dirty),
    .tvm_i                        (1'b0),
    .tw_i                         (1'b0),
    .vtw_i                        (1'b0),
    .tsr_i                        (1'b0),
    .hu_i                         (1'b0),
    .instruction_o                (cva6_decoded),
    .orig_instr_o                 (cva6_orig_instr),
    .is_control_flow_instr_o      (cva6_is_control_flow)
  );

  assign rs1_addr = cva6_decoded.rs1;
  assign rs2_addr = cva6_decoded.rs2;

  // Stall integer RAW and WAW conflicts against an older in-flight vset VL
  // writeback. FP-source reads target the FRF and are excluded.
  logic vset_gpr_hazard_stall;
  always_comb begin : p_vset_gpr_hazard_stall
    automatic logic [31:0] curr_write_mask;

    curr_write_mask = curr_slot_found
                    ? scalar_write_mask_conservative(curr_is_32b, curr_insn)
                    : '0;
    vset_gpr_hazard_stall = 1'b0;
    for (int unsigned v = 0; v < 2; v++) begin
      if (vec_vset_inflight_valid_i[v] &&
          (vec_vset_inflight_rd_i[v] != 5'd0) &&
          curr_slot_found) begin
        vset_gpr_hazard_stall |=
          (!(CVA6Cfg.FpPresent && ariane_pkg::is_rs1_fpr(cva6_decoded.op)) &&
           (rs1_addr == vec_vset_inflight_rd_i[v])) ||
          (!(CVA6Cfg.FpPresent && ariane_pkg::is_rs2_fpr(cva6_decoded.op)) &&
           (rs2_addr == vec_vset_inflight_rd_i[v])) ||
          curr_write_mask[vec_vset_inflight_rd_i[v]];
      end
    end
  end
  assign rs1_data = (rs1_addr == 5'd0) ? '0 : xrf_q[rs1_addr];
  assign rs2_data = (rs2_addr == 5'd0) ? '0 : xrf_q[rs2_addr];
  assign rs3_data = frf_q[cva6_decoded.result[4:0]];

  always_comb begin : p_cva6_fu_data
    cva6_operand_a = (CVA6Cfg.FpPresent && ariane_pkg::is_rs1_fpr(cva6_decoded.op)) ?
                     frf_q[rs1_addr] : rs1_data;
    cva6_operand_b = (CVA6Cfg.FpPresent && ariane_pkg::is_rs2_fpr(cva6_decoded.op)) ?
                     frf_q[rs2_addr] : rs2_data;

    if (cva6_decoded.use_pc) begin
      cva6_operand_a = {{(XLEN-CVA6Cfg.VLEN){cva6_decoded.pc[CVA6Cfg.VLEN-1]}},
                        cva6_decoded.pc};
    end

    if (cva6_decoded.use_zimm) begin
      cva6_operand_a = {{(XLEN-5){1'b0}}, cva6_decoded.rs1};
    end

    if (cva6_decoded.use_imm &&
        (cva6_decoded.fu != STORE) &&
        (cva6_decoded.fu != CTRL_FLOW) &&
        (cva6_decoded.fu != ACCEL)) begin
      cva6_operand_b = cva6_decoded.result;
    end

    cva6_fu_data.fu        = cva6_decoded.fu;
    cva6_fu_data.operation = cva6_decoded.op;
    cva6_fu_data.operand_a = cva6_operand_a;
    cva6_fu_data.operand_b = cva6_operand_b;
    cva6_fu_data.imm       = (CVA6Cfg.FpPresent && ariane_pkg::is_imm_fpr(cva6_decoded.op)) ?
                             rs3_data : cva6_decoded.result;
    cva6_fu_data.trans_id  = cva6_decoded.trans_id;
  end

  // Decode and register-file access are separate pipeline stages.  The full
  // CVA6 decoder feeds issue_decoded_q first; this block then reads the scalar
  // register files and builds the execution-unit payload in COMPLEX_ISSUE.
  always_comb begin : p_issue_operands
    issue_operand_a = (CVA6Cfg.FpPresent &&
                       ariane_pkg::is_rs1_fpr(issue_decoded_q.op)) ?
                      frf_q[issue_decoded_q.rs1] :
                      ((issue_decoded_q.rs1 == 5'd0) ? '0 :
                       xrf_q[issue_decoded_q.rs1]);
    issue_operand_b = (CVA6Cfg.FpPresent &&
                       ariane_pkg::is_rs2_fpr(issue_decoded_q.op)) ?
                      frf_q[issue_decoded_q.rs2] :
                      ((issue_decoded_q.rs2 == 5'd0) ? '0 :
                       xrf_q[issue_decoded_q.rs2]);
    issue_operand_c = frf_q[issue_decoded_q.result[4:0]];

    if (issue_decoded_q.use_pc) begin
      issue_operand_a =
          {{(XLEN-CVA6Cfg.VLEN){issue_decoded_q.pc[CVA6Cfg.VLEN-1]}},
           issue_decoded_q.pc};
    end
    if (issue_decoded_q.use_zimm) begin
      issue_operand_a = {{(XLEN-5){1'b0}}, issue_decoded_q.rs1};
    end
    if (issue_decoded_q.use_imm &&
        (issue_decoded_q.fu != STORE) &&
        (issue_decoded_q.fu != CTRL_FLOW) &&
        (issue_decoded_q.fu != ACCEL)) begin
      issue_operand_b = issue_decoded_q.result;
    end

    issue_operand_fu_data.fu        = issue_decoded_q.fu;
    issue_operand_fu_data.operation = issue_decoded_q.op;
    issue_operand_fu_data.operand_a = issue_operand_a;
    issue_operand_fu_data.operand_b = issue_operand_b;
    issue_operand_fu_data.imm       =
        (CVA6Cfg.FpPresent && ariane_pkg::is_imm_fpr(issue_decoded_q.op)) ?
        issue_operand_c : issue_decoded_q.result;
    issue_operand_fu_data.trans_id  = issue_decoded_q.trans_id;
  end

  // Execution units consume only registered issue context.  Live slot decode
  // is used exclusively to classify and capture a candidate in EXECUTE; it has
  // no combinational path into ALU/branch/CSR results or redirect generation.
  assign exec_slot_found    = issue_valid_q;
  assign exec_pc            = issue_pc_q;
  assign exec_decoder_instr = issue_decoder_instr_q;
  assign exec_decoded       = issue_decoded_q;
  assign exec_fu_data       = issue_fu_data_q;

  // The CVA6 serial divider deasserts ready combinationally when valid rises.
  // Qualify the request with ready sampled in the preceding issue stage so
  // valid never depends on the current ready value and is emitted for one cycle.
  assign scalar_mult_issue = (state_q == COMPLEX_EXEC) && issue_valid_q &&
                             (issue_decoded_q.fu == MULT) &&
                             !issue_decoded_q.ex.valid && issue_mult_ready_q;
  assign local_mul_issue = scalar_mult_issue &&
                           is_local_mul_op(issue_decoded_q.op);
  assign cva6_mult_issue = scalar_mult_issue &&
                           !is_local_mul_op(issue_decoded_q.op);
  assign scalar_mult_valid = local_mul_valid | cva6_mult_valid;
  assign scalar_mult_result = local_mul_valid ? local_mul_result :
                                                cva6_mult_result;

  always_comb begin : p_local_mul_partial_products
    automatic logic sign_a;
    automatic logic sign_b;
    automatic logic [MulHalfW-1:0] a_lo;
    automatic logic [MulHalfW-1:0] b_lo;
    automatic logic signed [MulHalfW:0] a_hi;
    automatic logic signed [MulHalfW:0] b_hi;
    automatic logic signed [MulAccumW-1:0] term_ll;
    automatic logic signed [MulAccumW-1:0] term_hl;
    automatic logic signed [MulAccumW-1:0] term_lh;
    automatic logic signed [MulAccumW-1:0] term_hh;

    sign_a = issue_fu_data_q.operation inside {MULH, MULHSU};
    sign_b = issue_fu_data_q.operation == MULH;
    a_lo = issue_fu_data_q.operand_a[MulHalfW-1:0];
    b_lo = issue_fu_data_q.operand_b[MulHalfW-1:0];
    a_hi = $signed({sign_a & issue_fu_data_q.operand_a[XLEN-1],
                    issue_fu_data_q.operand_a[XLEN-1:MulHalfW]});
    b_hi = $signed({sign_b & issue_fu_data_q.operand_b[XLEN-1],
                    issue_fu_data_q.operand_b[XLEN-1:MulHalfW]});

    local_mul_ll_d = a_lo * b_lo;
    local_mul_hl_d = a_hi * $signed({1'b0, b_lo});
    local_mul_lh_d = $signed({1'b0, a_lo}) * b_hi;
    local_mul_hh_d = a_hi * b_hi;

    term_ll = $signed({{(MulAccumW-XLEN){1'b0}}, local_mul_ll_q});
    term_hl = $signed({{(MulAccumW-MulCrossW){local_mul_hl_q[MulCrossW-1]}},
                       local_mul_hl_q}) <<< MulHalfW;
    term_lh = $signed({{(MulAccumW-MulCrossW){local_mul_lh_q[MulCrossW-1]}},
                       local_mul_lh_q}) <<< MulHalfW;
    term_hh = $signed({{(MulAccumW-MulCrossW){local_mul_hh_q[MulCrossW-1]}},
                       local_mul_hh_q}) <<< XLEN;

    local_mul_pair_lo_d = term_ll + term_hl;
    local_mul_pair_hi_d = term_lh + term_hh;
    local_mul_product = local_mul_pair_lo_q + local_mul_pair_hi_q;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_local_mul_pipeline
    if (!rst_ni) begin
      local_mul_s1_valid_q <= 1'b0;
      local_mul_s2_valid_q <= 1'b0;
      local_mul_valid      <= 1'b0;
      local_mul_s1_op_q    <= MUL;
      local_mul_s2_op_q    <= MUL;
      local_mul_ll_q       <= '0;
      local_mul_hl_q       <= '0;
      local_mul_lh_q       <= '0;
      local_mul_hh_q       <= '0;
      local_mul_pair_lo_q  <= '0;
      local_mul_pair_hi_q  <= '0;
      local_mul_result     <= '0;
    end else if (flush_i) begin
      local_mul_s1_valid_q <= 1'b0;
      local_mul_s2_valid_q <= 1'b0;
      local_mul_valid      <= 1'b0;
    end else begin
      local_mul_s1_valid_q <= local_mul_issue;
      local_mul_s2_valid_q <= local_mul_s1_valid_q;
      local_mul_valid      <= local_mul_s2_valid_q;

      if (local_mul_issue) begin
        local_mul_s1_op_q <= issue_fu_data_q.operation;
        local_mul_ll_q    <= local_mul_ll_d;
        local_mul_hl_q    <= local_mul_hl_d;
        local_mul_lh_q    <= local_mul_lh_d;
        local_mul_hh_q    <= local_mul_hh_d;
      end
      if (local_mul_s1_valid_q) begin
        local_mul_s2_op_q   <= local_mul_s1_op_q;
        local_mul_pair_lo_q <= local_mul_pair_lo_d;
        local_mul_pair_hi_q <= local_mul_pair_hi_d;
      end
      if (local_mul_s2_valid_q) begin
        unique case (local_mul_s2_op_q)
          MULH, MULHU, MULHSU:
            local_mul_result <= local_mul_product[2*XLEN-1:XLEN];
          MULW:
            local_mul_result <=
                {{(XLEN-32){local_mul_product[31]}}, local_mul_product[31:0]};
          default:
            local_mul_result <= local_mul_product[XLEN-1:0];
        endcase
      end
    end
  end

  alu #(
    .CVA6Cfg(CVA6Cfg),
    .HasBranch(1'b1),
    .fu_data_t(fu_data_t)
  ) i_alu (
    .clk_i              (clk_i),
    .rst_ni             (rst_ni),
    .fu_data_i          (exec_fu_data),
    .result_o           (cva6_alu_result),
    .alu_branch_res_o   (cva6_alu_branch_res)
  );

  branch_unit #(
    .CVA6Cfg(CVA6Cfg),
    .bp_resolve_t(bp_resolve_t),
    .branchpredict_sbe_t(branchpredict_sbe_t),
    .exception_t(exception_t),
    .fu_data_t(fu_data_t)
  ) i_branch_unit (
    .clk_i                    (clk_i),
    .rst_ni                   (rst_ni),
    .v_i                      (1'b0),
    .debug_mode_i             (1'b0),
    .fu_data_i                (exec_fu_data),
    .pc_i                     (exec_decoded.pc),
    .is_zcmt_i                (exec_decoded.is_zcmt),
    .is_compressed_instr_i    (exec_decoded.is_compressed),
    .branch_valid_i           ((state_q == COMPLEX_EXEC) && issue_valid_q &&
                               (issue_decoded_q.fu == CTRL_FLOW)),
    .branch_comp_res_i        (cva6_alu_branch_res),
    .branch_result_o          (cva6_branch_result),
    .branch_predict_i         (exec_decoded.bp),
    .resolved_branch_o        (cva6_resolved_branch),
    .resolve_branch_o         (cva6_resolve_branch),
    .branch_exception_o       (cva6_branch_exception)
  );

  if (CVA6Cfg.RVB) begin : gen_cva6_clmul_div
    mult #(
      .CVA6Cfg(CVA6Cfg),
      .fu_data_t(fu_data_t)
    ) i_mult (
      .clk_i           (clk_i),
      .rst_ni          (rst_ni),
      .flush_i         (flush_i),
      .fu_data_i       (issue_fu_data_q),
      .mult_valid_i    (cva6_mult_issue),
      .result_o        (cva6_mult_result),
      .mult_valid_o    (cva6_mult_valid),
      .mult_ready_o    (cva6_mult_ready),
      .mult_trans_id_o (cva6_mult_trans_id)
    );
  end else begin : gen_cva6_div_only
    logic [XLEN-1:0] div_operand_a;
    logic [XLEN-1:0] div_operand_b;
    logic [XLEN-1:0] div_result;
    logic            div_signed;
    logic            div_remainder;
    logic            div_word_op;
    logic            div_word_op_q;

    assign div_signed = issue_fu_data_q.operation inside {DIV, DIVW, REM, REMW};
    assign div_remainder =
        issue_fu_data_q.operation inside {REM, REMU, REMW, REMUW};
    assign div_word_op =
        CVA6Cfg.IS_XLEN64 &&
        (issue_fu_data_q.operation inside {DIVW, DIVUW, REMW, REMUW});

    always_comb begin
      div_operand_a = issue_fu_data_q.operand_a;
      div_operand_b = issue_fu_data_q.operand_b;
      if (div_word_op) begin
        if (div_signed) begin
          div_operand_a = sext32to64(issue_fu_data_q.operand_a[31:0]);
          div_operand_b = sext32to64(issue_fu_data_q.operand_b[31:0]);
        end else begin
          div_operand_a = {{(XLEN-32){1'b0}}, issue_fu_data_q.operand_a[31:0]};
          div_operand_b = {{(XLEN-32){1'b0}}, issue_fu_data_q.operand_b[31:0]};
        end
      end
    end

    serdiv #(
      .CVA6Cfg(CVA6Cfg),
      .WIDTH  (XLEN)
    ) i_div (
      .clk_i    (clk_i),
      .rst_ni   (rst_ni),
      .id_i     (issue_fu_data_q.trans_id),
      .op_a_i   (div_operand_a),
      .op_b_i   (div_operand_b),
      .opcode_i ({div_remainder, div_signed}),
      .in_vld_i (cva6_mult_issue),
      .in_rdy_o (cva6_mult_ready),
      .flush_i  (flush_i),
      .out_vld_o(cva6_mult_valid),
      .out_rdy_i(1'b1),
      .id_o     (cva6_mult_trans_id),
      .res_o    (div_result)
    );

    assign cva6_mult_result =
        (CVA6Cfg.IS_XLEN64 && div_word_op_q) ?
        sext32to64(div_result[31:0]) : div_result;

    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        div_word_op_q <= 1'b0;
      end else if (flush_i) begin
        div_word_op_q <= 1'b0;
      end else if (cva6_mult_issue) begin
        div_word_op_q <= div_word_op;
      end
    end
  end

  fpu_wrap #(
    .CVA6Cfg(CVA6Cfg),
    .exception_t(exception_t),
    .fu_data_t(fu_data_t)
  ) i_fpu_wrap (
    .clk_i          (clk_i),
    .rst_ni         (rst_ni),
    .flush_i        (flush_i),
    .fpu_valid_i    ((state_q == COMPLEX_EXEC) && issue_valid_q && fpu_issue),
    .fpu_ready_o    (cva6_fpu_ready),
    .fu_data_i      (issue_fu_data_q),
    .fpu_fmt_i      (issue_decoder_instr_q[26:25]),
    .fpu_rm_i       (issue_decoder_instr_q[14:12]),
    .fpu_frm_i      (csr_frm_q),
    .fpu_prec_i     ('0),
    .fpu_trans_id_o (cva6_fpu_trans_id),
    .result_o       (cva6_fpu_result),
    .fpu_valid_o    (cva6_fpu_valid),
    .fpu_exception_o(cva6_fpu_exception)
  );

  always_comb begin : p_execute_decode
    wb_en           = 1'b0;
    wb_is_fpr       = 1'b0;
    wb_addr         = exec_decoded.rd;
    wb_data         = '0;
    unsupported     = 1'b0;
    branch_resolved = 1'b0;
    branch_taken    = 1'b0;
    branch_target   = '0;
    branch_backward = 1'b0;
    fpu_issue       = 1'b0;
    fpu_writes_fpr  = 1'b0;
    fpu_writes_xrf  = 1'b0;
    hdv_task_ret    = 1'b0;
    hdv_task_ebreak = 1'b0;

    if (exec_slot_found) begin
      unsupported = exec_decoded.ex.valid;
      hdv_task_ret = TreatRetAsTaskExit &&
                     (exec_decoder_instr == 32'h00008067);
      hdv_task_ebreak = TreatEbreakAsTaskExit &&
                        (exec_decoder_instr == 32'h00100073);

      // FENCE / FENCE.I (opcode 0x0F): architecturally a NOP in a single-core
      // in-order HDV system.  Treat as no-op to avoid spurious unsupported errors.
      // VLIWPU already classifies FENCE as HDV_INST_SYSTEM (hard EP boundary).
      if (exec_decoder_instr[6:0] == 7'b0001111) begin
        wb_en          = 1'b0;
        unsupported    = 1'b0;
        branch_resolved = 1'b0;
      end else begin

      unique case (exec_decoded.fu)
        ALU: begin
          wb_en   = !unsupported;
          wb_data = cva6_alu_result;
        end

        CTRL_FLOW: begin
          branch_resolved = cva6_resolve_branch && !cva6_branch_exception.valid &&
                            !unsupported && !hdv_task_ret;
          branch_taken    = cva6_resolved_branch.is_taken;
          branch_target   = addr_t'(cva6_resolved_branch.target_address);
          // "backward" must be a property of the branch instruction itself, not
          // of the resolved direction.  For a conditional branch the CVA6 unit
          // reports target_address as the FALL-THROUGH PC when NOT taken, which
          // would hide a backward (loop back-edge) target and break loop-exit
          // signalling (scalar_loop_exit = !taken && backward).  Derive backward
          // from the B-type immediate sign (insn[31] = imm[12]) for conditional
          // branches; keep the target-vs-pc test for jumps (always taken).
          branch_backward = branch_resolved &&
                            (ariane_pkg::op_is_branch(exec_decoded.op)
                               ? exec_decoder_instr[31]
                               : (addr_t'(cva6_resolved_branch.target_address) < exec_pc));
          wb_en           = branch_resolved && (exec_decoded.rd != 5'd0) &&
                            !ariane_pkg::op_is_branch(exec_decoded.op);
          wb_data         = {{(XLEN-CVA6Cfg.VLEN){cva6_branch_result[CVA6Cfg.VLEN-1]}},
                             cva6_branch_result};
          unsupported     = unsupported || (cva6_branch_exception.valid && !hdv_task_ret);
        end

        CSR: begin
          if (csr_supported) begin
            wb_en   = !unsupported;
            wb_data = csr_rdata;
          end else if (exec_decoder_instr == 32'h00000013 ||
                       exec_decoder_instr == 32'h00100073) begin
            wb_en = 1'b0;
          end else begin
            unsupported = 1'b1;
          end
        end

        FPU: begin
          fpu_issue      = !unsupported;
          fpu_writes_fpr = ariane_pkg::is_rd_fpr(exec_decoded.op);
          fpu_writes_xrf = !fpu_writes_fpr && (exec_decoded.rd != 5'd0);
        end

        FPU_VEC,
        CVXIF,
        ACCEL,
        AES: begin
          unsupported = 1'b1;
        end

        LOAD,
        STORE: begin
          unsupported = exec_decoded.ex.valid || issue_lsu_misaligned;
        end

        MULT: begin
          unsupported = exec_decoded.ex.valid;
        end

        NONE: begin
          unsupported = (exec_decoder_instr != 32'h00000013);
        end

        default: begin
          unsupported = 1'b1;
        end
      endcase
      end // closes: else begin (not FENCE)
    end // closes: if (curr_slot_found)
  end // closes: always_comb p_execute_decode

  assign scalar_ready_o         = (state_q == IDLE);
  assign scalar_ep_done_o      = (state_q == DONE);
  assign scalar_error_o         = (state_q == DONE) && error_seen_q;
  assign redirect_valid_o       = (state_q == REDIRECT) && redirect_pending_q;
  assign redirect_pc_o          = redirect_pc_q;
  assign branch_resolved_valid_o = branch_resolved_pulse_q;
  assign branch_taken_o         = branch_taken_q;
  assign branch_pc_o            = branch_pc_q;
  assign branch_target_o        = branch_target_q;
  assign branch_backward_o      = branch_backward_q;
  assign task_complete_o        = (state_q == DONE) && task_complete_pending_q &&
                                  !error_seen_q;


  assign vec_operand_req_ready_o = 1'b1;
  assign vec_rs1_data_o          = (vec_rs1_addr_i == 5'd0) ? '0 : xrf_q[vec_rs1_addr_i];
  assign vec_rs2_data_o          = (vec_rs2_addr_i == 5'd0) ? '0 : xrf_q[vec_rs2_addr_i];
  assign vec_frs1_data_o         = frf_q[vec_frs1_addr_i];
  assign scalar_axi_req_o        = scalar_axi_req;

  always_comb begin : p_csr_stub
    csr_addr      = exec_decoder_instr[31:20];
    csr_op_supported = 1'b0;
    csr_addr_supported = 1'b0;
    csr_supported = 1'b0;
    csr_write     = 1'b0;
    csr_rdata     = '0;
    csr_wdata     = exec_fu_data.operand_a;
    csr_wmask     = exec_fu_data.operand_a;

    unique case (exec_decoder_instr[14:12])
      riscv::CSRRW: begin
        csr_op_supported = 1'b1;
        csr_write     = 1'b1;
        csr_wdata     = exec_fu_data.operand_a;
      end
      riscv::CSRRS: begin
        csr_op_supported = 1'b1;
        csr_write     = (exec_decoded.rs1 != 5'd0);
      end
      riscv::CSRRC: begin
        csr_op_supported = 1'b1;
        csr_write     = (exec_decoded.rs1 != 5'd0);
      end
      riscv::CSRRWI: begin
        csr_op_supported = 1'b1;
        csr_write     = 1'b1;
        csr_wdata     = {{(XLEN-5){1'b0}}, exec_decoded.rs1};
        csr_wmask     = csr_wdata;
      end
      riscv::CSRRSI: begin
        csr_op_supported = 1'b1;
        csr_write     = (exec_decoded.rs1 != 5'd0);
        csr_wmask     = {{(XLEN-5){1'b0}}, exec_decoded.rs1};
      end
      riscv::CSRRCI: begin
        csr_op_supported = 1'b1;
        csr_write     = (exec_decoded.rs1 != 5'd0);
        csr_wmask     = {{(XLEN-5){1'b0}}, exec_decoded.rs1};
      end
      default: csr_op_supported = 1'b0;
    endcase

    unique case (csr_addr)
      riscv::CSR_CYCLE,
      riscv::CSR_TIME,
      riscv::CSR_INSTRET: begin
        csr_addr_supported = 1'b1;
        csr_rdata = {{(XLEN-64){1'b0}}, cycle_q};
      end
      riscv::CSR_FRM: begin
        csr_addr_supported = 1'b1;
        csr_rdata = {{(XLEN-3){1'b0}}, csr_frm_q};
      end
      riscv::CSR_FFLAGS: begin
        csr_addr_supported = 1'b1;
        csr_rdata = '0;
      end
      riscv::CSR_FCSR: begin
        csr_addr_supported = 1'b1;
        csr_rdata = {{(XLEN-8){1'b0}}, csr_frm_q, 5'b0};
      end
      riscv::CSR_VL: begin
        csr_addr_supported = 1'b1;
        csr_rdata = csr_vl_q;
      end
      riscv::CSR_VTYPE: begin
        csr_addr_supported = 1'b1;
        csr_rdata = csr_vtype_q;
      end
      riscv::CSR_VLENB: begin
        csr_addr_supported = 1'b1;
        csr_rdata = XLEN'(VectorVlenBytes);
      end
      default: begin
        csr_addr_supported = 1'b0;
        csr_rdata = '0;
      end
    endcase

    csr_supported = csr_op_supported && csr_addr_supported;
  end

  // The live candidate alignment check is used only while deciding whether an
  // instruction can enter the LSU.  Once in an LSU state, request generation
  // is driven exclusively by the oldest valid serial slot below.
  always_comb begin : p_live_lsu_alignment
    automatic addr_t live_addr;
    automatic addr_t issued_addr;
    automatic logic [1:0] live_size;
    automatic logic [1:0] issued_size;

    live_addr = addr_t'(cva6_fu_data.operand_a + cva6_fu_data.imm);
    live_size = ariane_pkg::extract_transfer_size(cva6_decoded.op);
    live_lsu_addr = live_addr;
    live_lsu_size = live_size;
    live_lsu_is_fpr =
        cva6_decoded.op inside {FLD, FLW, FLH, FLB, FSD, FSW, FSH, FSB};
    unique case (cva6_decoded.op)
      LB:      live_lsu_ext = 3'd0;
      LBU:     live_lsu_ext = 3'd1;
      LH:      live_lsu_ext = 3'd2;
      LHU:     live_lsu_ext = 3'd3;
      LW:      live_lsu_ext = 3'd4;
      LWU:     live_lsu_ext = 3'd5;
      FLW:     live_lsu_ext = 3'd6;
      default: live_lsu_ext = 3'd7;
    endcase
    live_lsu_misaligned = curr_slot_found &&
                          (cva6_decoded.fu inside {LOAD, STORE}) &&
                          addr_is_misaligned(live_addr, live_size);

    issued_addr = addr_t'(issue_fu_data_q.operand_a + issue_fu_data_q.imm);
    issued_size = ariane_pkg::extract_transfer_size(issue_decoded_q.op);
    issue_lsu_misaligned = issue_valid_q &&
                           (issue_decoded_q.fu inside {LOAD, STORE}) &&
                           addr_is_misaligned(issued_addr, issued_size);
  end

  always_comb begin : p_serial_lsu_decode
    automatic logic [6:0] opcode;
    automatic logic [2:0] funct3;
    automatic logic [XLEN-1:0] imm;
    automatic logic [XLEN-1:0] base_operand;
    automatic logic [XLEN-1:0] store_operand;
    automatic int unsigned byte_offset;
    automatic int unsigned transfer_bytes;

    opcode = serial_decoder_instr[6:0];
    funct3 = serial_decoder_instr[14:12];
    serial_lsu_rd  = serial_decoder_instr[11:7];
    serial_lsu_rs2 = serial_decoder_instr[24:20];
    serial_lsu_encoding_valid = 1'b0;
    unique case (opcode)
      7'b0000011: serial_lsu_encoding_valid = funct3 != 3'b111;
      7'b0100011: serial_lsu_encoding_valid = funct3 inside {
          3'b000, 3'b001, 3'b010, 3'b011
        };
      // CVA6 defines byte/half/single/double scalar FP memory operations.
      7'b0000111,
      7'b0100111: serial_lsu_encoding_valid = funct3 inside {
          3'b000, 3'b001, 3'b010, 3'b011
        };
      default: serial_lsu_encoding_valid = 1'b0;
    endcase
    lsu_is_load = serial_slot_found &&
                  (opcode inside {7'b0000011, 7'b0000111});
    lsu_is_fp = opcode inside {7'b0000111, 7'b0100111};
    serial_lsu_supported = serial_slot_found &&
        serial_lsu_encoding_valid &&
        (serial_is_32b || !serial_illegal_compressed);

    if (opcode inside {7'b0000011, 7'b0000111}) begin
      imm = {{(XLEN-12){serial_decoder_instr[31]}}, serial_decoder_instr[31:20]};
    end else begin
      imm = {{(XLEN-12){serial_decoder_instr[31]}},
             serial_decoder_instr[31:25], serial_decoder_instr[11:7]};
    end
    base_operand = (serial_decoder_instr[19:15] == 5'd0) ? '0 :
                   xrf_q[serial_decoder_instr[19:15]];
    lsu_addr = addr_t'(base_operand + imm);

    unique case (funct3)
      3'b000, 3'b100: lsu_size = 2'b00;
      3'b001, 3'b101: lsu_size = 2'b01;
      3'b010, 3'b110: lsu_size = 2'b10;
      default:        lsu_size = 2'b11;
    endcase
    lsu_misaligned = serial_lsu_supported && addr_is_misaligned(lsu_addr, lsu_size);

    if (opcode == 7'b0000111) begin
      curr_ld_ext = (funct3 == 3'b010) ? 3'd6 : 3'd7;
    end else begin
      unique case (funct3)
        3'b000: curr_ld_ext = 3'd0;
        3'b100: curr_ld_ext = 3'd1;
        3'b001: curr_ld_ext = 3'd2;
        3'b101: curr_ld_ext = 3'd3;
        3'b010: curr_ld_ext = 3'd4;
        3'b110: curr_ld_ext = 3'd5;
        default: curr_ld_ext = 3'd7;
      endcase
    end

    byte_offset = lsu_addr[ByteOffW-1:0];
    transfer_bytes = 1 << lsu_size;
    store_operand = lsu_is_fp ? frf_q[serial_lsu_rs2] :
                    ((serial_lsu_rs2 == 5'd0) ? '0 : xrf_q[serial_lsu_rs2]);
    lsu_store_strb = (({(AxiDataWidth/8){1'b0}} |
                       ((1 << transfer_bytes) - 1)) << byte_offset);
    lsu_store_data = AxiDataWidth'(store_operand) << (8 * byte_offset);
    lsu_load_data = ld_extend(scalar_axi_resp_i.r.data,
                              lsu_addr[ByteOffW-1:0], curr_ld_ext);

    lsu_resp_error = 1'b0;
    if (state_q == LSU_R) begin
      lsu_resp_error = scalar_axi_resp_i.r.resp != axi_pkg::RESP_OKAY;
    end else if (state_q == LSU_B) begin
      lsu_resp_error = scalar_axi_resp_i.b.resp != axi_pkg::RESP_OKAY;
    end
  end

  always_comb begin : p_ldq_ctrl
    serial_load_base_raw = 1'b0;
    for (int unsigned i = 0; i < LdQDepth; i++) begin
      if ((i < ldq_count_q) &&
          !ldq_is_fpr_q[ldq_head_q + LdQPtrW'(i)] &&
          (ldq_rd_q[ldq_head_q + LdQPtrW'(i)] != 5'd0) &&
          (serial_decoder_instr[19:15] ==
           ldq_rd_q[ldq_head_q + LdQPtrW'(i)])) begin
        serial_load_base_raw = 1'b1;
      end
    end
    curr_is_load = serial_lsu_supported && lsu_is_load && !lsu_misaligned &&
                   !serial_load_base_raw;
    ldq_full     = (ldq_count_q == LdQDepthC);
    ldq_empty    = (ldq_count_q == '0);
    ld_req_enter = (state_q == EXECUTE) && curr_slot_found &&
                   complex_prefix_ready && !vset_gpr_hazard_stall &&
                   !complex_simple_raw_stall &&
                   (cva6_decoded.fu == LOAD) && !cva6_decoded.ex.valid &&
                   !live_lsu_misaligned && !vec_store_inflight_i && !flush_i;
    ld_ar_valid  = (state_q == LSU_AR) && ld_req_valid_q &&
                   !vec_store_inflight_i && !ldq_full;
    ld_ar_fire   = ld_ar_valid && scalar_axi_resp_i.ar_ready && !flush_i;
    ld_r_fire    = (state_q == LSU_AR) && !ldq_empty && scalar_axi_resp_i.r_valid && !flush_i;
    ld_req_capture = ld_req_enter ||
                     ((state_q == LSU_AR) && (!ld_req_valid_q || ld_ar_fire) &&
                      curr_is_load && !vec_store_inflight_i && !flush_i);
    ldq_pop_data = ld_extend(scalar_axi_resp_i.r.data, ldq_off_q[ldq_head_q], ldq_ext_q[ldq_head_q]);
    ldq_pop_err  = ld_r_fire && (scalar_axi_resp_i.r.resp != axi_pkg::RESP_OKAY);
  end

  // Register the decoded load request before it reaches the shared AXI
  // interconnect.  On a handshake the next load can replace the current entry
  // in the same edge, preserving one request per cycle after the initial fill.
  always_comb begin : p_ld_req_update
    ld_req_valid_d = ld_req_valid_q;
    ld_req_addr_d = ld_req_addr_q;
    ld_req_size_d = ld_req_size_q;
    ld_req_rd_d = ld_req_rd_q;
    ld_req_is_fpr_d = ld_req_is_fpr_q;
    ld_req_off_d = ld_req_off_q;
    ld_req_ext_d = ld_req_ext_q;

    if (ld_ar_fire) begin
      ld_req_valid_d = 1'b0;
    end
    if (ld_req_enter) begin
      ld_req_valid_d = 1'b1;
      ld_req_addr_d = live_lsu_addr;
      ld_req_size_d = live_lsu_size;
      ld_req_rd_d = cva6_decoded.rd;
      ld_req_is_fpr_d = live_lsu_is_fpr;
      ld_req_off_d = live_lsu_addr[ByteOffW-1:0];
      ld_req_ext_d = live_lsu_ext;
    end else if (ld_req_capture) begin
      ld_req_valid_d = 1'b1;
      ld_req_addr_d = lsu_addr;
      ld_req_size_d = lsu_size;
      ld_req_rd_d = serial_lsu_rd;
      ld_req_is_fpr_d = lsu_is_fp;
      ld_req_off_d = lsu_addr[ByteOffW-1:0];
      ld_req_ext_d = curr_ld_ext;
    end
    if (flush_i) begin
      ld_req_valid_d = 1'b0;
    end
  end

  always_comb begin : p_ldq_update
    ldq_rd_d     = ldq_rd_q;
    ldq_is_fpr_d = ldq_is_fpr_q;
    ldq_off_d    = ldq_off_q;
    ldq_ext_d    = ldq_ext_q;
    ldq_head_d   = ldq_head_q;
    ldq_tail_d   = ldq_tail_q;
    ldq_count_d  = ldq_count_q;
    if (ld_ar_fire) begin
      ldq_rd_d[ldq_tail_q]     = ld_req_rd_q;
      ldq_is_fpr_d[ldq_tail_q] = ld_req_is_fpr_q;
      ldq_off_d[ldq_tail_q]    = ld_req_off_q;
      ldq_ext_d[ldq_tail_q]    = ld_req_ext_q;
      ldq_tail_d               = ldq_tail_q + 1'b1;
    end
    if (ld_r_fire) begin
      ldq_head_d = ldq_head_q + 1'b1;
    end
    unique case ({ld_ar_fire, ld_r_fire})
      2'b10:   ldq_count_d = ldq_count_q + 1'b1;
      2'b01:   ldq_count_d = ldq_count_q - 1'b1;
      default: ldq_count_d = ldq_count_q;
    endcase
    if (flush_i) begin
      ldq_head_d  = '0;
      ldq_tail_d  = '0;
      ldq_count_d = '0;
    end
  end

  always_comb begin : p_scalar_axi_req
    scalar_axi_req = '0;
    scalar_axi_req.ar.id     = '0;
    scalar_axi_req.ar.addr   = ld_req_addr_q;
    scalar_axi_req.ar.len    = '0;
    scalar_axi_req.ar.size   = {1'b0, ld_req_size_q};
    scalar_axi_req.ar.burst  = axi_pkg::BURST_INCR;
    scalar_axi_req.ar.lock   = 1'b0;
    scalar_axi_req.ar.cache  = axi_pkg::CACHE_MODIFIABLE;
    scalar_axi_req.ar.prot   = '0;
    scalar_axi_req.ar.qos    = '0;
    scalar_axi_req.ar.region = '0;
    scalar_axi_req.ar.user   = '0;

    scalar_axi_req.aw.id     = '0;
    scalar_axi_req.aw.addr   = lsu_addr;
    scalar_axi_req.aw.len    = '0;
    scalar_axi_req.aw.size   = {1'b0, lsu_size};
    scalar_axi_req.aw.burst  = axi_pkg::BURST_INCR;
    scalar_axi_req.aw.lock   = 1'b0;
    scalar_axi_req.aw.cache  = axi_pkg::CACHE_MODIFIABLE;
    scalar_axi_req.aw.prot   = '0;
    scalar_axi_req.aw.qos    = '0;
    scalar_axi_req.aw.region = '0;
    scalar_axi_req.aw.atop   = '0;
    scalar_axi_req.aw.user   = '0;

    scalar_axi_req.w.data = lsu_store_data;
    scalar_axi_req.w.strb = lsu_store_strb;
    scalar_axi_req.w.last = 1'b1;
    scalar_axi_req.w.user = '0;

    scalar_axi_req.ar_valid = ld_ar_valid && !flush_i;
    scalar_axi_req.r_ready  = (state_q == LSU_AR) && !ldq_empty && !flush_i;
    scalar_axi_req.aw_valid = (state_q == LSU_AW) && !flush_i;
    scalar_axi_req.w_valid  = (state_q == LSU_W)  && !flush_i;
    scalar_axi_req.b_ready  = (state_q == LSU_B)  && !flush_i;
  end

  always_comb begin : p_next
    state_d = state_q;
    insn_valid_d = insn_valid_q;
    insn_d = insn_q;
    insn_is_32b_d = insn_is_32b_q;
    insn_pc_d = insn_pc_q;
    cycle_d = cycle_q + 64'd1;
    redirect_pending_d = redirect_pending_q;
    redirect_pc_d = redirect_pc_q;
    error_seen_d = error_seen_q;
    task_complete_pending_d = task_complete_pending_q;
    csr_vl_d = csr_vl_q;
    csr_vtype_d = csr_vtype_q;
    csr_frm_d = csr_frm_q;
    issue_valid_d = issue_valid_q;
    issue_slot_idx_d = issue_slot_idx_q;
    issue_insn_d = issue_insn_q;
    issue_is_32b_d = issue_is_32b_q;
    issue_pc_d = issue_pc_q;
    issue_decoder_instr_d = issue_decoder_instr_q;
    issue_decoded_d = issue_decoded_q;
    issue_fu_data_d = issue_fu_data_q;
    issue_mult_ready_d = issue_mult_ready_q;
    scalar_mem_order_pending_d = scalar_mem_order_pending_q;
    scalar_mem_release_forbidden_d = scalar_mem_release_forbidden_q;
    branch_resolved_pulse_d = 1'b0;
    branch_taken_d = branch_taken_q;
    branch_pc_d = branch_pc_q;
    branch_target_d = branch_target_q;
    branch_backward_d = branch_backward_q;
    remaining_slots = insn_valid_q;

    for (int unsigned i = 0; i < 32; i++) begin
      xrf_d[i] = xrf_q[i];
      frf_d[i] = frf_q[i];
    end

    if (vec_wb_valid_i && (vec_wb_is_fpr_i || (vec_wb_rd_i != 5'd0))) begin
      if (vec_wb_is_fpr_i) begin
        frf_d[vec_wb_rd_i] = vec_wb_data_i;
      end else begin
        xrf_d[vec_wb_rd_i] = vec_wb_data_i;
      end
    end
    if (vec_wb_valid_i && vec_wb_is_vset_i) begin
      csr_vl_d = vec_wb_data_i;
    end

    unique case (state_q)
      IDLE: begin
        issue_valid_d = 1'b0;
        redirect_pending_d = 1'b0;
        error_seen_d = 1'b0;
        task_complete_pending_d = 1'b0;
        scalar_mem_order_pending_d = 1'b0;
        scalar_mem_release_forbidden_d = 1'b0;
        if (scalar_valid_i) begin
          insn_valid_d = scalar_insn_valid_i;
          insn_d = scalar_insn_i;
          insn_is_32b_d = scalar_insn_is_32b_i;
          insn_pc_d = scalar_insn_pc_i;
          scalar_mem_order_pending_d = scalar_input_has_mem_order;
          scalar_mem_release_forbidden_d =
              scalar_input_has_nonreleasable_order;
          state_d = (|scalar_insn_valid_i) ? EXECUTE : DONE;
        end
      end

      EXECUTE: begin
        if (simple_batch_valid) begin
          remaining_slots = insn_valid_q & ~simple_batch_mask;
          insn_valid_d = remaining_slots;

          for (int unsigned i = 0; i < NumSlots; i++) begin
            if (simple_batch_mask[i] && simple_batch_wb_en[i] &&
                (simple_batch_rd[i] != 5'd0)) begin
              xrf_d[simple_batch_rd[i]] = simple_batch_result[i];
            end
          end
        end else begin
          remaining_slots = insn_valid_q;
        end

        if ((curr_slot_found && !complex_prefix_ready) ||
            vset_gpr_hazard_stall || complex_simple_raw_stall) begin
          // Hold only the non-ALU lane: independent simple ALU slots selected
          // above have already been consumed and written back this cycle.
          state_d = EXECUTE;
        end else if (curr_slot_found) begin
          if (fast_branch_valid) begin
            remaining_slots[curr_slot_idx] = 1'b0;
            insn_valid_d = remaining_slots;
            branch_resolved_pulse_d = 1'b1;
            branch_taken_d = fast_branch_taken;
            branch_pc_d = curr_pc;
            branch_target_d = fast_branch_target;
            branch_backward_d = curr_insn[31];
            if (fast_branch_taken) begin
              redirect_pending_d = 1'b1;
              redirect_pc_d = fast_branch_target;
            end
            state_d = (|remaining_slots) ? EXECUTE : DONE;
          end else if (fast_task_exit) begin
            remaining_slots[curr_slot_idx] = 1'b0;
            insn_valid_d = remaining_slots;
            task_complete_pending_d = 1'b1;
            state_d = (|remaining_slots) ? EXECUTE : DONE;
          end else if ((cva6_decoded.fu inside {LOAD, STORE}) &&
              !cva6_decoded.ex.valid && !live_lsu_misaligned) begin
            if (vec_store_inflight_i) begin
              state_d = EXECUTE;
            end else begin
              if (cva6_decoded.fu == LOAD) begin
                remaining_slots[curr_slot_idx] = 1'b0;
              end
              insn_valid_d = remaining_slots;
              state_d = (cva6_decoded.fu == LOAD) ? LSU_AR : LSU_AW;
            end
          end else begin
            insn_valid_d = remaining_slots;
            issue_valid_d = 1'b1;
            issue_slot_idx_d = curr_slot_idx;
            issue_insn_d = curr_insn;
            issue_is_32b_d = curr_is_32b;
            issue_pc_d = curr_pc;
            issue_decoder_instr_d = cva6_decoder_instr;
            issue_decoded_d = cva6_decoded;
            state_d = COMPLEX_ISSUE;
          end
        end else if (simple_batch_valid) begin
          state_d = (|remaining_slots) ? EXECUTE : DONE;
        end else begin
          state_d = DONE;
        end
      end

      COMPLEX_ISSUE: begin
        if (!issue_valid_q) begin
          state_d = EXECUTE;
        end else if ((issue_decoded_q.fu == MULT) &&
                     !issue_decoded_q.ex.valid &&
                     !is_local_mul_op(issue_decoded_q.op) &&
                     !cva6_mult_ready) begin
          // DIV/REM use the serial CVA6 unit.  Wait before registering the
          // operand payload so COMPLEX_EXEC can emit a one-cycle request
          // without a valid/ready combinational dependency.
          state_d = COMPLEX_ISSUE;
        end else begin
          issue_fu_data_d = issue_operand_fu_data;
          issue_mult_ready_d = is_local_mul_op(issue_decoded_q.op) ?
                               1'b1 : cva6_mult_ready;
          state_d = COMPLEX_EXEC;
        end
      end

      COMPLEX_EXEC: begin
        if (!issue_valid_q) begin
          state_d = EXECUTE;
        end else if ((issue_decoded_q.fu == MULT) && !unsupported) begin
          if (issue_mult_ready_q) begin
            state_d = WAIT_MULT;
          end
        end else if ((issue_decoded_q.fu == FPU) && !unsupported) begin
          if (cva6_fpu_ready) begin
            state_d = WAIT_FPU;
          end
        end else begin
          remaining_slots = insn_valid_q;
          remaining_slots[issue_slot_idx_q] = 1'b0;
          insn_valid_d = remaining_slots;
          issue_valid_d = 1'b0;

          if (wb_en && !unsupported && (wb_addr != 5'd0)) begin
            if (wb_is_fpr) begin
              frf_d[wb_addr] = wb_data;
            end else begin
              xrf_d[wb_addr] = wb_data;
            end
          end

          if (!unsupported && (issue_decoded_q.fu == CSR) && csr_write) begin
            unique case (csr_addr)
              riscv::CSR_FRM: begin
                unique case (issue_decoder_instr_q[14:12])
                  riscv::CSRRW,
                  riscv::CSRRWI: csr_frm_d = csr_wdata[2:0];
                  riscv::CSRRS,
                  riscv::CSRRSI: csr_frm_d = csr_frm_q | csr_wmask[2:0];
                  riscv::CSRRC,
                  riscv::CSRRCI: csr_frm_d = csr_frm_q & ~csr_wmask[2:0];
                  default: ;
                endcase
              end
              riscv::CSR_FCSR: begin
                unique case (issue_decoder_instr_q[14:12])
                  riscv::CSRRW,
                  riscv::CSRRWI: csr_frm_d = csr_wdata[7:5];
                  riscv::CSRRS,
                  riscv::CSRRSI: csr_frm_d = csr_frm_q | csr_wmask[7:5];
                  riscv::CSRRC,
                  riscv::CSRRCI: csr_frm_d = csr_frm_q & ~csr_wmask[7:5];
                  default: ;
                endcase
              end
              riscv::CSR_VL: begin
                unique case (issue_decoder_instr_q[14:12])
                  riscv::CSRRW,
                  riscv::CSRRWI: csr_vl_d = csr_wdata;
                  riscv::CSRRS,
                  riscv::CSRRSI: csr_vl_d = csr_vl_q | csr_wmask;
                  riscv::CSRRC,
                  riscv::CSRRCI: csr_vl_d = csr_vl_q & ~csr_wmask;
                  default: ;
                endcase
              end
              riscv::CSR_VTYPE: begin
                unique case (issue_decoder_instr_q[14:12])
                  riscv::CSRRW,
                  riscv::CSRRWI: csr_vtype_d = csr_wdata;
                  riscv::CSRRS,
                  riscv::CSRRSI: csr_vtype_d = csr_vtype_q | csr_wmask;
                  riscv::CSRRC,
                  riscv::CSRRCI: csr_vtype_d = csr_vtype_q & ~csr_wmask;
                  default: ;
                endcase
              end
              default: ;
            endcase
          end

          if (branch_resolved) begin
            branch_resolved_pulse_d = 1'b1;
            branch_taken_d = branch_taken;
            branch_pc_d = issue_pc_q;
            branch_target_d = branch_target;
            branch_backward_d = branch_backward;
            if (branch_taken) begin
              redirect_pending_d = 1'b1;
              redirect_pc_d = branch_target;
            end
          end

          if (unsupported && (issue_decoder_instr_q != 32'h00000000)) begin
            error_seen_d = 1'b1;
          end
          if (!unsupported && (hdv_task_ret || hdv_task_ebreak)) begin
            task_complete_pending_d = 1'b1;
          end

          state_d = (|remaining_slots) ? EXECUTE : DONE;
        end
      end

      WAIT_MULT: begin
        if (scalar_mult_valid) begin
          remaining_slots = insn_valid_q;
          remaining_slots[issue_slot_idx_q] = 1'b0;
          insn_valid_d = remaining_slots;
          issue_valid_d = 1'b0;
          if (issue_decoded_q.rd != 5'd0) begin
            xrf_d[issue_decoded_q.rd] = scalar_mult_result;
          end
          state_d = (|remaining_slots) ? EXECUTE : DONE;
        end
      end

      WAIT_FPU: begin
        if (cva6_fpu_valid) begin
          remaining_slots = insn_valid_q;
          remaining_slots[issue_slot_idx_q] = 1'b0;
          insn_valid_d = remaining_slots;
          issue_valid_d = 1'b0;
          if (!cva6_fpu_exception.valid &&
              (fpu_writes_fpr || (issue_decoded_q.rd != 5'd0))) begin
            if (fpu_writes_fpr) begin
              frf_d[issue_decoded_q.rd] = XLEN'(cva6_fpu_result);
            end else if (fpu_writes_xrf) begin
              xrf_d[issue_decoded_q.rd] = XLEN'(cva6_fpu_result);
            end
          end
          if (cva6_fpu_exception.valid) begin
            error_seen_d = 1'b1;
          end
          state_d = (|remaining_slots) ? EXECUTE : DONE;
        end
      end

      LSU_AR: begin
        // Pipelined load: issue ARs for consecutive load slots (each cleared on
        // its AR fire so curr_slot advances to the next load) while collecting R
        // responses in order into FRF/XRF.  The EP only leaves this state once
        // every outstanding R has drained, so scalar_ep_done (=> a dependent
        // vfmacc's operand read) observes the written value.
        remaining_slots = insn_valid_q;
        if (ld_req_capture) begin
          remaining_slots[serial_slot_idx] = 1'b0;
          insn_valid_d = remaining_slots;
        end
        if (ld_r_fire) begin
          if (!ldq_pop_err &&
              (ldq_is_fpr_q[ldq_head_q] || (ldq_rd_q[ldq_head_q] != 5'd0))) begin
            if (ldq_is_fpr_q[ldq_head_q]) begin
              frf_d[ldq_rd_q[ldq_head_q]] = ldq_pop_data;
            end else begin
              xrf_d[ldq_rd_q[ldq_head_q]] = ldq_pop_data;
            end
          end
          if (ldq_pop_err) begin
            error_seen_d = 1'b1;
          end
        end
        // Leave once no further load AR can be issued and the queue has drained
        // (this cycle's pop empties it).
        if (!curr_is_load && !ld_req_valid_q &&
            ((ldq_count_q == '0) || (ld_r_fire && (ldq_count_q == 'd1)))) begin
          state_d = (|insn_valid_d) ? EXECUTE : DONE;
        end
      end

      LSU_R: begin
        if (scalar_axi_resp_i.r_valid) begin
          remaining_slots = insn_valid_q;
          remaining_slots[serial_slot_idx] = 1'b0;
          insn_valid_d = remaining_slots;
          if (!lsu_resp_error && (lsu_is_fp || (cva6_decoded.rd != 5'd0))) begin
            if (lsu_is_fp) begin
              frf_d[cva6_decoded.rd] = lsu_load_data;
            end else begin
              xrf_d[cva6_decoded.rd] = lsu_load_data;
            end
          end
          if (lsu_resp_error) begin
            error_seen_d = 1'b1;
          end
          state_d = (|remaining_slots) ? EXECUTE : DONE;
        end
      end

      LSU_AW: begin
        if (scalar_axi_resp_i.aw_ready) begin
          state_d = LSU_W;
        end
      end

      LSU_W: begin
        if (scalar_axi_resp_i.w_ready) begin
          state_d = LSU_B;
        end
      end

      LSU_B: begin
        if (scalar_axi_resp_i.b_valid) begin
          remaining_slots = insn_valid_q;
          remaining_slots[serial_slot_idx] = 1'b0;
          insn_valid_d = remaining_slots;
          if (lsu_resp_error) begin
            error_seen_d = 1'b1;
          end
          state_d = (|remaining_slots) ? EXECUTE : DONE;
        end
      end

      DONE: begin
        task_complete_pending_d = 1'b0;
        scalar_mem_order_pending_d = 1'b0;
        scalar_mem_release_forbidden_d = 1'b0;
        state_d = redirect_pending_q ? REDIRECT : IDLE;
      end

      REDIRECT: begin
        redirect_pending_d = 1'b0;
        scalar_mem_order_pending_d = 1'b0;
        scalar_mem_release_forbidden_d = 1'b0;
        state_d = IDLE;
      end

      default: state_d = IDLE;
    endcase

    // Clear the live memory-order boundary only after every supported scalar
    // load/store in this EP has completed.  This also covers the transition
    // into DONE: the response/data side effects commit at that edge, so the
    // buffered vector slice may start in the following cycle without waiting
    // for HEU's whole-EP completion observation. A request handshake alone is
    // not a completion point: loads remain covered by ld_req/ldq and stores by
    // LSU_AW/W/B.
    if (scalar_mem_order_pending_q &&
        !scalar_mem_release_forbidden_q &&
        !scalar_remaining_releasable_mem &&
        !scalar_remaining_nonreleasable_order &&
        !scalar_mem_inflight_d &&
        !error_seen_d &&
        !(state_d inside {IDLE, REDIRECT})) begin
      scalar_mem_order_pending_d = 1'b0;
    end

    xrf_d[0] = '0;

    if (flush_i) begin
      state_d = IDLE;
      insn_valid_d = '0;
      issue_valid_d = 1'b0;
      redirect_pending_d = 1'b0;
      error_seen_d = 1'b0;
      task_complete_pending_d = 1'b0;
      scalar_mem_order_pending_d = 1'b0;
      scalar_mem_release_forbidden_d = 1'b0;
      branch_resolved_pulse_d = 1'b0;
    end
  end

  // Build the next-state dependency summary captured by HEU.  Loads leave
  // insn_valid_d when their request is captured, so their destination remains
  // pending through the request register and load-response queue.
  always_comb begin : p_pending_dependency_masks
    pending_gpr_read_mask_d = '0;
    pending_gpr_write_mask_d = '0;
    pending_fpr_read_mask_d = '0;
    pending_fpr_write_mask_d = '0;

    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (insn_valid_d[i]) begin
        pending_gpr_read_mask_d |=
          pending_gpr_read_mask(insn_is_32b_d[i], insn_d[i]);
        pending_gpr_write_mask_d |=
          pending_gpr_write_mask(insn_is_32b_d[i], insn_d[i]);
        pending_fpr_read_mask_d |=
          pending_fpr_read_mask(insn_is_32b_d[i], insn_d[i]);
        pending_fpr_write_mask_d |=
          pending_fpr_write_mask(insn_is_32b_d[i], insn_d[i]);
      end
    end

    if (ld_req_valid_d) begin
      if (ld_req_is_fpr_d) begin
        pending_fpr_write_mask_d[ld_req_rd_d] = 1'b1;
      end else if (ld_req_rd_d != 5'd0) begin
        pending_gpr_write_mask_d[ld_req_rd_d] = 1'b1;
      end
    end

    for (int unsigned i = 0; i < LdQDepth; i++) begin
      if (i < ldq_count_d) begin
        if (ldq_is_fpr_d[ldq_head_d + LdQPtrW'(i)]) begin
          pending_fpr_write_mask_d[ldq_rd_d[ldq_head_d + LdQPtrW'(i)]] = 1'b1;
        end else if (ldq_rd_d[ldq_head_d + LdQPtrW'(i)] != 5'd0) begin
          pending_gpr_write_mask_d[ldq_rd_d[ldq_head_d + LdQPtrW'(i)]] = 1'b1;
        end
      end
    end
  end

`ifdef FOR_VERIFY
  // Runtime arg-injection override (simulation only).  `+HDV_A<n>=<val>` on the
  // simv command line sets xrf[10+n] at reset, beating the compile-time
  // InitialA<n>.  This lets an AVL sweep change the application vector length
  // per run WITHOUT re-elaborating: VCS keeps `../simv up to date` and ignores
  // changed +define+ values, so a define-based AVL is stale/unreliable.
  logic [63:0] hdv_arg_ovr [0:7];
  logic        hdv_arg_en  [0:7];
  initial begin
    longint unsigned v;
    for (int j = 0; j < 8; j++) hdv_arg_en[j] = 1'b0;
    if ($value$plusargs("HDV_A0=%d", v)) begin hdv_arg_en[0] = 1'b1; hdv_arg_ovr[0] = v; end
    if ($value$plusargs("HDV_A1=%d", v)) begin hdv_arg_en[1] = 1'b1; hdv_arg_ovr[1] = v; end
    if ($value$plusargs("HDV_A2=%d", v)) begin hdv_arg_en[2] = 1'b1; hdv_arg_ovr[2] = v; end
    if ($value$plusargs("HDV_A3=%d", v)) begin hdv_arg_en[3] = 1'b1; hdv_arg_ovr[3] = v; end
    if ($value$plusargs("HDV_A4=%d", v)) begin hdv_arg_en[4] = 1'b1; hdv_arg_ovr[4] = v; end
    if ($value$plusargs("HDV_A5=%d", v)) begin hdv_arg_en[5] = 1'b1; hdv_arg_ovr[5] = v; end
    if ($value$plusargs("HDV_A6=%d", v)) begin hdv_arg_en[6] = 1'b1; hdv_arg_ovr[6] = v; end
    if ($value$plusargs("HDV_A7=%d", v)) begin hdv_arg_en[7] = 1'b1; hdv_arg_ovr[7] = v; end
  end
`endif
  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      state_q <= IDLE;
      insn_valid_q <= '0;
      insn_q <= '0;
      insn_is_32b_q <= '0;
      insn_pc_q <= '0;
      issue_valid_q <= 1'b0;
      issue_slot_idx_q <= '0;
      issue_insn_q <= '0;
      issue_is_32b_q <= 1'b0;
      issue_pc_q <= '0;
      issue_decoder_instr_q <= '0;
      issue_decoded_q <= '0;
      issue_fu_data_q <= '0;
      issue_mult_ready_q <= 1'b0;
      scalar_mem_order_pending_q <= 1'b0;
      scalar_mem_release_forbidden_q <= 1'b0;
      cycle_q <= 64'd0;
      redirect_pending_q <= 1'b0;
      redirect_pc_q <= '0;
      error_seen_q <= 1'b0;
      task_complete_pending_q <= 1'b0;
      branch_resolved_pulse_q <= 1'b0;
      branch_taken_q <= 1'b0;
      branch_pc_q <= '0;
      branch_target_q <= '0;
      branch_backward_q <= 1'b0;
      csr_vl_q <= '0;
      csr_vtype_q <= '0;
      csr_frm_q <= 3'b000;
      ldq_rd_q <= '0;
      ldq_is_fpr_q <= '0;
      ldq_off_q <= '0;
      ldq_ext_q <= '0;
      ldq_head_q <= '0;
      ldq_tail_q <= '0;
      ldq_count_q <= '0;
      ld_req_valid_q <= 1'b0;
      ld_req_addr_q <= '0;
      ld_req_size_q <= '0;
      ld_req_rd_q <= '0;
      ld_req_is_fpr_q <= 1'b0;
      ld_req_off_q <= '0;
      ld_req_ext_q <= '0;
      for (int unsigned i = 0; i < 32; i++) begin
        xrf_q[i] <= '0;
        frf_q[i] <= '0;
      end
      xrf_q[1] <= InitialRa;
`ifdef FOR_VERIFY
      // Runtime arg override: +HDV_A<n>=<val> wins over the compile-time
      // InitialA<n> (see hdv_arg_* below).  Lets an AVL sweep change the
      // application vector length per run without re-elaborating the simv.
      xrf_q[10] <= hdv_arg_en[0] ? hdv_arg_ovr[0][XLEN-1:0] : InitialA0;
      xrf_q[11] <= hdv_arg_en[1] ? hdv_arg_ovr[1][XLEN-1:0] : InitialA1;
      xrf_q[12] <= hdv_arg_en[2] ? hdv_arg_ovr[2][XLEN-1:0] : InitialA2;
      xrf_q[13] <= hdv_arg_en[3] ? hdv_arg_ovr[3][XLEN-1:0] : InitialA3;
      xrf_q[14] <= hdv_arg_en[4] ? hdv_arg_ovr[4][XLEN-1:0] : InitialA4;
      xrf_q[15] <= hdv_arg_en[5] ? hdv_arg_ovr[5][XLEN-1:0] : InitialA5;
      xrf_q[16] <= hdv_arg_en[6] ? hdv_arg_ovr[6][XLEN-1:0] : InitialA6;
      xrf_q[17] <= hdv_arg_en[7] ? hdv_arg_ovr[7][XLEN-1:0] : InitialA7;
`else
      xrf_q[10] <= InitialA0;
      xrf_q[11] <= InitialA1;
      xrf_q[12] <= InitialA2;
      xrf_q[13] <= InitialA3;
      xrf_q[14] <= InitialA4;
      xrf_q[15] <= InitialA5;
      xrf_q[16] <= InitialA6;
      xrf_q[17] <= InitialA7;
`endif
      frf_q[10] <= InitialFa0;
    end else begin
      state_q <= state_d;
      insn_valid_q <= insn_valid_d;
      insn_q <= insn_d;
      insn_is_32b_q <= insn_is_32b_d;
      insn_pc_q <= insn_pc_d;
      issue_valid_q <= issue_valid_d;
      issue_slot_idx_q <= issue_slot_idx_d;
      issue_insn_q <= issue_insn_d;
      issue_is_32b_q <= issue_is_32b_d;
      issue_pc_q <= issue_pc_d;
      issue_decoder_instr_q <= issue_decoder_instr_d;
      issue_decoded_q <= issue_decoded_d;
      issue_fu_data_q <= issue_fu_data_d;
      issue_mult_ready_q <= issue_mult_ready_d;
      scalar_mem_order_pending_q <= scalar_mem_order_pending_d;
      scalar_mem_release_forbidden_q <= scalar_mem_release_forbidden_d;
      cycle_q <= cycle_d;
      redirect_pending_q <= redirect_pending_d;
      redirect_pc_q <= redirect_pc_d;
      error_seen_q <= error_seen_d;
      task_complete_pending_q <= task_complete_pending_d;
      branch_resolved_pulse_q <= branch_resolved_pulse_d;
      branch_taken_q <= branch_taken_d;
      branch_pc_q <= branch_pc_d;
      branch_target_q <= branch_target_d;
      branch_backward_q <= branch_backward_d;
      csr_vl_q <= csr_vl_d;
      csr_vtype_q <= csr_vtype_d;
      csr_frm_q <= csr_frm_d;
      ldq_rd_q <= ldq_rd_d;
      ldq_is_fpr_q <= ldq_is_fpr_d;
      ldq_off_q <= ldq_off_d;
      ldq_ext_q <= ldq_ext_d;
      ldq_head_q <= ldq_head_d;
      ldq_tail_q <= ldq_tail_d;
      ldq_count_q <= ldq_count_d;
      ld_req_valid_q <= ld_req_valid_d;
      ld_req_addr_q <= ld_req_addr_d;
      ld_req_size_q <= ld_req_size_d;
      ld_req_rd_q <= ld_req_rd_d;
      ld_req_is_fpr_q <= ld_req_is_fpr_d;
      ld_req_off_q <= ld_req_off_d;
      ld_req_ext_q <= ld_req_ext_d;
      for (int unsigned i = 0; i < 32; i++) begin
        xrf_q[i] <= xrf_d[i];
        frf_q[i] <= frf_d[i];
      end
    end
  end

  always_ff @(posedge clk_i) begin : p_unsupported_report
    if (rst_ni && (state_q == COMPLEX_EXEC) && issue_valid_q && unsupported) begin
      $warning("[HDV] hdv_scalar_backend unsupported scalar instruction pc=0x%016h insn=0x%08h is32=%0b",
               issue_pc_q, issue_insn_q, issue_is_32b_q);
    end
  end

`ifndef SYNTHESIS
  always_ff @(posedge clk_i) begin : p_issue_assertions
    automatic simple_alu_dec_t verify_simple_dec;
    automatic logic [31:0] verify_prior_read_mask;
    automatic logic [31:0] verify_read_mask;
    automatic logic [31:0] verify_write_mask;
    if (rst_ni && !flush_i) begin
      if (state_q == EXECUTE) begin
        verify_prior_read_mask = '0;
        for (int unsigned i = 0; i < NumSlots; i++) begin
          if (insn_valid_q[i]) begin
            verify_read_mask =
              simple_alu_read_mask(insn_is_32b_q[i], insn_q[i]);
            verify_write_mask =
              scalar_write_mask_conservative(insn_is_32b_q[i], insn_q[i]);
            verify_simple_dec = decode_simple_alu(
                insn_is_32b_q[i], insn_q[i], insn_pc_q[i],
                (insn_q[i][19:15] == 5'd0) ? '0 : xrf_q[insn_q[i][19:15]],
                (insn_q[i][24:20] == 5'd0) ? '0 : xrf_q[insn_q[i][24:20]]);
            assert (simple_class_valid[i] == verify_simple_dec.valid)
              else $error("[HDV] lightweight simple-ALU classifier disagrees with full decode");
            if (simple_batch_mask[i]) begin
              assert (simple_class_valid[i])
                else $error("[HDV] non-simple scalar instruction selected by simple batch");
              if (simple_batch_wb_en[i]) begin
                assert (!verify_prior_read_mask[simple_batch_rd[i]])
                  else $error("[HDV] younger simple scalar write crossed an older scalar read");
              end
            end
            verify_prior_read_mask |=
              pending_gpr_read_mask(insn_is_32b_q[i], insn_q[i]);
          end
        end
      end
      if (state_q inside {COMPLEX_ISSUE, COMPLEX_EXEC, WAIT_MULT, WAIT_FPU}) begin
        assert (issue_valid_q)
          else $error("[HDV] complex scalar state lost its registered issue context");
      end
      if (scalar_mult_issue) begin
        assert (issue_mult_ready_q)
          else $error("[HDV] MULT/DIV issued without a prechecked ready token");
        assert (state_d == WAIT_MULT)
          else $error("[HDV] MULT/DIV issue did not advance to WAIT_MULT");
      end
      if ((state_q == COMPLEX_EXEC) && issue_valid_q) begin
        assert (!(issue_decoded_q.fu inside {LOAD, STORE}) || unsupported)
          else $error("[HDV] supported scalar LOAD/STORE incorrectly entered complex issue stage");
      end
      if ((state_q == LSU_AR) && ld_req_capture) begin
        assert (serial_slot_found && serial_lsu_supported && lsu_is_load &&
                !lsu_misaligned && !serial_load_base_raw)
          else $error("[HDV] scalar load request was not captured from the oldest valid load slot");
        for (int unsigned i = 0; i < NumSlots; i++) begin
          if (i < serial_slot_idx) begin
            assert (!insn_valid_q[i])
              else $error("[HDV] scalar LSU skipped an older uncommitted slot");
          end
        end
      end
      if ((state_q == LSU_AR) && ld_ar_fire) begin
        assert (ld_req_valid_q)
          else $error("[HDV] scalar load AR fired without a registered request");
      end
      if (state_q inside {LSU_AW, LSU_W, LSU_B}) begin
        assert (serial_slot_found && serial_lsu_supported && !lsu_is_load)
          else $error("[HDV] scalar store state lost its oldest-slot context");
      end
      if (state_q == EXECUTE) begin
        for (int unsigned i = 0; i < NumSlots; i++) begin
          if (simple_batch_mask[i]) begin
            verify_read_mask =
              simple_alu_read_mask(insn_is_32b_q[i], insn_q[i]);
            verify_write_mask =
              scalar_write_mask_conservative(insn_is_32b_q[i], insn_q[i]);
            for (int unsigned v = 0; v < 2; v++) begin
              if (vec_vset_inflight_valid_i[v] &&
                  (vec_vset_inflight_rd_i[v] != 5'd0)) begin
                assert (!verify_read_mask[vec_vset_inflight_rd_i[v]])
                  else $error("[HDV] simple scalar lane consumed an in-flight vset result");
                assert (!verify_write_mask[vec_vset_inflight_rd_i[v]])
                  else $error("[HDV] simple scalar lane crossed an in-flight vset writer");
              end
            end
          end
        end
      end
      if ((state_q == EXECUTE) && curr_slot_found && fast_branch_valid) begin
        assert ((cva6_decoded.fu == CTRL_FLOW) && !cva6_decoded.ex.valid)
          else $error("[HDV] lightweight branch classifier disagrees with CVA6 decode");
      end
      if ((state_q != IDLE) && !scalar_mem_order_pending_q &&
          !(state_q inside {DONE, REDIRECT})) begin
        assert (!scalar_mem_order_pending_d)
          else $error("[HDV] scalar memory-order pending reasserted within one EP");
      end
      if (ld_req_valid_d || (ldq_count_d != '0) ||
          (state_d inside {LSU_AR, LSU_R, LSU_AW, LSU_W, LSU_B})) begin
        assert (scalar_mem_order_pending_d)
          else $error("[HDV] scalar memory-order boundary cleared with LSU work in flight");
      end
      if (scalar_mem_order_pending_q && !scalar_mem_order_pending_d &&
          !(state_q inside {IDLE, DONE, REDIRECT})) begin
        assert (!scalar_mem_release_forbidden_q &&
                !scalar_remaining_releasable_mem &&
                !scalar_remaining_nonreleasable_order &&
                !scalar_mem_inflight_d && !error_seen_d &&
                !(state_d inside {IDLE, REDIRECT}))
          else $error("[HDV] scalar memory-order boundary released before strict completion");
      end
      if (scalar_ep_done_o) begin
        assert (!scalar_mem_order_pending_o)
          else $error("[HDV] completed scalar EP still reports pending memory ordering");
      end
    end
  end
`endif

`ifdef FOR_VERIFY
  always_ff @(posedge clk_i) begin : p_pf_probe_scalar
    if (rst_ni && $test$plusargs("HDV_PF_PROBE")) begin
      if (scalar_valid_i && scalar_ready_o) begin
        $display("[PFPROBE-SCALAR] cyc=%0d ev=scalar_accept valid=%b pc0=0x%0h pc1=0x%0h pc2=0x%0h pc3=0x%0h insn0=0x%08h insn1=0x%08h insn2=0x%08h insn3=0x%08h x5=0x%0h x6=0x%0h x7=0x%0h a0=0x%0h a1=0x%0h a2=0x%0h",
                 cycle_q, scalar_insn_valid_i, scalar_insn_pc_i[0], scalar_insn_pc_i[1],
                 scalar_insn_pc_i[2], scalar_insn_pc_i[3], scalar_insn_i[0],
                 scalar_insn_i[1], scalar_insn_i[2], scalar_insn_i[3],
                 xrf_q[5], xrf_q[6], xrf_q[7], xrf_q[10], xrf_q[11], xrf_q[12]);
      end

      if (state_q == EXECUTE) begin
        for (int unsigned i = 0; i < NumSlots; i++) begin
          if (simple_batch_mask[i] && simple_batch_wb_en[i] &&
              ((simple_batch_rd[i] == 5'd5) || (simple_batch_rd[i] == 5'd6) ||
               (simple_batch_rd[i] == 5'd7) || (simple_batch_rd[i] == 5'd10) ||
               (simple_batch_rd[i] == 5'd11) || (simple_batch_rd[i] == 5'd12))) begin
            $display("[PFPROBE-SCALAR] cyc=%0d ev=simple_wb slot=%0d pc=0x%0h insn=0x%08h rd=x%0d data=0x%0h before_a0=0x%0h before_a1=0x%0h before_x5=0x%0h before_x6=0x%0h before_x7=0x%0h",
                     cycle_q, i, insn_pc_q[i], insn_q[i], simple_batch_rd[i],
                     simple_batch_result[i], xrf_q[10], xrf_q[11], xrf_q[5],
                     xrf_q[6], xrf_q[7]);
          end
        end

        if ((state_q == COMPLEX_EXEC) && issue_valid_q && wb_en && !unsupported &&
            ((wb_addr == 5'd5) || (wb_addr == 5'd6) || (wb_addr == 5'd7) ||
             (wb_addr == 5'd10) || (wb_addr == 5'd11) || (wb_addr == 5'd12))) begin
          $display("[PFPROBE-SCALAR] cyc=%0d ev=complex_wb slot=%0d pc=0x%0h insn=0x%08h rd=x%0d data=0x%0h before_a0=0x%0h before_a1=0x%0h before_x5=0x%0h before_x6=0x%0h before_x7=0x%0h",
                   cycle_q, issue_slot_idx_q, issue_pc_q, issue_insn_q, wb_addr, wb_data,
                   xrf_q[10], xrf_q[11], xrf_q[5], xrf_q[6], xrf_q[7]);
        end
      end

      if (branch_resolved_pulse_d) begin
        $display("[PFPROBE-SCALAR] cyc=%0d ev=branch pc=0x%0h target=0x%0h taken=%0d a0=0x%0h a1=0x%0h x5=0x%0h x6=0x%0h x7=0x%0h",
                 cycle_q, branch_pc_d, branch_target_d, branch_taken_d,
                 xrf_d[10], xrf_d[11], xrf_d[5], xrf_d[6], xrf_d[7]);
      end

      if (vec_wb_valid_i &&
          ((vec_wb_rd_i == 5'd5) || (vec_wb_rd_i == 5'd6) ||
           (vec_wb_rd_i == 5'd10) || (vec_wb_rd_i == 5'd11) ||
           (vec_wb_rd_i == 5'd12))) begin
        $display("[PFPROBE-SCALAR] cyc=%0d ev=vec_wb rd=x%0d data=0x%0h is_vset=%0d is_fpr=%0d before_x5=0x%0h before_x6=0x%0h a0=0x%0h a1=0x%0h",
                 cycle_q, vec_wb_rd_i, vec_wb_data_i, vec_wb_is_vset_i,
                 vec_wb_is_fpr_i, xrf_q[5], xrf_q[6], xrf_q[10], xrf_q[11]);
      end
    end
  end
`endif

  logic unused_vec_operand_req_valid;
  assign unused_vec_operand_req_valid = vec_operand_req_valid_i;

endmodule : hdv_scalar_backend
