// SPDX-License-Identifier: SHL-0.51
// Full source VLDU, with an unmasked, non-faulting load interface for equivalence tests.
module vldu_queue_probe import ara_pkg::*; import rvv_pkg::*; (
  input logic clk_i, rst_ni,
  input logic [10:0] vl_i,
  input logic [1:0] sew_i,
  input logic req_i,
  output logic ready_o,
  input logic [127:0] rdata_i,
  input logic rvalid_i,
  output logic rready_o,
  input logic [7:0] len_i,
  input logic addrvalid_i,
  output logic addrready_o,
  input logic [3:0] grant_i, final_i,
  output logic [3:0] valid_o,
  output logic [3:0][63:0] data_o,
  output logic [3:0][7:0] be_o,
  output logic [3:0][9:0] addr_o,
  output logic [3:0][2:0] id_o,
  output logic [NrVInsn-1:0] done_o
);
  typedef logic [10:0] vlen_t;
  `include "ara/ara_typedef.svh"
  typedef struct packed { logic [127:0] data; } r_t;
  pe_req_t request;
  pe_resp_t response;
  addrgen_axi_req_t address;
  r_t r;
  always_comb begin
    request = '0;
    request.id = 3;
    request.op = VLE;
    request.vfu = VFU_LoadUnit;
    request.vm = 1;
    request.vd = 8;
    request.use_vd = 1;
    request.vl = vl_i;
    request.vtype.vsew = vew_e'({1'b0, sew_i});
    request.vtype.vlmul = LMUL_4;
    request.emul = LMUL_4;
    address = '0;
    address.addr = 'h80000000;
    address.size = 4;
    address.len = len_i;
    address.is_load = 1;
    r.data = rdata_i;
  end
  assign done_o = response.vinsn_done;
  vldu #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic [9:0]),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t),
    .AxiDataWidth(128), .AxiAddrWidth(64), .axi_r_t(r_t)) dut (
    .clk_i, .rst_ni, .axi_r_i(r), .axi_r_valid_i(rvalid_i), .axi_r_ready_o(rready_o),
    .pe_req_i(request), .pe_req_valid_i(req_i), .pe_vinsn_running_i('1),
    .pe_req_ready_o(ready_o), .pe_resp_o(response),
    .axi_addrgen_req_i(address), .axi_addrgen_req_valid_i(addrvalid_i),
    .axi_addrgen_req_ready_o(addrready_o), .addrgen_illegal_load_i(1'b0),
    .ldu_result_req_o(valid_o), .ldu_result_id_o(id_o), .ldu_result_addr_o(addr_o),
    .ldu_result_wdata_o(data_o), .ldu_result_be_o(be_o),
    .ldu_result_gnt_i(grant_i), .ldu_result_final_gnt_i(final_i),
    .lsu_ex_flush_i(1'b0), .mask_i('0), .mask_valid_i('0),
    .mask_owner_id_i('0), .mask_first_element_i('0)
  );
endmodule
