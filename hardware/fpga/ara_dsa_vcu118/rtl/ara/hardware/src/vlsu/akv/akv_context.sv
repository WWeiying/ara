// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Six-KiB AKV payload store. Adjacent 256-bit logical rows are placed in
// separate banks, so one compact 128-bit AXI beat may cross a row boundary
// without requiring two accesses to either single-port bank.
module akv_context
  import akv_pkg::*;
(
    input logic clk_i,
    input logic rst_ni,

    input  logic         write_valid_i,
    input  logic [  4:0] write_slot_i,
    input  logic [  7:0] write_offset_i,
    input  logic [127:0] write_data_i,
    input  logic [ 15:0] write_strb_i,
    output logic         write_busy_o,

    input  logic         replay_read_i,
    input  logic [  4:0] replay_slot_i,
    input  logic [  3:0] replay_word_i,
    output logic [255:0] replay_data_o
);

  localparam int unsigned BankCount = 2;
  localparam int unsigned RowBytes = 32;
  localparam int unsigned SlotBytes = AkvMaxHeadDim * 2;
  localparam int unsigned LogicalRows = AkvContextBytes / RowBytes;
  localparam int unsigned BankDepth = LogicalRows / BankCount;
  localparam int unsigned BankAddrWidth = $clog2(BankDepth);
  localparam int unsigned MacroAddrWidth = 6;
  localparam int unsigned MacroDepth = 1 << MacroAddrWidth;
  localparam int unsigned MacroCount = (BankDepth + MacroDepth - 1) / MacroDepth;

  logic [BankCount-1:0] bank_req;
  logic [BankCount-1:0] bank_we;
  logic [BankAddrWidth-1:0] bank_addr[BankCount];
  logic [255:0] bank_wdata[BankCount];
  logic [31:0] bank_be[BankCount];
  logic [255:0] bank_rdata[BankCount];
  logic replay_bank;
  logic replay_bank_q;

  logic write_stage0_valid_q;
  logic [4:0] write_stage0_slot_q;
  logic [7:0] write_stage0_offset_q;
  logic [127:0] write_stage0_data_q;
  logic [15:0] write_stage0_strb_q;
  logic [BankCount-1:0] write_bank_req_d, write_bank_req_q;
  logic [BankAddrWidth-1:0] write_bank_addr_d[BankCount];
  logic [BankAddrWidth-1:0] write_bank_addr_q[BankCount];
  logic [255:0] write_bank_data_d[BankCount];
  logic [255:0] write_bank_data_q[BankCount];
  logic [31:0] write_bank_be_d[BankCount];
  logic [31:0] write_bank_be_q[BankCount];

  assign write_busy_o = write_valid_i || write_stage0_valid_q || |write_bank_req_q;

  always_comb begin : route_staged_write
    automatic logic [383:0] shifted_data;
    automatic logic [47:0] shifted_strb;
    automatic logic [7:0] low_row;
    automatic logic [7:0] high_row;
    automatic int unsigned low_bank;
    automatic int unsigned high_bank;

    write_bank_req_d = '0;
    for (int unsigned bank = 0; bank < BankCount; bank++) begin
      write_bank_addr_d[bank] = '0;
      write_bank_data_d[bank] = '0;
      write_bank_be_d[bank]   = '0;
    end

    // AKV v1 carries only F16 payloads and validates every base and stride as
    // halfword-aligned. Express that invariant here to halve the alignment
    // mux instead of synthesizing an unreachable byte-granular shift network.
    shifted_data = {256'b0, write_stage0_data_q} << (unsigned'(write_stage0_offset_q[4:1]) * 16);
    shifted_strb = {32'b0, write_stage0_strb_q} << (unsigned'(write_stage0_offset_q[4:1]) * 2);
    low_row   = write_stage0_valid_q ?
                {write_stage0_slot_q, 3'b000} + {5'b0, write_stage0_offset_q[7:5]} : '0;
    high_row = low_row + 1'b1;
    low_bank = low_row[0];
    high_bank = high_row[0];

    if (write_stage0_valid_q && |shifted_strb[31:0]) begin
      write_bank_req_d[low_bank]  = 1'b1;
      write_bank_addr_d[low_bank] = BankAddrWidth'(low_row[7:1]);
      write_bank_data_d[low_bank] = shifted_data[255:0];
      write_bank_be_d[low_bank]   = shifted_strb[31:0];
    end
    if (write_stage0_valid_q && |shifted_strb[47:32]) begin
      write_bank_req_d[high_bank] = 1'b1;
      write_bank_addr_d[high_bank] = BankAddrWidth'(high_row[7:1]);
      write_bank_data_d[high_bank][127:0] = shifted_data[383:256];
      write_bank_be_d[high_bank][15:0] = shifted_strb[47:32];
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      write_stage0_valid_q <= 1'b0;
      write_bank_req_q <= '0;
    end else begin
      write_stage0_valid_q <= write_valid_i;
      if (write_valid_i) begin
        write_stage0_slot_q   <= write_slot_i;
        write_stage0_offset_q <= write_offset_i;
        write_stage0_data_q   <= write_data_i;
        write_stage0_strb_q   <= write_strb_i;
      end

      write_bank_req_q <= write_bank_req_d;
      for (int unsigned bank = 0; bank < BankCount; bank++) begin
        if (write_bank_req_d[bank]) begin
          write_bank_addr_q[bank] <= write_bank_addr_d[bank];
          write_bank_data_q[bank] <= write_bank_data_d[bank];
          write_bank_be_q[bank]   <= write_bank_be_d[bank];
        end
      end
    end
  end

  always_comb begin : steer_context_banks
    automatic logic [7:0] logical_row;

    bank_req = '0;
    bank_we = '0;
    replay_bank = 1'b0;
    for (int unsigned index = 0; index < BankCount; index++) begin
      bank_addr[index] = '0;
      bank_wdata[index] = '0;
      bank_be[index] = '0;
    end

    if (|write_bank_req_q) begin
      bank_req = write_bank_req_q;
      bank_we  = write_bank_req_q;
      for (int unsigned bank = 0; bank < BankCount; bank++) begin
        bank_addr[bank] = write_bank_addr_q[bank];
        bank_wdata[bank] = write_bank_data_q[bank];
        bank_be[bank] = write_bank_be_q[bank];
      end
    end else if (replay_read_i) begin
      logical_row = {replay_slot_i, 3'b000} + {4'b0, replay_word_i};
      replay_bank = logical_row[0];
      bank_req[replay_bank] = 1'b1;
      bank_addr[replay_bank] = BankAddrWidth'(logical_row[7:1]);
    end
  end

`ifndef TARGET_SRAM_MC
  for (genvar bank = 0; bank < BankCount; bank++) begin : gen_context_bank
    tc_sram #(
        .NumWords (BankDepth),
        .DataWidth(256),
        .NumPorts (1),
        .Latency  (1)
    ) i_context_sram (
        .clk_i,
        .rst_ni,
        .req_i  (bank_req[bank]),
        .we_i   (bank_we[bank]),
        .addr_i (bank_addr[bank]),
        .wdata_i(bank_wdata[bank]),
        .be_i   (bank_be[bank]),
        .rdata_o(bank_rdata[bank])
    );
  end
`else
  logic [255:0] macro_q[BankCount][MacroCount];
  logic [$clog2(MacroCount)-1:0] macro_read_select_q[BankCount];

  for (genvar bank = 0; bank < BankCount; bank++) begin : gen_context_bank
    logic [MacroCount-1:0] macro_req;
    logic [MacroCount-1:0] macro_we;
    logic [MacroAddrWidth-1:0] macro_addr[MacroCount];
    logic [255:0] macro_wdata[MacroCount];
    logic [255:0] macro_bweb[MacroCount];

    always_comb begin : steer_macros
      automatic int unsigned selected_macro;
      automatic int unsigned selected_row;
      macro_req = '0;
      macro_we  = '0;
      for (int unsigned macro = 0; macro < MacroCount; macro++) begin
        macro_addr[macro]  = '0;
        macro_wdata[macro] = '0;
        macro_bweb[macro]  = '1;
      end
      if (bank_req[bank]) begin
        selected_macro = unsigned'(bank_addr[bank]) / MacroDepth;
        selected_row = unsigned'(bank_addr[bank]) % MacroDepth;
        macro_req[selected_macro] = 1'b1;
        macro_we[selected_macro] = bank_we[bank];
        macro_addr[selected_macro] = MacroAddrWidth'(selected_row);
        if (bank_we[bank]) begin
          macro_wdata[selected_macro] = bank_wdata[bank];
          for (int unsigned byte_lane = 0; byte_lane < RowBytes; byte_lane++) begin
            if (bank_be[bank][byte_lane]) macro_bweb[selected_macro][byte_lane*8+:8] = '0;
          end
        end
      end
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) macro_read_select_q[bank] <= '0;
      else if (bank_req[bank] && !bank_we[bank])
        macro_read_select_q[bank] <= $clog2(MacroCount)'(unsigned'(bank_addr[bank]) / MacroDepth);
    end

    assign bank_rdata[bank] = macro_q[bank][macro_read_select_q[bank]];

    for (genvar macro = 0; macro < MacroCount; macro++) begin : gen_macro
      TS1N28HPCPUHDSVTB64X256M1SWBSO i_context_sram (
          .SLP  (1'b0),
          .SD   (1'b0),
          .CLK  (clk_i),
          .CEB  (!macro_req[macro]),
          .WEB  (!macro_we[macro]),
          .CEBM (1'b1),
          .WEBM (1'b1),
          .A    (macro_addr[macro]),
          .D    (macro_wdata[macro]),
          .BWEB (macro_bweb[macro]),
          .AM   ('0),
          .DM   ('0),
          .BWEBM('1),
          .BIST (1'b0),
          .RTSEL(2'b01),
          .WTSEL(2'b00),
          .Q    (macro_q[bank][macro])
      );
    end
  end
`endif

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) replay_bank_q <= 1'b0;
    else if (replay_read_i) replay_bank_q <= replay_bank;
  end

  assign replay_data_o = bank_rdata[replay_bank_q];

`ifndef SYNTHESIS
  initial begin
    assert (AkvContextBytes == 6144);
    assert (LogicalRows == 192);
    assert (BankDepth == 96);
    assert (MacroCount == 2);
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni && write_valid_i) begin
      assert (unsigned'(write_slot_i) < AkvMaxQRows + 2 * AkvTileTokens);
      assert (!write_offset_i[0]);
      for (int unsigned byte_lane = 0; byte_lane < 16; byte_lane++) begin
        if (write_strb_i[byte_lane]) assert (unsigned'(write_offset_i) + byte_lane < SlotBytes);
      end
    end
    if (rst_ni && replay_read_i) begin
      assert (!write_busy_o);
      assert (unsigned'(replay_slot_i) < AkvMaxQRows + 2 * AkvTileTokens);
      assert (unsigned'(replay_word_i) < SlotBytes / RowBytes);
    end
  end
`endif

endmodule : akv_context
