// Isolated 2-KiB Q store. Aligned half-row writes come from the unchanged repacker.
module akv_q_store (
  input logic clk_i, rst_ni,
  input logic write_valid_i,
  input logic [2:0] write_slot_i,
  input logic [7:0] write_offset_i,
  input logic [127:0] write_data_i,
  input logic read_i,
  input logic [2:0] read_slot_i,
  input logic [3:0] read_word_i,
  output logic [255:0] read_data_o
);
  localparam int NumWords = 64;
  logic req, we;
  logic [5:0] addr;
  logic [255:0] wdata;
  logic [31:0] be;

  always_comb begin
    req = write_valid_i || read_i;
    we = write_valid_i;
    addr = {read_slot_i, read_word_i[2:0]};
    wdata = '0;
    be = '0;
    if (write_valid_i) begin
      addr = {write_slot_i, write_offset_i[7:5]};
      if (write_offset_i[4]) begin
        wdata[255:128] = write_data_i;
        be[31:16] = '1;
      end else begin
        wdata[127:0] = write_data_i;
        be[15:0] = '1;
      end
    end
  end

`ifndef TARGET_SRAM_MC
  tc_sram #(.NumWords(NumWords), .DataWidth(256), .NumPorts(1), .Latency(1)) i_q_sram (
    .clk_i, .rst_ni, .req_i(req), .we_i(we), .addr_i(addr),
    .wdata_i(wdata), .be_i(be), .rdata_o(read_data_o)
  );
`else
  wire [255:0] bweb;
  for (genvar byte_lane = 0; byte_lane < 32; byte_lane++) begin : gen_byte
    assign bweb[byte_lane*8 +: 8] = {8{!(we && be[byte_lane])}};
  end
  TS1N28HPCPUHDSVTB64X256M1SWBSO i_q_sram (
    .SLP(1'b0), .SD(1'b0), .CLK(clk_i), .CEB(!req), .WEB(!we),
    .CEBM(1'b1), .WEBM(1'b1), .A(addr), .D(wdata), .BWEB(bweb),
    .AM('0), .DM('0), .BWEBM('1), .BIST(1'b0), .RTSEL(2'b01),
    .WTSEL(2'b00), .Q(read_data_o)
  );
`endif

`ifndef SYNTHESIS
  always @(posedge clk_i) if (rst_ni) begin
    assert (!(write_valid_i && read_i)) else $fatal(1, "Q_STORE_CONFLICT");
    if (write_valid_i)
      assert (write_offset_i[3:0] == 0) else $fatal(1, "Q_STORE_ALIGNMENT");
    if (read_i)
      assert (read_word_i < 8) else $fatal(1, "Q_STORE_WORD");
  end
`endif
endmodule
