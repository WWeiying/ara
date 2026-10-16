// SPDX-License-Identifier: SHL-0.51
// Zero-offset slide still exercises the real partial-write result queue.
module sldu_queue_probe import ara_pkg::*; import rvv_pkg::*; (
  input logic clk_i,rst_ni,
  input logic [10:0] vl_i,
  input logic [1:0] sew_i,
  input logic req_i,
  output logic ready_o,
  input logic [255:0] rdata_i,
  input logic rvalid_i,
  output logic rready_o,
  input logic [7:0] len_i,
  input logic addrvalid_i,
  output logic addrready_o,
  input logic [3:0] grant_i,final_i,
  output logic [3:0] valid_o,
  output logic [3:0][63:0] data_o,
  output logic [3:0][7:0] be_o,
  output logic [3:0][9:0] addr_o,
  output logic [3:0][2:0] id_o,
  output logic [NrVInsn-1:0] done_o
);
  typedef logic [10:0] vlen_t;
  `include "ara/ara_typedef.svh"
  pe_req_t request;
  pe_resp_t response;
  logic [3:0] operand_ready;
  always_comb begin
    request='0;
    request.id=3; request.op=VSLIDEDOWN; request.vfu=VFU_SlideUnit;
    request.vm=1; request.vd=8; request.use_vd=1; request.vl=vl_i;
    request.vtype.vsew=vew_e'({1'b0,sew_i});
    request.vtype.vlmul=LMUL_4; request.emul=LMUL_4;
    request.eew_vs2=vew_e'({1'b0,sew_i});
  end
  assign rready_o=&operand_ready;
  assign addrready_o=0;
  assign done_o=response.vinsn_done;
  sldu #(.NrLanes(4),.VLEN(1024),.vaddr_t(logic[9:0]),
    .pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t)) dut (
    .clk_i,.rst_ni,.pe_req_i(request),.pe_req_valid_i(req_i),
    .pe_vinsn_running_i('1),.pe_req_ready_o(ready_o),.pe_resp_o(response),
    .maintenance_drain_i(1'b0),.sldu_operand_i(rdata_i),
    .sldu_operand_valid_i({4{rvalid_i}}),.sldu_operand_reduction_i('0),
    .sldu_operand_ready_o(operand_ready),.sldu_result_req_o(valid_o),
    .sldu_result_id_o(id_o),.sldu_result_addr_o(addr_o),.sldu_result_wdata_o(data_o),
    .sldu_result_be_o(be_o),.sldu_result_gnt_i(grant_i),.sldu_result_final_gnt_i(final_i),
    .mask_i('0),.mask_valid_i('0)
  );
`ifndef SYNTHESIS
  always @(posedge clk_i) if(rst_ni && rvalid_i)
    assert(operand_ready=='0 || operand_ready=='1)
      else $fatal(1,"Probe requires synchronized operand acceptance");
`endif
endmodule
