// Offline MIG clock/pin legality test, never a board-programming image.
module c2_clock_preflight (
  input wire c2_sys_clk_p, c2_sys_clk_n, sys_reset,
  output wire c0_ddr4_act_n,
  output wire [16:0] c0_ddr4_adr,
  output wire [1:0] c0_ddr4_ba,
  output wire [0:0] c0_ddr4_bg, c0_ddr4_ck_t, c0_ddr4_ck_c,
  output wire [0:0] c0_ddr4_cke, c0_ddr4_cs_n, c0_ddr4_odt,
  output wire c0_ddr4_reset_n, calibrated,
  inout wire [7:0] c0_ddr4_dm_dbi_n,
  inout wire [63:0] c0_ddr4_dq,
  inout wire [7:0] c0_ddr4_dqs_t, c0_ddr4_dqs_c
);
  wire c2_sys_clk;
  IBUFDS #(.IBUF_LOW_PWR("FALSE")) i_ref (
    .I(c2_sys_clk_p), .IB(c2_sys_clk_n), .O(c2_sys_clk)
  );
  (* DONT_TOUCH = "TRUE" *) ddr4_c2 i_mig (
    .sys_rst(sys_reset), .c0_sys_clk_i(c2_sys_clk),
    .c0_ddr4_aresetn(1'b1), .c0_init_calib_complete(calibrated),
    .c0_ddr4_s_axi_awid(8'b0), .c0_ddr4_s_axi_awaddr(31'b0),
    .c0_ddr4_s_axi_awlen(8'b0), .c0_ddr4_s_axi_awsize(3'b110),
    .c0_ddr4_s_axi_awburst(2'b01), .c0_ddr4_s_axi_awlock(1'b0),
    .c0_ddr4_s_axi_awcache(4'b0), .c0_ddr4_s_axi_awprot(3'b0),
    .c0_ddr4_s_axi_awqos(4'b0), .c0_ddr4_s_axi_awvalid(1'b0),
    .c0_ddr4_s_axi_wdata(512'b0), .c0_ddr4_s_axi_wstrb(64'b0),
    .c0_ddr4_s_axi_wlast(1'b0), .c0_ddr4_s_axi_wvalid(1'b0),
    .c0_ddr4_s_axi_bready(1'b1),
    .c0_ddr4_s_axi_arid(8'b0), .c0_ddr4_s_axi_araddr(31'b0),
    .c0_ddr4_s_axi_arlen(8'b0), .c0_ddr4_s_axi_arsize(3'b110),
    .c0_ddr4_s_axi_arburst(2'b01), .c0_ddr4_s_axi_arlock(1'b0),
    .c0_ddr4_s_axi_arcache(4'b0), .c0_ddr4_s_axi_arprot(3'b0),
    .c0_ddr4_s_axi_arqos(4'b0), .c0_ddr4_s_axi_arvalid(1'b0),
    .c0_ddr4_s_axi_rready(1'b1),
    .c0_ddr4_act_n(c0_ddr4_act_n), .c0_ddr4_adr(c0_ddr4_adr),
    .c0_ddr4_ba(c0_ddr4_ba), .c0_ddr4_bg(c0_ddr4_bg),
    .c0_ddr4_ck_t(c0_ddr4_ck_t), .c0_ddr4_ck_c(c0_ddr4_ck_c),
    .c0_ddr4_cke(c0_ddr4_cke), .c0_ddr4_cs_n(c0_ddr4_cs_n),
    .c0_ddr4_odt(c0_ddr4_odt), .c0_ddr4_reset_n(c0_ddr4_reset_n),
    .c0_ddr4_dm_dbi_n(c0_ddr4_dm_dbi_n), .c0_ddr4_dq(c0_ddr4_dq),
    .c0_ddr4_dqs_t(c0_ddr4_dqs_t), .c0_ddr4_dqs_c(c0_ddr4_dqs_c)
  );
endmodule
