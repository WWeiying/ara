`timescale 1ns/1ps

module ddr_r_cut_tb;
  typedef struct packed {
    logic [7:0] id;
    logic [511:0] data;
    logic [1:0] resp;
    logic last;
    logic user;
  } r_t;
  typedef struct packed {
    logic [7:0] aw;
    logic aw_valid;
    logic [7:0] w;
    logic w_valid;
    logic b_ready;
    logic [7:0] ar;
    logic ar_valid;
    logic r_ready;
  } req_t;
  typedef struct packed {
    logic aw_ready;
    logic w_ready;
    logic [7:0] b;
    logic b_valid;
    logic ar_ready;
    r_t r;
    logic r_valid;
  } resp_t;

  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;
  req_t cdc_req, mig_req;
  resp_t cdc_rsp, mig_rsp;

  axi_cut #(
    .Bypass(1'b1), .BypassR(1'b0),
    .aw_chan_t(logic [7:0]), .w_chan_t(logic [7:0]),
    .b_chan_t(logic [7:0]), .ar_chan_t(logic [7:0]),
    .r_chan_t(r_t), .axi_req_t(req_t), .axi_resp_t(resp_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n),
    .slv_req_i(cdc_req), .slv_resp_o(cdc_rsp),
    .mst_req_o(mig_req), .mst_resp_i(mig_rsp)
  );

  function automatic r_t beat(input int idx);
    r_t result;
    result.id = 8'(idx % 5);
    for (int k = 0; k < 16; k++)
      result.data[k*32+:32] = 32'(idx * 37 + k);
    result.resp = 2'(idx % 3);
    result.last = (idx % 7 == 6);
    result.user = 1'(idx % 2);
    return result;
  endfunction

  initial begin : test
    int sent = 0;
    int received = 0;
    bit ready_before;
    cdc_req = '0;
    mig_rsp = '0;
    repeat (4) @(negedge clk);
    rst_n = 1;
    for (int cycle = 0; cycle < 1000 && received < 128; cycle++) begin
      @(negedge clk);
      cdc_req.aw = 8'(cycle);
      cdc_req.aw_valid = 1'(cycle % 2);
      cdc_req.w = 8'(cycle ^ 8'h65);
      cdc_req.w_valid = 1'(cycle % 3);
      cdc_req.b_ready = 1'(cycle % 4);
      cdc_req.ar = 8'(cycle ^ 8'h96);
      cdc_req.ar_valid = 1'(cycle % 5);
      mig_rsp.aw_ready = 1'(cycle % 3);
      mig_rsp.w_ready = 1'(cycle % 4);
      mig_rsp.b = 8'(cycle ^ 8'hac);
      mig_rsp.b_valid = 1'(cycle % 2);
      mig_rsp.ar_ready = 1'(cycle % 5);
      mig_rsp.r_valid = (sent < 128);
      mig_rsp.r = beat(sent);

      cdc_req.r_ready = 0;
      #1;
      ready_before = mig_req.r_ready;
      cdc_req.r_ready = 1;
      #1;
      if (mig_req.r_ready !== ready_before)
        $fatal(1, "MIG RREADY has a combinational path from CDC RREADY");
      cdc_req.r_ready = (cycle < 24 || cycle % 53 >= 18) && (cycle % 7 != 0);
      #1;
      if (mig_req.aw !== cdc_req.aw || mig_req.aw_valid !== cdc_req.aw_valid ||
          mig_req.w !== cdc_req.w || mig_req.w_valid !== cdc_req.w_valid ||
          mig_req.ar !== cdc_req.ar || mig_req.ar_valid !== cdc_req.ar_valid ||
          mig_req.b_ready !== cdc_req.b_ready ||
          cdc_rsp.aw_ready !== mig_rsp.aw_ready ||
          cdc_rsp.w_ready !== mig_rsp.w_ready ||
          cdc_rsp.ar_ready !== mig_rsp.ar_ready ||
          cdc_rsp.b !== mig_rsp.b || cdc_rsp.b_valid !== mig_rsp.b_valid)
        $fatal(1, "A bypassed AXI channel changed");
      @(posedge clk);
      if (cdc_rsp.r_valid && cdc_req.r_ready) begin
        if (cdc_rsp.r !== beat(received))
          $fatal(1, "R beat %0d changed or reordered", received);
        received++;
      end
      if (mig_rsp.r_valid && mig_req.r_ready) sent++;
    end
    if (sent != 128 || received != 128)
      $fatal(1, "Incomplete R transfer sent=%0d received=%0d", sent, received);
    $display("PASS DDR R cut: 128 ordered 512-bit beats with stalls and independent RREADY");
    $finish;
  end
endmodule
