module eth_diag_top (
  input wire clk_in_p, clk_in_n, sys_rst,
  input wire mgt_clk_p, mgt_clk_n,
  input wire sgmii_rxp, sgmii_rxn,
  output wire sgmii_txp, sgmii_txn,
  output wire phy_rst_n, mdio_mdc,
  inout wire mdio
);
  wire ctrl_clk, locked, ctrl_reset, phy_request, echo_enable, pcs_request, phy_settled;
  wire mac_reset, packet_reset, tx_clk, rx_clk;
  wire [31:0] awaddr, araddr, wdata, rdata;
  wire [3:0] wstrb;
  wire [1:0] bresp, rresp;
  wire awvalid, awready, wvalid, wready, bvalid, bready;
  wire arvalid, arready, rvalid, rready;
  wire mdio_i, mdio_o, mdio_t;
  wire [15:0] pcs_status;
  wire [7:0] mac_rx_data, mac_tx_data, rx_data, tx_data;
  wire mac_rx_valid, mac_rx_last, mac_rx_bad, mac_tx_valid, mac_tx_last;
  wire mac_tx_ready, mac_tx_bad, rx_valid, rx_last, rx_ready;
  wire tx_valid, tx_last, tx_ready, enable_tx, seen, sent, rejected;
  wire [19:0] status_async, status_sync;
  wire [3:0] tx_beat_gray, tx_beat_sync;
  reg [22:0] tx_beat_div = 0;
  reg [3:0] tx_beat_bin = 0;
  reg response_error = 0;

  eth_j10_clocks_resets i_clocks (
    .clk_in_p(clk_in_p), .clk_in_n(clk_in_n), .sys_rst(sys_rst), .soft_rst(1'b0),
    .mmcm_locked_out(locked), .axi_lite_clk_bufg(ctrl_clk),
    .axi_lite_resetn(), .axis_rstn(), .sys_out_rst(),
    .gtx_clk_bufg(), .ref_clk_bufg(), .ref_clk_50_bufg(), .axis_clk_bufg()
  );
  eth_diag_reset_sync i_ctrl_reset (.clk(ctrl_clk), .reset(sys_rst | !locked), .reset_out(ctrl_reset));
  eth_diag_reset i_phy_reset (
    .clk(ctrl_clk), .reset(ctrl_reset), .request(phy_request),
    .phy_reset_n(phy_rst_n), .settled(phy_settled)
  );
  // Management release depends on the independent timer, NOT on PCS lock.
  eth_diag_pcs_reset i_pcs_reset (
    .clk(ctrl_clk), .reset(ctrl_reset), .phy_settled(phy_settled),
    .request(pcs_request), .mac_reset(mac_reset)
  );
  eth_diag_reset_sync i_packet_reset (.clk(tx_clk), .reset(mac_reset), .reset_out(packet_reset));
  eth_j10_bit_sync i_enable (.clk(tx_clk), .data_in(echo_enable), .data_out(enable_tx));

  eth_jtag i_jtag (
    .aclk(ctrl_clk), .aresetn(!ctrl_reset),
    .m_axi_awaddr(awaddr), .m_axi_awprot(), .m_axi_awvalid(awvalid), .m_axi_awready(awready),
    .m_axi_wdata(wdata), .m_axi_wstrb(wstrb), .m_axi_wvalid(wvalid), .m_axi_wready(wready),
    .m_axi_bresp(bresp), .m_axi_bvalid(bvalid), .m_axi_bready(bready),
    .m_axi_araddr(araddr), .m_axi_arprot(), .m_axi_arvalid(arvalid), .m_axi_arready(arready),
    .m_axi_rdata(rdata), .m_axi_rresp(rresp), .m_axi_rvalid(rvalid), .m_axi_rready(rready)
  );
  // This diagnostic port accepts aligned full-word access to 0x000..0xffc only.
  // The host must reject aliases/partial writes; sticky status also exposes misuse.
  always @(posedge ctrl_clk) begin
    if (ctrl_reset || phy_request) response_error <= 0;
    else if ((bvalid && bready && bresp != 0) || (rvalid && rready && rresp != 0) ||
             (awvalid && awready && (awaddr[31:12] != 0 || awaddr[1:0] != 0)) ||
             (arvalid && arready && (araddr[31:12] != 0 || araddr[1:0] != 0)) ||
             (wvalid && wready && wstrb != 4'hf)) response_error <= 1;
  end
  assign status_async = {pcs_status, rejected, sent, seen, echo_enable};
  for (genvar i = 0; i < 20; i = i + 1) begin: gen_status
    eth_j10_bit_sync i_sync (.clk(ctrl_clk), .data_in(status_async[i]), .data_out(status_sync[i]));
  end
  always @(posedge tx_clk or posedge mac_reset) begin
    if (mac_reset) begin
      tx_beat_div <= 0;
      tx_beat_bin <= 0;
    end else begin
      tx_beat_div <= tx_beat_div + 1'b1;
      if (&tx_beat_div) tx_beat_bin <= tx_beat_bin + 1'b1;
    end
  end
  assign tx_beat_gray = tx_beat_bin ^ (tx_beat_bin >> 1);
  for (genvar i = 0; i < 4; i = i + 1) begin: gen_beat
    eth_j10_bit_sync i_sync (.clk(ctrl_clk), .data_in(tx_beat_gray[i]), .data_out(tx_beat_sync[i]));
  end
  // Independent status bits, not an atomic PCS snapshot or a link-pass indication.
  eth_vio i_vio (
    .clk(ctrl_clk), .probe_in0({3'b0, mac_reset, tx_beat_sync, status_sync,
                               response_error, phy_settled, phy_rst_n, locked}),
    .probe_out0(phy_request), .probe_out1(echo_enable), .probe_out2(pcs_request)
  );
  IOBUF i_mdio (.I(mdio_o), .T(mdio_t), .O(mdio_i), .IO(mdio));
  eth_j10_support i_mac (
    .s_axi_lite_resetn(!mac_reset), .s_axi_lite_clk(ctrl_clk),
    .s_axi_araddr(araddr[17:0]), .s_axi_arready(arready), .s_axi_arvalid(arvalid),
    .s_axi_awaddr(awaddr[17:0]), .s_axi_awready(awready), .s_axi_awvalid(awvalid),
    .s_axi_bready(bready), .s_axi_bresp(bresp), .s_axi_bvalid(bvalid),
    .s_axi_rdata(rdata), .s_axi_rready(rready), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid),
    .s_axi_wdata(wdata), .s_axi_wready(wready), .s_axi_wvalid(wvalid),
    .tx_mac_aclk(tx_clk), .rx_mac_aclk(rx_clk), .glbl_rst(mac_reset),
    .s_axis_tx_tdata(mac_tx_data), .s_axis_tx_tlast(mac_tx_last), .s_axis_tx_tready(mac_tx_ready),
    .s_axis_tx_tuser(mac_tx_bad), .s_axis_tx_tvalid(mac_tx_valid),
    .m_axis_rx_tdata(mac_rx_data), .m_axis_rx_tlast(mac_rx_last),
    .m_axis_rx_tuser(mac_rx_bad), .m_axis_rx_tvalid(mac_rx_valid),
    .phy_rst_n(), .ref_clk(1'b0), .signal_detect(1'b1),
    .sgmii_rxp(sgmii_rxp), .sgmii_rxn(sgmii_rxn), .sgmii_txp(sgmii_txp), .sgmii_txn(sgmii_txn),
    .mgt_clk_p(mgt_clk_p), .mgt_clk_n(mgt_clk_n), .status_vector(pcs_status),
    .mdio_mdc(mdio_mdc), .mdio_mdio_i(mdio_i), .mdio_mdio_o(mdio_o), .mdio_mdio_t(mdio_t)
  );
  eth_j10_ten_100_1g_eth_fifo i_fifo (
    .tx_fifo_aclk(tx_clk), .tx_fifo_resetn(!mac_reset),
    .tx_axis_fifo_tdata(tx_data), .tx_axis_fifo_tvalid(tx_valid), .tx_axis_fifo_tlast(tx_last),
    .tx_axis_fifo_tready(tx_ready), .tx_mac_aclk(tx_clk), .tx_mac_resetn(!mac_reset),
    .tx_axis_mac_tdata(mac_tx_data), .tx_axis_mac_tvalid(mac_tx_valid),
    .tx_axis_mac_tlast(mac_tx_last), .tx_axis_mac_tready(mac_tx_ready), .tx_axis_mac_tuser(mac_tx_bad),
    .rx_fifo_aclk(tx_clk), .rx_fifo_resetn(!mac_reset),
    .rx_axis_fifo_tdata(rx_data), .rx_axis_fifo_tvalid(rx_valid), .rx_axis_fifo_tlast(rx_last),
    .rx_axis_fifo_tready(rx_ready), .rx_mac_aclk(rx_clk), .rx_mac_resetn(!mac_reset),
    .rx_axis_mac_tdata(mac_rx_data), .rx_axis_mac_tvalid(mac_rx_valid),
    .rx_axis_mac_tlast(mac_rx_last), .rx_axis_mac_tuser(mac_rx_bad)
  );
  eth_diag_echo i_echo (
    .clk(tx_clk), .reset(packet_reset), .enable(enable_tx),
    .s_data(rx_data), .s_valid(rx_valid), .s_last(rx_last), .s_ready(rx_ready),
    .m_data(tx_data), .m_valid(tx_valid), .m_last(tx_last), .m_ready(tx_ready),
    .seen_frame(seen), .sent_frame(sent), .rejected_frame(rejected)
  );
endmodule
