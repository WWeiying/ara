// SPDX-License-Identifier: SHL-0.51
// Test-only AXI endpoint, NOT a simulation of the Xilinx MIG or DDR PHY.
`include "axi/typedef.svh"
module ddr4 (
  input logic sys_rst, c0_sys_clk_i, c0_ddr4_aresetn,
  output logic c0_ddr4_ui_clk = 0,
  output logic c0_ddr4_ui_clk_sync_rst, c0_init_calib_complete,
  output logic addn_ui_clkout1, dbg_clk,
  output logic [511:0] dbg_bus,
  input logic [7:0] c0_ddr4_s_axi_awid,
  input logic [30:0] c0_ddr4_s_axi_awaddr,
  input logic [7:0] c0_ddr4_s_axi_awlen,
  input logic [2:0] c0_ddr4_s_axi_awsize,
  input logic [1:0] c0_ddr4_s_axi_awburst,
  input logic c0_ddr4_s_axi_awlock,
  input logic [3:0] c0_ddr4_s_axi_awcache,
  input logic [2:0] c0_ddr4_s_axi_awprot,
  input logic [3:0] c0_ddr4_s_axi_awqos,
  input logic c0_ddr4_s_axi_awvalid,
  output logic c0_ddr4_s_axi_awready,
  input logic [511:0] c0_ddr4_s_axi_wdata,
  input logic [63:0] c0_ddr4_s_axi_wstrb,
  input logic c0_ddr4_s_axi_wlast, c0_ddr4_s_axi_wvalid,
  output logic c0_ddr4_s_axi_wready,
  input logic c0_ddr4_s_axi_bready,
  output logic [7:0] c0_ddr4_s_axi_bid,
  output logic [1:0] c0_ddr4_s_axi_bresp,
  output logic c0_ddr4_s_axi_bvalid,
  input logic [7:0] c0_ddr4_s_axi_arid,
  input logic [30:0] c0_ddr4_s_axi_araddr,
  input logic [7:0] c0_ddr4_s_axi_arlen,
  input logic [2:0] c0_ddr4_s_axi_arsize,
  input logic [1:0] c0_ddr4_s_axi_arburst,
  input logic c0_ddr4_s_axi_arlock,
  input logic [3:0] c0_ddr4_s_axi_arcache,
  input logic [2:0] c0_ddr4_s_axi_arprot,
  input logic [3:0] c0_ddr4_s_axi_arqos,
  input logic c0_ddr4_s_axi_arvalid,
  output logic c0_ddr4_s_axi_arready,
  input logic c0_ddr4_s_axi_rready,
  output logic [7:0] c0_ddr4_s_axi_rid,
  output logic [511:0] c0_ddr4_s_axi_rdata,
  output logic [1:0] c0_ddr4_s_axi_rresp,
  output logic c0_ddr4_s_axi_rlast, c0_ddr4_s_axi_rvalid
);
  timeunit 1ns;
  timeprecision 1ps;
  // Not phase-aligned with the 50 MHz source; no metastability is modeled.
  initial begin
    #0.713;
    forever #1.667 c0_ddr4_ui_clk = ~c0_ddr4_ui_clk;
  end
  int calibration = 0;
  always @(posedge c0_ddr4_ui_clk or posedge sys_rst) begin
    if (sys_rst) calibration <= 0;
    else if (calibration != 20) calibration <= calibration + 1;
  end
  assign c0_ddr4_ui_clk_sync_rst = sys_rst || calibration < 10;
  assign c0_init_calib_complete = !sys_rst && calibration == 20;
  assign addn_ui_clkout1 = c0_ddr4_ui_clk;
  assign dbg_clk = c0_ddr4_ui_clk;
  assign dbg_bus = '0;
  typedef logic [30:0] addr_t;
  typedef logic [511:0] data_t;
  typedef logic [63:0] strb_t;
  typedef logic [7:0] id_t;
  typedef logic [1:0] user_t;
  `AXI_TYPEDEF_ALL(mig, addr_t, id_t, data_t, strb_t, user_t)
  mig_req_t req;
  mig_resp_t rsp;
  assign req.aw = '{id:c0_ddr4_s_axi_awid, addr:c0_ddr4_s_axi_awaddr,
    len:c0_ddr4_s_axi_awlen, size:c0_ddr4_s_axi_awsize,
    burst:c0_ddr4_s_axi_awburst, lock:c0_ddr4_s_axi_awlock,
    cache:c0_ddr4_s_axi_awcache, prot:c0_ddr4_s_axi_awprot,
    qos:c0_ddr4_s_axi_awqos, default:'0};
  assign req.aw_valid = c0_ddr4_s_axi_awvalid;
  assign req.w = '{data:c0_ddr4_s_axi_wdata, strb:c0_ddr4_s_axi_wstrb,
    last:c0_ddr4_s_axi_wlast, default:'0};
  assign req.w_valid = c0_ddr4_s_axi_wvalid;
  assign req.b_ready = c0_ddr4_s_axi_bready;
  assign req.ar = '{id:c0_ddr4_s_axi_arid, addr:c0_ddr4_s_axi_araddr,
    len:c0_ddr4_s_axi_arlen, size:c0_ddr4_s_axi_arsize,
    burst:c0_ddr4_s_axi_arburst, lock:c0_ddr4_s_axi_arlock,
    cache:c0_ddr4_s_axi_arcache, prot:c0_ddr4_s_axi_arprot,
    qos:c0_ddr4_s_axi_arqos, default:'0};
  assign req.ar_valid = c0_ddr4_s_axi_arvalid;
  assign req.r_ready = c0_ddr4_s_axi_rready;
  assign c0_ddr4_s_axi_awready = rsp.aw_ready;
  assign c0_ddr4_s_axi_wready = rsp.w_ready;
  assign c0_ddr4_s_axi_bid = rsp.b.id;
  assign c0_ddr4_s_axi_bresp = rsp.b.resp;
  assign c0_ddr4_s_axi_bvalid = rsp.b_valid;
  assign c0_ddr4_s_axi_arready = rsp.ar_ready;
  assign c0_ddr4_s_axi_rid = rsp.r.id;
  assign c0_ddr4_s_axi_rdata = rsp.r.data;
  assign c0_ddr4_s_axi_rresp = rsp.r.resp;
  assign c0_ddr4_s_axi_rlast = rsp.r.last;
  assign c0_ddr4_s_axi_rvalid = rsp.r_valid;

  logic [0:0] ram_req, ram_gnt, ram_we, ram_valid;
  addr_t [0:0] ram_addr;
  data_t [0:0] ram_wdata, ram_rdata;
  strb_t [0:0] ram_strb;
  data_t ram [addr_t];
  int cycles = 0;
  assign ram_gnt = ram_req & {1{cycles % 5 != 0}};
  axi_to_mem #(
    .axi_req_t(mig_req_t), .axi_resp_t(mig_resp_t),
    .AddrWidth(31), .DataWidth(512), .IdWidth(8), .NumBanks(1), .BufDepth(1)
  ) i_model_adapter (
    .clk_i(c0_ddr4_ui_clk), .rst_ni(c0_ddr4_aresetn), .busy_o(),
    .axi_req_i(req), .axi_resp_o(rsp),
    .mem_req_o(ram_req), .mem_gnt_i(ram_gnt), .mem_addr_o(ram_addr),
    .mem_wdata_o(ram_wdata), .mem_strb_o(ram_strb), .mem_atop_o(), .mem_we_o(ram_we),
    .mem_rvalid_i(ram_valid), .mem_rdata_i(ram_rdata)
  );
  always @(posedge c0_ddr4_ui_clk) begin
    cycles <= cycles + 1;
    ram_valid <= c0_ddr4_aresetn ? ram_gnt : '0;
    if (c0_ddr4_aresetn && ram_gnt[0]) begin
      if (ram.exists(ram_addr[0] >> 6) == 0) ram[ram_addr[0] >> 6] = '0;
      ram_rdata[0] <= ram[ram_addr[0] >> 6];
      if (ram_we[0])
        for (int b = 0; b < 64; b++)
          if (ram_strb[0][b]) ram[ram_addr[0] >> 6][8*b+:8] = ram_wdata[0][8*b+:8];
    end
    if (c0_ddr4_aresetn && req.ar_valid && rsp.ar_ready)
      $display("MIG_MODEL AR cycle=%0d addr=%h len=%0d size=%0d id=%h", cycles,
               req.ar.addr, req.ar.len, req.ar.size, req.ar.id);
    if (c0_ddr4_aresetn && req.aw_valid && rsp.aw_ready)
      $display("MIG_MODEL AW cycle=%0d addr=%h len=%0d size=%0d id=%h", cycles,
               req.aw.addr, req.aw.len, req.aw.size, req.aw.id);
  end
endmodule
