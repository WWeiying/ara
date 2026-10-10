// Real exported AXI/reg/PLIC RTL; no CPU, UART model, board, or forced DUT state.
// Fixed AXI data/address/user widths 64/48/2, CutMemReqs=1. These match the
// current board's inherited DefaultCfg, but omit its ID topology/atomics/cuts.
// All software addresses are physical. In particular, never subtract Base.
`include "axi/typedef.svh"
`include "register_interface/typedef.svh"

module plic_contract_tb;
  timeunit 1ns;
  timeprecision 1ps;
  import rv_plic_reg_pkg::*;
  localparam int MaxCycles = 8192;
  localparam int WaitCycles = 100;
  localparam int SrcWidth = $clog2(NumSrc);
  typedef logic [47:0] addr_t;
  typedef logic [63:0] data_t;
  typedef logic [7:0] strb_t;
  typedef logic [3:0] id_t;
  typedef logic [1:0] user_t;
  typedef logic [31:0] word_t;
  typedef logic [3:0] byte_en_t;
  `AXI_TYPEDEF_ALL(axi, addr_t, id_t, data_t, strb_t, user_t)
  `REG_BUS_TYPEDEF_ALL(reg_bus, addr_t, word_t, byte_en_t)
  typedef struct packed { int unsigned idx; addr_t start_addr; addr_t end_addr; } rule_t;
  localparam addr_t Base = 48'h04000000;
  localparam rule_t [0:0] Rules = '{'{idx: 0, start_addr: Base, end_addr: 48'h08000000}};
  localparam int Sources[6] = '{1, 31, 32, 51, 52, 57};

  logic clk_i = 0;
  logic rst_ni = 0;
  always #5ns clk_i = ~clk_i;
  axi_req_t axi_req = '0;
  axi_resp_t axi_rsp;
  reg_bus_req_t reg_req;
  reg_bus_rsp_t reg_rsp;
  reg_bus_req_t [1:0] out_req;
  reg_bus_rsp_t [1:0] out_rsp;
  logic select, decode_valid, decode_error, busy;
  id_t reg_id;
  logic [NumSrc-1:0] sources = '0;
  logic [NumTarget-1:0] irq, msip;
  logic [SrcWidth-1:0] irq_id[NumTarget];
  logic [NumTarget-1:0][NumSrc-1:0] ie;
  logic [NumTarget-1:0][PrioWidth-1:0] threshold;
  logic [NumTarget-1:0][SrcWidth-1:0] claim_id, complete_id, target_id;

  axi_to_reg_v2 #(
    .AxiAddrWidth(48), .AxiDataWidth(64), .AxiIdWidth(4), .AxiUserWidth(2),
    .RegDataWidth(32), .CutMemReqs(1), .CutMemRsps(0),
    .axi_req_t(axi_req_t), .axi_rsp_t(axi_resp_t),
    .reg_req_t(reg_bus_req_t), .reg_rsp_t(reg_bus_rsp_t)
  ) i_bridge (
    .clk_i, .rst_ni, .axi_req_i(axi_req), .axi_rsp_o(axi_rsp),
    .reg_req_o(reg_req), .reg_rsp_i(reg_rsp), .reg_id_o(reg_id), .busy_o(busy)
  );
  addr_decode #(.NoIndices(2), .NoRules(1), .addr_t(addr_t), .rule_t(rule_t)) i_decode (
    .addr_i(reg_req.addr), .addr_map_i(Rules), .idx_o(select),
    .dec_valid_o(decode_valid), .dec_error_o(decode_error),
    .en_default_idx_i(1'b1), .default_idx_i(1'b1)
  );
  reg_demux #(.NoPorts(2), .req_t(reg_bus_req_t), .rsp_t(reg_bus_rsp_t)) i_demux (
    .clk_i, .rst_ni, .in_select_i(select), .in_req_i(reg_req), .in_rsp_o(reg_rsp),
    .out_req_o(out_req), .out_rsp_i(out_rsp)
  );
  reg_err_slv #(.DW(32), .ERR_VAL(32'hbadcab1e),
                .req_t(reg_bus_req_t), .rsp_t(reg_bus_rsp_t)) i_error (
    .req_i(out_req[1]), .rsp_o(out_rsp[1])
  );
  rv_plic #(.reg_req_t(reg_bus_req_t), .reg_rsp_t(reg_bus_rsp_t)) i_plic (
    .clk_i, .rst_ni, .reg_req_i(out_req[0]), .reg_rsp_o(out_rsp[0]),
    .intr_src_i(sources), .irq_o(irq), .irq_id_o(irq_id), .msip_o(msip)
  );
  for (genvar t = 0; t < NumTarget; t++) begin : gen_probe
    assign ie[t] = i_plic.ie[t];
    assign threshold[t] = i_plic.threshold[t];
    assign claim_id[t] = i_plic.claim_id[t];
    assign complete_id[t] = i_plic.complete_id[t];
    assign target_id[t] = irq_id[t];
  end

  int fd, cycles = 0, transactions = 0, checks = 0, cases_done = 0;
  int failures = 0, case_failures = 0;
  int reg_writes = 0, claim_reads = 0, r_stalls = 0, b_stalls = 0;
  int aw_count = 0, w_count = 0, b_count = 0, ar_count = 0, r_count = 0;
  bit completed = 0;
  int transaction_id = -1;
  addr_t transaction_addr = '0;
  string case_name = "reset";
  clocking cb @(posedge clk_i);
    default input #1step;
    input rst_ni, axi_req, axi_rsp, reg_req, reg_rsp, select, decode_valid, decode_error;
    input out_req, out_rsp, sources, irq, msip, ie, threshold, claim_id, complete_id, target_id;
    input paddr = i_plic.u_reg.reg_addr;
    input hit = i_plic.u_reg.addr_hit;
    input miss = i_plic.u_reg.addrmiss;
    input wr_error = i_plic.u_reg.wr_err;
    input synced = i_plic.intr_src_synced;
    input ip = i_plic.ip;
    input ia = i_plic.u_gateway.ia;
    input prio = i_plic.prio;
    input claim_re = i_plic.claim_re;
    input complete_we = i_plic.complete_we;
    input claim = i_plic.claim;
    input complete = i_plic.complete;
  endclocking

  task automatic fail(input string code);
    $display("PLIC_FAIL code=%s case=%s txn=%0d addr=%h cycle=%0d",
             code, case_name, transaction_id, transaction_addr, cycles);
    $fflush(fd);
    $fatal(1, "PLIC contract failed");
  endtask
  task automatic check(input logic condition, input string code);
    checks++;
    if (condition !== 1'b1) fail(code);
  endtask
  // Only isolated, recoverable functional violations use this path. Transport
  // corruption, X, timeout, and unexpected setup failures still stop immediately.
  task automatic observe_check(input logic condition, input string code,
                               input data_t expected, input data_t actual);
    checks++;
    $display("PLIC_EXPECT code=%s case=%s txn=%0d cycle=%0d expected=%h actual=%h status=%s",
             code, case_name, transaction_id, cycles, expected, actual,
             condition === 1'b1 ? "PASS" : "FAIL");
    if (condition !== 1'b1) begin
      failures++;
      case_failures++;
    end
  endtask
  task automatic settle(input int n = 8);
    repeat (n) @(negedge clk_i);
  endtask
  function automatic addr_t enable_addr(input int t, input int word_index);
    return Base + 48'h2000 + addr_t'(t * 128 + word_index * 4);
  endfunction
  function automatic addr_t threshold_addr(input int t);
    return Base + 48'h200000 + addr_t'(t * 4096);
  endfunction
  function automatic addr_t cc_addr(input int t);
    return threshold_addr(t) + 4;
  endfunction
  task automatic case_pass;
    cases_done++;
    $display("PLIC_CASE name=%s status=%s failures=%0d", case_name,
             case_failures == 0 ? "PASS" : "FAIL", case_failures);
    case_failures = 0;
  endtask
  task automatic reset_boundary;
    @(negedge clk_i);
    check(!busy && axi_req === '0, "reset_inflight");
    $display("PLIC_RESET case=%s cycle=%0d", case_name, cycles);
    sources = '0;
    rst_ni = 0;
    settle(5);
    rst_ni = 1;
    settle();
    check(irq === '0 && i_plic.ip === '0 && i_plic.u_gateway.ia === '0,
          "reset_state");
  endtask

  // Drive only on falling edges. Payloads are inspected from the pre-edge snapshot.
  // AW and W launch independently; neither channel waits for READY before VALID.
  task automatic transfer(input bit write, input addr_t address, input data_t data,
                          input strb_t strobes, input logic [2:0] size,
                          input logic [1:0] expected_resp, output data_t result);
    bit aw_done, w_done, ar_done, response_seen;
    axi_b_chan_t held_b;
    axi_r_chan_t held_r;
    id_t id;
    @(negedge clk_i);
    transaction_id = transactions;
    transaction_addr = address;
    id = id_t'(transactions);
    $display("PLIC_TX_BEGIN txn=%0d write=%b addr=%h size=%0d data=%h strb=%h expected=%b",
             transaction_id, write, address, size, data, strobes, expected_resp);
    aw_done = 0; w_done = 0; ar_done = 0; response_seen = 0; result = '0;
    axi_req = '0;
    if (write) begin
      axi_req.aw = '{id: id, addr: address, len: 0, size: size,
                     burst: axi_pkg::BURST_INCR, default: '0};
      axi_req.w = '{data: data, strb: strobes, last: 1'b1, default: '0};
      axi_req.aw_valid = (transactions % 2 == 0);
      axi_req.w_valid = !axi_req.aw_valid;
    end else begin
      axi_req.ar = '{id: id, addr: address, len: 0, size: size,
                     burst: axi_pkg::BURST_INCR, default: '0};
      axi_req.ar_valid = 1;
    end
    for (int k = 0; k < WaitCycles; k++) begin
      @(cb);
      if (write) begin
        if (cb.axi_req.aw_valid && cb.axi_rsp.aw_ready) aw_done = 1;
        if (cb.axi_req.w_valid && cb.axi_rsp.w_ready) w_done = 1;
      end else if (cb.axi_req.ar_valid && cb.axi_rsp.ar_ready) ar_done = 1;
      @(negedge clk_i);
      if (write) begin
        if (k >= 1) begin
          axi_req.aw_valid = !aw_done;
          axi_req.w_valid = !w_done;
        end
        if (aw_done) axi_req.aw_valid = 0;
        if (w_done) axi_req.w_valid = 0;
      end else if (ar_done) axi_req.ar_valid = 0;
      if ((write && aw_done && w_done) || (!write && ar_done)) break;
      if (k == WaitCycles-1) fail("request_timeout");
    end
    for (int k = 0; k < WaitCycles; k++) begin
      @(cb);
      if (write ? cb.axi_rsp.b_valid : cb.axi_rsp.r_valid) begin
        held_b = cb.axi_rsp.b; held_r = cb.axi_rsp.r;
        response_seen = 1;
        break;
      end
    end
    check(response_seen, "response_timeout");
    // READY remains low for four additional cycles after VALID is observed.
    repeat (4) begin
      @(cb);
      if (write) check(cb.axi_rsp.b_valid && cb.axi_rsp.b === held_b, "unstable_b");
      else check(cb.axi_rsp.r_valid && cb.axi_rsp.r === held_r, "unstable_r");
    end
    if (write) begin
      check(held_b.id === id, "b_id");
      check(held_b.resp === expected_resp, "axi_response");
    end else begin
      check(held_r.id === id && held_r.last === 1'b1, "r_id_last");
      check(held_r.resp === expected_resp, "axi_response");
      result = held_r.data;
    end
    @(negedge clk_i);
    if (write) axi_req.b_ready = 1; else axi_req.r_ready = 1;
    @(cb);
    check(write ? cb.axi_rsp.b_valid : cb.axi_rsp.r_valid, "response_disappeared");
    @(negedge clk_i);
    axi_req = '0;
    $display("PLIC_TX_END txn=%0d resp=%b data=%h", transaction_id,
             write ? held_b.resp : held_r.resp, result);
    transactions++;
  endtask
  task automatic wr(input addr_t address, input word_t value,
                    input byte_en_t be = 4'hf, input logic [1:0] resp = axi_pkg::RESP_OKAY);
    data_t unused;
    transfer(1, address, data_t'(value) << (address[2] ? 32 : 0),
             strb_t'(be) << (address[2] ? 4 : 0), 3'd2, resp, unused);
  endtask
  task automatic rd(input addr_t address, input word_t expected,
                    input logic [1:0] resp = axi_pkg::RESP_OKAY);
    data_t value;
    transfer(0, address, '0, '0, 3'd2, resp, value);
    if (resp == axi_pkg::RESP_OKAY)
      check(word_t'(value >> (address[2] ? 32 : 0)) === expected, "read_data");
  endtask
  task automatic enables(input int t, input logic [63:0] value);
    wr(enable_addr(t, 0), value[31:0]);
    wr(enable_addr(t, 1), value[63:32]);
  endtask
  task automatic isolated(input int t, input logic [63:0] value);
    enables(0, t == 0 ? value : 0);
    enables(1, t == 1 ? value : 0);
    wr(threshold_addr(0), 0); wr(threshold_addr(1), 0);
  endtask
  task automatic irq_is(input logic [1:0] expected);
    settle();
    check(irq === NumTarget'(expected), "irq_context");
  endtask
  task automatic pending(input logic [63:0] expected);
    rd(Base + 48'h1000, expected[31:0]);
    rd(Base + 48'h1004, expected[63:32]);
  endtask
  task automatic source_level(input int id, input bit value);
    @(negedge clk_i);
    sources[id] = value;
    settle();
  endtask

  always @(cb) begin : observe
    if (fd != 0) begin
      $fwrite(fd, {"cycle=%0d time_ns=%0.3f rst=%b txn=%0d case=%s",
        " awv=%b awr=%b awaddr=%h awid=%h awsize=%h wv=%b wr=%b wd=%h ws=%h wl=%b",
        " bv=%b br=%b bid=%h bresp=%b arv=%b arr=%b araddr=%h arid=%h arsize=%h",
        " rv=%b rr=%b rid=%h rresp=%b rd=%h rl=%b",
        " regv=%b regr=%b regw=%b regaddr=%h regwd=%h regbe=%h regrd=%h regerr=%b",
        " sel=%b decvalid=%b decerr=%b pvalid=%b paddr=%h hit=%h miss=%b wrerr=%b",
        " src=%h synced=%h ip=%h ia=%h ie=%h prio=%h threshold=%h",
        " claim_re=%h claim_id=%h claim=%h complete_we=%h complete_id=%h complete=%h",
        " irq=%h irq_id=%h msip=%h\n"},
        cycles, $realtime, cb.rst_ni, transaction_id, case_name,
        cb.axi_req.aw_valid, cb.axi_rsp.aw_ready, cb.axi_req.aw.addr, cb.axi_req.aw.id,
        cb.axi_req.aw.size, cb.axi_req.w_valid, cb.axi_rsp.w_ready, cb.axi_req.w.data,
        cb.axi_req.w.strb, cb.axi_req.w.last, cb.axi_rsp.b_valid, cb.axi_req.b_ready,
        cb.axi_rsp.b.id, cb.axi_rsp.b.resp, cb.axi_req.ar_valid, cb.axi_rsp.ar_ready,
        cb.axi_req.ar.addr, cb.axi_req.ar.id, cb.axi_req.ar.size,
        cb.axi_rsp.r_valid, cb.axi_req.r_ready, cb.axi_rsp.r.id, cb.axi_rsp.r.resp,
        cb.axi_rsp.r.data, cb.axi_rsp.r.last, cb.reg_req.valid, cb.reg_rsp.ready,
        cb.reg_req.write, cb.reg_req.addr, cb.reg_req.wdata, cb.reg_req.wstrb,
        cb.reg_rsp.rdata, cb.reg_rsp.error, cb.select, cb.decode_valid, cb.decode_error,
        cb.out_req[0].valid, cb.paddr, cb.hit, cb.miss, cb.wr_error,
        cb.sources, cb.synced, cb.ip, cb.ia, cb.ie, cb.prio, cb.threshold,
        cb.claim_re, cb.claim_id, cb.claim, cb.complete_we, cb.complete_id, cb.complete,
        cb.irq, cb.target_id, cb.msip);
      cycles++;
      if (cycles % 64 == 0) $fflush(fd);
    end
    if (cb.rst_ni) begin
      aw_count += cb.axi_req.aw_valid && cb.axi_rsp.aw_ready;
      w_count += cb.axi_req.w_valid && cb.axi_rsp.w_ready;
      b_count += cb.axi_rsp.b_valid && cb.axi_req.b_ready;
      ar_count += cb.axi_req.ar_valid && cb.axi_rsp.ar_ready;
      r_count += cb.axi_rsp.r_valid && cb.axi_req.r_ready;
      r_stalls += cb.axi_rsp.r_valid && !cb.axi_req.r_ready;
      b_stalls += cb.axi_rsp.b_valid && !cb.axi_req.b_ready;
      reg_writes += cb.reg_req.valid && cb.reg_rsp.ready && cb.reg_req.write;
      claim_reads += $countones(cb.claim_re);
      if ($isunknown({cb.axi_rsp.aw_ready, cb.axi_rsp.w_ready, cb.axi_rsp.ar_ready,
                      cb.axi_rsp.b_valid, cb.axi_rsp.r_valid, cb.irq})) fail("unknown_control");
    end
    if (cycles >= MaxCycles) fail("cycle_timeout");
  end
  final begin
    if (fd != 0) begin
      $fwrite(fd, "# END rows=%0d completed=%b transactions=%0d checks=%0d\n",
              cycles, completed, transactions, checks);
      $fclose(fd);
    end
  end

  initial begin : stimulus
    data_t value, saved_value;
    int before_count;
    fd = $fopen("plic_signals.log", "w");
    if (fd == 0) $fatal(1, "PLIC probe open failed");
    $fwrite(fd, "# PLIC_PROBE schema=1 sample=pre_edge max_cycles=%0d\n", MaxCycles);
    $display("PLIC_CONFIG src=%0d targets=%0d prio_width=%0d block_aw=%0d axi_data=64 axi_addr=48 cut=1",
             NumSrc, NumTarget, PrioWidth, BlockAw);
    settle(5); rst_ni = 1; settle();
    case_name = "physical_decode";
    // Must remain transaction zero, before shape checks: the legacy package
    // fails on absolute priority1, not on a synthetic relative-offset test.
    wr(Base + 4, 3);
    check(NumSrc == 58 && NumTarget == 2 && BlockAw == 26 && PrioWidth == 3, "ip_shape");
    rd(Base + 4, 3);
    check(msip === '0 && irq === '0, "reset_outputs");
    case_pass();

    case_name = "word_lanes";
    transfer(1, Base + 8, 64'h0000000600000005, 8'hff, 3'd3, axi_pkg::RESP_OKAY, value);
    transfer(0, Base + 8, '0, '0, 3'd3, axi_pkg::RESP_OKAY, value);
    check(value === 64'h0000000600000005, "doubleword_lanes");
    rd(Base + 8, 5); rd(Base + 12, 6);
    wr(Base + 4, 5, 4'h1); rd(Base + 4, 5);
    wr(Base + 4, 7, 4'h2, axi_pkg::RESP_SLVERR); rd(Base + 4, 5);
    before_count = reg_writes;
    wr(Base + 4, 7, 4'h0);
    check(reg_writes == before_count, "zero_strobe_side_effect"); rd(Base + 4, 5);
    case_pass();

    case_name = "reserved_holes";
    for (int t = 0; t < 2; t++) begin
      enables(t, '1);
      transfer(0, enable_addr(t, 0), '0, '0, 3'd2, axi_pkg::RESP_OKAY, value);
      check(value[31:1] === 31'h7fffffff, "ie_word0_valid_bits");
      observe_check(value[0] === 1'b0, $sformatf("ie_zero_context%0d", t),
                    64'hfffffffe, {32'b0, value[31:0]});
      saved_value = value;
      rd(enable_addr(t, 1), 32'h03ffffff);
      wr(enable_addr(t, 0), 0, 4'h1, axi_pkg::RESP_SLVERR);
      transfer(0, enable_addr(t, 0), '0, '0, 3'd2, axi_pkg::RESP_OKAY, value);
      check(value[31:0] === saved_value[31:0], "failed_ie_write_changed_state");
      enables(t, 0);
    end
    wr(Base, 7); enables(0, 1); irq_is(0); pending(0); rd(cc_addr(0), 0);
    enables(0, 0);
    wr(Base + 4, 32'hffffffff); rd(Base + 4, 7);
    wr(Base + 48'he8, 7, 4'hf, axi_pkg::RESP_SLVERR);
    rd(Base + 48'he8, 0, axi_pkg::RESP_SLVERR);
    rd(Base + 48'h1008, 0, axi_pkg::RESP_SLVERR);
    wr(Base + 48'h2100, '1, 4'hf, axi_pkg::RESP_SLVERR);
    rd(Base + 48'h2100, 0, axi_pkg::RESP_SLVERR);
    rd(Base + 48'h202000, 0, axi_pkg::RESP_SLVERR);
    wr(Base + 48'h202004, 1, 4'hf, axi_pkg::RESP_SLVERR);
    rd(48'h03fffffc, 0, axi_pkg::RESP_SLVERR);
    rd(48'h08000000, 0, axi_pkg::RESP_SLVERR);
    wr(48'h08004000, 1, 4'hf, axi_pkg::RESP_SLVERR);
    rd(48'h07fffff0, 0, axi_pkg::RESP_SLVERR);
    wr(48'h07fffff8, 1); check(msip === '0, "nonstandard_msip");
    rd(48'h07fffff8, 1); wr(48'h07fffff8, 0);
    wr(48'h07fffffc, 1); rd(48'h07fffffc, 0);
    rd(Base + 4, 7);
    case_pass();
    reset_boundary();

    case_name = "source_context_matrix";
    for (int t = 0; t < 2; t++) begin
      foreach (Sources[k]) begin
        automatic int id = Sources[k];
        isolated(t, 64'b1 << id); wr(Base + addr_t'(4*id), 3);
        source_level(id, 1); irq_is(2'(1 << t)); pending(64'b1 << id);
        rd(cc_addr(t), word_t'(id)); irq_is(0); pending(0);
        rd(cc_addr(t), 0); // A held source cannot re-pend before completion.
        wr(cc_addr(t), word_t'(id)); irq_is(2'(1 << t));
        rd(cc_addr(t), word_t'(id)); source_level(id, 0);
        wr(cc_addr(t), word_t'(id)); irq_is(0); pending(0);
        source_level(id, 1); irq_is(2'(1 << t)); rd(cc_addr(t), word_t'(id));
        source_level(id, 0); wr(cc_addr(t), word_t'(id)); irq_is(0);
        $display("PLIC_SOURCE id=%0d context=%0d status=PASS", id, t);
      end
    end
    case_pass();

    case_name = "priority_threshold";
    isolated(0, (64'b1 << 31) | (64'b1 << 32));
    wr(Base + 4*31, 3); wr(Base + 4*32, 5); wr(threshold_addr(0), 5);
    source_level(31, 1); source_level(32, 1); irq_is(0);
    // PLIC 1.0: claim is independent of threshold. Exercise it below.
    wr(threshold_addr(0), 4); irq_is(1); rd(cc_addr(0), 32);
    source_level(32, 0); wr(cc_addr(0), 32); irq_is(0);
    wr(threshold_addr(0), 2); irq_is(1); rd(cc_addr(0), 31);
    source_level(31, 0); wr(cc_addr(0), 31); irq_is(0);
    isolated(0, (64'b1 << 51) | (64'b1 << 52));
    wr(Base + 4*51, 4); wr(Base + 4*52, 4);
    source_level(51, 1); source_level(52, 1); rd(cc_addr(0), 51);
    source_level(51, 0); wr(cc_addr(0), 51); settle(); rd(cc_addr(0), 52);
    source_level(52, 0); wr(cc_addr(0), 52); irq_is(0);
    isolated(0, 64'b1 << 57); wr(Base + 4*57, 0);
    source_level(57, 1); irq_is(0); wr(Base + 4*57, 1); irq_is(1);
    wr(threshold_addr(0), 7); irq_is(0); rd(cc_addr(0), 57);
    source_level(57, 0); wr(cc_addr(0), 57); wr(threshold_addr(0), 0); irq_is(0);
    case_pass();

    case_name = "competition_completion";
    enables(0, 64'b1 << 57); enables(1, 64'b1 << 57);
    wr(Base + 4*57, 3); source_level(57, 1); irq_is(3);
    rd(cc_addr(0), 57); irq_is(0); rd(cc_addr(1), 0);
    wr(cc_addr(0), 0); wr(cc_addr(0), 58); wr(cc_addr(1), 63);
    irq_is(0); pending(0);
    // Both contexts enable 57; the gateway has no context ownership state.
    wr(cc_addr(1), 57); irq_is(3); rd(cc_addr(1), 57);
    source_level(57, 0); wr(cc_addr(1), 57); irq_is(0); pending(0);
    // Unlike the preceding enabled-context completion, this must be ignored.
    isolated(0, 64'b1 << 57); source_level(57, 1); irq_is(1);
    rd(cc_addr(0), 57); irq_is(0);
    wr(cc_addr(1), 57); settle();
    value = (data_t'(irq) << 2) | (data_t'(i_plic.ip[57]) << 1) |
            data_t'(i_plic.u_gateway.ia[57]);
    observe_check(value === 64'd1, "disabled_context_completion", 64'd1, value);
    case_pass();
    reset_boundary();

    case_name = "read_side_effect";
    isolated(0, 64'b1 << 1); wr(Base + 4, 3);
    // Threshold WARL readback with no pending source, followed by the
    // discriminating live-pending read. Do not mask a bridge over-read.
    wr(threshold_addr(0), '1); rd(threshold_addr(0), 7);
    wr(threshold_addr(0), 0); source_level(1, 1); irq_is(1);
    before_count = claim_reads;
    rd(threshold_addr(0), 0);
    observe_check(claim_reads == before_count, "threshold_read_claimed", 0,
                  data_t'(claim_reads - before_count));
    settle();
    value = (data_t'(irq) << 2) | data_t'(i_plic.ip[1:0]);
    observe_check(value === 64'd6, "threshold_read_pending", 6, value);
    case_pass();
    reset_boundary();
    settle();
    check(aw_count == w_count && w_count == b_count && ar_count == r_count &&
          transactions == b_count + r_count, "handshake_counts");
    check(r_stalls >= 4 && b_stalls >= 4, "backpressure_missing");
    completed = 1;
    $display("PLIC_RESULT status=%s cases=%0d transactions=%0d checks=%0d cycles=%0d failures=%0d",
             failures == 0 ? "PASS" : "FAIL", cases_done, transactions, checks, cycles, failures);
    if (failures != 0) $fatal(1, "PLIC contract has %0d functional failures", failures);
    $finish;
  end
endmodule
