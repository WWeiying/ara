// Independent boundary checks in addition to the unchanged actual SoC UVM AXI monitor.
module reader_fault_boundary_probe #(
  parameter type axi_req_t=logic, axi_resp_t=logic
) (
  input logic clk_i, rst_ni, block_ar, block_r, inject_resp,
  input axi_req_t slv_req_i, cut_req,
  input axi_resp_t slv_resp_o, cut_resp
);
  property held_ar;
    @(posedge clk_i) disable iff (!rst_ni)
      slv_req_i.ar_valid && !slv_resp_o.ar_ready |=>
      slv_req_i.ar_valid && $stable(slv_req_i.ar);
  endproperty
  property held_r;
    @(posedge clk_i) disable iff (!rst_ni)
      slv_resp_o.r_valid && !slv_req_i.r_ready |=>
      slv_resp_o.r_valid && $stable(slv_resp_o.r);
  endproperty
  assert property (held_ar) else $fatal(1,"READER_FAULT_ERROR upstream AR stability");
  assert property (held_r) else $fatal(1,"READER_FAULT_ERROR upstream R stability");
  always @(posedge clk_i) if (rst_ni) begin
    automatic axi_req_t expected_req = slv_req_i;
    automatic axi_resp_t expected_rsp = cut_resp;
    expected_req.ar_valid = slv_req_i.ar_valid && !block_ar;
    expected_req.r_ready = slv_req_i.r_ready && !block_r;
    expected_rsp.ar_ready = cut_resp.ar_ready && !block_ar;
    expected_rsp.r_valid = cut_resp.r_valid && !block_r;
    if (inject_resp) expected_rsp.r.resp = axi_pkg::RESP_SLVERR;
    if (cut_req !== expected_req || slv_resp_o !== expected_rsp ||
        (slv_req_i.ar_valid && slv_resp_o.ar_ready) !==
        (cut_req.ar_valid && cut_resp.ar_ready) ||
        (slv_resp_o.r_valid && slv_req_i.r_ready) !==
        (cut_resp.r_valid && cut_req.r_ready))
      $fatal(1,"READER_FAULT_ERROR interposer changed payload/side-channel/acceptance");
  end
endmodule

bind reader_fault_cut reader_fault_boundary_probe #(
  .axi_req_t(axi_req_t), .axi_resp_t(axi_resp_t)
) i_boundary_probe (.*);
