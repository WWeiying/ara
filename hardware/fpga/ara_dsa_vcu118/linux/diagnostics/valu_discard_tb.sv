// SPDX-License-Identifier: SHL-0.51
// Operation type follows ETH Zurich/Bologna lane.sv; standalone completion probe.
`timescale 1ns/1ps
module valu_discard_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
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
    vlen_t vl, vstart;
    vtype_t vtype;
  } operation_t;
  logic clk = 0, rst = 0, valid = 0, ready;
  operation_t operation;
  logic [NrVInsn-1:0] done;
  logic req, grant;
  vid_t id;
  logic [9:0] addr;
  logic [63:0] data;
  logic [7:0] be;
  int cycles = 0, completed = 0;
  int writes[4] = '{default:0};
  int gap = 0, backpressure = 0;
  int pattern = 0, elements = 256;
  logic [3:0] accepted_ids = 0, completed_ids = 0;
  function automatic logic [7:0] test_byte(input int instruction);
    if (!pattern) return 8'hff;
    case (instruction)
      0: return 8'ha5;
      1: return 8'h00;
      2: return 8'h5a;
      default: return 8'hff;
    endcase
  endfunction
  logic held = 0;
  logic [81:0] held_payload;
  always #5 clk = ~clk;
  assign grant = req && (!backpressure || cycles % 7 < 4);
`ifdef MAPPED_VALU
  `MAPPED_VALU dut (
`else
  valu #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic [9:0]),
         .vfu_operation_t(operation_t)) dut (
`endif
    .clk_i(clk), .rst_ni(rst), .lane_id_i(2'b0), .alu_vxrm_i(2'b0),
`ifdef MAPPED_VALU
    .\vfu_operation_i[id] (operation.id),
    .\vfu_operation_i[op] (operation.op),
    .\vfu_operation_i[vm] (operation.vm),
    .\vfu_operation_i[use_vs1] (operation.use_vs1),
    .\vfu_operation_i[use_vs2] (operation.use_vs2),
    .\vfu_operation_i[use_vd_op] (operation.use_vd_op),
    .\vfu_operation_i[preserve_narrow_vd] (operation.preserve_narrow_vd),
    .\vfu_operation_i[scalar_op] (operation.scalar_op),
    .\vfu_operation_i[use_scalar_op] (operation.use_scalar_op),
    .\vfu_operation_i[skip_sldu_operand] (operation.skip_sldu_operand),
    .\vfu_operation_i[vfu] (operation.vfu),
    .\vfu_operation_i[vd] (operation.vd),
    .\vfu_operation_i[use_vd] (operation.use_vd),
    .\vfu_operation_i[swap_vs2_vd_op] (operation.swap_vs2_vd_op),
    .\vfu_operation_i[fp_rm] (operation.fp_rm),
    .\vfu_operation_i[wide_fp_imm] (operation.wide_fp_imm),
    .\vfu_operation_i[cvt_resize] (operation.cvt_resize),
    .\vfu_operation_i[vl] (operation.vl),
    .\vfu_operation_i[vstart] (operation.vstart),
    .\vfu_operation_i[vtype][vill] (operation.vtype.vill),
    .\vfu_operation_i[vtype][vma] (operation.vtype.vma),
    .\vfu_operation_i[vtype][vta] (operation.vtype.vta),
    .\vfu_operation_i[vtype][vsew] (operation.vtype.vsew),
    .\vfu_operation_i[vtype][vlmul] (operation.vtype.vlmul),
    .\alu_operand_i[0] (64'b0), .\alu_operand_i[1] (64'b0),
`else
    .vfu_operation_i(operation), .alu_operand_i('0),
`endif
    .vfu_operation_valid_i(valid),
    .alu_ready_o(ready), .alu_vinsn_done_o(done),
    .alu_operand_valid_i('0),
    .alu_result_req_o(req), .alu_result_id_o(id), .alu_result_addr_o(addr),
    .alu_result_wdata_o(data), .alu_result_be_o(be), .alu_result_gnt_i(grant),
    .alu_red_ready_i(1'b1), .sldu_operand_i('0), .sldu_alu_valid_i(1'b0),
    .mask_operand_ready_i(1'b1), .mask_i('1), .mask_valid_i(1'b0)
  );
  always @(posedge clk) if (rst) begin
    cycles <= cycles + 1;
    if (valid && ready) begin
      if (operation.id >= 4 || accepted_ids[operation.id])
        $fatal(1, "unexpected/duplicate instruction acceptance");
      accepted_ids[operation.id] = 1'b1;
    end
    if (held && (!req || {id, addr[6:0], data, be} !== held_payload))
      $fatal(1, "pending result changed without a grant");
    held <= req && !grant;
    held_payload <= {id, addr[6:0], data, be};
    if ($test$plusargs("TRACE") && cycles < 40) begin
      $display("TRACE cycle=%0d valid=%b ready=%b req=%b grant=%b id=%0d addr=%h data=%h be=%h done=%h",
               cycles, valid, ready, req, grant, id, addr, data, be, done);
`ifdef MAPPED_ROUTED_TRACE
      $display("QUEUE read=%b write=%b replicas=%b%b valid=%b",
               dut.result_queue_read_pnt_q, dut.result_queue_write_pnt_q,
               dut.\result_queue_write_pnt_q_reg[0]_rep_n_0 ,
               dut.\result_queue_write_pnt_q_reg[0]_rep__0_n_0 ,
               dut.result_queue_valid_q);
      $display("DATA0 next=%h ce=%b DATA1 next=%h",
               dut.\result_queue_d[0][wdata] ,
               dut.\result_queue_q[0][wdata][63]_i_1_n_0 ,
               dut.\result_queue_d[1][wdata] );
`endif
    end
    if (req && grant) begin
      logic [7:0] expected_be;
      if (id >= 4 || !accepted_ids[id] || completed_ids[id])
        $fatal(1, "write for unaccepted/completed instruction id=%0d", id);
      expected_be = 8'((1 << ((elements - writes[id]*8 >= 8) ?
                             8 : elements - writes[id]*8)) - 1);
      if (writes[id] >= (elements+7)/8 || be !== expected_be)
        $fatal(1, "bad result id=%0d data=%h be=%h", id, data, be);
      for (int b=0; b<8; b++)
        if (expected_be[b] && data[8*b +: 8] !== test_byte(id))
          $fatal(1, "bad data id=%0d byte=%0d data=%h", id, b, data);
`ifdef MAPPED_VALU
      // The routed parent consumes only seven word-address bits. Exported
      // cell ports retain three undriven, optimized-away upper bits.
      if ((addr[9:7] !== 3'bzzz && addr[9:7] !== 3'b000) ||
          addr[6:0] !== 7'(id * 32 + writes[id]))
`else
      if (addr !== (id * 32 + writes[id]))
`endif
        $fatal(1, "bad address id=%0d addr=%0d count=%0d", id, addr, writes[id]);
      writes[id]++;
    end
    for (int i=0; i<NrVInsn; i++) if (done[i]) begin
      if (i >= 4 || !accepted_ids[i] || completed_ids[i] ||
          writes[i] != (elements+7)/8)
        $fatal(1, "unexpected/duplicate/early completion id=%0d", i);
      completed_ids[i] = 1'b1;
      completed++;
      $display("DONE id=%0d cycle=%0d writes=%0d", i, cycles, writes[i]);
    end
    if (completed == 4) begin
      if (completed_ids !== 4'b1111) $fatal(1, "missing completion");
      $display("VALU_DISCARD_PASS gap=%0d backpressure=%0d pattern=%0d vl=%0d",
               gap, backpressure, pattern, elements);
      $finish;
    end
    if (cycles > 2000) $fatal(1, "completion timeout completed=%0d", completed);
  end
  initial begin
    void'($value$plusargs("GAP=%d", gap));
    void'($value$plusargs("BACKPRESSURE=%d", backpressure));
    void'($value$plusargs("PATTERN=%d", pattern));
    void'($value$plusargs("VL=%d", elements));
    if (elements < 1 || elements > 256) $fatal(1, "VL outside test capacity");
    operation = '0;
    repeat (20) @(negedge clk);
    rst = 1;
    repeat (2) @(negedge clk);
    for (int i=0; i<4; i++) begin
      operation = '0;
      operation.id = vid_t'(i);
      operation.op = VMERGE;
      operation.vm = 1;
      operation.scalar_op = {8{test_byte(i)}};
      operation.use_scalar_op = 1;
      operation.vfu = VFU_Alu;
      operation.vd = 5'(8*i);
      operation.use_vd = 1;
      operation.vl = vlen_t'(elements);
      operation.vtype = '{vma:1, vta:1, vsew:EW8, vlmul:LMUL_8, default:'0};
      valid = 1;
      do @(posedge clk); while (!ready);
      @(negedge clk);
      valid = 0;
      repeat (gap) @(negedge clk);
    end
  end
endmodule
