// Copyright 2026. Solderpad Hardware License, Version 0.51.
// Measured motivation: the single-entry candidate retained 30/30 first-load
// hits but took 3223 cycles versus 2786 baseline. Its Empty-only hint admission
// cannot retain the second load exposed by vsetvli-result forwarding.
// Hypothesis: two disjoint 128-byte hints can finish before store B and produce
// two exact demand hits. Check private AR/R completion, hit_o, and replay RLAST;
// occupancy alone is not evidence of either consumption or a speedup.
// This is a cancellable data buffer, never an architectural instruction grant.
module store_load_lookahead_pair #(
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
  typedef enum logic [2:0] {Empty, Pending, Send, Fill, Ready, Replay} state_t;
  state_t state_q [2], state_d [2];
  ar_t saved_ar_q [2];
  ar_t replay_ar_q;
  logic [1:0] killed_q, invalidate;
  logic locked_q, normal_ar_locked_q;
  logic [8:0] normal_outstanding_q;
  logic [PtrWidth-1:0] fill_ptr_q, replay_ptr_q;
  logic [DataWidth-1:0] data_q [2][Beats];
  logic free_valid, pending_valid, send_valid, fill_valid, replay_valid;
  logic free_idx, pending_idx, send_idx, fill_idx, replay_idx_q, hit_idx;
  logic private_busy, choose_prepare, prepare_fire, normal_fire, normal_last;
  logic fill_fire, fill_target, fill_last, replay_fire, replay_last;
  logic hint_overlap, hint_supported, hint_invalid, write_supported;
  logic [64:0] write_start, write_end;
  r_t replay_r;

  // All-ones RID is reserved by the caller. Only one private burst is issued
  // until its RLAST drains, including killed fills; no private response queue
  // or cross-ID ordering assumption is needed. Ordinary reads retain their IDs.
  function automatic logic exact(input ar_t demand, input ar_t hint);
    ar_t a, b;
    a = demand;
    b = hint;
    a.id = '0;
    b.id = '0;
    return demand.id == '0 && !demand.lock && a == b;
  endfunction

  assign write_start = 65'(axi_pkg::aligned_addr(req_i.aw.addr, req_i.aw.size));
  assign write_end = write_start + ((65'(req_i.aw.len) + 65'd1) << req_i.aw.size);
  assign write_supported = allow_disjoint_writes_i &&
      req_i.aw.burst == axi_pkg::BURST_INCR && req_i.aw.size <= $clog2(DataWidth/8);
  assign hint_invalid = invalidate_i || (req_i.aw_valid && !(write_supported &&
      (write_end <= 65'(prepare_ar_i.addr) ||
       write_start >= 65'(prepare_ar_i.addr) + 65'(Bytes))));
  assign hint_supported = prepare_ar_i.len == 8'(Beats - 1) &&
      prepare_ar_i.size == $clog2(DataWidth/8) &&
      prepare_ar_i.burst == axi_pkg::BURST_INCR && !prepare_ar_i.lock &&
      (65'(prepare_ar_i.addr) % (DataWidth/8)) == 0 &&
      (13'(prepare_ar_i.addr[11:0]) + 13'(Bytes) <= 13'd4096);

  always_comb begin
    free_valid = 1'b0;
    pending_valid = 1'b0;
    send_valid = 1'b0;
    fill_valid = 1'b0;
    replay_valid = 1'b0;
    free_idx = 1'b0;
    pending_idx = 1'b0;
    send_idx = 1'b0;
    fill_idx = 1'b0;
    hint_overlap = 1'b0;
    inflight_o = 1'b0;
    for (int i = 0; i < 2; i++) begin
      invalidate[i] = invalidate_i || (req_i.aw_valid && !(write_supported &&
          (write_end <= 65'(saved_ar_q[i].addr) ||
           write_start >= 65'(saved_ar_q[i].addr) + 65'(Bytes))));
      if (state_q[i] == Empty) begin
        free_valid = 1'b1;
        free_idx = 1'(i);
      end
      if (state_q[i] == Pending) begin
        pending_valid = 1'b1;
        pending_idx = 1'(i);
      end
      if (state_q[i] == Send) begin
        send_valid = 1'b1;
        send_idx = 1'(i);
      end
      if (state_q[i] == Fill) begin
        fill_valid = 1'b1;
        fill_idx = 1'(i);
      end
      replay_valid |= state_q[i] == Replay;
      inflight_o |= state_q[i] inside {Pending, Send, Fill, Replay};
      hint_overlap |= state_q[i] != Empty &&
          65'(prepare_ar_i.addr) < 65'(saved_ar_q[i].addr) + 65'(Bytes) &&
          65'(saved_ar_q[i].addr) < 65'(prepare_ar_i.addr) + 65'(Bytes);
    end
  end

  assign private_busy = send_valid || fill_valid;
  assign prepare_ready_o = free_valid && !hint_invalid && hint_supported &&
      !hint_overlap && !req_i.ar_valid && !normal_ar_locked_q;
  assign choose_prepare = send_valid && (locked_q ||
      (!req_i.ar_valid && !normal_ar_locked_q && !invalidate[send_idx]));
  assign prepare_fire = choose_prepare && resp_i.ar_ready;
  assign prepare_fire_o = prepare_fire;
  assign fill_target = fill_valid ? fill_idx : send_idx;
  assign fill_fire = (fill_valid || prepare_fire) && resp_i.r_valid &&
      resp_i.r.id == '1 && req_o.r_ready;
  assign fill_last = fill_ptr_q == PtrWidth'(Beats - 1);
  assign replay_last = replay_ptr_q == PtrWidth'(Beats - 1);
  assign replay_fire = replay_valid && req_i.r_ready;
  assign normal_fire = req_i.ar_valid && resp_o.ar_ready && !hit_o;
  assign normal_last = resp_i.r_valid && resp_i.r.id != '1 &&
      req_o.r_ready && resp_i.r.last;

  // No normal AR passes during replay. A second hit is accepted only together
  // with the first replay's final R handshake. This also prevents a younger
  // same-ID normal response overtaking either replay, even under R backpressure.
  always_comb begin
    hit_o = 1'b0;
    hit_idx = 1'b0;
    for (int i = 0; i < 2; i++) begin
      if (state_q[i] == Ready && !invalidate[i] && !resp_i.b_valid &&
          !normal_ar_locked_q && normal_outstanding_q == 0 &&
          !(resp_i.r_valid && resp_i.r.id != '1) && !choose_prepare &&
          (!replay_valid || (replay_fire && replay_last)) &&
          req_i.ar_valid && exact(req_i.ar, saved_ar_q[i])) begin
        hit_o = 1'b1;
        hit_idx = 1'(i);
      end
    end
  end

  always_comb begin
    replay_r = '0;
    replay_r.id = replay_ar_q.id;
    replay_r.data = data_q[replay_idx_q][replay_ptr_q];
    replay_r.last = replay_last;
    replay_r.resp = axi_pkg::RESP_OKAY;
    req_o = req_i;
    resp_o = resp_i;
    if (replay_valid) begin
      req_o.ar_valid = 1'b0;
      resp_o.ar_ready = 1'b0;
      req_o.r_ready = 1'b0;
      resp_o.r = replay_r;
      resp_o.r_valid = 1'b1;
    end
    if (choose_prepare) begin
      req_o.ar = saved_ar_q[send_idx];
      req_o.ar.id = '1;
      req_o.ar_valid = 1'b1;
      resp_o.ar_ready = 1'b0;
    end
    if (resp_i.r_valid && resp_i.r.id == '1) begin
      req_o.r_ready = 1'b1;
      if (!replay_valid) resp_o.r_valid = 1'b0;
    end
    if (hit_o) begin
      req_o.ar_valid = 1'b0;
      resp_o.ar_ready = 1'b1;
    end
  end

  always_comb begin
    state_d = state_q;
    if (!private_busy && pending_valid) state_d[pending_idx] = Send;
    for (int i = 0; i < 2; i++) begin
      case (state_q[i])
        Empty: if (prepare_i && prepare_ready_o && free_idx == 1'(i))
          state_d[i] = private_busy || pending_valid ? Pending : Send;
        Pending: if (invalidate[i] || normal_fire) state_d[i] = Empty;
        Send: begin
          if (prepare_fire) state_d[i] = Fill;
          else if (!locked_q && (invalidate[i] || normal_fire)) state_d[i] = Empty;
        end
        Ready: begin
          if (invalidate[i] || normal_fire) state_d[i] = Empty;
          else if (hit_o && hit_idx == 1'(i)) state_d[i] = Replay;
        end
        Replay: if (replay_fire && replay_last) state_d[i] = Empty;
        default: ;
      endcase
    end
    if (fill_fire && resp_i.r.last)
      state_d[fill_target] = (killed_q[fill_target] || invalidate[fill_target] ||
          normal_fire || resp_i.r.resp != axi_pkg::RESP_OKAY || !fill_last) ? Empty : Ready;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= '{default: Empty};
      saved_ar_q <= '{default: '0};
      replay_ar_q <= '0;
      killed_q <= '0;
      locked_q <= 1'b0;
      normal_ar_locked_q <= 1'b0;
      normal_outstanding_q <= '0;
      fill_ptr_q <= '0;
      replay_ptr_q <= '0;
      replay_idx_q <= 1'b0;
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
      if (!send_valid || prepare_fire) locked_q <= 1'b0;
      if (choose_prepare && !resp_i.ar_ready) locked_q <= 1'b1;
      for (int i = 0; i < 2; i++) begin
        if (state_q[i] == Empty) killed_q[i] <= 1'b0;
        if (state_q[i] inside {Pending, Send, Fill}) begin
          if (invalidate[i] || normal_fire) killed_q[i] <= 1'b1;
        end
      end
      if (prepare_i && prepare_ready_o) saved_ar_q[free_idx] <= prepare_ar_i;
      if (fill_fire) begin
        if (resp_i.r.resp != axi_pkg::RESP_OKAY || (fill_last && !resp_i.r.last))
          killed_q[fill_target] <= 1'b1;
        // Saturation makes an overlong malformed private response drain safely.
        if (resp_i.r.last) fill_ptr_q <= '0;
        else if (!fill_last) fill_ptr_q <= fill_ptr_q + 1'b1;
      end
      if (replay_fire) replay_ptr_q <= replay_last ? '0 : replay_ptr_q + 1'b1;
      if (hit_o) begin
        replay_idx_q <= hit_idx;
        replay_ar_q <= req_i.ar;
        replay_ptr_q <= '0;
      end
    end
  end

  // Data is qualified by a complete successful fill, not by reset contents.
  always_ff @(posedge clk_i) begin
    if (fill_fire) data_q[fill_target][fill_ptr_q] <= resp_i.r.data;
  end

  // synthesis translate_off
  // Sample pre-edge state and the selected next state. invN includes external
  // flush and AWVALID (not only AW handshake); normal_fire excludes cached hits.
  // States: 0 Empty, 1 Pending, 2 Send, 3 Fill, 4 Ready, 5 Replay.
  always @(posedge clk_i) begin : trace_pair_events
    if (rst_ni && $test$plusargs("STORE_LOAD_PREPARE_TRACE") &&
        (prepare_i || prepare_fire || fill_fire || normal_fire || normal_last ||
         hit_o || replay_fire || state_q[0] != state_d[0] || state_q[1] != state_d[1] ||
         ((state_q[0] != Empty || state_q[1] != Empty) &&
          (invalidate_i || req_i.aw_valid || req_i.ar_valid ||
           (replay_valid && !req_i.r_ready)))))
      $display({
        "[STORE_LOAD_PAIR] t=%0t ",
        "state0=%0d next0=%0d inv0=%b killed0=%b addr0=%h len0=%0d exact0=%b ",
        "state1=%0d next1=%0d inv1=%b killed1=%b addr1=%h len1=%0d exact1=%b ",
        "prep=%b prep_ready=%b prep_addr=%h prep_len=%0d hint_inv=%b hint_overlap=%b ",
        "pending=%b pending_idx=%b send=%b send_idx=%b choose=%b locked=%b pf_ar=%b ",
        "fill=%b fill_idx=%b fill_fire=%b fill_ptr=%0d rid=%h rresp=%b rlast=%b ",
        "normal_fire=%b normal_last=%b normal_locked=%b normal_out=%0d hit=%b hit_idx=%b ",
        "ar_valid=%b ar_ready=%b ar_id=%h ar_addr=%h ar_len=%0d ar_size=%0d ",
        "ar_burst=%b ar_lock=%b ar_cache=%h ar_prot=%h ar_qos=%h ar_region=%h ar_user=%h ",
        "saved_ar0=%h saved_ar1=%h ",
        "bus_ar_valid=%b bus_ar_ready=%b bus_ar_id=%h bus_ar_addr=%h bus_ar_len=%0d ",
        "inv_ext=%b allow_disjoint=%b write_supported=%b aw_valid=%b aw_ready=%b ",
        "aw_addr=%h aw_len=%0d aw_size=%0d aw_burst=%b write_start=%h write_end=%h b_valid=%b ",
        "replay=%b replay_idx=%b replay_ptr=%0d replay_fire=%b replay_last=%b cpu_r_ready=%b"},
        $time,
        state_q[0], state_d[0], invalidate[0], killed_q[0],
        saved_ar_q[0].addr, saved_ar_q[0].len, exact(req_i.ar, saved_ar_q[0]),
        state_q[1], state_d[1], invalidate[1], killed_q[1],
        saved_ar_q[1].addr, saved_ar_q[1].len, exact(req_i.ar, saved_ar_q[1]),
        prepare_i, prepare_ready_o, prepare_ar_i.addr, prepare_ar_i.len,
        hint_invalid, hint_overlap,
        pending_valid, pending_idx, send_valid, send_idx, choose_prepare, locked_q, prepare_fire,
        fill_valid, fill_target, fill_fire, fill_ptr_q, resp_i.r.id, resp_i.r.resp, resp_i.r.last,
        normal_fire, normal_last, normal_ar_locked_q, normal_outstanding_q, hit_o, hit_idx,
        req_i.ar_valid, resp_o.ar_ready, req_i.ar.id, req_i.ar.addr, req_i.ar.len, req_i.ar.size,
        req_i.ar.burst, req_i.ar.lock, req_i.ar.cache, req_i.ar.prot,
        req_i.ar.qos, req_i.ar.region, req_i.ar.user, saved_ar_q[0], saved_ar_q[1],
        req_o.ar_valid, resp_i.ar_ready, req_o.ar.id, req_o.ar.addr, req_o.ar.len,
        invalidate_i, allow_disjoint_writes_i, write_supported, req_i.aw_valid, resp_i.aw_ready,
        req_i.aw.addr, req_i.aw.len, req_i.aw.size, req_i.aw.burst, write_start, write_end,
        resp_i.b_valid, replay_valid, replay_idx_q, replay_ptr_q, replay_fire, replay_last,
        req_i.r_ready);
  end
  initial begin
    assert (DataWidth >= 8 && Bytes >= DataWidth/8 && Bytes <= 4096 &&
            Bytes % (DataWidth/8) == 0 && Beats <= 256 &&
            (Beats & (Beats-1)) == 0 && ((DataWidth/8) & (DataWidth/8-1)) == 0)
      else $fatal(1, "invalid lookahead pair burst dimensions");
  end
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    req_o.ar_valid && !resp_i.ar_ready |=> req_o.ar_valid && $stable(req_o.ar));
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    resp_o.r_valid && !req_i.r_ready |=> resp_o.r_valid && $stable(resp_o.r));
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    normal_last |-> normal_outstanding_q != 0 || normal_fire);
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    normal_fire && !normal_last |-> !(&normal_outstanding_q));
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    !(state_q[0] inside {Send, Fill} && state_q[1] inside {Send, Fill}));
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    !(state_q[0] == Replay && state_q[1] == Replay));
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    resp_i.r_valid && resp_i.r.id == '1 |-> fill_valid || prepare_fire);
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    hit_o |-> normal_outstanding_q == 0 && !normal_ar_locked_q);
  // synthesis translate_on
endmodule
