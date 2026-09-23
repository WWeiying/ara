// SPDX-License-Identifier: SHL-0.51
// Independent host register bank. No request back to the observed fabric.
module ara_fpga_debug #(
  parameter bit DualDdr = 0,
  parameter type reg_req_t = logic,
  parameter type reg_rsp_t = logic
) (
  input logic clk_i, rst_ni, soc_rst_ni,
  input logic [3:0] status_i,
  input reg_req_t host_req_i, cpu_req_i,
  output reg_rsp_t host_rsp_o, cpu_rsp_o,
  input logic [7:0] retire_count_i,
  input logic [63:0] retire_pc_i, head_pc_i,
  input logic trap_i,
  input logic [63:0] trap_pc_i, trap_cause_i, trap_tval_i,
  input logic [1:0][14:0][63:0] ddr_metrics_i,
  output logic count_enable_o, count_clear_o
);
  logic frozen_q, timeout_q, soc_rst_q;
  logic [31:0] sequence_q, marker_q, result_q, run_id_q, done_q;
  logic [31:0] watchdog_q, idle_q;
  logic [15:0][31:0] mailbox_q;
  logic [7:0][63:0] live_q, snapshot_q;
  logic [1:0][14:0][63:0] ddr_snapshot_q;
  reg_req_t write_req;
  logic write_valid, cmd, snapshot, timeout_event, reset_event;

  // Both ports read concurrently. Host has priority for simultaneous writes;
  // CPU ready is held low, so no accepted CPU write is lost.
  always_comb begin
    write_req = cpu_req_i;
    if (host_req_i.valid && host_req_i.write) write_req = host_req_i;
    write_valid = write_req.valid && write_req.write;
    cmd = write_valid && write_req.addr[11:0] == 12'h010 && write_req.wstrb[0];
    count_clear_o = cmd && write_req.wdata[0];
    timeout_event = watchdog_q != 0 && !frozen_q && soc_rst_ni &&
                    retire_count_i == 0 && idle_q >= watchdog_q - 1;
    reset_event = soc_rst_q && !soc_rst_ni;
    snapshot = (cmd && write_req.wdata[1]) || timeout_event || reset_event;
    count_enable_o = soc_rst_ni && !frozen_q;
    host_rsp_o = '0;
    cpu_rsp_o = '0;
    host_rsp_o.ready = 1'b1;
    cpu_rsp_o.ready = !(host_req_i.valid && host_req_i.write && cpu_req_i.write);
    host_rsp_o.rdata = read_word(host_req_i.addr[11:0]);
    cpu_rsp_o.rdata = read_word(cpu_req_i.addr[11:0]);
    host_rsp_o.error = host_req_i.addr[1:0] != 0 || !mapped(host_req_i.addr[11:0]);
    cpu_rsp_o.error = cpu_req_i.addr[1:0] != 0 || !mapped(cpu_req_i.addr[11:0]);
  end

  function automatic logic mapped(input logic [11:0] addr);
    return (addr <= 12'h030) || (addr >= 12'h040 && addr < 12'h080) ||
           (addr >= 12'h100 && addr < 12'h140) ||
           (addr >= 12'h180 && addr < 12'h1f8) ||
           (addr >= 12'h200 && addr < 12'h278);
  endfunction
  function automatic logic [31:0] read_word(input logic [11:0] addr);
    logic [63:0] value;
    value = 0;
    case (addr)
      12'h000: return 32'h41524442;
      12'h004: return 1;
      12'h008: return 32'h1 | (DualDdr ? 32'h2 : 0);
      12'h00c: return 50000000;
      12'h010: return {31'b0, frozen_q};
      12'h014: return {28'b0, status_i};
      12'h018: return sequence_q;
      12'h01c: return marker_q;
      12'h020: return result_q;
      12'h024: return run_id_q;
      12'h028: return watchdog_q;
      12'h02c: return {31'b0, timeout_q};
      12'h030: return done_q;
      default: begin
        if (addr >= 12'h040 && addr < 12'h080) return mailbox_q[addr[5:2]];
        if (addr >= 12'h100 && addr < 12'h140) value = snapshot_q[addr[5:3]];
        if (addr >= 12'h180 && addr < 12'h1f8) value = ddr_snapshot_q[0][addr[6:3]];
        if (addr >= 12'h200 && addr < 12'h278) value = ddr_snapshot_q[1][addr[6:3]];
        return addr[2] ? value[63:32] : value[31:0];
      end
    endcase
  endfunction
  function automatic logic [31:0] merge_bytes(input logic [31:0] old_value,
                                             input logic [31:0] new_value,
                                             input logic [3:0] mask);
    logic [31:0] value;
    value = old_value;
    for (int i = 0; i < 4; i++) if (mask[i]) value[8*i +: 8] = new_value[8*i +: 8];
    return value;
  endfunction
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      frozen_q <= 0;
      timeout_q <= 0;
      soc_rst_q <= 0;
      sequence_q <= 0;
      marker_q <= 0;
      result_q <= 0;
      run_id_q <= 0;
      done_q <= 0;
      watchdog_q <= 0;
      idle_q <= 0;
      mailbox_q <= '0;
      live_q <= '0;
      snapshot_q <= '0;
      ddr_snapshot_q <= '0;
    end else begin
      soc_rst_q <= soc_rst_ni;
      if (write_valid && write_req.addr[1:0] == 0) begin
        case (write_req.addr[11:0])
          12'h01c: marker_q <= merge_bytes(marker_q, write_req.wdata, write_req.wstrb);
          12'h020: result_q <= merge_bytes(result_q, write_req.wdata, write_req.wstrb);
          12'h024: run_id_q <= merge_bytes(run_id_q, write_req.wdata, write_req.wstrb);
          12'h028: watchdog_q <= merge_bytes(watchdog_q, write_req.wdata, write_req.wstrb);
          12'h030: done_q <= merge_bytes(done_q, write_req.wdata, write_req.wstrb);
          default: if (write_req.addr[11:0] >= 12'h040 && write_req.addr[11:0] < 12'h080)
            mailbox_q[write_req.addr[5:2]] <= merge_bytes(
                mailbox_q[write_req.addr[5:2]], write_req.wdata, write_req.wstrb);
        endcase
      end
      if (count_enable_o) begin
        live_q[0] <= live_q[0] + 1;
        live_q[1] <= live_q[1] + 64'(retire_count_i);
        if (retire_count_i != 0) live_q[2] <= retire_pc_i;
        live_q[3] <= head_pc_i;
        if (trap_i) begin
          live_q[4] <= trap_pc_i;
          live_q[5] <= trap_cause_i;
          live_q[6] <= trap_tval_i;
          live_q[7] <= live_q[7] + 1;
        end
      end
      if (!count_enable_o || retire_count_i != 0) idle_q <= 0;
      else if (idle_q != 32'hffffffff) idle_q <= idle_q + 1;
      if (cmd && write_req.wdata[2]) frozen_q <= 1;
      if (cmd && write_req.wdata[3]) frozen_q <= 0;
      if (timeout_event || reset_event) frozen_q <= 1;
      if (timeout_event) timeout_q <= 1;
      if (snapshot) begin
        // All fields refer to the same pre-edge state. Software can snapshot
        // after freeze to include the final completed work without torn reads.
        snapshot_q <= live_q;
        ddr_snapshot_q <= ddr_metrics_i;
        sequence_q <= sequence_q + 1;
      end
      if (count_clear_o) begin
        live_q <= '0;
        frozen_q <= 0;
        timeout_q <= 0;
        idle_q <= 0;
        done_q <= 0;
      end
    end
  end
endmodule
