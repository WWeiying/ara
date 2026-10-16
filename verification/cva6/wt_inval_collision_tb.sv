`timescale 1ns/1ps
`include "axi/typedef.svh"

// Derived from linux/diagnostics/inval_read_collision_tb.sv. Direct external
// invalidation only; collision_types.svh is extracted from the compiled core.
module wt_inval_collision_tb;
  import ariane_pkg::*;
  import wt_cache_pkg::*;

  function automatic config_pkg::cva6_cfg_t config_value();
    config_pkg::cva6_user_cfg_t c = cva6_config_pkg::cva6_cfg;
    c.AxiAddrWidth = 48;
    c.AxiDataWidth = 64;
    c.AxiIdWidth = 4;
    c.AxiUserWidth = 2;
    return build_config_pkg::build_config(c);
  endfunction

  localparam config_pkg::cva6_cfg_t CVA6Cfg = config_value();
  typedef logic [47:0] addr_t;
  typedef logic [3:0] id_t;
  typedef logic [63:0] data_t;
  typedef logic [7:0] strb_t;
  typedef logic [1:0] user_t;
  `AXI_TYPEDEF_ALL(axi, addr_t, id_t, data_t, strb_t, user_t)
  `include "collision_types.svh"

  localparam addr_t READ_ADDR = 48'h828597e0;
  localparam addr_t STORE_ADDR = 48'h83299000;
  localparam logic [63:0] INVAL_ADDR = 64'h83299f80;
  localparam data_t STORE_DATA = 64'hb97a1357e02468cf;
  localparam logic [255:0] EXPECTED = {
    64'h4444444444444444, 64'h0000000020b94801,
    64'h2222222222222222, 64'h1111111111111111
  };
  localparam logic [CVA6Cfg.MEM_TID_WIDTH-1:0] READ_TID = 1;
  localparam logic [CVA6Cfg.MEM_TID_WIDTH-1:0] STORE_TID = 2;

  logic clk = 0;
  logic rst = 0;
  logic dc_req = 0;
  logic ic_req = 0;
  logic inv = 0;
  wire dc_ack, ic_ack, inv_ready, ret_valid, ic_valid;
  dcache_req_t dc;
  dcache_rtrn_t ret;
  icache_req_t ic;
  icache_rtrn_t ic_ret;
  axi_req_t req;
  axi_resp_t rsp;

  int mode = 0;
  int collide = -1;
  int hold_cycles = 1;
  int b_concurrent = 0;
  int filter_mode = 0;
  int beats = 4;
  int cycles = 0;
  int errors = 0;
  int ar_count = 0, aw_count = 0, w_count = 0;
  int reads = 0, read_last = 0, returns = 0;
  int captures_d = 0, captures_i = 0, pops_d = 0, pops_i = 0;
  int b_count = 0, b_pops = 0, write_pops = 0, store_acks = 0;
  int external_invals = 0, internal_invals = 0, inv_returns = 0;
  int collision_stalls = 0, b_collision = 0;
  int dc_accepts = 0, ic_accepts = 0;
  int inv_events = 0;
  logic [CVA6Cfg.DCACHE_INDEX_WIDTH-1:0] inv_indices [0:7];
  id_t read_id = '0, write_id = '0;
  bit r_stalled = 0, b_stalled = 0, result_printed = 0;
  axi_r_chan_t held_r;
  axi_b_chan_t held_b;
  string first_error = "";

  wt_axi_adapter #(
    .CVA6Cfg(CVA6Cfg), .axi_req_t(axi_req_t), .axi_rsp_t(axi_resp_t),
    .dcache_req_t(dcache_req_t), .dcache_rtrn_t(dcache_rtrn_t),
    .dcache_inval_t(dcache_inval_t), .icache_req_t(icache_req_t),
    .icache_rtrn_t(icache_rtrn_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst),
    .icache_data_req_i(ic_req), .icache_data_i(ic),
    .icache_data_ack_o(ic_ack), .icache_rtrn_vld_o(ic_valid), .icache_rtrn_o(ic_ret),
    .dcache_data_req_i(dc_req), .dcache_data_i(dc),
    .dcache_data_ack_o(dc_ack), .dcache_rtrn_vld_o(ret_valid), .dcache_rtrn_o(ret),
    .axi_req_o(req), .axi_resp_i(rsp), .inval_addr_i(INVAL_ADDR),
    .inval_valid_i(inv), .inval_ready_o(inv_ready)
  );

  // Observation only: no force, internal injection or AXI ID remapping.
  wire capture_d = dut.dcache_rtrn_rd_en;
  wire capture_i = dut.icache_rtrn_rd_en;
  wire pop_d = dut.dcache_rd_pop;
  wire pop_i = dut.icache_rtrn_vld_d;
  wire pop_w = dut.dcache_wr_pop;
  wire b_push = dut.b_push;
  wire b_pop = dut.b_pop;
  wire internal_inv = dut.invalidate;
  wire rd_empty_d = dut.dcache_rd_empty;
  wire rd_empty_i = dut.icache_rd_empty;
  wire wr_empty = dut.dcache_wr_empty;
  wire b_empty = dut.b_empty;
  wire request_empty_d = dut.dcache_data_empty;
  wire request_empty_i = dut.icache_data_empty;

  always #5 clk = ~clk;
  clocking cb @(posedge clk);
    default input #1step;
    input rst, dc_ack, ic_ack, dc_req, ic_req;
    input req, rsp, inv, inv_ready, ret_valid, ret, ic_valid, ic_ret;
    input capture_d, capture_i, pop_d, pop_i, pop_w, b_push, b_pop;
    input internal_inv, rd_empty_d, rd_empty_i, wr_empty, b_empty;
    input request_empty_d, request_empty_i;
  endclocking

  task automatic bad(input string reason);
    if (errors == 0) first_error = reason;
    errors++;
    $display("INVAL_READ_BAD cycles=%0d reason=%s", cycles, reason);
  endtask

  task automatic result(input bit pass);
    if (!result_printed) begin
      result_printed = 1;
      $display("COLLISION_RESULT pass=%0d errors=%0d mode=%0d collide=%0d hold=%0d b_concurrent=%0d cycles=%0d axi_beats=%0d captures=%0d read_returns=%0d read_last=%0d read_outstanding=%0d read_pops=%0d external_invals=%0d internal_invals=%0d invalidations=%0d collision_stalls=%0d aw=%0d w=%0d b=%0d b_pop=%0d storeacks=%0d write_outstanding=%0d b_collision=%0d pending_d=%b pending_i=%b pending_w=%b pending_b=%b",
        pass, errors, mode, collide, hold_cycles, b_concurrent, cycles,
        reads, captures_d + captures_i, returns, read_last, ar_count - read_last,
        pops_d + pops_i, external_invals, internal_invals, inv_returns,
        collision_stalls, aw_count, w_count, b_count, b_pops, store_acks,
        aw_count - b_count, b_collision, !rd_empty_d, !rd_empty_i, !wr_empty, !b_empty);
    end
  endtask

  always @(cb) begin : monitor
    if (cb.rst) begin
      cycles++;
      if (cycles >= 3000) begin
        bad("READ_COMPLETION_LOST");
        result(0);
        $fatal(1, "READ_COMPLETION_LOST cycle_limit=3000");
      end

      if (cb.rsp.r_valid || cb.rsp.b_valid || cb.inv || cb.internal_inv ||
          cb.ret_valid || cb.ic_valid || cb.b_pop) begin
        $display("READ_CYCLE cycles=%0d rvalid=%b rready=%b rid=%h rdata=%h rlast=%b inval=%b inval_ready=%b internal_inv=%b capture_d=%b capture_i=%b pop_d=%b pop_i=%b bvalid=%b bready=%b bid=%h bpush=%b bpop=%b wpop=%b dvalid=%b dtype=%0d dtid=%h ddata=%h ivalid=%b itid=%h idata=%h pending_d=%b pending_i=%b pending_w=%b",
          cycles, cb.rsp.r_valid, cb.req.r_ready, cb.rsp.r.id, cb.rsp.r.data,
          cb.rsp.r.last, cb.inv, cb.inv_ready, cb.internal_inv,
          cb.capture_d, cb.capture_i, cb.pop_d, cb.pop_i,
          cb.rsp.b_valid, cb.req.b_ready, cb.rsp.b.id, cb.b_push, cb.b_pop, cb.pop_w,
          cb.ret_valid, cb.ret.rtype, cb.ret.tid, cb.ret.data,
          cb.ic_valid, cb.ic_ret.tid, cb.ic_ret.data,
          !cb.rd_empty_d, !cb.rd_empty_i, !cb.wr_empty);
      end
      if ((cb.req.ar_valid && cb.rsp.ar_ready) ||
          (cb.req.aw_valid && cb.rsp.aw_ready) || (cb.req.w_valid && cb.rsp.w_ready))
        $display("REQUEST_CYCLE cycles=%0d arvalid=%b arready=%b arid=%h araddr=%h arlen=%0d awvalid=%b awready=%b awid=%h awaddr=%h wvalid=%b wready=%b wdata=%h wstrb=%h wlast=%b",
          cycles, cb.req.ar_valid, cb.rsp.ar_ready, cb.req.ar.id, cb.req.ar.addr,
          cb.req.ar.len, cb.req.aw_valid, cb.rsp.aw_ready, cb.req.aw.id, cb.req.aw.addr,
          cb.req.w_valid, cb.rsp.w_ready, cb.req.w.data, cb.req.w.strb, cb.req.w.last);

      if ($isunknown({cb.req.r_ready, cb.req.b_ready, cb.inv_ready,
                      cb.ret_valid, cb.ic_valid})) bad("UNKNOWN_CONTROL");
      if (r_stalled && (!cb.rsp.r_valid || cb.rsp.r !== held_r))
        bad("TB_R_CHANGED_BEFORE_HANDSHAKE");
      if (b_stalled && (!cb.rsp.b_valid || cb.rsp.b !== held_b))
        bad("TB_B_CHANGED_BEFORE_HANDSHAKE");
      r_stalled = cb.rsp.r_valid && !cb.req.r_ready;
      b_stalled = cb.rsp.b_valid && !cb.req.b_ready;
      held_r = cb.rsp.r;
      held_b = cb.rsp.b;

      if (cb.dc_req && cb.dc_ack) dc_accepts++;
      if (cb.ic_req && cb.ic_ack) ic_accepts++;
      if (cb.req.ar_valid && cb.rsp.ar_ready) begin
        ar_count++;
        read_id = cb.req.ar.id;
        if (ar_count != 1 || cb.req.ar.addr !== READ_ADDR ||
            cb.req.ar.len !== 8'(beats-1) || cb.req.ar.size !== 3'd3 ||
            cb.req.ar.lock !== (mode == 2) || cb.req.ar.burst !== axi_pkg::BURST_INCR ||
            cb.req.ar.id !== id_t'(mode == 1 ? 0 : mode == 2 ? 3 : 1))
          bad("WRONG_AXI_READ_REQUEST");
      end
      if (cb.req.aw_valid && cb.rsp.aw_ready) begin
        aw_count++;
        write_id = cb.req.aw.id;
        if (!b_concurrent || aw_count != 1 || cb.req.aw.addr !== STORE_ADDR ||
            cb.req.aw.id !== id_t'(1) || cb.req.aw.len !== 8'd0 ||
            cb.req.aw.size !== 3'd3 || cb.req.aw.lock !== 1'b0 || cb.req.aw.atop !== '0)
          bad("WRONG_AXI_STORE_REQUEST");
      end
      if (cb.req.w_valid && cb.rsp.w_ready) begin
        w_count++;
        if (!b_concurrent || w_count != 1 || cb.req.w.data !== STORE_DATA ||
            cb.req.w.strb !== 8'hff || cb.req.w.last !== 1'b1)
          bad("WRONG_AXI_STORE_DATA");
      end

      // Each ready/valid cycle is one accepted external invalidation. Holding
      // valid for four ready cycles deliberately exercises four return slots.
      if (cb.inv && cb.inv_ready) begin
        external_invals++;
        if (inv_events >= 8) bad("TOO_MANY_INVALIDATIONS");
        else inv_indices[inv_events++] = INVAL_ADDR[CVA6Cfg.DCACHE_INDEX_WIDTH-1:0];
      end
      if (cb.internal_inv) begin
        internal_invals++;
        if (mode != 2 || cb.inv || inv_events >= 8) bad("WRONG_INTERNAL_INVALIDATION");
        else inv_indices[inv_events++] = READ_ADDR[CVA6Cfg.DCACHE_INDEX_WIDTH-1:0];
      end
      if (cb.inv && cb.rsp.r_valid) begin
        if (cb.req.r_ready) bad("READ_ACCEPTED_DURING_INVALIDATION");
        else collision_stalls++;
      end

      if (cb.rsp.r_valid && cb.req.r_ready) begin
        if (ar_count != 1 || reads >= beats) bad("EXTRA_AXI_READ_BEAT");
        else if (cb.rsp.r.data !== EXPECTED[64*reads+:64] || cb.rsp.r.id !== read_id ||
                 cb.rsp.r.last !== (reads == beats-1)) bad("WRONG_ACCEPTED_AXI_BEAT");
        if ((mode == 1 && !cb.capture_i) || (mode != 1 && !cb.capture_d))
          bad("READ_COMPLETION_LOST");
        reads++;
        if (cb.rsp.r.last) read_last++;
      end
      if (cb.capture_d) begin
        captures_d++;
        if (mode == 1 || !cb.rsp.r_valid || !cb.req.r_ready) bad("UNOWNED_D_CAPTURE");
      end
      if (cb.capture_i) begin
        captures_i++;
        if (mode != 1 || !cb.rsp.r_valid || !cb.req.r_ready) bad("UNOWNED_I_CAPTURE");
      end
      if (cb.pop_d) begin
        pops_d++;
        if (mode == 1 || !cb.capture_d || !cb.rsp.r.last) bad("WRONG_D_READ_POP");
      end
      if (cb.pop_i) begin
        pops_i++;
        if (mode != 1 || !cb.capture_i || !cb.rsp.r.last) bad("WRONG_I_READ_POP");
      end
      if (cb.rsp.b_valid && cb.req.b_ready) begin
        b_count++;
        if (cb.inv) b_collision++;
        if (!b_concurrent || !cb.rsp.r_valid || aw_count != 1 || w_count != 1 || b_count != 1 ||
            cb.rsp.b.id !== write_id || cb.rsp.b.resp !== axi_pkg::RESP_OKAY || !cb.b_push)
          bad("WRONG_ACCEPTED_B");
      end
      if (cb.b_pop) b_pops++;
      if (cb.pop_w) write_pops++;

      if (cb.ic_valid) begin
        returns++;
        if (mode != 1 || cb.ic_ret.rtype !== ICACHE_IFILL_ACK ||
            cb.ic_ret.tid !== READ_TID || cb.ic_ret.user !== '0 ||
            cb.ic_ret.data !== EXPECTED[CVA6Cfg.ICACHE_LINE_WIDTH-1:0])
          bad("RETURN_DATA_CORRUPT");
      end
      if (cb.ret_valid) begin
        case (cb.ret.rtype)
          DCACHE_INV_REQ: begin
            if (inv_returns >= inv_events || cb.ret.inv.all !== 1'b1 ||
                cb.ret.inv.idx !== inv_indices[inv_returns]) bad("WRONG_INVALIDATION_RETURN");
            inv_returns++;
          end
          DCACHE_LOAD_ACK, DCACHE_ATOMIC_ACK: begin
            returns++;
            if (mode == 1 || cb.ret.tid !== READ_TID || cb.ret.user !== '0 ||
                ((mode == 2) != (cb.ret.rtype == DCACHE_ATOMIC_ACK)))
              bad("RETURN_DATA_CORRUPT");
            if (mode == 2) begin
              if (cb.ret.data[63:0] !== EXPECTED[63:0]) bad("RETURN_DATA_CORRUPT");
            end else if (cb.ret.data !== EXPECTED) bad("RETURN_DATA_CORRUPT");
          end
          DCACHE_STORE_ACK: begin
            store_acks++;
            if (!b_concurrent || cb.ret.tid !== STORE_TID || store_acks != 1 || b_count != 1)
              bad("WRONG_STORE_ACK");
          end
          default: bad("WRONG_RETURN_TYPE");
        endcase
      end
    end
  end

  task automatic enqueue_store;
    @(negedge clk);
    dc = '0;
    dc.rtype = DCACHE_STORE_REQ;
    dc.paddr = STORE_ADDR;
    dc.size = 3;
    dc.data = STORE_DATA;
    dc.tid = STORE_TID;
    dc_req = 1;
    rsp.aw_ready = 1;
    rsp.w_ready = 1;
    do @(cb); while (cb.dc_ack !== 1'b1);
    @(negedge clk);
    dc_req = 0;
    while (aw_count != 1 || w_count != 1) @(negedge clk);
    rsp.aw_ready = 0;
    rsp.w_ready = 0;
  endtask

  task automatic enqueue_read;
    @(negedge clk);
    dc = '0;
    ic = '0;
    dc.rtype = mode == 2 ? DCACHE_ATOMIC_REQ : DCACHE_LOAD_REQ;
    dc.amo_op = mode == 2 ? AMO_LR : AMO_NONE;
    dc.paddr = READ_ADDR;
    dc.size = mode == 2 ? 3 : 7;
    dc.tid = READ_TID;
    ic.paddr = READ_ADDR;
    ic.tid = READ_TID;
    dc_req = mode != 1;
    ic_req = mode == 1;
    do @(cb); while ((mode == 1 ? cb.ic_ack : cb.dc_ack) !== 1'b1);
    @(negedge clk);
    dc_req = 0;
    ic_req = 0;
    rsp.ar_ready = 1;
    do @(cb); while (!(cb.req.ar_valid && cb.rsp.ar_ready));
    @(negedge clk);
    rsp.ar_ready = 0;
  endtask

  task automatic send_beat(input int beat);
    bit accepted;
    bit b_accepted;
    int held_invalidations;
    accepted = 0;
    b_accepted = 0;
    held_invalidations = 0;
    @(negedge clk);
    rsp.r_valid = 1;
    rsp.r = '0;
    rsp.r.id = read_id;
    rsp.r.data = EXPECTED[64*beat+:64];
    rsp.r.last = beat == beats-1;
    rsp.r.resp = mode == 2 ? axi_pkg::RESP_EXOKAY : axi_pkg::RESP_OKAY;
    inv = collide == beat;
    if (b_concurrent && beat == (collide < 0 ? 0 : collide)) begin
      rsp.b_valid = 1;
      rsp.b = '0;
      rsp.b.id = write_id;
      rsp.b.resp = axi_pkg::RESP_OKAY;
    end
    do begin
      @(cb);
      if (cb.rsp.r_valid && cb.req.r_ready) accepted = 1;
      if (cb.inv && cb.inv_ready) held_invalidations++;
      if (cb.rsp.b_valid && cb.req.b_ready) b_accepted = 1;
      @(negedge clk);
      if (accepted) rsp.r_valid = 0;
      if (held_invalidations >= hold_cycles) inv = 0;
      if (b_accepted) rsp.b_valid = 0;
    end while (!accepted || inv || rsp.b_valid);
    repeat (2) @(negedge clk);
  endtask

  initial begin : stimulus
    dc = '0;
    ic = '0;
    rsp = '0;
    if ($value$plusargs("collide=%d", collide)) begin end
    if ($value$plusargs("mode=%d", mode)) begin end
    if ($value$plusargs("hold=%d", hold_cycles)) begin end
    if ($value$plusargs("b_concurrent=%d", b_concurrent)) begin end
    if ($value$plusargs("filter=%d", filter_mode)) begin end
    beats = mode == 2 ? 1 : mode == 1 ? CVA6Cfg.ICACHE_LINE_WIDTH/64 : 4;
    if (mode < 0 || mode > 2 || collide < -1 || collide >= beats ||
        !(hold_cycles inside {1, 4}) || !(b_concurrent inside {0, 1}) ||
        (b_concurrent && mode != 0) || filter_mode != 0 ||
        CVA6Cfg.DCACHE_LINE_WIDTH != 256 || CVA6Cfg.ICACHE_LINE_WIDTH != 128 ||
        CVA6Cfg.MEM_TID_WIDTH < 2 || !CVA6Cfg.RVA) begin
      bad("INVALID_CASE_CONFIGURATION");
      result(0);
      $fatal(1, "INVALID_CASE_CONFIGURATION");
    end
    repeat (4) @(negedge clk);
    rst = 1;
    if (b_concurrent) enqueue_store();
    enqueue_read();
    for (int beat = 0; beat < beats; beat++) send_beat(beat);
    repeat (20) @(negedge clk);

    if (ar_count != 1 || reads != beats || read_last != 1 || returns != 1 ||
        captures_d + captures_i != beats || pops_d + pops_i != 1 ||
        rd_empty_d !== 1'b1 || rd_empty_i !== 1'b1 ||
        request_empty_d !== 1'b1 || request_empty_i !== 1'b1)
      bad("READ_COMPLETION_LOST");
    if (dc_accepts != (mode != 1) + b_concurrent || ic_accepts != (mode == 1))
      bad("WRONG_CACHE_REQUEST_COUNT");
    if (external_invals != (collide >= 0 ? hold_cycles : 0) ||
        internal_invals != (mode == 2) || inv_returns != external_invals + internal_invals ||
        collision_stalls != (collide >= 0 ? hold_cycles : 0))
      bad("INVALIDATION_COUNT_MISMATCH");
    if (aw_count != b_concurrent || w_count != b_concurrent || b_count != b_concurrent ||
        b_pops != b_concurrent || write_pops != b_concurrent || store_acks != b_concurrent ||
        wr_empty !== 1'b1 || b_empty !== 1'b1 ||
        b_collision != ((b_concurrent && collide >= 0) ? 1 : 0))
      bad("STORE_B_COMPLETION_LOST");
    result(errors == 0);
    if (errors != 0) $fatal(1, "%s", first_error);
    $display("INVAL_READ_PASS collide=%0d", collide);
    $finish;
  end
endmodule
