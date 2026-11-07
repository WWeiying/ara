// Verification-only cycle window and command-boundary records. No driven DUT ports.
module chain_boundary_monitor (
  input logic clk_i, rst_ni,
  input logic front_valid_i, front_ready_i,
  input logic [31:0] insn_i,
  input logic ara_idle_i, normal_idle_i,
  input logic qbs_fire_i, qbs_terminal_i, qbs_busy_i,
  input logic akv_fire_i, akv_terminal_i, akv_busy_i,
  input logic tile_start_i, tile_done_i, wait_weight_i,
  input logic ar_valid_i, ar_ready_i, r_valid_i, r_ready_i
);
  string path;
  integer fd;
  bit enabled, seen;
  longint unsigned cycle, window_start, rows, limit;
  logic is_custom;
  assign is_custom = front_valid_i && insn_i[6:0] == 7'h5b &&
                     !(insn_i[14:12] inside {3'd1,3'd4});
  initial begin
    enabled = $value$plusargs("CHAIN_TRACE=%s", path);
    limit = 1000;
    if ($value$plusargs("CHAIN_WINDOW=%d", limit)) begin
      if (limit == 0 || limit > 10000) $fatal(1, "Invalid CHAIN_WINDOW");
    end
    fd = 0;
    if (enabled) begin
      fd = $fopen(path, "w");
      if (!fd) $fatal(1, "Cannot open chain trace");
      $fdisplay(fd, "cycle,insn,front_valid,front_ready,ara_idle,normal_idle,qbs_fire,qbs_terminal,qbs_busy,akv_fire,akv_terminal,akv_busy,tile_start,tile_done,wait_weight,ar_valid,ar_ready,r_valid,r_ready");
    end
  end
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cycle <= 0;
      rows <= 0;
      seen <= 0;
      window_start <= 0;
    end else begin
      cycle <= cycle + 1;
      if (enabled && is_custom && !seen) begin
        seen <= 1;
        window_start <= cycle;
      end
      if (enabled && (qbs_fire_i || qbs_terminal_i || akv_fire_i || akv_terminal_i))
        $display("[CHAIN_BOUNDARY] cycle=%0d insn=%08h qbs_fire=%0d qbs_terminal=%0d akv_fire=%0d akv_terminal=%0d",
                 cycle, insn_i, qbs_fire_i, qbs_terminal_i, akv_fire_i, akv_terminal_i);
      if (enabled && ((seen && cycle-window_start < limit) || (!seen && is_custom))) begin
        $fdisplay(fd, "%0d,%08h,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
          cycle, insn_i, front_valid_i, front_ready_i, ara_idle_i, normal_idle_i,
          qbs_fire_i, qbs_terminal_i, qbs_busy_i, akv_fire_i, akv_terminal_i, akv_busy_i,
          tile_start_i, tile_done_i, wait_weight_i, ar_valid_i, ar_ready_i, r_valid_i, r_ready_i);
        rows <= rows + 1;
      end
    end
  end
  final begin
    if (enabled) begin
      $display("[CHAIN_WINDOW] start=%0d rows=%0d limit=%0d", window_start, rows, limit);
      $fclose(fd);
    end
  end
endmodule

bind ara_system chain_boundary_monitor i_chain_boundary_monitor (
  .clk_i(clk_i), .rst_ni(rst_ni),
  .front_valid_i(acc_req.acc_req.req_valid), .front_ready_i(acc_resp.acc_resp.req_ready),
  .insn_i(acc_req.acc_req.insn), .ara_idle_i(i_ara.ara_idle),
  .normal_idle_i(i_ara.i_vlsu.normal_vlsu_idle),
  .qbs_fire_i(i_ara.i_vlsu.qbs_command_fire),
  .qbs_terminal_i(i_ara.i_vlsu.qbs_terminal), .qbs_busy_i(i_ara.i_vlsu.qbs_busy),
  .akv_fire_i(i_ara.i_vlsu.akv_command_fire),
  .akv_terminal_i(i_ara.i_vlsu.akv_terminal), .akv_busy_i(i_ara.i_vlsu.akv_busy),
  .tile_start_i(i_ara.i_vlsu.i_qbs_engine.i_compute_engine.integer_start_fire),
  .tile_done_i(i_ara.i_vlsu.i_qbs_engine.i_compute_engine.integer_done),
  .wait_weight_i(i_ara.i_vlsu.i_qbs_engine.i_compute_engine.probe_weight_wait_active),
  .ar_valid_i(i_ara.i_vlsu.qbs_axi_ar_valid), .ar_ready_i(i_ara.i_vlsu.qbs_axi_ar_ready),
  .r_valid_i(i_ara.i_vlsu.qbs_axi_r_valid), .r_ready_i(i_ara.i_vlsu.qbs_axi_r_ready)
);
