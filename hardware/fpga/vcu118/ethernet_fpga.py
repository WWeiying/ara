"""Optional loader attachment before the existing MIG R-channel timing cut."""


def patch_ethernet(text):
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise RuntimeError("Ethernet DDR integration source changed: " + old)
        text = text.replace(old, new)

    replace("  // PHY interfaces", """`ifdef ARA_FPGA_ETHERNET
  input logic eth_ref_p, eth_ref_n, eth_rxp, eth_rxn,
  output logic eth_txp, eth_txn, eth_mdc, eth_phy_reset_n,
  inout wire eth_mdio,
`endif
  // PHY interfaces""")
    replace("iresizer_cdc_req, cdc_cut_req, cdc_dram_req;",
            "iresizer_cdc_req, cdc_ara_req, cdc_cut_req, cdc_dram_req;")
    replace("iresizer_cdc_rsp, cdc_cut_rsp, cdc_dram_rsp;",
            "iresizer_cdc_rsp, cdc_ara_rsp, cdc_cut_rsp, cdc_dram_rsp;")
    replace(".dst_req_o  ( cdc_cut_req )", ".dst_req_o  ( cdc_ara_req )")
    replace(".dst_resp_i ( cdc_cut_rsp )", ".dst_resp_i ( cdc_ara_rsp )")
    replace("assign cdc_cut_req      = iresizer_cdc_req;", "assign cdc_ara_req      = iresizer_cdc_req;")
    replace("assign iresizer_cdc_rsp = cdc_cut_rsp;", "assign iresizer_cdc_rsp = cdc_ara_rsp;")
    marker = "`ifdef TARGET_VCU118\n  // Isolate the CDC read-FIFO"
    replace(marker, """`ifdef ARA_FPGA_ETHERNET
  if (Channel == 0) begin : gen_ethernet
  axi_dw_iw_req_t loader_req;
  axi_dw_iw_resp_t loader_rsp;
  logic loader_lock;
  logic [255:0] loader_status;
  ara_eth_loader #(.req_t(axi_dw_iw_req_t), .rsp_t(axi_dw_iw_resp_t)) i_eth_loader (
    .sys_clk_i(dram_clk_i), .sys_rst_i(sys_rst_i),
    .ui_clk_i(dram_axi_clk), .ui_resetn_i(ui_resetn),
    .req_o(loader_req), .rsp_i(loader_rsp), .status_i(loader_status), .lock_o(loader_lock),
    .eth_ref_p, .eth_ref_n, .eth_rxp, .eth_rxn, .eth_txp, .eth_txn, .eth_mdc, .eth_phy_reset_n, .eth_mdio
  );
  ara_eth_shared_ddr #(.AddrWidth(SocAddrWidth), .UserWidth(SocUserWidth),
    .LoaderSingleId(1),
    .StaticIdPartition(SocIdWidth < cfg.IdWidth && cfg.IdWidth == 8),
    .req_t(axi_dw_iw_req_t), .rsp_t(axi_dw_iw_resp_t)) i_eth_shared_ddr (
    .clk_i(dram_axi_clk), .rst_ni(ui_resetn), .lock_i(loader_lock),
    .ara_req_i(cdc_ara_req), .ara_rsp_o(cdc_ara_rsp),
    .loader_req_i(loader_req), .loader_rsp_o(loader_rsp),
    .mem_req_o(cdc_cut_req), .mem_rsp_i(cdc_cut_rsp), .status_o(loader_status)
  );
  end else begin : gen_no_ethernet
    assign cdc_cut_req = cdc_ara_req;
    assign cdc_ara_rsp = cdc_cut_rsp;
    assign {eth_txp, eth_txn, eth_mdc, eth_phy_reset_n} = '0;
    assign eth_mdio = 1'bz;
  end
`else
  assign cdc_cut_req = cdc_ara_req;
  assign cdc_ara_rsp = cdc_cut_rsp;
`endif

""" + marker)
    return text
