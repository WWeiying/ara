// Standalone unchanged wt_dcache_ctrl plus an explicit environment model.
// No CPU/PTW, full cache memory, missunit, or AXI adapter is instantiated.
// A future local VDB MUST NOT be admitted to the system population.
module cache_port1_refill_successor_fixture;
  timeunit 1ns;
  timeprecision 1ps;
  function automatic config_pkg::cva6_user_cfg_t fixture_config();
    config_pkg::cva6_user_cfg_t c = cva6_config_pkg::cva6_cfg;
    c.NrCachedRegionRules = 1;
    c.CachedRegionAddrBase = {64'h80000000};
    c.CachedRegionLength = {64'h40000000};
    return c;
  endfunction
  localparam config_pkg::cva6_cfg_t C = build_config_pkg::build_config(fixture_config());
  localparam logic [63:0] A = 64'h80010000, B = 64'h80020000;
  localparam logic [63:0] B_WORD = 64'h13579bdf2468ace0;
  typedef struct packed {
    logic [C.DCACHE_INDEX_WIDTH-1:0] address_index;
    logic [C.DCACHE_TAG_WIDTH-1:0] address_tag;
    logic [C.XLEN-1:0] data_wdata;
    logic [C.DCACHE_USER_WIDTH-1:0] data_wuser;
    logic data_req, data_we;
    logic [C.XLEN/8-1:0] data_be;
    logic [1:0] data_size;
    logic [C.DcacheIdWidth-1:0] data_id;
    logic kill_req, tag_valid;
  } req_t;
  typedef struct packed {
    logic data_gnt, data_rvalid;
    logic [C.DcacheIdWidth-1:0] data_rid;
    logic [C.XLEN-1:0] data_rdata;
    logic [C.DCACHE_USER_WIDTH-1:0] data_ruser;
  } rsp_t;
  logic clk = 0, rst_n = 0;
  always #0.5 clk = ~clk;
  req_t req;
  rsp_t rsp;
  logic rd_ack, rd_req, miss_req, miss_ack, miss_return;
  logic a_last_valid, return_valid, a_mshr_valid, load_ack;
  logic [1:0] mshr_owner;
  logic [C.PLEN-1:0] miss_addr;
  // This models exactly the one return-valid register in wt_axi_adapter,
  // not the latency through the SoC AXI fabric and not an implemented PTW.
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) return_valid <= 0;
    else return_valid <= a_last_valid;
  end
  assign load_ack = return_valid && a_mshr_valid && mshr_owner == 0;
  assign rd_ack = rd_req && !load_ack;
  wt_dcache_ctrl #(
    .CVA6Cfg(C), .DCACHE_CL_IDX_WIDTH(C.DCACHE_INDEX_WIDTH-C.DCACHE_OFFSET_WIDTH),
    .dcache_req_i_t(req_t), .dcache_req_o_t(rsp_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .cache_en_i(1'b1), .stall_i(1'b0),
    .busy_o(), .req_port_i(req), .req_port_o(rsp),
    .miss_req_o(miss_req), .miss_ack_i(miss_ack), .miss_we_o(),
    .miss_wdata_o(), .miss_wuser_o(), .miss_vld_bits_o(),
    .miss_paddr_o(miss_addr), .miss_nc_o(), .miss_size_o(), .miss_id_o(),
    .miss_replay_i(1'b0), .miss_rtrn_vld_i(miss_return), .wr_cl_vld_i(load_ack),
    .rd_tag_o(), .rd_idx_o(), .rd_off_o(), .rd_req_o(rd_req), .rd_tag_only_o(),
    .rd_ack_i(rd_ack), .rd_data_i(B_WORD), .rd_user_i('0),
    .rd_vld_bits_i('0), .rd_hit_oh_i('0)
  );
  cache_port1_refill_successor_probe probe (
    .clk, .rst_n, .state_q(dut.state_q), .state_d(dut.state_d),
    .data_req(req.data_req), .tag_valid(req.tag_valid), .kill_req(req.kill_req),
    .rd_ack, .rd_ack_q(dut.rd_ack_q), .wr_cl_vld(load_ack), .any_hit(1'b0),
    .miss_req, .miss_ack, .miss_return, .data_gnt(rsp.data_gnt),
    .data_rvalid(rsp.data_rvalid), .data_rdata(rsp.data_rdata),
    .data_rid(8'(rsp.data_rid)), .mshr_valid(a_mshr_valid), .mshr_owner,
    .axi_rvalid(a_last_valid), .axi_rready(1'b1), .axi_rlast(a_last_valid),
    .axi_rid(8'd1), .return_valid, .load_ack, .a_addr(A), .b_addr(B)
  );
  task automatic edge_check(input logic [2:0] before_state, after_state);
    @(posedge clk);
    if (dut.state_q !== before_state || dut.state_d !== after_state)
      $fatal(1, "Unexpected controller transition");
  endtask
  initial begin
    req = '0;
    miss_ack = 0; miss_return = 0; a_last_valid = 0;
    a_mshr_valid = 0; mshr_owner = 0;
    if (C.XLEN != 64 || C.DCACHE_OFFSET_WIDTH != 5) $fatal(1, "Wrong fixture geometry");
    repeat (3) @(negedge clk);
    rst_n = 1;
    // Prepared external context: accepted A read owned by port0.
    // Its last AXI beat is released at B grant, never by forcing dut state.
    a_mshr_valid = 1;
    req.address_index = C.DCACHE_INDEX_WIDTH'(B);
    req.address_tag = C.DCACHE_TAG_WIDTH'(B >> C.DCACHE_INDEX_WIDTH);
    req.data_size = 2'b11; req.data_be = '1; req.data_id = 1;
    req.data_req = 1; a_last_valid = 1;
    edge_check(0, 1); // C0 B grant and last-A handshake
    @(negedge clk);
    req.data_req = 0; req.tag_valid = 1; a_last_valid = 0;
    edge_check(1, 6); // C1 registered A return masks SRAM grant
    @(negedge clk);
    req.tag_valid = 0; a_mshr_valid = 0;
    edge_check(6, 7); // C2 normal replay SRAM grant
    @(negedge clk);
    edge_check(7, 2); // C3 cold B misses using saved tag
    @(negedge clk);
    miss_ack = 1;
    edge_check(2, 3);
    if (miss_addr !== C.PLEN'(B)) $fatal(1, "Saved B physical address corrupted");
    @(negedge clk);
    miss_ack = 0; miss_return = 1; mshr_owner = 1; a_mshr_valid = 1;
    edge_check(3, 0);
    if (!rsp.data_rvalid || rsp.data_rdata !== B_WORD || rsp.data_rid != 1)
      $fatal(1, "B completion/data/id failed");
    @(negedge clk);
    $display("CACHE_PORT1_LOCAL_FIXTURE_PASS_NOT_SYSTEM_ADMISSION");
    $finish;
  end
  initial begin
    #32;
    $fatal(1, "Standalone fixture timeout");
  end
endmodule
