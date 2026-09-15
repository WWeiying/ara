// SPDX-License-Identifier: SHL-0.51
// Board integration derived from the Cheshire Xilinx platform.
`include "cheshire/typedef.svh"
`include "phy_definitions.svh"

module ara_dsa_vcu118 import cheshire_pkg::*; (
  input logic sys_clk_p,
  input logic sys_clk_n,
  input logic sys_reset,
  // The TAP already instantiates a BUFGMUX; do not infer a second BUFG.
  (* CLOCK_BUFFER_TYPE = "NONE" *) input logic jtag_tck_i,
  input logic jtag_tms_i,
  input logic jtag_tdi_i,
  output logic jtag_tdo_o,
  `DDR4_INTF(1, 8, 64, 8)
  input logic uart_rx_i,
  output logic uart_tx_o
);
  function automatic cheshire_cfg_t board_cfg();
    cheshire_cfg_t cfg = DefaultCfg;
    cfg.RtcFreq = 1000000;
    cfg.NumCores = 1;
    cfg.Ara = 1;
    cfg.AraVLEN = 1024;
    cfg.AraNrLanes = 4;
    cfg.SerialLink = 0;
    cfg.Usb = 0;
    cfg.Vga = 0;
    cfg.I2c = 0;
    cfg.Dma = 0;
    cfg.Clic = 0;
    return cfg;
  endfunction
  localparam cheshire_cfg_t FPGACfg = board_cfg();
  `CHESHIRE_TYPEDEF_ALL(, FPGACfg)

  wire sys_clk, soc_clk, clk_locked;
  wire rst_n, fabric_ready;
  logic vio_reset, vio_boot_select;
  logic [1:0] vio_boot_mode, boot_mode;
  wire sys_rst = sys_reset | vio_reset | ~clk_locked;
  wire [3:0] status_async = {rst_n, fabric_ready, clk_locked, sys_rst};
  wire [3:0] status;

  // Independent debug indicators, not an atomic status word. Keep sampling
  // during reset so VIO can show why the SoC is being held in reset.
  for (genvar bit_idx = 0; bit_idx < 4; bit_idx++) begin : gen_status_sync
    sync #(.STAGES(2)) i_sync (
      .clk_i(soc_clk), .rst_ni(1'b1),
      .serial_i(status_async[bit_idx]), .serial_o(status[bit_idx])
    );
  end : gen_status_sync

  IBUFDS #(.IBUF_LOW_PWR("FALSE")) i_bufds_sys_clk (
    .I(sys_clk_p), .IB(sys_clk_n), .O(sys_clk)
  );
  clkwiz i_clkwiz (
    .clk_in1(sys_clk), .reset(1'b0), .locked(clk_locked),
    .clk_50(soc_clk)
  );
  vio i_vio (
    .clk(soc_clk), .probe_in0(status), .probe_out0(vio_reset),
    .probe_out1(vio_boot_mode), .probe_out2(vio_boot_select)
  );
  assign boot_mode = vio_boot_select ? vio_boot_mode : 2'b00;

  // Both sides of the DDR CDC use the same asynchronous POR condition;
  // deassertion is synchronized independently in their respective domains.
  rstgen i_rstgen (
    .clk_i(soc_clk), .rst_ni(fabric_ready), .test_mode_i(1'b0),
    .rst_no(rst_n), .init_no()
  );

  logic [4:0] rtc_count;
  logic rtc_clk;
  always_ff @(posedge soc_clk or negedge rst_n) begin
    if (!rst_n) begin
      rtc_count <= '0;
      rtc_clk <= 1'b0;
    end else if (rtc_count == 5'd24) begin
      rtc_count <= '0;
      rtc_clk <= ~rtc_clk;
    end else begin
      rtc_count <= rtc_count + 1'b1;
    end
  end

  logic spi_sck, spi_sck_en;
  logic [1:0] spi_cs, spi_cs_en;
  logic [3:0] spi_out, spi_in, spi_en;
  STARTUPE3 #(.PROG_USR("FALSE"), .SIM_CCLK_FREQ(0.0)) i_startupe3 (
    .CFGCLK(), .CFGMCLK(), .DI(spi_in), .EOS(), .PREQ(),
    .DO(spi_out), .DTS(~spi_en), .FCSBO(spi_cs[1]), .FCSBTS(~spi_cs_en[1]),
    .GSR(1'b0), .GTS(1'b0), .KEYCLEARB(1'b1), .PACK(1'b0),
    .USRCCLKO(spi_sck), .USRCCLKTS(~spi_sck_en),
    .USRDONEO(1'b1), .USRDONETS(1'b1)
  );

  axi_llc_req_t axi_llc_req;
  axi_llc_rsp_t axi_llc_rsp;
  dram_wrapper_xilinx #(
    .axi_soc_aw_chan_t(axi_llc_aw_chan_t), .axi_soc_w_chan_t(axi_llc_w_chan_t),
    .axi_soc_b_chan_t(axi_llc_b_chan_t), .axi_soc_ar_chan_t(axi_llc_ar_chan_t),
    .axi_soc_r_chan_t(axi_llc_r_chan_t), .axi_soc_req_t(axi_llc_req_t),
    .axi_soc_resp_t(axi_llc_rsp_t)
  ) i_dram_wrapper (
    .sys_rst_i(sys_rst), .soc_resetn_i(rst_n), .soc_clk_i(soc_clk),
    .dram_clk_i(sys_clk), .fabric_ready_o(fabric_ready),
    .soc_req_i(axi_llc_req), .soc_rsp_o(axi_llc_rsp), .*
  );

  cheshire_soc #(
    .Cfg(FPGACfg), .ExtHartinfo('0),
    .axi_ext_llc_req_t(axi_llc_req_t), .axi_ext_llc_rsp_t(axi_llc_rsp_t),
    .axi_ext_mst_req_t(axi_mst_req_t), .axi_ext_mst_rsp_t(axi_mst_rsp_t),
    .axi_ext_slv_req_t(axi_slv_req_t), .axi_ext_slv_rsp_t(axi_slv_rsp_t),
    .reg_ext_req_t(reg_req_t), .reg_ext_rsp_t(reg_rsp_t)
  ) i_cheshire_soc (
    .clk_i(soc_clk), .rst_ni(rst_n), .test_mode_i(1'b0),
    .boot_mode_i(boot_mode), .rtc_i(rtc_clk),
    .axi_llc_mst_req_o(axi_llc_req), .axi_llc_mst_rsp_i(axi_llc_rsp),
    .axi_ext_mst_req_i('0), .axi_ext_mst_rsp_o(),
    .axi_ext_slv_req_o(), .axi_ext_slv_rsp_i('0),
    .reg_ext_slv_req_o(), .reg_ext_slv_rsp_i('0),
    .intr_ext_i('0), .intr_ext_o(), .xeip_ext_o(), .mtip_ext_o(), .msip_ext_o(),
    .dbg_active_o(), .dbg_ext_req_o(), .dbg_ext_unavail_i('0),
    .slink_rcv_clk_i(1'b0), .slink_rcv_clk_o(), .slink_i('0), .slink_o(),
    .jtag_tck_i, .jtag_trst_ni(1'b1), .jtag_tms_i, .jtag_tdi_i,
    .jtag_tdo_o, .jtag_tdo_oe_o(),
    .i2c_sda_o(), .i2c_sda_i(1'b1), .i2c_sda_en_o(),
    .i2c_scl_o(), .i2c_scl_i(1'b1), .i2c_scl_en_o(),
    .spih_sck_o(spi_sck), .spih_sck_en_o(spi_sck_en),
    .spih_csb_o(spi_cs), .spih_csb_en_o(spi_cs_en),
    .spih_sd_o(spi_out), .spih_sd_en_o(spi_en), .spih_sd_i(spi_in),
    .vga_hsync_o(), .vga_vsync_o(), .vga_red_o(), .vga_green_o(), .vga_blue_o(),
    .uart_tx_o, .uart_rx_i,
    .uart_cts_ni(1'b0), .uart_dsr_ni(1'b0), .uart_dcd_ni(1'b0), .uart_rin_ni(1'b1),
    .uart_rts_no(), .uart_dtr_no(), .gpio_i('0), .gpio_o(), .gpio_en_o(),
    .usb_clk_i(soc_clk), .usb_rst_ni(rst_n),
    .usb_dm_i('0), .usb_dm_o(), .usb_dm_oe_o(),
    .usb_dp_i('0), .usb_dp_o(), .usb_dp_oe_o()
  );
endmodule
