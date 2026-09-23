// SPDX-License-Identifier: SHL-0.51
// Board integration derived from the Cheshire Xilinx platform.
`include "cheshire/typedef.svh"
`include "phy_definitions.svh"

module ara_dsa_vcu118 import cheshire_pkg::*; (
  input logic sys_clk_p,
  input logic sys_clk_n,
  input logic sys_reset,
  // J53 TCK is sampled as data by the FPGA-only TAP, not used as a clock.
  (* CLOCK_BUFFER_TYPE = "NONE" *) input logic jtag_tck_i,
  input logic jtag_tms_i,
  input logic jtag_tdi_i,
  output logic jtag_tdo_o,
  `DDR4_INTF(1, 8, 64, 8)
`ifdef ARA_FPGA_DDR2
  output logic c1_ddr4_act_n,
  output logic [16:0] c1_ddr4_adr,
  output logic [1:0] c1_ddr4_ba,
  output logic [0:0] c1_ddr4_bg,
  output logic [0:0] c1_ddr4_ck_t, c1_ddr4_ck_c,
  output logic [0:0] c1_ddr4_cke, c1_ddr4_cs_n,
  inout wire [7:0] c1_ddr4_dm_dbi_n,
  inout wire [63:0] c1_ddr4_dq,
  inout wire [7:0] c1_ddr4_dqs_t, c1_ddr4_dqs_c,
  output logic [0:0] c1_ddr4_odt,
  output logic c1_ddr4_reset_n,
`endif
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
`ifdef ARA_FPGA_HOST
    cfg.AxiExtNumMst = 1;
    cfg.RegExtNumSlv = 1;
    cfg.RegExtNumRules = 1;
    cfg.RegExtRegionIdx[0] = 0;
    cfg.RegExtRegionStart[0] = 'h03010000;
    cfg.RegExtRegionEnd[0] = 'h03011000;
`endif
`ifdef ARA_FPGA_DDR2
    cfg.LlcOutRegionEnd = 'h180000000;
`endif
    return cfg;
  endfunction
  localparam cheshire_cfg_t FPGACfg = board_cfg();
  `CHESHIRE_TYPEDEF_ALL(, FPGACfg)

  wire sys_clk, soc_clk, clk_locked;
  wire rst_n, fabric_ready;
  logic vio_reset, vio_boot_select;
  logic [1:0] vio_boot_mode, boot_mode;
  // Keep the VIO reset local before crossing to MIG. External reset or clock
  // loss asserts immediately; release is synchronized before this register.
  wire board_arst_n = ~sys_reset & clk_locked;
  wire board_reset_n;
  rstgen i_board_por (
    .clk_i(soc_clk), .rst_ni(board_arst_n), .test_mode_i(1'b0),
    .rst_no(board_reset_n), .init_no()
  );
  logic sys_rst;
  always_ff @(posedge soc_clk or negedge board_reset_n) begin
    if (!board_reset_n) sys_rst <= 1'b1;
    else sys_rst <= vio_reset;
  end
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
  axi_llc_req_t [1:0] dram_req;
  axi_llc_rsp_t [1:0] dram_rsp;
  wire [1:0] dram_ready;
`ifdef ARA_FPGA_DDR2
  ara_ddr_router #(
    .req_t(axi_llc_req_t), .rsp_t(axi_llc_rsp_t)
  ) i_ddr_router (
    .clk_i(soc_clk), .rst_ni(rst_n),
    .req_i(axi_llc_req), .rsp_o(axi_llc_rsp),
    .req_o(dram_req), .rsp_i(dram_rsp)
  );
  assign fabric_ready = &dram_ready;
  if (1) begin : gen_ddr2
    dram_wrapper_xilinx #(
      .Channel(1),
      .axi_soc_aw_chan_t(axi_llc_aw_chan_t), .axi_soc_w_chan_t(axi_llc_w_chan_t),
      .axi_soc_b_chan_t(axi_llc_b_chan_t), .axi_soc_ar_chan_t(axi_llc_ar_chan_t),
      .axi_soc_r_chan_t(axi_llc_r_chan_t), .axi_soc_req_t(axi_llc_req_t),
      .axi_soc_resp_t(axi_llc_rsp_t)
    ) i_dram_wrapper_c2 (
      .sys_rst_i(sys_rst), .soc_resetn_i(rst_n), .soc_clk_i(soc_clk),
      .fabric_reset_ni(fabric_ready),
      .dram_clk_i(sys_clk), .fabric_ready_o(dram_ready[1]),
      .soc_req_i(dram_req[1]), .soc_rsp_o(dram_rsp[1]),
      .c0_ddr4_act_n(c1_ddr4_act_n), .c0_ddr4_adr(c1_ddr4_adr),
      .c0_ddr4_ba(c1_ddr4_ba), .c0_ddr4_bg(c1_ddr4_bg),
      .c0_ddr4_ck_t(c1_ddr4_ck_t), .c0_ddr4_ck_c(c1_ddr4_ck_c),
      .c0_ddr4_cke(c1_ddr4_cke), .c0_ddr4_cs_n(c1_ddr4_cs_n),
      .c0_ddr4_dm_dbi_n(c1_ddr4_dm_dbi_n), .c0_ddr4_dq(c1_ddr4_dq),
      .c0_ddr4_dqs_t(c1_ddr4_dqs_t), .c0_ddr4_dqs_c(c1_ddr4_dqs_c),
      .c0_ddr4_odt(c1_ddr4_odt), .c0_ddr4_reset_n(c1_ddr4_reset_n)
    );
  end
`else
  assign dram_req[0] = axi_llc_req;
  assign axi_llc_rsp = dram_rsp[0];
  assign dram_req[1] = '0;
  assign dram_rsp[1] = '0;
  assign dram_ready[1] = 1'b0;
  assign fabric_ready = dram_ready[0];
`endif
  dram_wrapper_xilinx #(
    .axi_soc_aw_chan_t(axi_llc_aw_chan_t), .axi_soc_w_chan_t(axi_llc_w_chan_t),
    .axi_soc_b_chan_t(axi_llc_b_chan_t), .axi_soc_ar_chan_t(axi_llc_ar_chan_t),
    .axi_soc_r_chan_t(axi_llc_r_chan_t), .axi_soc_req_t(axi_llc_req_t),
    .axi_soc_resp_t(axi_llc_rsp_t)
  ) i_dram_wrapper (
    .sys_rst_i(sys_rst), .soc_resetn_i(rst_n), .soc_clk_i(soc_clk),
`ifdef ARA_FPGA_DDR2
    .fabric_reset_ni(fabric_ready),
`endif
    .dram_clk_i(sys_clk), .fabric_ready_o(dram_ready[0]),
    .soc_req_i(dram_req[0]), .soc_rsp_o(dram_rsp[0]), .*
  );

  axi_mst_req_t [0:0] host_req;
  axi_mst_rsp_t [0:0] host_rsp;
  reg_req_t [0:0] cpu_debug_req;
  reg_rsp_t [0:0] cpu_debug_rsp;
`ifdef ARA_FPGA_HOST
  logic [7:0] retire_count;
  logic [63:0] retire_pc, head_pc, trap_pc, trap_cause, trap_tval;
  logic trap;
  if (1) begin : gen_host
    reg_req_t debug_req;
    reg_rsp_t debug_rsp;
    logic enable_count, clear_count;
    logic [1:0][14:0][63:0] ddr_metrics;
    ara_host_bridge #(
      .axi_req_t(axi_mst_req_t), .axi_rsp_t(axi_mst_rsp_t),
      .reg_req_t(reg_req_t), .reg_rsp_t(reg_rsp_t)
    ) i_host_bridge (
      .clk_i(soc_clk), .board_rst_ni(board_reset_n), .soc_rst_ni(rst_n),
      .mem_req_o(host_req[0]), .mem_rsp_i(host_rsp[0]),
      .debug_req_o(debug_req), .debug_rsp_i(debug_rsp)
    );
    for (genvar c = 0; c < 2; c++) begin : gen_observer
      ara_axi_observer #(.req_t(axi_llc_req_t), .rsp_t(axi_llc_rsp_t)) i_observer (
        .clk_i(soc_clk), .rst_ni(board_reset_n), .soc_rst_ni(rst_n),
        .enable_i(enable_count), .clear_i(clear_count),
        .req_i(dram_req[c]), .rsp_i(dram_rsp[c]), .counters_o(ddr_metrics[c])
      );
    end
    ara_fpga_debug #(
`ifdef ARA_FPGA_DDR2
      .DualDdr(1),
`endif
      .reg_req_t(reg_req_t), .reg_rsp_t(reg_rsp_t)
    ) i_debug (
      .clk_i(soc_clk), .rst_ni(board_reset_n), .soc_rst_ni(rst_n),
      // Synchronized board indicators; CPU reset itself is already local.
      .status_i({status[0],status[1],status[2],rst_n}),
      .host_req_i(debug_req), .host_rsp_o(debug_rsp),
      .cpu_req_i(cpu_debug_req[0]), .cpu_rsp_o(cpu_debug_rsp[0]),
      .retire_count_i(retire_count), .retire_pc_i(retire_pc), .head_pc_i(head_pc),
      .trap_i(trap), .trap_pc_i(trap_pc), .trap_cause_i(trap_cause),
      .trap_tval_i(trap_tval), .ddr_metrics_i(ddr_metrics),
      .count_enable_o(enable_count), .count_clear_o(clear_count)
    );
  end
`else
  assign host_req = '0;
  assign cpu_debug_rsp = '0;
`endif

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
    .axi_ext_mst_req_i(host_req), .axi_ext_mst_rsp_o(host_rsp),
    .axi_ext_slv_req_o(), .axi_ext_slv_rsp_i('0),
    .reg_ext_slv_req_o(cpu_debug_req), .reg_ext_slv_rsp_i(cpu_debug_rsp),
`ifdef ARA_FPGA_HOST
    .fpga_retire_count_o(retire_count), .fpga_retire_pc_o(retire_pc),
    .fpga_head_pc_o(head_pc), .fpga_trap_o(trap), .fpga_trap_pc_o(trap_pc),
    .fpga_trap_cause_o(trap_cause), .fpga_trap_tval_o(trap_tval),
`endif
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
