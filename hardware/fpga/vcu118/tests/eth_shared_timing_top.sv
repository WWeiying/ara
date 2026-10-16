`include "axi/typedef.svh"
package eth_shared_timing_pkg;
  `AXI_TYPEDEF_ALL(bus, logic[47:0], logic[7:0], logic[511:0], logic[63:0], logic[0:0])
endpackage

module eth_shared_timing_top #(
  parameter bit LoaderAdapterConstants = 0,
  parameter bit StaticIdPartition = 0,
  parameter bit LoaderSingleId = 0
) (
  input logic clk_i, rst_ni, lock_i,
  input eth_shared_timing_pkg::bus_req_t ara_req_i, loader_req_i,
  output eth_shared_timing_pkg::bus_resp_t ara_rsp_o, loader_rsp_o,
  output eth_shared_timing_pkg::bus_req_t mem_req_o,
  input eth_shared_timing_pkg::bus_resp_t mem_rsp_i,
  output logic [255:0] status_o
);
  eth_shared_timing_pkg::bus_req_t loader_request;
  always_comb begin
    loader_request = loader_req_i;
    if (LoaderAdapterConstants) begin
      // Match ara_eth_loader, without assuming anything about DMA burst sizes.
      loader_request.aw.addr[47:32] = '0;
      loader_request.ar.addr[47:32] = '0;
      loader_request.aw.id = '0;
      loader_request.ar.id = '0;
      loader_request.aw.atop = '0;
      loader_request.aw.region = '0;
      loader_request.ar.region = '0;
      loader_request.aw.user = '0;
      loader_request.ar.user = '0;
      loader_request.w.user = '0;
    end
  end
  ara_eth_shared_ddr #(.StaticIdPartition(StaticIdPartition), .LoaderSingleId(LoaderSingleId), .req_t(eth_shared_timing_pkg::bus_req_t),
    .rsp_t(eth_shared_timing_pkg::bus_resp_t)) dut (.loader_req_i(loader_request), .*);
endmodule
