// Testbench-only wrapper BEFORE the original, unchanged registered AXI cut.
// A two-entry ledger observes real handshakes; it stores no AXI payload.
module reader_fault_cut #(
  parameter type aw_chan_t = logic, w_chan_t = logic, b_chan_t = logic,
  parameter type ar_chan_t = logic, r_chan_t = logic,
  parameter type axi_req_t = logic, axi_resp_t = logic
) (
  input logic clk_i, rst_ni,
  input axi_req_t slv_req_i, output axi_resp_t slv_resp_o,
  output axi_req_t mst_req_o, input axi_resp_t mst_resp_i,
  input logic [1:0] owner_i, fire_i, terminal_i,
  input logic qbs_fault_i, reader_stalled_i, reader_pending_i, reader_drain_i,
  input logic [1:0] reader_bursts_i
);
  typedef enum logic [2:0] {WAIT_TARGET, WAIT_HELD, ERROR_BEAT,
                           DRAIN_OLDER, HOLD_EMPTY, RELEASE_AR, FINISHED} state_t;
  state_t state_q;
  axi_req_t cut_req;
  axi_resp_t cut_resp;
  ar_chan_t ledger_ar [2];
  logic [8:0] ledger_left [2];
  logic ledger_target [2];
  logic rd_q, wr_q;
  int unsigned count_q, ordinal_q, held_q, empty_q, age_q;
  int unsigned injected_q, target_ar_q, younger_ar_q;
  logic [63:0] target;
  logic block_ar, block_r, inject_resp, head_target, ar_fire, r_fire, tracking;

  initial begin
    if (!$value$plusargs("READER_FAULT_TARGET=%h", target) || target == 0 || target[5:0] != 0 ||
        int'(target[11:0]) > 4096-288)
      $fatal(1, "READER_FAULT_ERROR missing/misaligned target");
  end

  assign head_target = count_q != 0 && ledger_target[rd_q];
  assign block_ar = state_q inside {WAIT_HELD, ERROR_BEAT, DRAIN_OLDER, HOLD_EMPTY};
  assign block_r = state_q == WAIT_HELD && head_target;
  assign inject_resp = state_q == ERROR_BEAT && head_target;
  assign ar_fire = slv_req_i.ar_valid && slv_resp_o.ar_ready;
  assign r_fire = slv_resp_o.r_valid && slv_req_i.r_ready;
  assign tracking = owner_i == 1 && ordinal_q == 2;

  always_comb begin
    cut_req = slv_req_i;
    slv_resp_o = cut_resp;
    // Both participants agree on acceptance. All payloads remain wired through.
    cut_req.ar_valid = slv_req_i.ar_valid && !block_ar;
    slv_resp_o.ar_ready = cut_resp.ar_ready && !block_ar;
    cut_req.r_ready = slv_req_i.r_ready && !block_r;
    slv_resp_o.r_valid = cut_resp.r_valid && !block_r;
    if (inject_resp) slv_resp_o.r.resp = axi_pkg::RESP_SLVERR;
  end

  axi_cut #(
    .aw_chan_t(aw_chan_t), .w_chan_t(w_chan_t), .b_chan_t(b_chan_t),
    .ar_chan_t(ar_chan_t), .r_chan_t(r_chan_t),
    .axi_req_t(axi_req_t), .axi_resp_t(axi_resp_t)
  ) i_cut (
    .clk_i, .rst_ni, .slv_req_i(cut_req), .slv_resp_o(cut_resp),
    .mst_req_o, .mst_resp_i
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= WAIT_TARGET;
      rd_q <= 0; wr_q <= 0; count_q <= 0; ordinal_q <= 0;
      held_q <= 0; empty_q <= 0; age_q <= 0;
      injected_q <= 0; target_ar_q <= 0; younger_ar_q <= 0;
      for (int i=0;i<2;i++) begin
        ledger_ar[i] <= '0; ledger_left[i] <= '0; ledger_target[i] <= 0;
      end
    end else begin
      if ($isunknown({state_q, owner_i, fire_i, terminal_i}))
        $fatal(1, "READER_FAULT_ERROR unknown owner/control");
      if (tracking && $isunknown({reader_stalled_i, reader_pending_i, reader_drain_i,
                                 reader_bursts_i, qbs_fault_i}))
        $fatal(1, "READER_FAULT_ERROR unknown active reader control");
      if (fire_i[0]) ordinal_q <= ordinal_q + 1;
      if (state_q != WAIT_TARGET && state_q != FINISHED) begin
        age_q <= age_q + 1;
        if (age_q >= 4096) $fatal(1, "READER_FAULT_ERROR scenario bound");
        if (owner_i !== 2'b01) $fatal(1, "READER_FAULT_ERROR owner escaped");
      end
      if (ar_fire && tracking) begin
        if (count_q >= 2) $fatal(1, "READER_FAULT_ERROR ledger overflow");
        ledger_ar[wr_q] <= slv_req_i.ar;
        ledger_left[wr_q] <= 9'(slv_req_i.ar.len) + 1'b1;
        ledger_target[wr_q] <= state_q == WAIT_TARGET && ordinal_q == 2 &&
                               owner_i == 1 && slv_req_i.ar.addr == target;
        wr_q <= !wr_q;
        if (state_q == WAIT_TARGET && ordinal_q == 2 && owner_i == 1 &&
            slv_req_i.ar.addr == target) begin
          if (slv_req_i.ar.len != 8 || slv_req_i.ar.size != 4 || slv_req_i.ar.burst != 1)
            $fatal(1, "READER_FAULT_ERROR expected 144B row burst");
          state_q <= WAIT_HELD;
          target_ar_q <= target_ar_q + 1;
        end
        if (state_q == RELEASE_AR) begin
          if (slv_req_i.ar.addr != target + 144)
            $fatal(1, "READER_FAULT_ERROR younger row address");
          younger_ar_q <= younger_ar_q + 1;
        end
      end
      if (r_fire && tracking) begin
        if (count_q == 0 || slv_resp_o.r.id !== ledger_ar[rd_q].id ||
            slv_resp_o.r.last !== (ledger_left[rd_q] == 1))
          $fatal(1, "READER_FAULT_ERROR response not backed by accepted burst");
        if (cut_resp.r.resp !== axi_pkg::RESP_OKAY)
          $fatal(1, "READER_FAULT_ERROR unexpected actual memory error");
        if (slv_resp_o.r.last) rd_q <= !rd_q;
        else ledger_left[rd_q] <= ledger_left[rd_q] - 1'b1;
      end
      case ({ar_fire && tracking, r_fire && tracking && slv_resp_o.r.last})
        2'b10: count_q <= count_q+1;
        2'b01: count_q <= count_q-1;
        default: ;
      endcase
      case (state_q)
        WAIT_HELD: begin
          if (reader_stalled_i && slv_req_i.ar_valid && !slv_resp_o.ar_ready)
            held_q <= held_q+1;
          if (held_q >= 2 && head_target && cut_resp.r_valid) begin
            if (reader_bursts_i !== 1 || slv_req_i.ar.addr != target+144 ||
                cut_resp.r.last || ledger_left[rd_q] != 9)
              $fatal(1, "READER_FAULT_ERROR no older burst plus reader-held row");
            state_q <= ERROR_BEAT;
          end
        end
        ERROR_BEAT: if (r_fire) begin
          if (!head_target || !reader_stalled_i || slv_resp_o.r.last)
            $fatal(1, "READER_FAULT_ERROR wrong injection beat");
          injected_q <= injected_q + 1;
          state_q <= DRAIN_OLDER;
        end
        DRAIN_OLDER: if (r_fire && slv_resp_o.r.last) begin
          if (!head_target) $fatal(1, "READER_FAULT_ERROR wrong draining burst");
          state_q <= HOLD_EMPTY;
        end
        HOLD_EMPTY: begin
          if (count_q != 0 || !reader_stalled_i || !reader_pending_i ||
              reader_bursts_i != 0 || terminal_i != 0 || qbs_fault_i)
            $fatal(1, "READER_FAULT_ERROR premature completion before held AR acceptance");
          empty_q <= empty_q + 1;
          if (empty_q == 5) state_q <= RELEASE_AR;
        end
        RELEASE_AR: if (terminal_i[0]) begin
          if (!qbs_fault_i || count_q != 0 || reader_stalled_i ||
              reader_bursts_i != 0 || injected_q != 1 || younger_ar_q != 1)
            $fatal(1, "READER_FAULT_ERROR terminal before complete real drain");
          state_q <= FINISHED;
        end
        default: ;
      endcase
    end
  end

  final begin
    if (state_q != FINISHED || injected_q != 1 || target_ar_q != 1 || younger_ar_q != 1)
      $display("READER_FAULT_ERROR incomplete scenario");
    else $display("READER_FAULT_INJECTOR_PASS target_ar=1 younger_ar=1 errors=1 held_min=2 empty_hold=6");
  end
endmodule
