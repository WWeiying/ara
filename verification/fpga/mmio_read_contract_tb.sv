// AXI64/reg32 bridge only. No CPU, PLIC, interconnect, atomics, or board model.
// The oracle is driven by AXI handshakes, never by DUT metadata or bank strobes.
`include "axi/typedef.svh"
`include "register_interface/typedef.svh"

module mmio_read_contract_tb;
  timeunit 1ns;
  timeprecision 1ps;
  localparam int MaxCycles = 4096;
  localparam int Limit = 256;
  localparam logic [47:0] Base = 48'h04000000;
  typedef logic [47:0] addr_t;
  typedef logic [63:0] data_t;
  typedef logic [7:0] strb_t;
  typedef logic [3:0] id_t;
  typedef logic [1:0] user_t;
  typedef logic [31:0] word_t;
  typedef logic [3:0] be_t;
  `AXI_TYPEDEF_ALL(axi, addr_t, id_t, data_t, strb_t, user_t)
  `REG_BUS_TYPEDEF_ALL(reg_bus, addr_t, word_t, be_t)
  logic clk_i = 0, rst_ni = 0;
  always #5ns clk_i = ~clk_i;
  axi_req_t req = '0;
  axi_resp_t rsp;
  reg_bus_req_t reg_req;
  reg_bus_rsp_t reg_rsp;
  id_t reg_id;
  logic busy, reg_ready = 0;
  axi_to_reg_v2 #(
    .AxiAddrWidth(48), .AxiDataWidth(64), .AxiIdWidth(4), .AxiUserWidth(2),
    .RegDataWidth(32), .CutMemReqs(1), .CutMemRsps(0),
    .axi_req_t(axi_req_t), .axi_rsp_t(axi_resp_t),
    .reg_req_t(reg_bus_req_t), .reg_rsp_t(reg_bus_rsp_t)
  ) dut (
    .clk_i, .rst_ni, .axi_req_i(req), .axi_rsp_o(rsp),
    .reg_req_o(reg_req), .reg_rsp_i(reg_rsp), .reg_id_o(reg_id), .busy_o(busy)
  );

  word_t storage[128], shadow[128];
  int error_profile = 0;
  int unsigned read_effects[128], shadow_effects[128];
  int model_reads = 0, model_writes = 0;
  function automatic bit mapped(input addr_t address);
    return address >= Base && address < Base + 512 &&
           address != Base + 48'h34 && address != Base + 48'h38 &&
           !(error_profile == 1 && (address == Base+4 || address == Base+12)) &&
           !(error_profile == 2 && address == Base+8);
  endfunction
  function automatic word_t initial_word(input int index);
    return 32'ha5000000 ^ (word_t'(index) * 32'h00110307);
  endfunction
  // Every successful read changes the next read value. Writes update selected bytes.
  always_comb begin
    reg_rsp = '0;
    reg_rsp.ready = reg_ready;
    reg_rsp.error = !mapped(reg_req.addr);
    reg_rsp.rdata = 32'hbadcab1e;
    if (mapped(reg_req.addr))
      reg_rsp.rdata = storage[(reg_req.addr-Base)/4] ^
                     (word_t'(read_effects[(reg_req.addr-Base)/4]) * 32'h01010101);
  end
  always @(posedge clk_i) begin
    if (!rst_ni) begin
      for (int i = 0; i < 128; i++) begin
        storage[i] <= initial_word(i);
        read_effects[i] <= 0;
      end
      model_reads <= 0;
      model_writes <= 0;
    end else if (reg_req.valid && reg_rsp.ready && !reg_rsp.error) begin
      if (reg_req.write) begin
        for (int b = 0; b < 4; b++)
          if (reg_req.wstrb[b]) storage[(reg_req.addr-Base)/4][b*8+:8] <= reg_req.wdata[b*8+:8];
        model_writes <= model_writes + 1;
      end else begin
        read_effects[(reg_req.addr-Base)/4] <= read_effects[(reg_req.addr-Base)/4] + 1;
        model_reads <= model_reads + 1;
      end
    end
  end

  int fd, cycles = 0, checks = 0, cases_done = 0;
  int failures = 0, case_failures = 0;
  int epoch_regs = 0, epoch_expected = 0;
  int ar_count = 0, aw_count = 0, w_count = 0, r_count = 0, b_count = 0;
  int read_beats = 0, write_beats = 0, reg_count = 0, expected_regs = 0;
  int r_stalls = 0, b_stalls = 0, reg_stalls = 0, queued_ar = 0, held_w_reads = 0;
  int burst_requests = 0, unaligned_requests = 0;
  bit completed = 0;
  string case_name = "reset";

  typedef struct packed {
    addr_t address;
    strb_t lanes;
    id_t id;
    bit last;
    logic [1:0] response;
    data_t data;
    logic [1:0] banks, seen;
  } beat_t;
  typedef struct packed {
    addr_t address;
    be_t be;
    word_t data;
    int beat;
  } expected_t;
  typedef struct packed {
    reg_bus_req_t request;
    reg_bus_rsp_t response;
    int cycle;
  } actual_t;
  typedef expected_t expect_queue_t[$];
  typedef actual_t actual_queue_t[$];
  expect_queue_t expected[2][2]; // [write][bank], independent of reg arbitration order
  actual_queue_t actual[2][2];
  beat_t reads[Limit], writes[Limit];
  axi_aw_chan_t aw_queue[$];
  axi_w_chan_t w_queue[$];
  axi_r_chan_t last_r;
  axi_b_chan_t last_b;
  bit r_held = 0, b_held = 0;

  logic [1:0] cut_valid, cut_ready;
  addr_t [1:0] cut_addr;
  logic [1:0][3:0] cut_strb;
  logic [1:0] cut_write;
  for (genvar i = 0; i < 2; i++) begin : gen_probe
    assign cut_valid[i] = dut.gen_tcdm_to_reg[i].mem_cut_req_valid;
    assign cut_ready[i] = dut.gen_tcdm_to_reg[i].mem_cut_req_ready;
    assign cut_addr[i] = dut.gen_tcdm_to_reg[i].mem_cut_req.addr;
    assign cut_strb[i] = dut.gen_tcdm_to_reg[i].mem_cut_req.strb;
    assign cut_write[i] = dut.gen_tcdm_to_reg[i].mem_cut_req.we;
  end
  clocking cb @(posedge clk_i);
    default input #1step;
    input rst_ni, req, rsp, reg_req, reg_rsp, busy, reg_id;
    input cut_valid, cut_ready, cut_addr, cut_strb, cut_write;
    input arb_v = dut.i_axi_to_detailed_mem.arb_valid;
    input arb_r = dut.i_axi_to_detailed_mem.arb_ready;
    input meta = dut.i_axi_to_detailed_mem.meta;
    input meta_v = dut.i_axi_to_detailed_mem.meta_valid;
    input meta_r = dut.i_axi_to_detailed_mem.meta_ready;
    input meta_buf = dut.i_axi_to_detailed_mem.meta_buf;
    input meta_buf_v = dut.i_axi_to_detailed_mem.meta_buf_valid;
    input meta_buf_r = dut.i_axi_to_detailed_mem.meta_buf_ready;
    input mem_v = dut.i_axi_to_detailed_mem.m2s_req_valid;
    input mem_r = dut.i_axi_to_detailed_mem.m2s_req_ready;
    input mem_req = dut.i_axi_to_detailed_mem.m2s_req;
    input mem_pv = dut.i_axi_to_detailed_mem.m2s_resp_valid;
    input mem_pr = dut.i_axi_to_detailed_mem.m2s_resp_ready;
    input bank_v = dut.mem_qvalid;
    input bank_r = dut.mem_qready;
    input bank_addr = dut.mem_addr;
    input bank_strb = dut.mem_strb;
    input bank_write = dut.mem_we;
    input bank_id = dut.mem_id;
    input bank_pv = dut.mem_pvalid;
    input bank_err = dut.mem_err;
    input bank_rd = dut.mem_rdata;
    input active_req = dut.valid_req;
    input zero_req = dut.zero_w_req;
    input r_left = dut.i_axi_to_detailed_mem.r_cnt_q;
    input w_left = dut.i_axi_to_detailed_mem.w_cnt_q;
    input model_reads, model_writes;
    input response_banks = dut.i_axi_to_detailed_mem.meta_buf_size_enable;
  endclocking

  task automatic check(input logic condition, input string code);
    checks++;
    if (condition !== 1'b1) begin
      $display("MMIO_FAIL code=%s case=%s cycle=%0d ar=%0d r=%0d aw=%0d b=%0d reg=%0d",
               code, case_name, cycles, ar_count, r_count, aw_count, b_count, reg_count);
      $fflush(fd);
      $fatal(1, "MMIO contract failed");
    end
  endtask
  task automatic verify(input logic condition, input string code);
    checks++;
    if (condition !== 1'b1) begin
      failures++; case_failures++;
      $display("MMIO_MISMATCH code=%s case=%s cycle=%0d r=%0d b=%0d reg=%0d",
               code, case_name, cycles-1, r_count, b_count, reg_count);
    end
  endtask
  function automatic data_t byte_mask(input strb_t lanes);
    data_t result = '0;
    for (int i = 0; i < 8; i++) if (lanes[i]) result[i*8+:8] = 8'hff;
    return result;
  endfunction

  // Byte interval [first address, end of its size-aligned transfer). Later INCR
  // beats start at size-aligned addresses. Do not reuse axi_pkg/DUT mask helpers.
  task automatic accept_read(input axi_ar_chan_t ar);
    addr_t address, upper, beat_base;
    beat_t item;
    expected_t bank;
    int bytes_per_beat;
    check(ar.size <= 3 && ar.burst == axi_pkg::BURST_INCR, "read_shape");
    bytes_per_beat = 1 << ar.size;
    if (ar.len != 0) burst_requests++;
    if ((ar.addr % bytes_per_beat) != 0) unaligned_requests++;
    for (int n = 0; n <= int'(ar.len); n++) begin
      check(read_beats < Limit, "read_scoreboard_bound");
      address = n == 0 ? ar.addr : (ar.addr / bytes_per_beat + addr_t'(n)) * bytes_per_beat;
      upper = (address / bytes_per_beat + 1) * bytes_per_beat;
      beat_base = (address / 8) * 8;
      item = '0;
      item.address = address; item.id = ar.id; item.last = (n == int'(ar.len));
      for (int lane = 0; lane < 8; lane++)
        item.lanes[lane] = (beat_base + addr_t'(lane) >= address && beat_base + addr_t'(lane) < upper);
      for (int b = 0; b < 2; b++) begin
        bank = '0;
        bank.address = beat_base + addr_t'(4*b);
        bank.be = item.lanes[b*4+:4]; bank.beat = read_beats;
        if (bank.be != 0) begin
          item.banks[b] = 1;
          if (!mapped(bank.address)) item.response = axi_pkg::RESP_SLVERR;
          expected[0][b].push_back(bank);
          expected_regs++;
        end
      end
      reads[read_beats] = item;
      $display("MMIO_EXPECT_R beat=%0d id=%h addr=%h lanes=%h banks=%h last=%b resp=%b",
               read_beats, item.id, item.address, item.lanes, item.banks, item.last, item.response);
      read_beats++;
    end
  endtask
  task automatic pair_write;
    axi_aw_chan_t aw;
    axi_w_chan_t w;
    beat_t item;
    expected_t bank;
    while (aw_queue.size() != 0 && w_queue.size() != 0) begin
      aw = aw_queue.pop_front(); w = w_queue.pop_front();
      check(aw.len == 0 && w.last && aw.size <= 3, "write_shape");
      check(write_beats < Limit, "write_scoreboard_bound");
      item = '0;
      item.address = aw.addr; item.id = aw.id; item.lanes = w.strb;
      for (int b = 0; b < 2; b++) begin
        bank = '0;
        bank.address = (aw.addr / 8) * 8 + addr_t'(4*b);
        bank.be = w.strb[b*4+:4]; bank.data = w.data[b*32+:32]; bank.beat = write_beats;
        if (bank.be != 0) begin
          item.banks[b] = 1;
          if (!mapped(bank.address)) item.response = axi_pkg::RESP_SLVERR;
          expected[1][b].push_back(bank);
          expected_regs++;
        end
      end
      writes[write_beats] = item;
      $display("MMIO_EXPECT_B beat=%0d id=%h addr=%h strb=%h banks=%h resp=%b",
               write_beats, item.id, item.address, item.lanes, item.banks, item.response);
      write_beats++;
    end
  endtask
  task automatic reconcile;
    expected_t e;
    actual_t a;
    word_t value;
    int index;
    // A fork can accept a memory leg before its AXI handshake. Buffer actual
    // reg events until the external request is accepted; never infer ownership
    // from reg_id_o (which forwards bank0's cut ID even when bank1 wins).
    for (int w = 0; w < 2; w++) begin
      for (int b = 0; b < 2; b++) begin
        while (expected[w][b].size() != 0 && actual[w][b].size() != 0) begin
          a = actual[w][b].pop_front();
          e = expected[w][b][0];
          if (a.request.addr !== e.address) begin
            $display("MMIO_EXTRA cycle=%0d write=%0d bank=%0d addr=%h expected_addr=%h",
                     a.cycle, w, b, a.request.addr, e.address);
            verify(0, "extra_register_address");
            continue;
          end
          e = expected[w][b].pop_front();
          $display("MMIO_MATCH cycle=%0d write=%0d bank=%0d beat=%0d expected_addr=%h actual_addr=%h expected_be=%h actual_be=%h",
                   a.cycle, w, b, e.beat, e.address, a.request.addr, e.be, a.request.wstrb);
          verify(a.request.wstrb === e.be, "reg_byte_mask");
          check(a.response.error === !mapped(e.address), "reg_error_model");
          value = 32'hbadcab1e;
          if (mapped(e.address)) begin
            index = int'((e.address-Base)/4);
            value = shadow[index] ^ (word_t'(shadow_effects[index]) * 32'h01010101);
            if (w == 0) shadow_effects[index]++;
            else for (int lane = 0; lane < 4; lane++)
              if (e.be[lane]) shadow[index][lane*8+:8] = e.data[lane*8+:8];
          end
          if (w == 0) begin
            verify(a.response.rdata === value, "reg_read_side_effect");
            reads[e.beat].data[b*32+:32] = value;
            reads[e.beat].seen[b] = 1;
          end else begin
            for (int lane = 0; lane < 4; lane++)
              if (e.be[lane]) verify(a.request.wdata[lane*8+:8] === e.data[lane*8+:8], "reg_write_data");
            writes[e.beat].seen[b] = 1;
          end
        end
      end
    end
  endtask

  always @(negedge clk_i) begin
    req.r_ready = rst_ni && (cycles % 13 >= 8);
    req.b_ready = rst_ni && (cycles % 11 >= 7);
    reg_ready = rst_ni && (cycles % 5 >= 2);
  end
  always @(cb) begin : observe
    actual_t event_item;
    if (fd != 0) begin
      $fwrite(fd, {"cycle=%0d rst=%b case=%s awv=%b awr=%b awaddr=%h awid=%h awsize=%h awlen=%h",
        " wv=%b wr=%b wd=%h ws=%h wl=%b bv=%b br=%b bid=%h bresp=%b",
        " arv=%b arr=%b araddr=%h arid=%h arsize=%h arlen=%h rv=%b rr=%b rid=%h rresp=%b rd=%h rl=%b",
        " arbv=%b arbr=%b meta_addr=%h meta_size=%h meta_strb=%h meta_write=%b meta_id=%h meta_last=%b metav=%b metar=%b",
        " bufv=%b bufr=%b buf_addr=%h buf_size=%h buf_strb=%h buf_write=%b buf_id=%h buf_last=%b",
        " memv=%b memr=%b mem_addr=%h mem_strb=%h mem_write=%b mem_id=%h mempv=%b mempr=%b",
        " bankv=%b bankr=%b bank_addr=%h bank_strb=%h bank_write=%b bank_id=%h bankpv=%b bankerr=%b bankrd=%h",
        " cutv=%b cutr=%b cut_addr=%h cut_strb=%h cut_write=%b active0=%b active1=%b zero0=%b zero1=%b",
        " regv=%b regr=%b regaddr=%h regw=%b regbe=%h regwd=%h regerr=%b regrd=%h regid=%h",
        " rleft=%h wleft=%h busy=%b model_reads=%0d model_writes=%0d response_banks=%b error_profile=%0d\n"},
        cycles, cb.rst_ni, case_name, cb.req.aw_valid, cb.rsp.aw_ready, cb.req.aw.addr,
        cb.req.aw.id, cb.req.aw.size, cb.req.aw.len, cb.req.w_valid, cb.rsp.w_ready,
        cb.req.w.data, cb.req.w.strb, cb.req.w.last, cb.rsp.b_valid, cb.req.b_ready, cb.rsp.b.id, cb.rsp.b.resp,
        cb.req.ar_valid, cb.rsp.ar_ready, cb.req.ar.addr, cb.req.ar.id, cb.req.ar.size, cb.req.ar.len,
        cb.rsp.r_valid, cb.req.r_ready, cb.rsp.r.id, cb.rsp.r.resp, cb.rsp.r.data, cb.rsp.r.last,
        cb.arb_v, cb.arb_r, cb.meta.addr, cb.meta.size, cb.meta.strb, cb.meta.write, cb.meta.id, cb.meta.last, cb.meta_v, cb.meta_r,
        cb.meta_buf_v, cb.meta_buf_r, cb.meta_buf.addr, cb.meta_buf.size, cb.meta_buf.strb,
        cb.meta_buf.write, cb.meta_buf.id, cb.meta_buf.last, cb.mem_v, cb.mem_r,
        cb.mem_req.addr, cb.mem_req.strb, cb.mem_req.we, cb.mem_req.id, cb.mem_pv, cb.mem_pr,
        cb.bank_v, cb.bank_r, cb.bank_addr, cb.bank_strb, cb.bank_write, cb.bank_id,
        cb.bank_pv, cb.bank_err, cb.bank_rd, cb.cut_valid, cb.cut_ready, cb.cut_addr,
        cb.cut_strb, cb.cut_write, cb.active_req[0].valid, cb.active_req[1].valid,
        cb.zero_req[0].valid, cb.zero_req[1].valid, cb.reg_req.valid, cb.reg_rsp.ready,
        cb.reg_req.addr, cb.reg_req.write, cb.reg_req.wstrb, cb.reg_req.wdata, cb.reg_rsp.error,
        cb.reg_rsp.rdata, cb.reg_id, cb.r_left, cb.w_left, cb.busy, cb.model_reads, cb.model_writes,
        cb.response_banks, error_profile);
      cycles++;
      if (cycles % 32 == 0) $fflush(fd);
    end
    if (cb.rst_ni) begin
      check(!$isunknown({cb.rsp.aw_ready, cb.rsp.w_ready, cb.rsp.ar_ready,
                         cb.rsp.b_valid, cb.rsp.r_valid, cb.reg_req.valid, cb.reg_rsp.ready}), "unknown_control");
      if (cb.req.ar_valid && cb.rsp.ar_ready) begin
        $display("MMIO_AR seq=%0d cycle=%0d case=%s addr=%h id=%h size=%0d len=%0d",
                 ar_count, cycles-1, case_name, cb.req.ar.addr, cb.req.ar.id, cb.req.ar.size, cb.req.ar.len);
        ar_count++; accept_read(cb.req.ar);
      end
      if (cb.req.aw_valid && cb.rsp.aw_ready) begin
        $display("MMIO_AW seq=%0d cycle=%0d case=%s addr=%h id=%h size=%0d",
                 aw_count, cycles-1, case_name, cb.req.aw.addr, cb.req.aw.id, cb.req.aw.size);
        aw_count++; aw_queue.push_back(cb.req.aw);
      end
      if (cb.req.w_valid && cb.rsp.w_ready) begin
        w_count++;
        $display("MMIO_W seq=%0d cycle=%0d data=%h strb=%h", w_count-1, cycles-1, cb.req.w.data, cb.req.w.strb);
        w_queue.push_back(cb.req.w);
      end
      pair_write();
      if (cb.reg_req.valid && cb.reg_rsp.ready) begin
        check(!$isunknown({cb.reg_req.addr, cb.reg_req.write, cb.reg_req.wstrb,
                           cb.reg_rsp.error}), "unknown_register_control");
        event_item = '{request: cb.reg_req, response: cb.reg_rsp, cycle: cycles-1};
        actual[cb.reg_req.write][cb.reg_req.addr[2]].push_back(event_item);
        reg_count++;
      end
      reconcile();
      if (r_held) check(cb.rsp.r_valid && cb.rsp.r === last_r, "r_unstable");
      if (b_held) check(cb.rsp.b_valid && cb.rsp.b === last_b, "b_unstable");
      r_held = cb.rsp.r_valid && !cb.req.r_ready; last_r = cb.rsp.r;
      b_held = cb.rsp.b_valid && !cb.req.b_ready; last_b = cb.rsp.b;
      r_stalls += r_held; b_stalls += b_held;
      reg_stalls += cb.reg_req.valid && !cb.reg_rsp.ready;
      queued_ar += cb.req.ar_valid && !cb.rsp.ar_ready && r_held;
      held_w_reads += cb.req.w_valid && !cb.rsp.w_ready && cb.req.ar_valid && cb.rsp.ar_ready;
      if (cb.rsp.r_valid && cb.req.r_ready) begin
        check(r_count < read_beats, "unexpected_r");
        check(!$isunknown({cb.rsp.r.id, cb.rsp.r.last, cb.rsp.r.resp}), "unknown_r_control");
        verify(reads[r_count].seen === reads[r_count].banks, "r_missing_registers");
        check(cb.rsp.r.id === reads[r_count].id && cb.rsp.r.last === reads[r_count].last, "r_id_last");
        verify(cb.rsp.r.resp === reads[r_count].response, "r_response");
        if (reads[r_count].response == axi_pkg::RESP_OKAY) begin
          check(!$isunknown(cb.rsp.r.data & byte_mask(reads[r_count].lanes)), "unknown_r_data");
          verify((cb.rsp.r.data & byte_mask(reads[r_count].lanes)) ===
                (reads[r_count].data & byte_mask(reads[r_count].lanes)), "r_valid_bytes");
        end
        $display("MMIO_R beat=%0d cycle=%0d id=%h last=%b resp=%b data=%h",
                 r_count, cycles-1, cb.rsp.r.id, cb.rsp.r.last, cb.rsp.r.resp, cb.rsp.r.data);
        r_count++;
      end
      if (cb.rsp.b_valid && cb.req.b_ready) begin
        check(b_count < write_beats, "unexpected_b");
        check(!$isunknown({cb.rsp.b.id, cb.rsp.b.resp}), "unknown_b_control");
        verify(writes[b_count].seen === writes[b_count].banks, "b_missing_registers");
        check(cb.rsp.b.id === writes[b_count].id, "b_id");
        verify(cb.rsp.b.resp === writes[b_count].response, "b_response");
        $display("MMIO_B beat=%0d cycle=%0d id=%h resp=%b", b_count, cycles-1, cb.rsp.b.id, cb.rsp.b.resp);
        b_count++;
      end
    end
    if (cycles >= MaxCycles) check(0, "cycle_timeout");
  end

  task automatic send_ar(input addr_t address, input int size, input int length, input id_t id);
    bit accepted = 0;
    @(negedge clk_i);
    req.ar = '{addr: address, size: 3'(size), len: 8'(length), id: id,
               burst: axi_pkg::BURST_INCR, default: '0};
    req.ar_valid = 1;
    repeat (256) begin
      @(cb);
      if (cb.req.ar_valid && cb.rsp.ar_ready) begin accepted = 1; break; end
    end
    @(negedge clk_i); req.ar_valid = 0;
    check(accepted, "ar_timeout");
  endtask
  task automatic send_aw(input addr_t address, input int size, input id_t id, input int delay_cycles);
    bit accepted = 0;
    repeat (delay_cycles) @(negedge clk_i);
    @(negedge clk_i);
    req.aw = '{addr: address, size: 3'(size), id: id, burst: axi_pkg::BURST_INCR, default: '0};
    req.aw_valid = 1;
    repeat (256) begin
      @(cb);
      if (cb.req.aw_valid && cb.rsp.aw_ready) begin accepted = 1; break; end
    end
    @(negedge clk_i); req.aw_valid = 0;
    check(accepted, "aw_timeout");
  endtask
  task automatic send_w(input data_t data, input strb_t strobes, input int delay_cycles);
    bit accepted = 0;
    repeat (delay_cycles) @(negedge clk_i);
    @(negedge clk_i);
    req.w = '{data: data, strb: strobes, last: 1'b1, default: '0};
    req.w_valid = 1;
    repeat (256) begin
      @(cb);
      if (cb.req.w_valid && cb.rsp.w_ready) begin accepted = 1; break; end
    end
    @(negedge clk_i); req.w_valid = 0;
    check(accepted, "w_timeout");
  endtask
  task automatic drain;
    bit done = 0;
    repeat (256) begin
      @(negedge clk_i);
      if (r_count == read_beats && b_count == write_beats && !busy) begin done = 1; break; end
    end
    check(done && aw_queue.size() == 0 && w_queue.size() == 0, "drain_timeout");
    repeat (8) @(negedge clk_i);
    verify(reg_count-epoch_regs == expected_regs-epoch_expected, "extra_or_missing_register_access");
    for (int w = 0; w < 2; w++)
      for (int b = 0; b < 2; b++) begin
        verify(expected[w][b].size() == 0 && actual[w][b].size() == 0, "unmatched_register_access");
        expected[w][b].delete(); actual[w][b].delete();
      end
    for (int i = 0; i < 128; i++)
      verify(storage[i] === shadow[i] && read_effects[i] == shadow_effects[i], "side_effect_state");
  endtask
  task automatic finish_case;
    drain(); cases_done++;
    $display("MMIO_CASE name=%s status=%s failures=%0d ar=%0d r=%0d aw=%0d b=%0d regs=%0d",
             case_name, case_failures == 0 ? "PASS" : "FAIL", case_failures,
             ar_count, r_count, aw_count, b_count, reg_count);
    case_failures = 0;
    epoch_regs = reg_count; epoch_expected = expected_regs;
    // Keep aggregate transport counts, reset only the independent peripheral
    // and its oracle. A baseline failure must not hide a later mask/error bug.
    $display("MMIO_RESET case=%s cycle=%0d", case_name, cycles);
    rst_ni = 0;
    repeat (5) @(negedge clk_i);
    for (int i = 0; i < 128; i++) begin shadow[i] = initial_word(i); shadow_effects[i] = 0; end
    rst_ni = 1;
    repeat (3) @(negedge clk_i);
  endtask
  final begin
    if (fd != 0) begin
      $fwrite(fd, "# END rows=%0d completed=%b ar=%0d r=%0d aw=%0d w=%0d b=%0d regs=%0d checks=%0d\n",
              cycles, completed, ar_count, r_count, aw_count, w_count, b_count, reg_count, checks);
      $fclose(fd);
    end
  end

  initial begin
    fd = $fopen("mmio_signals.log", "w");
    if (!fd) $fatal(1, "MMIO probe open failed");
    $fwrite(fd, "# MMIO_PROBE schema=1 sample=pre_edge max_cycles=%0d\n", MaxCycles);
    $display("MMIO_CONFIG axi_data=64 axi_addr=48 axi_id=4 axi_user=2 reg_data=32 cut=1");
    for (int i = 0; i < 128; i++) begin shadow[i] = initial_word(i); shadow_effects[i] = 0; end
    repeat (5) @(negedge clk_i);
    rst_ni = 1;
    repeat (3) @(negedge clk_i);

    case_name = "size_lanes";
    for (int s = 0; s <= 3; s++) begin
      for (int lane = 0; lane < 8; lane++) begin
        send_ar(Base + addr_t'(lane), s, 0, id_t'(lane+s)); drain();
      end
    end
    finish_case();

    case_name = "queued_reads";
    for (int k = 0; k < 8; k++)
      send_ar(Base + 48'h80 + addr_t'(8*k + (k%2)*4), k%3, 0, id_t'(k+3));
    finish_case();

    case_name = "mixed_channels";
    fork
      send_aw(Base+48'h180, 2, 12, 18);
      send_w(64'h5566778811223344, 8'h0f, 0);
      begin send_ar(Base+48'h94, 2, 0, 4); send_ar(Base+48'h99, 0, 0, 5); end
    join
    drain();
    fork
      send_aw(Base+48'h184, 2, 13, 0);
      send_w(64'ha1b2c3d4ffeeddcc, 8'hf0, 10);
      begin send_ar(Base+48'ha0, 2, 0, 6); send_ar(Base+48'ha6, 1, 0, 7); end
    join
    drain();
    fork
      send_aw(Base+48'h188, 3, 14, 0);
      send_w(64'hfedcba9876543210, 8'h81, 3);
      send_ar(Base+48'ha8, 3, 0, 8);
    join
    drain();
    fork
      send_aw(Base+48'h18c, 2, 15, 3);
      send_w('1, 0, 0);
      send_ar(Base+48'hb4, 2, 0, 9);
    join
    drain();
    send_ar(Base+48'h180, 3, 0, 10); send_ar(Base+48'h188, 3, 0, 11);
    finish_case();

    case_name = "incr_bursts";
    send_ar(Base+48'h100, 2, 3, 1);
    send_ar(Base+48'h124, 1, 3, 2);
    send_ar(Base+48'h140, 3, 1, 3);
    send_ar(Base+48'h163, 2, 2, 4);
    finish_case();

    case_name = "error_mapping";
    error_profile = 1;
    send_ar(Base, 2, 0, 1); send_ar(Base+4, 2, 0, 2);
    send_ar(Base+8, 2, 0, 3); send_ar(Base+12, 2, 0, 4);
    send_ar(Base+48'h30, 2, 0, 5); send_ar(Base+48'h34, 2, 0, 6);
    send_ar(Base+48'h38, 2, 0, 7); send_ar(Base+48'h3c, 2, 0, 8);
    send_ar(Base+48'h30, 3, 0, 9); send_ar(Base+48'h38, 3, 0, 10);
    send_ar(Base+48'h200, 2, 0, 11); drain();
    error_profile = 2;
    send_ar(Base+8, 2, 0, 14); send_ar(Base+12, 2, 0, 15); drain();
    fork send_aw(Base+48'h34, 2, 12, 0); send_w('1, 8'hf0, 2); join
    drain();
    fork send_aw(Base+48'h38, 2, 13, 2); send_w('1, 8'h0f, 0); join
    finish_case();
    check(r_stalls > 0 && b_stalls > 0 && reg_stalls > 0 && queued_ar > 0 && held_w_reads > 0,
          "traffic_coverage");
    check(burst_requests == 4 && unaligned_requests == 18, "shape_coverage");
    completed = 1;
    $display({"MMIO_RESULT status=%s failures=%0d cases=%0d ar=%0d r=%0d aw=%0d w=%0d b=%0d regs=%0d",
              " checks=%0d cycles=%0d r_stalls=%0d b_stalls=%0d reg_stalls=%0d queued_ar=%0d held_w_reads=%0d bursts=%0d unaligned=%0d"},
             failures == 0 ? "PASS" : "FAIL", failures, cases_done, ar_count, r_count, aw_count, w_count, b_count, reg_count, checks, cycles,
             r_stalls, b_stalls, reg_stalls, queued_ar, held_w_reads, burst_requests, unaligned_requests);
    if (failures != 0) $fatal(1, "MMIO contract functional failures=%0d", failures);
    $finish;
  end
endmodule
