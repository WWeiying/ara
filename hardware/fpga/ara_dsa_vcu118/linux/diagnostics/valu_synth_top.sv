package valu_probe_pkg;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef struct packed {
    vid_t id;
    ara_op_e op;
    logic vm, use_vs1, use_vs2, use_vd_op, preserve_narrow_vd;
    elen_t scalar_op;
    logic use_scalar_op, skip_sldu_operand;
    vfu_e vfu;
    logic [4:0] vd;
    logic use_vd, swap_vs2_vd_op;
    fpnew_pkg::roundmode_e fp_rm;
    logic wide_fp_imm;
    resize_e cvt_resize;
    logic [10:0] vl, vstart;
    vtype_t vtype;
  } operation_t;
endpackage

module valu_synth_top import ara_pkg::*; (
  input logic clk_i, rst_ni,
  input logic [1:0] lane_id_i,
  output logic vxsat_flag_o,
  input logic [1:0] alu_vxrm_i,
  input valu_probe_pkg::operation_t vfu_operation_i,
  input logic vfu_operation_valid_i,
  output logic alu_ready_o,
  output logic [NrVInsn-1:0] alu_vinsn_done_o,
  output logic alu_red_complete_o,
  input logic [1:0][63:0] alu_operand_i,
  input logic [1:0] alu_operand_valid_i,
  output logic [1:0] alu_operand_ready_o,
  output logic alu_result_req_o,
  output vid_t alu_result_id_o,
  output logic [9:0] alu_result_addr_o,
  output logic [63:0] alu_result_wdata_o,
  output logic [7:0] alu_result_be_o,
  input logic alu_result_gnt_i,
  output logic alu_red_valid_o,
  input logic alu_red_ready_i,
  input logic [63:0] sldu_operand_i,
  input logic sldu_alu_valid_i,
  output logic sldu_alu_ready_o,
  output logic [63:0] mask_operand_o,
  output logic mask_operand_valid_o,
  input logic mask_operand_ready_i,
  input logic [7:0] mask_i,
  input logic mask_valid_i,
  output logic mask_ready_o
);
  valu #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic [9:0]),
         .vfu_operation_t(valu_probe_pkg::operation_t)) dut (.*);
endmodule
