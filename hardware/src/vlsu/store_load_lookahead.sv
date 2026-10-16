// Copyright 2026. Solderpad Hardware License, Version 0.51.
// One speculative read buffer. Only a later, exact, architectural AR consumes
// its data; this block never completes an instruction or writes a register.
module store_load_lookahead #(
  parameter int unsigned Bytes = 128,
  parameter int unsigned DataWidth = 128,
  parameter type ar_t = logic,
  parameter type r_t = logic,
  parameter type req_t = logic,
  parameter type resp_t = logic,
  localparam int unsigned Beats = Bytes / (DataWidth / 8),
  localparam int unsigned PtrWidth = (Beats > 1) ? $clog2(Beats) : 1
) (
  input logic clk_i,
  input logic rst_ni,
  input logic prepare_i,
  output logic prepare_ready_o,
  input ar_t prepare_ar_i,
  input logic invalidate_i,
  input logic allow_disjoint_writes_i,
  input req_t req_i,
  output resp_t resp_o,
  output req_t req_o,
  input resp_t resp_i,
  output logic inflight_o,
  output logic prepare_fire_o,
  output logic hit_o
);
  typedef enum logic [2:0] {Empty, Send, Fill, Ready, Replay} state_t;
  state_t state_q, state_d;
  ar_t saved_ar_q, replay_ar_q;
  logic locked_q, killed_q, normal_ar_locked_q;
  logic [PtrWidth-1:0] ptr_q;
  logic [DataWidth-1:0] data_q [Beats];
  logic [8:0] normal_outstanding_q;
  logic choose_prepare, prepare_fire, normal_fire, normal_last, fill_fire;
  logic invalidate, exact, replay_last, replay_fire;
  logic write_disjoint;
  logic [64:0] write_start, write_end;
  r_t replay_r;

  // Ordinary AddrGen uses ID zero. The all-ones ID is private to this buffer.
  // QBS/AKV cannot acquire the bus while inflight_o is set.
  assign write_start = 65'(axi_pkg::aligned_addr(req_i.aw.addr, req_i.aw.size));
  assign write_end = write_start + ((65'(req_i.aw.len) + 65'd1) << req_i.aw.size);
  assign write_disjoint = req_i.aw.burst == axi_pkg::BURST_INCR &&
      req_i.aw.size <= $clog2(DataWidth/8) &&
      (write_end <= 65'(saved_ar_q.addr) ||
       write_start >= 65'(saved_ar_q.addr) + 65'(Bytes));
  assign invalidate = invalidate_i ||
      (req_i.aw_valid && !(allow_disjoint_writes_i && write_disjoint));
  assign prepare_ready_o = state_q == Empty && !invalidate && !req_i.ar_valid;
  assign exact = req_i.ar.addr == saved_ar_q.addr &&
      req_i.ar.len == saved_ar_q.len && req_i.ar.size == saved_ar_q.size &&
      req_i.ar.burst == saved_ar_q.burst && req_i.ar.cache == saved_ar_q.cache &&
      req_i.ar.prot == saved_ar_q.prot && !req_i.ar.lock && req_i.ar.id == '0;
  assign inflight_o = state_q inside {Send, Fill, Replay};
  assign choose_prepare = state_q == Send &&
      (locked_q || (!req_i.ar_valid && !invalidate));
  assign prepare_fire = choose_prepare && resp_i.ar_ready;
  assign prepare_fire_o = prepare_fire;
  assign hit_o = state_q == Ready && !invalidate && !resp_i.b_valid &&
      !normal_ar_locked_q && normal_outstanding_q == '0 && req_i.ar_valid && exact;
  assign normal_fire = req_i.ar_valid && resp_o.ar_ready && !hit_o;
  assign normal_last = resp_o.r_valid && req_i.r_ready && resp_o.r.last &&
      state_q != Replay;
  assign fill_fire = state_q == Fill && resp_i.r_valid && resp_i.r.id == '1;
  assign replay_last = ptr_q == PtrWidth'(Beats - 1);
  assign replay_fire = state_q == Replay && req_i.r_ready;

  always_comb begin
    replay_r = '0;
    replay_r.id = replay_ar_q.id;
    replay_r.data = data_q[ptr_q];
    replay_r.last = replay_last;
    replay_r.resp = axi_pkg::RESP_OKAY;
    req_o = req_i;
    resp_o = resp_i;
    if (choose_prepare) begin
      req_o.ar = saved_ar_q;
      req_o.ar.id = '1;
      req_o.ar_valid = 1'b1;
      resp_o.ar_ready = 1'b0;
    end
    if (resp_i.r_valid && resp_i.r.id == '1) begin
      req_o.r_ready = 1'b1;
      resp_o.r_valid = 1'b0;
    end
    if (hit_o) begin
      req_o.ar_valid = 1'b0;
      resp_o.ar_ready = 1'b1;
    end
    if (state_q == Replay) begin
      req_o.ar_valid = 1'b0;
      resp_o.ar_ready = 1'b0;
      req_o.r_ready = 1'b0;
      resp_o.r = replay_r;
      resp_o.r_valid = 1'b1;
    end
  end

  always_comb begin
    state_d = state_q;
    case (state_q)
      Empty: if (prepare_i && prepare_ready_o) state_d = Send;
      Send: begin
        if (prepare_fire) state_d = Fill;
        else if (!locked_q && (invalidate || normal_fire)) state_d = Empty;
      end
      Fill: if (fill_fire && resp_i.r.last)
        state_d = (killed_q || invalidate || normal_fire ||
            resp_i.r.resp != axi_pkg::RESP_OKAY || !replay_last) ? Empty : Ready;
      Ready: begin
        if (invalidate || normal_fire) state_d = Empty;
        else if (hit_o) state_d = Replay;
      end
      Replay: if (replay_fire && replay_last) state_d = Empty;
      default: state_d = Empty;
    endcase
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= Empty;
      saved_ar_q <= '0;
      replay_ar_q <= '0;
      ptr_q <= '0;
      locked_q <= 1'b0;
      killed_q <= 1'b0;
      normal_ar_locked_q <= 1'b0;
      normal_outstanding_q <= '0;
    end else begin
      state_q <= state_d;
      if (req_o.ar_valid && !choose_prepare && !resp_i.ar_ready)
        normal_ar_locked_q <= 1'b1;
      if (normal_fire) normal_ar_locked_q <= 1'b0;
      case ({normal_fire, normal_last})
        2'b10: normal_outstanding_q <= normal_outstanding_q + 1'b1;
        2'b01: normal_outstanding_q <= normal_outstanding_q - 1'b1;
        default: ;
      endcase
      if (state_q == Empty) begin
        saved_ar_q <= prepare_ar_i;
        ptr_q <= '0;
        locked_q <= 1'b0;
        killed_q <= 1'b0;
      end
      if (choose_prepare && !resp_i.ar_ready) locked_q <= 1'b1;
      if (state_q inside {Send, Fill}) begin
        if (invalidate || normal_fire) killed_q <= 1'b1;
      end
      if (fill_fire) begin
        if (resp_i.r.resp != axi_pkg::RESP_OKAY) killed_q <= 1'b1;
        ptr_q <= replay_last ? '0 : ptr_q + 1'b1;
      end
      if (hit_o) begin
        replay_ar_q <= req_i.ar;
        ptr_q <= '0;
      end
      if (replay_fire) ptr_q <= replay_last ? '0 : ptr_q + 1'b1;
    end
  end

  // No reset mux on the data array. State and successful RLAST qualify reads.
  always_ff @(posedge clk_i) begin
    if (fill_fire) data_q[ptr_q] <= resp_i.r.data;
  end

  // synthesis translate_off
  always @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("STORE_LOAD_PREPARE_TRACE") &&
        state_q != Empty && (invalidate || normal_fire || fill_fire))
      $display("[STORE_LOAD_BUFFER] t=%0t state=%0d inv=%b inv_ext=%b aw=%b disjoint=%b killed=%b demand=%b fill=%b last=%b rresp=%b addr=%h",
          $time, state_q, invalidate, invalidate_i, req_i.aw_valid,
          write_disjoint, killed_q, normal_fire, fill_fire, resp_i.r.last,
          resp_i.r.resp, saved_ar_q.addr);
  end
  initial begin
    assert (Bytes >= DataWidth/8 && Bytes % (DataWidth/8) == 0 &&
            Beats <= 256 && (Beats & (Beats-1)) == 0)
      else $fatal(1, "invalid lookahead burst dimensions");
  end
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    req_o.ar_valid && !resp_i.ar_ready |=>
      req_o.ar_valid && $stable(req_o.ar));
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    resp_o.r_valid && !req_i.r_ready |=>
      resp_o.r_valid && $stable(resp_o.r));
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    normal_last |-> normal_outstanding_q != 0 || normal_fire);
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    fill_fire |-> resp_i.r.last == replay_last);
  // synthesis translate_on
endmodule
