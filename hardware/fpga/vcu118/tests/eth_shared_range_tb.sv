module tb;
  import eth_shared_timing_pkg::*;
  bus_req_t ara_req_i, loader_req_i, mem_req_o;
  bus_resp_t ara_rsp_o, loader_rsp_o, mem_rsp_i;
  logic [255:0] status_o;
  logic clk_i = 0, rst_ni = 0, lock_i = 0;
  eth_shared_timing_top top (.*);
  longint unsigned checks = 0;

  function automatic logic reference_allowed(logic[47:0] address,
      logic[7:0] len, logic[2:0] size, logic[1:0] burst);
    logic [64:0] aligned, limit;
    aligned = 65'(address) & ~((65'd1 << size) - 1);
    limit = aligned + ((65'(len) + 1) << size);
    return address >= 64'h80000000 && limit <= 65'h100000000 &&
        size <= 6 && burst == axi_pkg::BURST_INCR &&
        (65'(address) >> 12) == ((limit - 1) >> 12);
  endfunction

  task automatic check(input logic[47:0] address, input logic[7:0] len,
      input logic[2:0] size, input logic[1:0] burst);
    logic expected, actual;
    expected = reference_allowed(address, len, size, burst);
    actual = top.dut.allowed(address, len, size, burst);
    if (actual !== expected)
      $fatal(1, "range mismatch addr=%h len=%d size=%d burst=%d got=%b want=%b",
             address, len, size, burst, actual, expected);
    checks++;
  endtask

  initial begin
    ara_req_i = '0; loader_req_i = '0; mem_rsp_i = '0;
    // Every page offset, AxLEN and AxSIZE at both legal window boundaries,
    // including unaligned requests, exact page ends and illegal size 7.
    for (int offset = 0; offset < 4096; offset++)
      for (int len = 0; len < 256; len++)
        for (int size = 0; size < 8; size++) begin
          check(48'h80000000 + offset, 8'(len), 3'(size), 1);
          check(48'hfffff000 + offset, 8'(len), 3'(size), 1);
        end
    for (int burst = 0; burst < 4; burst++)
      for (int size = 0; size < 8; size++)
        for (int len = 0; len < 256; len++) begin
          check(48'h7fffffff, 8'(len), 3'(size), 2'(burst));
          check(48'h100000000, 8'(len), 3'(size), 2'(burst));
          check(48'hffffffffffff, 8'(len), 3'(size), 2'(burst));
          check(48'h81234000, 8'(len), 3'(size), 2'(burst));
        end
    for (int i = 0; i < 100000; i++) begin
      check({16'($urandom), $urandom}, 8'($urandom), 3'($urandom), 2'($urandom));
      check(48'h80000000 | 48'($urandom & 32'h7fffffff),
            8'($urandom), 3'($urandom), 2'($urandom));
    end
    $display("PASS: shared DDR range equivalence checks=%0d", checks);
    $finish;
  end
endmodule
