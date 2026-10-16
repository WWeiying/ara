`include "axi/typedef.svh"
module tb;
  timeunit 1ns; timeprecision 1ps;
  `AXI_TYPEDEF_ALL(bus, logic[47:0], logic[7:0], logic[511:0], logic[63:0], logic[1:0])
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  bus_req_t [1:0] req = '0;
  bus_resp_t [1:0] rsp;
  bus_req_t mem_req;
  bus_resp_t mem_rsp = '0;
  logic [255:0] status;
  bit [255:0] aw_seen = '0, ar_seen = '0;
  int aw_count = 0, ar_count = 0, w_count = 0;
  ara_eth_shared_ddr #(.UserWidth(2), .StaticIdPartition(1),
    .req_t(bus_req_t), .rsp_t(bus_resp_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .lock_i(1'b0),
    .ara_req_i(req[0]), .ara_rsp_o(rsp[0]),
    .loader_req_i(req[1]), .loader_rsp_o(rsp[1]),
    .mem_req_o(mem_req), .mem_rsp_i(mem_rsp), .status_o(status)
  );
  // Queue 16 distinct IDs per source without retiring any response. Addresses
  // carry the expected source/ID independently of the DUT's output ID.
  always @(posedge clk) if (rst_n) begin
    if (mem_req.aw_valid && mem_rsp.aw_ready) begin
      if (mem_req.aw.id !== mem_req.aw.addr[13:6] || aw_seen[mem_req.aw.id])
        $fatal(1, "AW source tag/collision");
      aw_seen[mem_req.aw.id] = 1; aw_count++;
    end
    if (mem_req.ar_valid && mem_rsp.ar_ready) begin
      if (mem_req.ar.id !== mem_req.ar.addr[13:6] || ar_seen[mem_req.ar.id])
        $fatal(1, "AR source tag/collision");
      ar_seen[mem_req.ar.id] = 1; ar_count++;
    end
    if (mem_req.w_valid && mem_rsp.w_ready) begin
      if (!mem_req.w.last) $fatal(1, "W last");
      w_count++;
    end
  end
  task automatic send(int port);
    for (int id = 0; id < 16; id++) begin
      @(negedge clk);
      req[port].aw = '0;
      req[port].aw.id = 8'(id);
      req[port].aw.addr = 48'h80000000 + 48'((port * 128 + id) * 64);
      req[port].aw.burst = axi_pkg::BURST_INCR;
      req[port].aw.size = 6;
      req[port].aw_valid = 1;
      do @(posedge clk); while (!rsp[port].aw_ready);
      @(negedge clk); req[port].aw_valid = 0;
      req[port].w = '0; req[port].w.last = 1; req[port].w.strb = '1;
      req[port].w_valid = 1;
      do @(posedge clk); while (!rsp[port].w_ready);
      @(negedge clk); req[port].w_valid = 0;
      req[port].ar = '0;
      req[port].ar.id = 8'(id);
      req[port].ar.addr = req[port].aw.addr;
      req[port].ar.burst = axi_pkg::BURST_INCR;
      req[port].ar.size = 6; req[port].ar_valid = 1;
      do @(posedge clk); while (!rsp[port].ar_ready);
      @(negedge clk); req[port].ar_valid = 0;
    end
  endtask
  task automatic return_b(int port, int id);
    fork
      begin
        @(negedge clk);
        mem_rsp.b.id = 8'(port * 128 + id); mem_rsp.b.user = 2'(id);
        mem_rsp.b.resp = axi_pkg::resp_t'(id % 4); mem_rsp.b_valid = 1;
        do @(posedge clk); while (!mem_req.b_ready);
        @(negedge clk); mem_rsp.b_valid = 0;
      end
      begin
        wait (rsp[port].b_valid);
        repeat (3) begin
          @(negedge clk);
          if (!rsp[port].b_valid || rsp[1-port].b_valid || rsp[port].b.id !== 8'(id) ||
              rsp[port].b.user !== 2'(id) || rsp[port].b.resp !== axi_pkg::resp_t'(id % 4))
            $fatal(1, "B reorder, sideband or backpressure");
        end
        req[port].b_ready = 1;
        @(posedge clk); @(negedge clk); req[port].b_ready = 0;
      end
    join
  endtask
  task automatic return_r(int port, int id);
    fork
      begin
        @(negedge clk);
        mem_rsp.r.id = 8'(port * 128 + id); mem_rsp.r.user = 2'(id);
        mem_rsp.r.data = 512'(port * 128 + id); mem_rsp.r.last = 1;
        mem_rsp.r.resp = axi_pkg::resp_t'(id % 4); mem_rsp.r_valid = 1;
        do @(posedge clk); while (!mem_req.r_ready);
        @(negedge clk); mem_rsp.r_valid = 0;
      end
      begin
        wait (rsp[port].r_valid);
        repeat (4) begin
          @(negedge clk);
          if (!rsp[port].r_valid || rsp[1-port].r_valid || rsp[port].r.id !== 8'(id) ||
              rsp[port].r.user !== 2'(id) || rsp[port].r.resp !== axi_pkg::resp_t'(id % 4) ||
              rsp[port].r.data !== 512'(port * 128 + id) || !rsp[port].r.last)
            $fatal(1, "R reorder, sideband or backpressure");
        end
        req[port].r_ready = 1;
        @(posedge clk); @(negedge clk); req[port].r_ready = 0;
      end
    join
  endtask
  initial begin
    repeat (4) @(negedge clk); rst_n = 1;
    mem_rsp.aw_ready = 1; mem_rsp.w_ready = 1; mem_rsp.ar_ready = 1;
    fork send(0); send(1); join
    wait (aw_count == 32 && ar_count == 32 && w_count == 32);
    // Different IDs may retire in reverse order; B and R retire independently.
    for (int id = 15; id >= 0; id--) begin
      fork return_b(0, id); return_r(1, id); join
      fork return_b(1, id); return_r(0, id); join
    end
    repeat (5) @(negedge clk);
    if (rsp[0].b_valid || rsp[1].b_valid || rsp[0].r_valid || rsp[1].r_valid)
      $fatal(1, "Duplicate response");
    $display("PASS: shared DDR 32 outstanding reads + 32 writes, reverse IDs, sidebands, backpressure");
    $finish;
  end
  initial begin #100000; $fatal(1, "ID reorder watchdog"); end
endmodule
