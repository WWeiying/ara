// SPDX-License-Identifier: SHL-0.51
// Protocol isolation: real exported interconnect/LLC, not vendor JTAG/MIG/XPM.
`include "axi/typedef.svh"
`include "register_interface/typedef.svh"

module host_burst_path_tb;
  timeunit 1ns;
  timeprecision 1ps;
  logic clk = 0, por_n = 0;
  wire rst_n, fabric_ready;
  always #10 clk = ~clk;
  typedef logic [47:0] addr_t;
  typedef logic [63:0] data_t;
  typedef logic [7:0] strb_t;
  typedef logic [1:0] user_t;
  typedef logic [1:0] host_id_t;
  typedef logic [3:0] soc_id_t;
  typedef logic [4:0] mem_id_t;
  `AXI_TYPEDEF_ALL(host, addr_t, host_id_t, data_t, strb_t, user_t)
  `AXI_TYPEDEF_ALL(soc, addr_t, soc_id_t, data_t, strb_t, user_t)
  `AXI_TYPEDEF_ALL(mem, addr_t, mem_id_t, data_t, strb_t, user_t)
  typedef logic [31:0] reg_word_t;
  typedef logic [3:0] reg_strb_t;
  `REG_BUS_TYPEDEF_ALL(reg_bus, reg_word_t, reg_word_t, reg_strb_t)
  typedef struct packed {logic [7:0] idx; addr_t start_addr; addr_t end_addr;} rule_t;

  // Host profile: CPU, debug and Ara inputs idle; external JTAG uses input 3.
  localparam axi_pkg::xbar_cfg_t XbarCfg = '{
    NoSlvPorts:4, NoMstPorts:3, MaxMstTrans:24, MaxSlvTrans:24,
    FallThrough:0, LatencyMode:axi_pkg::CUT_ALL_PORTS, PipelineStages:0,
    AxiIdWidthSlvPorts:2, AxiIdUsedSlvPorts:2, UniqueIds:0,
    AxiAddrWidth:48, AxiDataWidth:64, NoAddrRules:6
  };
  localparam rule_t [5:0] Map = '{
    '{1, 48'h03010000, 48'h03011000},
    '{2, 48'h14000000, 48'h14020000},
    '{2, 48'h10000000, 48'h10020000},
    '{2, 48'h80000000, 48'h100000000},
    '{1, 48'h02000000, 48'h0c000000},
    '{0, 48'h00000000, 48'h00040000}
  };
  host_req_t drive;
  host_req_t [3:0] inputs;
  host_resp_t [3:0] responses;
  soc_req_t [2:0] outputs;
  soc_resp_t [2:0] output_responses;
  soc_req_t amo_req, cut_req, llc_req;
  soc_resp_t amo_rsp, cut_rsp;
  mem_req_t mem_req;
  mem_resp_t mem_rsp;
  reg_bus_req_t cfg_req = '0;
  reg_bus_rsp_t cfg_rsp;
  assign inputs[3] = drive;
  assign inputs[2:0] = '0;
  assign output_responses[1:0] = '0;

  axi_xbar #(
    .Cfg(XbarCfg), .ATOPs(1), .Connectivity('1),
    .slv_aw_chan_t(host_aw_chan_t), .mst_aw_chan_t(soc_aw_chan_t), .w_chan_t(host_w_chan_t),
    .slv_b_chan_t(host_b_chan_t), .mst_b_chan_t(soc_b_chan_t),
    .slv_ar_chan_t(host_ar_chan_t), .mst_ar_chan_t(soc_ar_chan_t),
    .slv_r_chan_t(host_r_chan_t), .mst_r_chan_t(soc_r_chan_t),
    .slv_req_t(host_req_t), .slv_resp_t(host_resp_t),
    .mst_req_t(soc_req_t), .mst_resp_t(soc_resp_t), .rule_t(rule_t)
  ) i_xbar (
    .clk_i(clk), .rst_ni(rst_n), .test_i(1'b0),
    .slv_ports_req_i(inputs), .slv_ports_resp_o(responses),
    .mst_ports_req_o(outputs), .mst_ports_resp_i(output_responses),
    .addr_map_i(Map), .en_default_mst_port_i('0), .default_mst_port_i('0)
  );
  axi_riscv_atomics_structs #(
    .AxiAddrWidth(48), .AxiDataWidth(64), .AxiIdWidth(4), .AxiUserWidth(2),
    .AxiMaxReadTxns(16), .AxiMaxWriteTxns(16), .AxiUserAsId(1),
    .AxiUserIdMsb(1), .AxiUserIdLsb(0), .RiscvWordWidth(64), .NAxiCuts(1),
    .axi_req_t(soc_req_t), .axi_rsp_t(soc_resp_t)
  ) i_atomics (
    .clk_i(clk), .rst_ni(rst_n), .axi_slv_req_i(outputs[2]),
    .axi_slv_rsp_o(output_responses[2]), .axi_mst_req_o(amo_req), .axi_mst_rsp_i(amo_rsp)
  );
  axi_cut #(
    .Bypass(0), .aw_chan_t(soc_aw_chan_t), .w_chan_t(soc_w_chan_t), .b_chan_t(soc_b_chan_t),
    .ar_chan_t(soc_ar_chan_t), .r_chan_t(soc_r_chan_t),
    .axi_req_t(soc_req_t), .axi_resp_t(soc_resp_t)
  ) i_cut (
    .clk_i(clk), .rst_ni(rst_n), .slv_req_i(amo_req), .slv_resp_o(amo_rsp),
    .mst_req_o(cut_req), .mst_resp_i(cut_rsp)
  );
  always_comb begin
    llc_req = cut_req;
    if ((cut_req.ar.addr & 48'hfffffc000000) == 48'h14000000)
      llc_req.ar.addr = 48'h10000000 | (cut_req.ar.addr & 48'h03ffffff);
    if ((cut_req.aw.addr & 48'hfffffc000000) == 48'h14000000)
      llc_req.aw.addr = 48'h10000000 | (cut_req.aw.addr & 48'h03ffffff);
  end
  axi_llc_reg_wrap #(
    .SetAssociativity(8), .NumLines(256), .NumBlocks(8),
    .AxiIdWidth(4), .AxiAddrWidth(48), .AxiDataWidth(64), .AxiUserWidth(2),
    .slv_req_t(soc_req_t), .slv_resp_t(soc_resp_t),
    .mst_req_t(mem_req_t), .mst_resp_t(mem_resp_t),
    .reg_req_t(reg_bus_req_t), .reg_resp_t(reg_bus_rsp_t), .rule_full_t(rule_t)
  ) i_llc (
    .clk_i(clk), .rst_ni(rst_n), .test_i(1'b0),
    .slv_req_i(llc_req), .slv_resp_o(cut_rsp), .mst_req_o(mem_req), .mst_resp_i(mem_rsp),
    .conf_req_i(cfg_req), .conf_resp_o(cfg_rsp),
    .cached_start_addr_i(48'h80000000), .cached_end_addr_i(48'h100000000),
    .spm_start_addr_i(48'h10000000), .axi_llc_events_o()
  );

  // Keep the production data/ID converters, CDC and reset chains in the DUT.
  // Only the vendor MIG AXI endpoint is modeled, with a separate UI clock.
  rstgen i_soc_reset (
    .clk_i(clk), .rst_ni(fabric_ready), .test_mode_i(1'b0), .rst_no(rst_n), .init_no()
  );
  dram_wrapper_xilinx #(
    .axi_soc_aw_chan_t(mem_aw_chan_t), .axi_soc_w_chan_t(mem_w_chan_t),
    .axi_soc_b_chan_t(mem_b_chan_t), .axi_soc_ar_chan_t(mem_ar_chan_t),
    .axi_soc_r_chan_t(mem_r_chan_t), .axi_soc_req_t(mem_req_t), .axi_soc_resp_t(mem_resp_t)
  ) i_dram_wrapper (
    .sys_rst_i(~por_n), .dram_clk_i(clk), .soc_resetn_i(rst_n), .soc_clk_i(clk),
    .fabric_ready_o(fabric_ready), .soc_req_i(mem_req), .soc_rsp_o(mem_rsp)
  );

  int cycles = 0, checks = 0, accepted = 0, stalled = 0;
  int host_ar_count = 0, xbar_ar_count = 0, llc_ar_count = 0;
  addr_t expected_ar_addr;
  int expected_ar_beats;
  axi_pkg::burst_t expected_ar_burst;
  bit host_held = 0, llc_held = 0;
  host_r_chan_t host_prev_r;
  soc_r_chan_t llc_prev_r;
  bit stall_reads = 0;
  always @(posedge clk) begin
    cycles <= cycles + 1;
    if (cycles > 250000) $fatal(1, "Bounded test timeout");
    if (rst_n) begin
      if (host_held && (!responses[3].r_valid || responses[3].r !== host_prev_r))
        $fatal(1, "Host R changed under backpressure");
      if (llc_held && (!cut_rsp.r_valid || cut_rsp.r !== llc_prev_r))
        $fatal(1, "LLC R changed under backpressure");
      host_held = responses[3].r_valid && !drive.r_ready;
      llc_held = cut_rsp.r_valid && !llc_req.r_ready;
      host_prev_r = responses[3].r;
      llc_prev_r = cut_rsp.r;
      if (host_held) stalled++;
      if (drive.ar_valid && responses[3].ar_ready) begin
        host_ar_count++;
        $display("HOST AR cycle=%0d addr=%h len=%0d size=%0d", cycles, drive.ar.addr, drive.ar.len, drive.ar.size);
      end
      if (outputs[2].ar_valid && output_responses[2].ar_ready) begin
        xbar_ar_count++;
        if (outputs[2].ar.addr != expected_ar_addr || outputs[2].ar.len != expected_ar_beats-1 ||
            outputs[2].ar.size != 3 || outputs[2].ar.burst != expected_ar_burst)
          $fatal(1, "Xbar changed AR fields");
        $display("XBAR AR cycle=%0d addr=%h len=%0d size=%0d", cycles, outputs[2].ar.addr, outputs[2].ar.len, outputs[2].ar.size);
      end
      if (llc_req.ar_valid && cut_rsp.ar_ready) begin
        llc_ar_count++;
        if (cut_req.ar.addr != expected_ar_addr || llc_req.ar.len != expected_ar_beats-1 ||
            llc_req.ar.size != 3 || llc_req.ar.burst != expected_ar_burst)
          $fatal(1, "Atomics/cut changed AR fields");
        $display("LLC AR cycle=%0d addr=%h len=%0d size=%0d", cycles, llc_req.ar.addr, llc_req.ar.len, llc_req.ar.size);
      end
      if (cut_rsp.r_valid && llc_req.r_ready)
        $display("LLC R cycle=%0d data=%h last=%b", cycles, cut_rsp.r.data, cut_rsp.r.last);
      if (responses[3].r_valid && drive.r_ready) begin
        accepted++;
        $display("HOST R cycle=%0d data=%h last=%b", cycles, responses[3].r.data, responses[3].r.last);
      end
    end
  end
  always @(negedge clk) drive.r_ready = rst_n && (!stall_reads || cycles % 7 == 0);

  function automatic data_t pattern(addr_t address, int epoch);
    return 64'hefcdab8967452301 ^ ((64'(address) >> 3) * 64'h9e3779b97f4a7c15)
           ^ (64'(epoch) * 64'h1032547698badcfe);
  endfunction

  task automatic write_words(addr_t address, int beats, int epoch);
    @(negedge clk);
    drive.aw = '0;
    drive.aw.addr = address;
    drive.aw.len = 8'(beats-1);
    drive.aw.size = 3;
    drive.aw.burst = axi_pkg::BURST_INCR;
    drive.aw_valid = 1;
    do @(posedge clk); while (!responses[3].aw_ready);
    @(negedge clk);
    drive.aw_valid = 0;
    for (int i = 0; i < beats; i++) begin
      drive.w.data = pattern(address + 8*i, epoch);
      drive.w.strb = '1;
      drive.w.last = (i == beats-1);
      drive.w_valid = 1;
      do @(posedge clk); while (!responses[3].w_ready);
      @(negedge clk);
      drive.w_valid = 0;
    end
    drive.b_ready = 1;
    do @(posedge clk); while (!responses[3].b_valid);
    if (responses[3].b.resp != axi_pkg::RESP_OKAY || responses[3].b.id != 0)
      $fatal(1, "Unexpected write response");
    @(negedge clk);
    drive.b_ready = 0;
  endtask

  task automatic read_words_mode(addr_t address, int beats, int epoch,
                                 axi_pkg::burst_t burst);
    @(negedge clk);
    expected_ar_addr = address;
    expected_ar_beats = beats;
    expected_ar_burst = burst;
    drive.ar = '0;
    drive.ar.addr = address;
    drive.ar.len = 8'(beats-1);
    drive.ar.size = 3;
    drive.ar.burst = burst;
    drive.ar_valid = 1;
    do @(posedge clk); while (!responses[3].ar_ready);
    @(negedge clk);
    drive.ar_valid = 0;
    for (int i = 0; i < beats; i++) begin
      do @(posedge clk); while (!(responses[3].r_valid && drive.r_ready));
      if (responses[3].r.data !== pattern(
          burst == axi_pkg::BURST_FIXED ? address : address + 8*i, epoch) ||
          responses[3].r.last != (i == beats-1) ||
          responses[3].r.resp != axi_pkg::RESP_OKAY || responses[3].r.id != 0)
        $fatal(1, "Read mismatch addr=%h beat=%0d got=%h expected=%h last=%b", address, i,
               responses[3].r.data,
               pattern(burst == axi_pkg::BURST_FIXED ? address : address+8*i, epoch),
               responses[3].r.last);
      checks++;
    end
    @(negedge clk);
  endtask

  task automatic read_words(addr_t address, int beats, int epoch);
    read_words_mode(address, beats, epoch, axi_pkg::BURST_INCR);
  endtask

  task automatic exercise(addr_t address, int beats);
    for (int i = 0; i < beats; i++) write_words(address+8*i, 1, 0);
    read_words(address, beats, 0);
    stall_reads = 1;
    read_words(address, beats, 0);
    stall_reads = 0;
    write_words(address, beats, 1);
    for (int i = 0; i < beats; i++) read_words(address+8*i, 1, 1);
    read_words(address, beats, 1);
  endtask

  task automatic config_access(bit write, reg_word_t address, reg_word_t value,
                               output reg_word_t result);
    @(negedge clk);
    cfg_req = '{addr:address, write:write, wdata:value, wstrb:'1, valid:1'b1};
    do @(posedge clk); while (!cfg_rsp.ready);
    if (cfg_rsp.error) $fatal(1, "LLC configuration access failed");
    result = cfg_rsp.rdata;
    @(negedge clk);
    cfg_req = '0;
  endtask

  initial begin
    reg_word_t value;
    drive = '0;
    repeat (5) @(negedge clk);
    por_n = 1;
    wait (rst_n);
    // Same initialization as software/reference/cheshire_bootrom.S.
    do config_access(0, 'h48, 0, value); while (value == 0);
    config_access(1, 'h00, '1, value);
    config_access(1, 'h04, '1, value);
    config_access(1, 'h10, 1, value);
    do config_access(0, 'h18, 0, value); while (value != 'hff);
    exercise(48'h1401ff00, 2);
    exercise(48'hffff0000, 2);
    exercise(48'h1401ff38, 16);
    exercise(48'h81000ff8, 1);
    exercise(48'h81001000, 16);
    // Reproduce the board's discriminating start offsets and lengths.
    exercise(48'h1401ff08, 2);
    exercise(48'h1401ff38, 2);
    exercise(48'h1401ff40, 2);
    exercise(48'h1401ff00, 3);
    exercise(48'h1401ff38, 3);
    exercise(48'hffff0008, 2);
    exercise(48'hffff0038, 2);
    exercise(48'hffff0040, 2);
    exercise(48'hffff0000, 3);
    exercise(48'hffff0038, 3);
    read_words_mode(48'h1401ff00, 2, 1, axi_pkg::BURST_FIXED);
    read_words_mode(48'h1401ff38, 3, 1, axi_pkg::BURST_FIXED);
    exercise(48'h14010000, 256);
    exercise(48'h81002000, 256);
    repeat (20) @(negedge clk);
    if (checks != 2297 || accepted != checks || stalled == 0 ||
        host_ar_count != 626 || xbar_ar_count != host_ar_count || llc_ar_count != host_ar_count)
      $fatal(1, "Coverage/count mismatch checks=%0d accepted=%0d stalled=%0d AR=%0d/%0d/%0d",
             checks, accepted, stalled, host_ar_count, xbar_ar_count, llc_ar_count);
    $display("PASS: host burst path checked_beats=%0d read_transactions=%0d stalled_cycles=%0d cycles=%0d",
             checks, host_ar_count, stalled, cycles);
    $finish;
  end
endmodule
