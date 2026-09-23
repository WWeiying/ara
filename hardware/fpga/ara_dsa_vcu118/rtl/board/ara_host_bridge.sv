// SPDX-License-Identifier: SHL-0.51
`include "axi/typedef.svh"

module ara_host_bridge #(
  parameter type axi_req_t = logic,
  parameter type axi_rsp_t = logic,
  parameter type reg_req_t = logic,
  parameter type reg_rsp_t = logic
) (
  input logic clk_i, board_rst_ni, soc_rst_ni,
  output axi_req_t mem_req_o,
  input axi_rsp_t mem_rsp_i,
  output reg_req_t debug_req_o,
  input reg_rsp_t debug_rsp_i
);
  typedef logic [31:0] word_t;
  typedef logic [3:0] strb_t;
  `AXI_LITE_TYPEDEF_ALL(debug_axi, word_t, word_t, strb_t)
  debug_axi_req_t debug_req;
  debug_axi_resp_t debug_rsp;
  logic [63:0] awaddr, araddr;
  assign mem_req_o.aw.addr = awaddr[$bits(mem_req_o.aw.addr)-1:0];
  assign mem_req_o.ar.addr = araddr[$bits(mem_req_o.ar.addr)-1:0];
  assign mem_req_o.aw.atop = '0;
  assign mem_req_o.aw.region = '0;
  assign mem_req_o.aw.user = '0;
  assign mem_req_o.w.user = '0;
  assign mem_req_o.ar.region = '0;
  assign mem_req_o.ar.user = '0;

  // Two IP cores, not a demux behind one stalled AXI master. The local
  // debug IP stays out of the SoC/MIG reset and cannot access the main bus.
  jtag_mem i_jtag_mem (
    .aclk(clk_i), .aresetn(soc_rst_ni),
    .m_axi_awid(mem_req_o.aw.id), .m_axi_awaddr(awaddr),
    .m_axi_awlen(mem_req_o.aw.len), .m_axi_awsize(mem_req_o.aw.size),
    .m_axi_awburst(mem_req_o.aw.burst), .m_axi_awlock(mem_req_o.aw.lock),
    .m_axi_awcache(mem_req_o.aw.cache), .m_axi_awprot(mem_req_o.aw.prot),
    .m_axi_awqos(mem_req_o.aw.qos), .m_axi_awvalid(mem_req_o.aw_valid),
    .m_axi_awready(mem_rsp_i.aw_ready),
    .m_axi_wdata(mem_req_o.w.data), .m_axi_wstrb(mem_req_o.w.strb),
    .m_axi_wlast(mem_req_o.w.last), .m_axi_wvalid(mem_req_o.w_valid),
    .m_axi_wready(mem_rsp_i.w_ready), .m_axi_bid(mem_rsp_i.b.id),
    .m_axi_bresp(mem_rsp_i.b.resp), .m_axi_bvalid(mem_rsp_i.b_valid),
    .m_axi_bready(mem_req_o.b_ready), .m_axi_arid(mem_req_o.ar.id),
    .m_axi_araddr(araddr), .m_axi_arlen(mem_req_o.ar.len),
    .m_axi_arsize(mem_req_o.ar.size), .m_axi_arburst(mem_req_o.ar.burst),
    .m_axi_arlock(mem_req_o.ar.lock), .m_axi_arcache(mem_req_o.ar.cache),
    .m_axi_arprot(mem_req_o.ar.prot), .m_axi_arqos(mem_req_o.ar.qos),
    .m_axi_arvalid(mem_req_o.ar_valid), .m_axi_arready(mem_rsp_i.ar_ready),
    .m_axi_rid(mem_rsp_i.r.id), .m_axi_rdata(mem_rsp_i.r.data),
    .m_axi_rresp(mem_rsp_i.r.resp), .m_axi_rlast(mem_rsp_i.r.last),
    .m_axi_rvalid(mem_rsp_i.r_valid), .m_axi_rready(mem_req_o.r_ready)
  );
  jtag_debug i_jtag_debug (
    .aclk(clk_i), .aresetn(board_rst_ni),
    .m_axi_awaddr(debug_req.aw.addr), .m_axi_awprot(debug_req.aw.prot),
    .m_axi_awvalid(debug_req.aw_valid), .m_axi_awready(debug_rsp.aw_ready),
    .m_axi_wdata(debug_req.w.data), .m_axi_wstrb(debug_req.w.strb),
    .m_axi_wvalid(debug_req.w_valid), .m_axi_wready(debug_rsp.w_ready),
    .m_axi_bresp(debug_rsp.b.resp), .m_axi_bvalid(debug_rsp.b_valid),
    .m_axi_bready(debug_req.b_ready), .m_axi_araddr(debug_req.ar.addr),
    .m_axi_arprot(debug_req.ar.prot), .m_axi_arvalid(debug_req.ar_valid),
    .m_axi_arready(debug_rsp.ar_ready), .m_axi_rdata(debug_rsp.r.data),
    .m_axi_rresp(debug_rsp.r.resp), .m_axi_rvalid(debug_rsp.r_valid),
    .m_axi_rready(debug_req.r_ready)
  );
  axi_lite_to_reg #(
    .ADDR_WIDTH(32), .DATA_WIDTH(32), .BUFFER_DEPTH(2),
    .axi_lite_req_t(debug_axi_req_t), .axi_lite_rsp_t(debug_axi_resp_t),
    .reg_req_t(reg_req_t), .reg_rsp_t(reg_rsp_t)
  ) i_debug_regs (
    .clk_i(clk_i), .rst_ni(board_rst_ni),
    .axi_lite_req_i(debug_req), .axi_lite_rsp_o(debug_rsp),
    .reg_req_o(debug_req_o), .reg_rsp_i(debug_rsp_i)
  );
endmodule
