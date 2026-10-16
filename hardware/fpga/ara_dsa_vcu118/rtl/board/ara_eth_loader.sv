// SPDX-License-Identifier: SHL-0.51
// Adapter for the validated id-less 32-address/512-data loader BD master.
module ara_eth_loader #(
  parameter type req_t = logic,
  parameter type rsp_t = logic
) (
  input logic sys_clk_i, sys_rst_i, ui_clk_i, ui_resetn_i,
  input logic eth_ref_p, eth_ref_n, eth_rxp, eth_rxn,
  output logic eth_txp, eth_txn, eth_mdc, eth_phy_reset_n,
  inout wire eth_mdio,
  output req_t req_o,
  input rsp_t rsp_i,
  input logic [255:0] status_i,
  output logic lock_o
);
  logic [31:0] awaddr, araddr;
  assign req_o.aw.addr = awaddr;
  assign req_o.ar.addr = araddr;
  assign req_o.aw.id = '0;
  assign req_o.aw.atop = '0;
  assign req_o.aw.region = '0;
  assign req_o.aw.user = '0;
  assign req_o.ar.id = '0;
  assign req_o.ar.region = '0;
  assign req_o.ar.user = '0;
  assign req_o.w.user = '0;
  eth_control i_control (
    .clk(ui_clk_i), .probe_in0(status_i), .probe_out0(lock_o)
  );
  loader_bd_wrapper i_loader (
    // Reset the upstream DMA/SmartConnect state too if the shared UI loses readiness.
    .sys_clk(sys_clk_i), .sys_reset(sys_rst_i || !ui_resetn_i),
    .ui_clk(ui_clk_i), .ui_reset(~ui_resetn_i),
    .sgmii_phyclk_clk_p(eth_ref_p), .sgmii_phyclk_clk_n(eth_ref_n),
    .sgmii_lvds_rxp(eth_rxp), .sgmii_lvds_rxn(eth_rxn),
    .sgmii_lvds_txp(eth_txp), .sgmii_lvds_txn(eth_txn),
    .mdio_mdc_mdc(eth_mdc), .mdio_mdc_mdio_io(eth_mdio), .phy_reset_out(eth_phy_reset_n),
    .M_DDR_awaddr(awaddr), .M_DDR_awburst(req_o.aw.burst), .M_DDR_awcache(req_o.aw.cache),
    .M_DDR_awlen(req_o.aw.len), .M_DDR_awlock(req_o.aw.lock), .M_DDR_awprot(req_o.aw.prot),
    .M_DDR_awqos(req_o.aw.qos), .M_DDR_awready(rsp_i.aw_ready),
    .M_DDR_awsize(req_o.aw.size), .M_DDR_awvalid(req_o.aw_valid),
    .M_DDR_wdata(req_o.w.data), .M_DDR_wlast(req_o.w.last), .M_DDR_wready(rsp_i.w_ready),
    .M_DDR_wstrb(req_o.w.strb), .M_DDR_wvalid(req_o.w_valid),
    .M_DDR_bready(req_o.b_ready), .M_DDR_bresp(rsp_i.b.resp), .M_DDR_bvalid(rsp_i.b_valid),
    .M_DDR_araddr(araddr), .M_DDR_arburst(req_o.ar.burst), .M_DDR_arcache(req_o.ar.cache),
    .M_DDR_arlen(req_o.ar.len), .M_DDR_arlock(req_o.ar.lock), .M_DDR_arprot(req_o.ar.prot),
    .M_DDR_arqos(req_o.ar.qos), .M_DDR_arready(rsp_i.ar_ready),
    .M_DDR_arsize(req_o.ar.size), .M_DDR_arvalid(req_o.ar_valid),
    .M_DDR_rdata(rsp_i.r.data), .M_DDR_rlast(rsp_i.r.last), .M_DDR_rready(req_o.r_ready),
    .M_DDR_rresp(rsp_i.r.resp), .M_DDR_rvalid(rsp_i.r_valid)
  );
endmodule
