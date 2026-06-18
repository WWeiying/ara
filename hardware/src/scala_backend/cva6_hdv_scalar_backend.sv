// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Minimal CVA6-style scalar backend for HDV.  HDV already owns fetch, packet
// formation, and scalar/vector splitting, so this block keeps only the pieces
// needed behind HEU: an architectural X/FP register context, a small RV64
// decoder/ALU/branch path, a CSR-cycle stub, and a vector operand service.

module cva6_hdv_scalar_backend
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
  parameter logic [XLEN-1:0] InitialFa0 = '0,
  parameter bit TreatRetAsTaskExit = 1'b1,
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
  output logic                         scalar_accepted_o,
  output logic                         scalar_error_o,

  output logic                         redirect_valid_o,
  output addr_t                        redirect_pc_o,
  output logic                         branch_resolved_valid_o,
  output logic                         branch_taken_o,
  output addr_t                        branch_pc_o,
  output addr_t                        branch_target_o,
  output logic                         task_complete_o,

  input  logic                         vec_operand_req_valid_i,
  output logic                         vec_operand_req_ready_o,
  input  logic [4:0]                   vec_rs1_addr_i,
  input  logic [4:0]                   vec_rs2_addr_i,
  input  logic [4:0]                   vec_frs1_addr_i,
  output logic [XLEN-1:0]              vec_rs1_data_o,
  output logic [XLEN-1:0]              vec_rs2_data_o,
  output logic [XLEN-1:0]              vec_frs1_data_o,

  input  logic                         vec_vset_wb_valid_i,
  input  logic [4:0]                   vec_vset_wb_rd_i,
  input  logic [XLEN-1:0]              vec_vset_wb_data_i,

  // In-flight vset (rd!=x0) hazard hint: a vector vsetvli whose VL writeback to
  // vec_vset_inflight_rd_i has not landed yet.  A scalar that reads this rd must
  // stall until the writeback (A2 RAW interlock).
  input  logic                         vec_vset_inflight_i,
  input  logic [4:0]                   vec_vset_inflight_rd_i,

  output axi_req_t                     scalar_axi_req_o,
  input  axi_resp_t                    scalar_axi_resp_i
);

  localparam int unsigned EffectiveSimpleAluIssueWidth =
      (SimpleAluIssueWidth < ScalarIssueWidth) ? SimpleAluIssueWidth : ScalarIssueWidth;

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
    REDIRECT  = 4'd10
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

  logic [XLEN-1:0] xrf_d [32];
  logic [XLEN-1:0] xrf_q [32];
  logic [XLEN-1:0] frf_d [32];
  logic [XLEN-1:0] frf_q [32];
  logic [63:0] cycle_d, cycle_q;
  logic [XLEN-1:0] csr_vl_d, csr_vl_q;
  logic [XLEN-1:0] csr_vtype_d, csr_vtype_q;
  logic [2:0]      csr_frm_d, csr_frm_q;

  logic [4:0] curr_slot_idx;
  logic       curr_slot_found;
  logic [31:0] curr_insn;
  logic        curr_is_32b;
  addr_t       curr_pc;
  logic [15:0] curr_cinsn;

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

  logic [4:0]  rs1_addr;
  logic [4:0]  rs2_addr;
  logic [4:0]  rd_addr;
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
  logic lsu_is_load;
  addr_t lsu_addr;
  logic [1:0] lsu_size;
  logic lsu_misaligned;
  logic [AxiDataWidth-1:0] lsu_store_data;
  logic [(AxiDataWidth/8)-1:0] lsu_store_strb;
  logic [XLEN-1:0] lsu_load_data;
  logic lsu_resp_error;
  logic lsu_is_fp;
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

  typedef struct packed {
    logic             valid;
    logic             wb_en;
    logic [4:0]       rd;
    logic [XLEN-1:0]  result;
  } simple_alu_dec_t;

  logic [NumSlots-1:0]       simple_batch_mask;
  logic [NumSlots-1:0]       simple_batch_wb_en;
  logic [NumSlots-1:0][4:0]  simple_batch_rd;
  logic [NumSlots-1:0][XLEN-1:0] simple_batch_result;
  logic                      simple_batch_valid;
  logic [31:0]               simple_batch_write_mask;
  logic [31:0]               curr_int_read_mask;
  logic                      complex_simple_raw_stall;

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

  function automatic logic [31:0] scalar_write_mask_conservative(input logic        is_32b,
                                                                 input logic [31:0] insn);
    automatic logic [31:0] mask;
    automatic logic [6:0] opcode;
    automatic logic [4:0] rd;
    begin
      mask = '0;
      opcode = insn[6:0];
      rd = insn[11:7];
      if (!is_32b) begin
        // Do not speculate across an unexpanded compressed instruction.
        mask = 32'hffff_ffff;
      end else if (rd != 5'd0) begin
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
          7'b0001111, // FENCE
          7'b1110011: // CSR/SYSTEM
            mask[rd] = 1'b1;
          default: mask = '0;
        endcase
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

  always_comb begin : p_find_slot
    curr_slot_found = 1'b0;
    curr_slot_idx   = '0;
    for (int unsigned i = 0; i < NumSlots; i++) begin
      if (insn_valid_q[i] && !simple_batch_mask[i] && !curr_slot_found) begin
        curr_slot_found = 1'b1;
        curr_slot_idx   = 5'(i);
      end
    end
  end

  assign curr_insn   = insn_q[curr_slot_idx];
  assign curr_is_32b = insn_is_32b_q[curr_slot_idx];
  assign curr_pc     = insn_pc_q[curr_slot_idx];
  assign curr_cinsn  = curr_insn[15:0];

  always_comb begin : p_simple_batch
    automatic int unsigned issued;
    automatic logic stop_scan;
    automatic logic [31:0] used_rd;
    automatic logic [31:0] prior_write_mask;
    automatic logic [31:0] read_mask;
    automatic logic [31:0] write_mask;
    automatic simple_alu_dec_t dec;
    automatic logic [XLEN-1:0] lane_rs1;
    automatic logic [XLEN-1:0] lane_rs2;
    automatic logic lane_vset_raw_stall;
    automatic logic lane_order_hazard;

    simple_batch_mask   = '0;
    simple_batch_wb_en  = '0;
    simple_batch_rd     = '0;
    simple_batch_result = '0;
    simple_batch_write_mask = '0;
    issued              = 0;
    stop_scan           = 1'b0;
    used_rd             = '0;
    prior_write_mask     = '0;

    for (int unsigned i = 0; i < NumSlots; i++) begin
      lane_rs1 = (insn_q[i][19:15] == 5'd0) ? '0 : xrf_q[insn_q[i][19:15]];
      lane_rs2 = (insn_q[i][24:20] == 5'd0) ? '0 : xrf_q[insn_q[i][24:20]];
      dec = decode_simple_alu(insn_is_32b_q[i], insn_q[i], insn_pc_q[i], lane_rs1, lane_rs2);
      read_mask = simple_alu_read_mask(insn_is_32b_q[i], insn_q[i]);
      write_mask = scalar_write_mask_conservative(insn_is_32b_q[i], insn_q[i]);
      lane_vset_raw_stall = vec_vset_inflight_i && (vec_vset_inflight_rd_i != 5'd0) &&
                             ((insn_q[i][19:15] == vec_vset_inflight_rd_i) ||
                              (insn_q[i][24:20] == vec_vset_inflight_rd_i));
      lane_order_hazard = ((read_mask & prior_write_mask) != 32'b0) ||
                          (dec.wb_en && prior_write_mask[dec.rd]);

      if (insn_valid_q[i] && !stop_scan) begin
        if ((issued < EffectiveSimpleAluIssueWidth) && dec.valid && !lane_vset_raw_stall &&
            !lane_order_hazard &&
            (!dec.wb_en || !used_rd[dec.rd])) begin
          simple_batch_mask[i]   = 1'b1;
          simple_batch_wb_en[i]  = dec.wb_en;
          simple_batch_rd[i]     = dec.rd;
          simple_batch_result[i] = dec.result;
          if (dec.wb_en) begin
            used_rd[dec.rd] = 1'b1;
            simple_batch_write_mask[dec.rd] = 1'b1;
          end
          issued++;
        end else if ((issued >= EffectiveSimpleAluIssueWidth) ||
                     (dec.valid && lane_vset_raw_stall) ||
                     (dec.valid && lane_order_hazard) ||
                     (dec.valid && dec.wb_en && used_rd[dec.rd])) begin
          stop_scan = 1'b1;
        end

        prior_write_mask |= write_mask;
        if (!dec.valid && scalar_order_barrier(insn_is_32b_q[i], insn_q[i])) begin
          stop_scan = 1'b1;
        end
      end
    end

    simple_batch_valid = |simple_batch_mask;
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

  assign cva6_decoder_instr = curr_is_32b ? curr_insn : cva6_dec_instr;

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
  assign rd_addr  = cva6_decoded.rd;

  // A2 RAW interlock: stall a scalar that reads an integer register still
  // awaiting an in-flight vset VL writeback.  FP-source reads (frs1/frs2) target
  // the FRF, not the integer rd, so they are excluded.  The window is already
  // covered by the EP's vector-side wait, so this does not extend EP latency.
  logic vset_raw_stall;
  assign vset_raw_stall = vec_vset_inflight_i && (vec_vset_inflight_rd_i != 5'd0) &&
                          curr_slot_found &&
    ((!(CVA6Cfg.FpPresent && ariane_pkg::is_rs1_fpr(cva6_decoded.op)) &&
      (rs1_addr == vec_vset_inflight_rd_i)) ||
     (!(CVA6Cfg.FpPresent && ariane_pkg::is_rs2_fpr(cva6_decoded.op)) &&
      (rs2_addr == vec_vset_inflight_rd_i)));
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

  alu #(
    .CVA6Cfg(CVA6Cfg),
    .HasBranch(1'b1),
    .fu_data_t(fu_data_t)
  ) i_alu (
    .clk_i              (clk_i),
    .rst_ni             (rst_ni),
    .fu_data_i          (cva6_fu_data),
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
    .fu_data_i                (cva6_fu_data),
    .pc_i                     (cva6_decoded.pc),
    .is_zcmt_i                (cva6_decoded.is_zcmt),
    .is_compressed_instr_i    (cva6_decoded.is_compressed),
    .branch_valid_i           (curr_slot_found && (cva6_decoded.fu == CTRL_FLOW)),
    .branch_comp_res_i        (cva6_alu_branch_res),
    .branch_result_o          (cva6_branch_result),
    .branch_predict_i         (cva6_decoded.bp),
    .resolved_branch_o        (cva6_resolved_branch),
    .resolve_branch_o         (cva6_resolve_branch),
    .branch_exception_o       (cva6_branch_exception)
  );

  mult #(
    .CVA6Cfg(CVA6Cfg),
    .fu_data_t(fu_data_t)
  ) i_mult (
    .clk_i           (clk_i),
    .rst_ni          (rst_ni),
    .flush_i         (flush_i),
    .fu_data_i       (cva6_fu_data),
    .mult_valid_i    ((state_q == EXECUTE) && curr_slot_found &&
                      (cva6_decoded.fu == MULT) && !cva6_decoded.ex.valid &&
                      cva6_mult_ready),
    .result_o        (cva6_mult_result),
    .mult_valid_o    (cva6_mult_valid),
    .mult_ready_o    (cva6_mult_ready),
    .mult_trans_id_o (cva6_mult_trans_id)
  );

  fpu_wrap #(
    .CVA6Cfg(CVA6Cfg),
    .exception_t(exception_t),
    .fu_data_t(fu_data_t)
  ) i_fpu_wrap (
    .clk_i          (clk_i),
    .rst_ni         (rst_ni),
    .flush_i        (flush_i),
    .fpu_valid_i    ((state_q == EXECUTE) && curr_slot_found && fpu_issue),
    .fpu_ready_o    (cva6_fpu_ready),
    .fu_data_i      (cva6_fu_data),
    .fpu_fmt_i      (cva6_decoder_instr[26:25]),
    .fpu_rm_i       (cva6_decoder_instr[14:12]),
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
    wb_addr         = rd_addr;
    wb_data         = '0;
    unsupported     = 1'b0;
    branch_resolved = 1'b0;
    branch_taken    = 1'b0;
    branch_target   = '0;
    fpu_issue       = 1'b0;
    fpu_writes_fpr  = 1'b0;
    fpu_writes_xrf  = 1'b0;
    hdv_task_ret    = 1'b0;

    if (curr_slot_found) begin
      unsupported = cva6_decoded.ex.valid;
      hdv_task_ret = TreatRetAsTaskExit &&
                     (cva6_decoder_instr == 32'h00008067);

      unique case (cva6_decoded.fu)
        ALU: begin
          wb_en   = !unsupported;
          wb_data = cva6_alu_result;
        end

        CTRL_FLOW: begin
          branch_resolved = cva6_resolve_branch && !cva6_branch_exception.valid &&
                            !unsupported && !hdv_task_ret;
          branch_taken    = cva6_resolved_branch.is_taken;
          branch_target   = addr_t'(cva6_resolved_branch.target_address);
          wb_en           = branch_resolved && (cva6_decoded.rd != 5'd0) &&
                            !ariane_pkg::op_is_branch(cva6_decoded.op);
          wb_data         = {{(XLEN-CVA6Cfg.VLEN){cva6_branch_result[CVA6Cfg.VLEN-1]}},
                             cva6_branch_result};
          unsupported     = unsupported || (cva6_branch_exception.valid && !hdv_task_ret);
        end

        CSR: begin
          if (csr_supported) begin
            wb_en   = !unsupported;
            wb_data = csr_rdata;
          end else if (cva6_decoder_instr == 32'h00000013 ||
                       cva6_decoder_instr == 32'h00100073) begin
            wb_en = 1'b0;
          end else begin
            unsupported = 1'b1;
          end
        end

        FPU: begin
          fpu_issue      = !unsupported;
          fpu_writes_fpr = ariane_pkg::is_rd_fpr(cva6_decoded.op);
          fpu_writes_xrf = !fpu_writes_fpr && (cva6_decoded.rd != 5'd0);
        end

        FPU_VEC,
        CVXIF,
        ACCEL,
        AES: begin
          unsupported = 1'b1;
        end

        LOAD,
        STORE: begin
          unsupported = cva6_decoded.ex.valid || lsu_misaligned;
        end

        MULT: begin
          unsupported = cva6_decoded.ex.valid;
        end

        NONE: begin
          unsupported = (cva6_decoder_instr != 32'h00000013);
        end

        default: begin
          unsupported = 1'b1;
        end
      endcase
    end
  end

  assign scalar_ready_o         = (state_q == IDLE);
  assign scalar_accepted_o      = (state_q == DONE);
  assign scalar_error_o         = (state_q == DONE) && error_seen_q;
  assign redirect_valid_o       = (state_q == REDIRECT) && redirect_pending_q;
  assign redirect_pc_o          = redirect_pc_q;
  assign branch_resolved_valid_o = branch_resolved_pulse_q;
  assign branch_taken_o         = branch_taken_q;
  assign branch_pc_o            = branch_pc_q;
  assign branch_target_o        = branch_target_q;
  assign task_complete_o        = (state_q == DONE) && task_complete_pending_q &&
                                  !error_seen_q;

  assign vec_operand_req_ready_o = 1'b1;
  assign vec_rs1_data_o          = (vec_rs1_addr_i == 5'd0) ? '0 : xrf_q[vec_rs1_addr_i];
  assign vec_rs2_data_o          = (vec_rs2_addr_i == 5'd0) ? '0 : xrf_q[vec_rs2_addr_i];
  assign vec_frs1_data_o         = frf_q[vec_frs1_addr_i];
  assign scalar_axi_req_o        = scalar_axi_req;

  always_comb begin : p_csr_stub
    csr_addr      = cva6_decoder_instr[31:20];
    csr_op_supported = 1'b0;
    csr_addr_supported = 1'b0;
    csr_supported = 1'b0;
    csr_write     = 1'b0;
    csr_rdata     = '0;
    csr_wdata     = rs1_data;
    csr_wmask     = rs1_data;

    unique case (cva6_decoder_instr[14:12])
      riscv::CSRRW: begin
        csr_op_supported = 1'b1;
        csr_write     = 1'b1;
        csr_wdata     = rs1_data;
      end
      riscv::CSRRS: begin
        csr_op_supported = 1'b1;
        csr_write     = (rs1_addr != 5'd0);
      end
      riscv::CSRRC: begin
        csr_op_supported = 1'b1;
        csr_write     = (rs1_addr != 5'd0);
      end
      riscv::CSRRWI: begin
        csr_op_supported = 1'b1;
        csr_write     = 1'b1;
        csr_wdata     = {{(XLEN-5){1'b0}}, rs1_addr};
        csr_wmask     = csr_wdata;
      end
      riscv::CSRRSI: begin
        csr_op_supported = 1'b1;
        csr_write     = (rs1_addr != 5'd0);
        csr_wmask     = {{(XLEN-5){1'b0}}, rs1_addr};
      end
      riscv::CSRRCI: begin
        csr_op_supported = 1'b1;
        csr_write     = (rs1_addr != 5'd0);
        csr_wmask     = {{(XLEN-5){1'b0}}, rs1_addr};
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

  always_comb begin : p_lsu_decode
    automatic int unsigned byte_offset;
    automatic int unsigned transfer_bytes;
    automatic logic [AxiDataWidth-1:0] raw_load_shifted;
    automatic logic [XLEN-1:0] store_operand;

    lsu_is_load = (cva6_decoded.fu == LOAD);
    lsu_is_fp = cva6_decoded.op inside {FLD, FLW, FLH, FLB, FSD, FSW, FSH, FSB};
    lsu_addr = addr_t'(cva6_fu_data.operand_a + cva6_fu_data.imm);
    lsu_size = ariane_pkg::extract_transfer_size(cva6_decoded.op);
    lsu_misaligned = 1'b0;
    unique case (lsu_size)
      2'b11: lsu_misaligned = |lsu_addr[2:0];
      2'b10: lsu_misaligned = |lsu_addr[1:0];
      2'b01: lsu_misaligned = lsu_addr[0];
      default: lsu_misaligned = 1'b0;
    endcase

    byte_offset = lsu_addr[$clog2(AxiDataWidth/8)-1:0];
    transfer_bytes = 1 << lsu_size;
    store_operand = lsu_is_fp ? frf_q[rs2_addr] : cva6_fu_data.operand_b;
    lsu_store_strb = (({(AxiDataWidth/8){1'b0}} | ((1 << transfer_bytes) - 1)) << byte_offset);
    lsu_store_data = AxiDataWidth'(store_operand) << (8 * byte_offset);

    raw_load_shifted = scalar_axi_resp_i.r.data >> (8 * byte_offset);
    unique case (cva6_decoded.op)
      LB:  lsu_load_data = {{(XLEN-8){raw_load_shifted[7]}}, raw_load_shifted[7:0]};
      LBU: lsu_load_data = {{(XLEN-8){1'b0}}, raw_load_shifted[7:0]};
      LH:  lsu_load_data = {{(XLEN-16){raw_load_shifted[15]}}, raw_load_shifted[15:0]};
      LHU: lsu_load_data = {{(XLEN-16){1'b0}}, raw_load_shifted[15:0]};
      LW:  lsu_load_data = {{(XLEN-32){raw_load_shifted[31]}}, raw_load_shifted[31:0]};
      LWU: lsu_load_data = {{(XLEN-32){1'b0}}, raw_load_shifted[31:0]};
      FLW: lsu_load_data = {{(XLEN-32){1'b1}}, raw_load_shifted[31:0]};
      FLD: lsu_load_data = raw_load_shifted[XLEN-1:0];
      default: lsu_load_data = raw_load_shifted[XLEN-1:0];
    endcase

    lsu_resp_error = 1'b0;
    if (state_q == LSU_R) begin
      lsu_resp_error = scalar_axi_resp_i.r.resp != axi_pkg::RESP_OKAY;
    end else if (state_q == LSU_B) begin
      lsu_resp_error = scalar_axi_resp_i.b.resp != axi_pkg::RESP_OKAY;
    end
  end

  always_comb begin : p_scalar_axi_req
    scalar_axi_req = '0;
    scalar_axi_req.ar.id     = '0;
    scalar_axi_req.ar.addr   = lsu_addr;
    scalar_axi_req.ar.len    = '0;
    scalar_axi_req.ar.size   = {1'b0, lsu_size};
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

    scalar_axi_req.ar_valid = (state_q == LSU_AR) && !flush_i;
    scalar_axi_req.r_ready  = (state_q == LSU_R)  && !flush_i;
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
    branch_resolved_pulse_d = 1'b0;
    branch_taken_d = branch_taken_q;
    branch_pc_d = branch_pc_q;
    branch_target_d = branch_target_q;
    remaining_slots = insn_valid_q;

    for (int unsigned i = 0; i < 32; i++) begin
      xrf_d[i] = xrf_q[i];
      frf_d[i] = frf_q[i];
    end

    if (vec_vset_wb_valid_i && (vec_vset_wb_rd_i != 5'd0)) begin
      xrf_d[vec_vset_wb_rd_i] = vec_vset_wb_data_i;
    end
    if (vec_vset_wb_valid_i) begin
      csr_vl_d = vec_vset_wb_data_i;
    end

    unique case (state_q)
      IDLE: begin
        redirect_pending_d = 1'b0;
        error_seen_d = 1'b0;
        task_complete_pending_d = 1'b0;
        if (scalar_valid_i) begin
          insn_valid_d = scalar_insn_valid_i;
          insn_d = scalar_insn_i;
          insn_is_32b_d = scalar_insn_is_32b_i;
          insn_pc_d = scalar_insn_pc_i;
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

        if (vset_raw_stall || complex_simple_raw_stall) begin
          // Hold only the non-ALU lane: independent simple ALU slots selected
          // above have already been consumed and written back this cycle.
          state_d = EXECUTE;
        end else if (curr_slot_found) begin
          if ((cva6_decoded.fu == MULT) && !unsupported) begin
            if (cva6_mult_ready) begin
              insn_valid_d = remaining_slots;
              state_d = WAIT_MULT;
            end
          end else if ((cva6_decoded.fu == FPU) && !unsupported) begin
            if (cva6_fpu_ready) begin
              insn_valid_d = remaining_slots;
              state_d = WAIT_FPU;
            end
          end else if ((cva6_decoded.fu inside {LOAD, STORE}) && !unsupported) begin
            insn_valid_d = remaining_slots;
            state_d = (cva6_decoded.fu == LOAD) ? LSU_AR : LSU_AW;
          end else begin
            remaining_slots[curr_slot_idx] = 1'b0;
            insn_valid_d = remaining_slots;

            if (wb_en && !unsupported && (wb_addr != 5'd0)) begin
              if (wb_is_fpr) begin
                frf_d[wb_addr] = wb_data;
              end else begin
                xrf_d[wb_addr] = wb_data;
              end
            end

            if (!unsupported && (cva6_decoded.fu == CSR) && csr_write) begin
              unique case (csr_addr)
                riscv::CSR_FRM: begin
                  unique case (cva6_decoder_instr[14:12])
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
                  unique case (cva6_decoder_instr[14:12])
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
                  unique case (cva6_decoder_instr[14:12])
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
                  unique case (cva6_decoder_instr[14:12])
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
              branch_pc_d = curr_pc;
              branch_target_d = branch_target;
              if (branch_taken) begin
                redirect_pending_d = 1'b1;
                redirect_pc_d = branch_target;
              end
            end

            if (unsupported) begin
              error_seen_d = 1'b1;
            end
            if (!unsupported && hdv_task_ret) begin
              task_complete_pending_d = 1'b1;
            end

            state_d = (|remaining_slots) ? EXECUTE : DONE;
          end
        end else if (simple_batch_valid) begin
          state_d = (|remaining_slots) ? EXECUTE : DONE;
        end else begin
          state_d = DONE;
        end
      end

      WAIT_MULT: begin
        if (cva6_mult_valid) begin
          remaining_slots = insn_valid_q;
          remaining_slots[curr_slot_idx] = 1'b0;
          insn_valid_d = remaining_slots;
          if (cva6_decoded.rd != 5'd0) begin
            xrf_d[cva6_decoded.rd] = cva6_mult_result;
          end
          state_d = (|remaining_slots) ? EXECUTE : DONE;
        end
      end

      WAIT_FPU: begin
        if (cva6_fpu_valid) begin
          remaining_slots = insn_valid_q;
          remaining_slots[curr_slot_idx] = 1'b0;
          insn_valid_d = remaining_slots;
          if (!cva6_fpu_exception.valid && (cva6_decoded.rd != 5'd0)) begin
            if (fpu_writes_fpr) begin
              frf_d[cva6_decoded.rd] = XLEN'(cva6_fpu_result);
            end else if (fpu_writes_xrf) begin
              xrf_d[cva6_decoded.rd] = XLEN'(cva6_fpu_result);
            end
          end
          if (cva6_fpu_exception.valid) begin
            error_seen_d = 1'b1;
          end
          state_d = (|remaining_slots) ? EXECUTE : DONE;
        end
      end

      LSU_AR: begin
        if (scalar_axi_resp_i.ar_ready) begin
          state_d = LSU_R;
        end
      end

      LSU_R: begin
        if (scalar_axi_resp_i.r_valid) begin
          remaining_slots = insn_valid_q;
          remaining_slots[curr_slot_idx] = 1'b0;
          insn_valid_d = remaining_slots;
          if (!lsu_resp_error && (cva6_decoded.rd != 5'd0)) begin
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
          remaining_slots[curr_slot_idx] = 1'b0;
          insn_valid_d = remaining_slots;
          if (lsu_resp_error) begin
            error_seen_d = 1'b1;
          end
          state_d = (|remaining_slots) ? EXECUTE : DONE;
        end
      end

      DONE: begin
        task_complete_pending_d = 1'b0;
        state_d = redirect_pending_q ? REDIRECT : IDLE;
      end

      REDIRECT: begin
        redirect_pending_d = 1'b0;
        state_d = IDLE;
      end

      default: state_d = IDLE;
    endcase

    xrf_d[0] = '0;

    if (flush_i) begin
      state_d = IDLE;
      insn_valid_d = '0;
      redirect_pending_d = 1'b0;
      error_seen_d = 1'b0;
      task_complete_pending_d = 1'b0;
      branch_resolved_pulse_d = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      state_q <= IDLE;
      insn_valid_q <= '0;
      insn_q <= '0;
      insn_is_32b_q <= '0;
      insn_pc_q <= '0;
      cycle_q <= 64'd0;
      redirect_pending_q <= 1'b0;
      redirect_pc_q <= '0;
      error_seen_q <= 1'b0;
      task_complete_pending_q <= 1'b0;
      branch_resolved_pulse_q <= 1'b0;
      branch_taken_q <= 1'b0;
      branch_pc_q <= '0;
      branch_target_q <= '0;
      csr_vl_q <= '0;
      csr_vtype_q <= '0;
      csr_frm_q <= 3'b000;
      for (int unsigned i = 0; i < 32; i++) begin
        xrf_q[i] <= '0;
        frf_q[i] <= '0;
      end
      xrf_q[1] <= InitialRa;
      xrf_q[10] <= InitialA0;
      xrf_q[11] <= InitialA1;
      xrf_q[12] <= InitialA2;
      frf_q[10] <= InitialFa0;
    end else begin
      state_q <= state_d;
      insn_valid_q <= insn_valid_d;
      insn_q <= insn_d;
      insn_is_32b_q <= insn_is_32b_d;
      insn_pc_q <= insn_pc_d;
      cycle_q <= cycle_d;
      redirect_pending_q <= redirect_pending_d;
      redirect_pc_q <= redirect_pc_d;
      error_seen_q <= error_seen_d;
      task_complete_pending_q <= task_complete_pending_d;
      branch_resolved_pulse_q <= branch_resolved_pulse_d;
      branch_taken_q <= branch_taken_d;
      branch_pc_q <= branch_pc_d;
      branch_target_q <= branch_target_d;
      csr_vl_q <= csr_vl_d;
      csr_vtype_q <= csr_vtype_d;
      csr_frm_q <= csr_frm_d;
      for (int unsigned i = 0; i < 32; i++) begin
        xrf_q[i] <= xrf_d[i];
        frf_q[i] <= frf_d[i];
      end
    end
  end

  always_ff @(posedge clk_i) begin : p_unsupported_report
    if (rst_ni && (state_q == EXECUTE) && curr_slot_found && unsupported) begin
      $warning("[HDV] cva6_hdv_scalar_backend unsupported scalar instruction pc=0x%016h insn=0x%08h is32=%0b",
               curr_pc, curr_insn, curr_is_32b);
    end
  end

  logic unused_vec_operand_req_valid;
  assign unused_vec_operand_req_valid = vec_operand_req_valid_i;

endmodule : cva6_hdv_scalar_backend
