// Passive, pre-edge samples. Not injected into the frozen executable.
module cache_port1_refill_successor_probe (
  input logic clk, rst_n,
  input logic [2:0] state_q, state_d,
  input logic data_req, tag_valid, kill_req, rd_ack, rd_ack_q,
  input logic wr_cl_vld, any_hit, miss_req, miss_ack, miss_return,
  input logic data_gnt, data_rvalid,
  input logic [63:0] data_rdata,
  input logic [7:0] data_rid,
  input logic mshr_valid,
  input logic [1:0] mshr_owner,
  input logic axi_rvalid, axi_rready, axi_rlast,
  input logic [7:0] axi_rid,
  input logic return_valid, load_ack,
  input logic [63:0] a_addr, b_addr
);
  integer fd, cycle;
  string filename;
  initial begin
    cycle = 0;
    if (!$value$plusargs("CACHE_PORT1_REFILL_TRACE=%s", filename))
      $fatal(1, "Explicit independent trace path required");
    fd = $fopen(filename, "w");
    if (!fd) $fatal(1, "Cannot open cache port1 trace");
    $fwrite(fd, "cycle,rst_n,state_q,state_d,data_req,tag_valid,kill_req,rd_ack,rd_ack_q,wr_cl_vld,any_hit,miss_req,miss_ack,miss_return,data_gnt,data_rvalid,data_rdata,data_rid,mshr_valid,mshr_owner,axi_rvalid,axi_rready,axi_rlast,axi_rid,return_valid,load_ack,a_addr,b_addr\n");
  end
  always @(posedge clk) begin
    if (rst_n) begin
      if (cycle >= 32) $fatal(1, "Focused trace exceeded 32-cycle bound");
      $fwrite(fd, "%0d,%b,%0d,%0d,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%0d,%0d,%b,%0d,%b,%b,%b,%0d,%b,%b,%0d,%0d\n",
        cycle, rst_n, state_q, state_d, data_req, tag_valid, kill_req,
        rd_ack, rd_ack_q, wr_cl_vld, any_hit, miss_req, miss_ack,
        miss_return, data_gnt, data_rvalid, data_rdata, data_rid,
        mshr_valid, mshr_owner, axi_rvalid, axi_rready, axi_rlast,
        axi_rid, return_valid, load_ack, a_addr, b_addr);
      cycle = cycle + 1;
      $fflush(fd);
    end
  end
  final $fclose(fd);
endmodule
