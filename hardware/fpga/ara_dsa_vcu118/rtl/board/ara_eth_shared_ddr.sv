// SPDX-License-Identifier: SHL-0.51
// Both ports use the MIG UI clock. Address checking precedes MIG base truncation.
`include "axi/typedef.svh"
module ara_eth_shared_ddr #(
  parameter int AddrWidth = 48,
  parameter int UserWidth = 1,
  // Enable only when both input ID MSBs are structurally zero.
  parameter bit StaticIdPartition = 0,
  // The generated loader master has no ID pins; ara_eth_loader supplies zero.
  parameter bit LoaderSingleId = 0,
  parameter type req_t = logic,
  parameter type rsp_t = logic
) (
  input logic clk_i, rst_ni, lock_i,
  input req_t ara_req_i, loader_req_i,
  output rsp_t ara_rsp_o, loader_rsp_o,
  output req_t mem_req_o,
  input rsp_t mem_rsp_i,
  output logic [255:0] status_o
);
  `AXI_TYPEDEF_ALL(bus, logic[AddrWidth-1:0], logic[7:0], logic[511:0], logic[63:0], logic[UserWidth-1:0])
  `AXI_TYPEDEF_ALL(merged, logic[AddrWidth-1:0], logic[8:0], logic[511:0], logic[63:0], logic[UserWidth-1:0])
  req_t isolated_req;
  rsp_t isolated_rsp;
  req_t [1:0] decoded_req, mux_req;
  rsp_t [1:0] decoded_rsp, mux_rsp;
  merged_req_t merged_req;
  merged_resp_t merged_rsp;
  logic locked_q, isolated, bad_aw, bad_ar;
  logic bad_address_q;
  logic [31:0] aw_q, b_q, ar_q, rlast_q, errors_q;

  function automatic logic allowed(logic[AddrWidth-1:0] address,
                                    logic[7:0] len, logic[2:0] size,
                                    logic[1:0] burst);
    logic [11:0] remaining;
    logic fits_page;
    // len is the number of beats AFTER the first aligned beat. Compare with
    // remaining aligned slots, avoiding a full-address add/subtract chain.
    remaining = ~address[11:0];
    case (size)
      0: fits_page = len <= remaining;
      1: fits_page = len <= remaining[11:1];
      2: fits_page = len <= remaining[11:2];
      3: fits_page = len <= remaining[11:3];
      4: fits_page = len <= remaining[11:4];
      5: fits_page = len <= remaining[11:5];
      6: fits_page = len <= remaining[11:6];
      default: fits_page = 1'b0;
    endcase
    return address >= 64'h80000000 && address < 64'h100000000 &&
        fits_page && burst == axi_pkg::BURST_INCR;
  endfunction

  assign bad_aw = !allowed(isolated_req.aw.addr, isolated_req.aw.len,
                          isolated_req.aw.size, isolated_req.aw.burst) ||
                  isolated_req.aw.lock || |isolated_req.aw.atop;
  assign bad_ar = !allowed(isolated_req.ar.addr, isolated_req.ar.len,
                          isolated_req.ar.size, isolated_req.ar.burst) || isolated_req.ar.lock;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      locked_q <= 0; bad_address_q <= 0;
      aw_q <= 0; b_q <= 0; ar_q <= 0; rlast_q <= 0; errors_q <= 0;
    end else begin
      locked_q <= locked_q | lock_i;
      if ((isolated_req.aw_valid && isolated_rsp.aw_ready && bad_aw) ||
          (isolated_req.ar_valid && isolated_rsp.ar_ready && bad_ar)) bad_address_q <= 1;
      aw_q <= aw_q + 32'(loader_req_i.aw_valid && loader_rsp_o.aw_ready);
      b_q <= b_q + 32'(loader_rsp_o.b_valid && loader_req_i.b_ready);
      ar_q <= ar_q + 32'(loader_req_i.ar_valid && loader_rsp_o.ar_ready);
      rlast_q <= rlast_q + 32'(loader_rsp_o.r_valid && loader_req_i.r_ready && loader_rsp_o.r.last);
      errors_q <= errors_q + 32'(loader_rsp_o.b_valid && loader_req_i.b_ready && loader_rsp_o.b.resp[1]) +
          32'(loader_rsp_o.r_valid && loader_req_i.r_ready && loader_rsp_o.r.resp[1]);
    end
  end
  always_comb begin
    status_o = '0;
    status_o[31:0] = 32'h45544831;
    status_o[32] = locked_q;
    status_o[33] = isolated;
    status_o[34] = bad_address_q;
    status_o[35] = |errors_q;
    status_o[95:64] = aw_q; status_o[127:96] = b_q;
    status_o[159:128] = ar_q; status_o[191:160] = rlast_q;
    status_o[223:192] = errors_q;
  end

  axi_isolate #(.NumPending(32), .TerminateTransaction(0), .AtopSupport(0),
    .AxiAddrWidth(AddrWidth), .AxiDataWidth(512), .AxiIdWidth(8), .AxiUserWidth(UserWidth),
    .axi_req_t(req_t), .axi_resp_t(rsp_t)) i_isolate (
    .clk_i, .rst_ni, .slv_req_i(loader_req_i), .slv_resp_o(loader_rsp_o),
    .mst_req_o(isolated_req), .mst_resp_i(isolated_rsp),
    .isolate_i(locked_q), .isolated_o(isolated)
  );
  axi_demux #(.AxiIdWidth(8), .AtopSupport(0), .NoMstPorts(2), .MaxTrans(32),
    .AxiLookBits(LoaderSingleId ? 1 : 8), .aw_chan_t(bus_aw_chan_t), .w_chan_t(bus_w_chan_t),
    .b_chan_t(bus_b_chan_t), .ar_chan_t(bus_ar_chan_t), .r_chan_t(bus_r_chan_t),
    .axi_req_t(req_t), .axi_resp_t(rsp_t)) i_range (
    .clk_i, .rst_ni, .test_i(1'b0), .slv_req_i(isolated_req), .slv_resp_o(isolated_rsp),
    .slv_aw_select_i(bad_aw), .slv_ar_select_i(bad_ar),
    .mst_reqs_o(decoded_req), .mst_resps_i(decoded_rsp)
  );
  // synthesis translate_off
  always @(posedge clk_i) if (rst_ni && LoaderSingleId) begin
    assert (!(loader_req_i.aw_valid && |loader_req_i.aw.id))
      else $fatal(1, "Single-ID loader AW must have ID zero");
    assert (!(loader_req_i.ar_valid && |loader_req_i.ar.id))
      else $fatal(1, "Single-ID loader AR must have ID zero");
  end
  // synthesis translate_on
  axi_err_slv #(.AxiIdWidth(8), .axi_req_t(req_t), .axi_resp_t(rsp_t),
    .Resp(axi_pkg::RESP_DECERR), .ATOPs(0), .MaxTrans(4)) i_error (
    .clk_i, .rst_ni, .test_i(1'b0), .slv_req_i(decoded_req[1]), .slv_resp_o(decoded_rsp[1])
  );
  assign mux_req[0] = ara_req_i;
  assign ara_rsp_o = mux_rsp[0];
  assign mux_req[1] = decoded_req[0];
  assign decoded_rsp[0] = mux_rsp[1];
  axi_mux #(.SlvAxiIDWidth(8), .NoSlvPorts(2), .MaxWTrans(32),
    .SpillAw(1), .SpillW(1), .SpillB(1), .SpillAr(1), .SpillR(1),
    .slv_aw_chan_t(bus_aw_chan_t), .mst_aw_chan_t(merged_aw_chan_t), .w_chan_t(bus_w_chan_t),
    .slv_b_chan_t(bus_b_chan_t), .mst_b_chan_t(merged_b_chan_t),
    .slv_ar_chan_t(bus_ar_chan_t), .mst_ar_chan_t(merged_ar_chan_t),
    .slv_r_chan_t(bus_r_chan_t), .mst_r_chan_t(merged_r_chan_t),
    .slv_req_t(req_t), .slv_resp_t(rsp_t), .mst_req_t(merged_req_t), .mst_resp_t(merged_resp_t)
  ) i_mux (
    .clk_i, .rst_ni, .test_i(1'b0), .slv_reqs_i(mux_req), .slv_resps_o(mux_rsp),
    .mst_req_o(merged_req), .mst_resp_i(merged_rsp)
  );
  if (StaticIdPartition) begin : gen_static_ids
    // axi_mux inserts source in bit 8. Remove only the unused input bit 7;
    // response expansion restores it before the mux routes by source.
    always_comb begin
      mem_req_o = '0;
      mem_req_o.aw = bus_aw_chan_t'(merged_req.aw);
      mem_req_o.aw.id = {merged_req.aw.id[8], merged_req.aw.id[6:0]};
      mem_req_o.aw_valid = merged_req.aw_valid;
      mem_req_o.w = merged_req.w;
      mem_req_o.w_valid = merged_req.w_valid;
      mem_req_o.b_ready = merged_req.b_ready;
      mem_req_o.ar = bus_ar_chan_t'(merged_req.ar);
      mem_req_o.ar.id = {merged_req.ar.id[8], merged_req.ar.id[6:0]};
      mem_req_o.ar_valid = merged_req.ar_valid;
      mem_req_o.r_ready = merged_req.r_ready;
      merged_rsp = '0;
      merged_rsp.aw_ready = mem_rsp_i.aw_ready;
      merged_rsp.w_ready = mem_rsp_i.w_ready;
      merged_rsp.ar_ready = mem_rsp_i.ar_ready;
      merged_rsp.b = merged_b_chan_t'(mem_rsp_i.b);
      merged_rsp.b.id = {mem_rsp_i.b.id[7], 1'b0, mem_rsp_i.b.id[6:0]};
      merged_rsp.b_valid = mem_rsp_i.b_valid;
      merged_rsp.r = merged_r_chan_t'(mem_rsp_i.r);
      merged_rsp.r.id = {mem_rsp_i.r.id[7], 1'b0, mem_rsp_i.r.id[6:0]};
      merged_rsp.r_valid = mem_rsp_i.r_valid;
    end
    // synthesis translate_off
    always @(posedge clk_i) if (rst_ni) begin
      assert (!(ara_req_i.aw_valid && ara_req_i.aw.id[7])) else $fatal(1, "Ara AW ID exceeds partition");
      assert (!(ara_req_i.ar_valid && ara_req_i.ar.id[7])) else $fatal(1, "Ara AR ID exceeds partition");
      assert (!(loader_req_i.aw_valid && loader_req_i.aw.id[7])) else $fatal(1, "Loader AW ID exceeds partition");
      assert (!(loader_req_i.ar_valid && loader_req_i.ar.id[7])) else $fatal(1, "Loader AR ID exceeds partition");
    end
    // synthesis translate_on
  end else begin : gen_dynamic_ids
  axi_id_remap #(.AxiSlvPortIdWidth(9), .AxiSlvPortMaxUniqIds(16), .AxiMaxTxnsPerId(32),
    .AxiMstPortIdWidth(8), .slv_req_t(merged_req_t), .slv_resp_t(merged_resp_t),
    .mst_req_t(req_t), .mst_resp_t(rsp_t)) i_ids (
    .clk_i, .rst_ni, .slv_req_i(merged_req), .slv_resp_o(merged_rsp),
    .mst_req_o(mem_req_o), .mst_resp_i(mem_rsp_i)
  );
  end
endmodule
