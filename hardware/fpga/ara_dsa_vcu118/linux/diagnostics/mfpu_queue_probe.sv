// Restricted integer multiply path; production VMFPU queue is not rewritten.
module mfpu_queue_probe import ara_pkg::*; import rvv_pkg::*; (
  input logic clk_i, rst_ni,
  input logic [2:0] id_i,
  input logic [4:0] vd_i,
  input logic [10:0] vl_i,
  input logic valid_i,
  output logic ready_o,
  input logic [63:0] operand_i,
  input logic operand_valid_i,
  output logic operand_ready_o,
  output logic req_o,
  input logic grant_i,
  output logic [2:0] id_o,
  output logic [9:0] addr_o,
  output logic [63:0] data_o,
  output logic [7:0] be_o, done_o
);
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
  operation_t operation;
  logic [2:0] operand_ready;
  always_comb begin
    operation = '0;
    operation.id = id_i;
    operation.op = VMUL;
    operation.vm = 1;
    operation.use_vs2 = 1;
    operation.scalar_op = 3;
    operation.use_scalar_op = 1;
    operation.vfu = VFU_MFpu;
    operation.vd = vd_i;
    operation.use_vd = 1;
    operation.vl = vl_i;
    operation.vtype = '{vma:1, vta:1, vsew:EW64, vlmul:LMUL_8, default:'0};
  end
  assign operand_ready_o = operand_ready[1];
`ifdef MFPU_PROBE_NO_FPU
  localparam fpu_support_e ProbeFPUSupport = FPUSupportNone;
`else
  localparam fpu_support_e ProbeFPUSupport = FPUSupportHalfSingleDouble;
`endif
  vmfpu #(.NrLanes(4), .VLEN(1024), .FPUSupport(ProbeFPUSupport),
          .CVA6Cfg(build_config_pkg::build_config(cva6_config_pkg::cva6_cfg)),
          .vaddr_t(logic [9:0]), .vfu_operation_t(operation_t)) dut (
    .clk_i, .rst_ni, .lane_id_i(2'b0), .mfpu_vxrm_i(2'b0),
    .vfu_operation_i(operation), .vfu_operation_valid_i(valid_i),
    .mfpu_ready_o(ready_o), .mfpu_vinsn_done_o(done_o),
    .reduction_global_any_active_i(1'b1),
    .mfpu_operand_i({64'b0, operand_i, 64'b0}),
    .mfpu_operand_valid_i({1'b0, operand_valid_i, 1'b0}),
    .mfpu_operand_ready_o(operand_ready),
    .mfpu_result_req_o(req_o), .mfpu_result_id_o(id_o),
    .mfpu_result_addr_o(addr_o), .mfpu_result_wdata_o(data_o),
    .mfpu_result_be_o(be_o), .mfpu_result_gnt_i(grant_i),
    .mfpu_red_ready_i(1'b1), .sldu_operand_i(64'b0), .sldu_mfpu_valid_i(1'b0),
    .mask_operand_ready_i(1'b1), .mask_i(8'hff), .mask_valid_i(1'b0)
  );
endmodule
