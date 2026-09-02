// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// AKV-v2 row-major K/V store with an eight-bank token-axis read view.  Token
// index selects the bank; token group and D-axis word select the row.  A row
// replay therefore uses one bank, while a K-column gather reads eight tokens
// in parallel without transposing the incoming model payload.
module akv_v2_context
  import akv_pkg::*;
(
    input  logic         clk_i,
    input  logic         rst_ni,

    input  logic         write_valid_i,
    input  akv_stream_e  write_stream_i,
    input  logic [5:0]   write_token_i,
    input  logic [7:0]   write_offset_i,
    input  logic [127:0] write_data_i,
    input  logic [15:0]  write_strb_i,
    output logic         write_busy_o,

    input  logic         row_read_i,
    input  akv_stream_e  row_stream_i,
    input  logic [5:0]   row_token_i,
    input  logic [3:0]   row_word_i,
    output logic [255:0] row_data_o,

    input  logic          column_start_i,
    input  akv_stream_e   column_stream_i,
    input  logic [6:0]    column_dimension_i,
    input  logic [2:0]    column_count_i,
    input  logic [6:0]    column_token_count_i,
    output logic          column_busy_o,
    output logic          column_valid_o,
    output logic [3:0][1023:0] column_data_o,
    output logic          column_bank_cycle_o,
    output logic          conflict_o
);

  localparam int unsigned BankCount = AkvV2TokenBanks;
  localparam int unsigned WordsPerSlot = AkvMaxHeadDim * 2 / 32;
  localparam int unsigned TokenGroups = AkvV2TileTokens / BankCount;
  localparam int unsigned StreamRows = TokenGroups * WordsPerSlot;
  localparam int unsigned BankDepth = 2 * StreamRows;
  localparam int unsigned BankAddrWidth = $clog2(BankDepth);
  localparam int unsigned RowBytes = 32;
  localparam int unsigned MacroAddrWidth = 6;
  localparam int unsigned MacroDepth = 1 << MacroAddrWidth;
  localparam int unsigned MacroCount = (BankDepth + MacroDepth - 1) / MacroDepth;

  logic [BankCount-1:0] bank_req;
  logic [BankCount-1:0] bank_we;
  logic [BankAddrWidth-1:0] bank_addr[BankCount];
  logic [255:0] bank_wdata[BankCount];
  logic [31:0] bank_be[BankCount];
  logic [255:0] bank_rdata[BankCount];

  logic row_bank_q;
  logic [2:0] row_bank_index_q;

  logic column_active_q;
  logic [3:0] column_issue_group_q;
  logic [3:0] column_capture_group_q;
  logic column_capture_valid_q;
  logic [6:0] column_dimension_q;
  logic [2:0] column_count_q;
  akv_stream_e column_stream_q;
  logic [6:0] column_token_count_q;
  logic [3:0] column_group_count;
  logic column_read_issue;
  logic [3:0][1023:0] column_data_q;
  logic column_valid_q;

  function automatic logic [BankAddrWidth-1:0] row_address(
      input akv_stream_e stream,
      input logic [2:0] token_group,
      input logic [3:0] word
  );
    automatic int unsigned address;
    address = (stream == AKV_STREAM_V ? StreamRows : 0) +
              unsigned'(token_group) * WordsPerSlot + unsigned'(word);
    return BankAddrWidth'(address);
  endfunction

  assign column_group_count =
      4'((unsigned'(column_token_count_q) + BankCount - 1) / BankCount);
  assign write_busy_o = write_valid_i;
  assign column_busy_o = column_active_q || column_capture_valid_q;
  assign column_valid_o = column_valid_q;
  assign column_data_o = column_data_q;

  always_comb begin : steer_banks
    automatic logic [2:0] write_bank;
    automatic logic [2:0] write_group;
    automatic logic [3:0] write_word;
    automatic logic write_upper_half;
    automatic logic [2:0] row_bank;
    automatic logic [2:0] row_group;

    bank_req = '0;
    bank_we = '0;
    for (int unsigned bank = 0; bank < BankCount; bank++) begin
      bank_addr[bank] = '0;
      bank_wdata[bank] = '0;
      bank_be[bank] = '0;
    end

    write_bank = write_token_i[2:0];
    write_group = write_token_i[5:3];
    write_word = write_offset_i[7:5];
    write_upper_half = write_offset_i[4];
    row_bank = row_token_i[2:0];
    row_group = row_token_i[5:3];

    if (write_valid_i) begin
      bank_req[write_bank] = 1'b1;
      bank_we[write_bank] = 1'b1;
      bank_addr[write_bank] =
          row_address(write_stream_i, write_group, write_word);
      if (write_upper_half) begin
        bank_wdata[write_bank][255:128] = write_data_i;
        bank_be[write_bank][31:16] = write_strb_i;
      end else begin
        bank_wdata[write_bank][127:0] = write_data_i;
        bank_be[write_bank][15:0] = write_strb_i;
      end
    end else if (row_read_i) begin
      bank_req[row_bank] = 1'b1;
      bank_addr[row_bank] =
          row_address(row_stream_i, row_group, row_word_i);
    end else if (column_active_q) begin
      for (int unsigned bank = 0; bank < BankCount; bank++) begin
        automatic int unsigned token =
            unsigned'(column_issue_group_q) * BankCount + bank;
        if (token < unsigned'(column_token_count_q)) begin
          bank_req[bank] = 1'b1;
          bank_addr[bank] = row_address(
              column_stream_q, 3'(column_issue_group_q),
              4'(column_dimension_q[6:4]));
        end
      end
    end
  end

  assign column_read_issue = column_active_q &&
      !write_valid_i && !row_read_i;
  assign column_bank_cycle_o = column_read_issue;
  assign conflict_o =
      (write_valid_i && (row_read_i || column_active_q || column_start_i)) ||
      (row_read_i && (column_active_q || column_start_i)) ||
      (column_start_i && column_busy_o);

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
      macro_we = '0;
      for (int unsigned macro = 0; macro < MacroCount; macro++) begin
        macro_addr[macro] = '0;
        macro_wdata[macro] = '0;
        macro_bweb[macro] = '1;
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
            if (bank_be[bank][byte_lane])
              macro_bweb[selected_macro][byte_lane*8+:8] = '0;
          end
        end
      end
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) macro_read_select_q[bank] <= '0;
      else if (bank_req[bank] && !bank_we[bank])
        macro_read_select_q[bank] <=
            $clog2(MacroCount)'(unsigned'(bank_addr[bank]) / MacroDepth);
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
    if (!rst_ni) begin
      row_bank_q <= 1'b0;
      row_bank_index_q <= '0;
      column_active_q <= 1'b0;
      column_issue_group_q <= '0;
      column_capture_group_q <= '0;
      column_capture_valid_q <= 1'b0;
      column_dimension_q <= '0;
      column_count_q <= 3'd1;
      column_stream_q <= AKV_STREAM_K;
      column_token_count_q <= '0;
      column_data_q <= '0;
      column_valid_q <= 1'b0;
    end else begin
      if (row_read_i && !write_valid_i && !column_active_q) begin
        row_bank_q <= 1'b1;
        row_bank_index_q <= row_token_i[2:0];
      end else begin
        row_bank_q <= 1'b0;
      end

      column_capture_valid_q <= column_read_issue;
      if (column_read_issue) begin
        column_capture_group_q <= column_issue_group_q;
        if (unsigned'(column_issue_group_q) + 1 ==
            unsigned'(column_group_count)) begin
          column_active_q <= 1'b0;
        end else begin
          column_issue_group_q <= column_issue_group_q + 1'b1;
        end
      end

      if (column_start_i && !column_busy_o && !write_valid_i && !row_read_i) begin
        column_active_q <= 1'b1;
        column_issue_group_q <= '0;
        column_stream_q <= column_stream_i;
        column_dimension_q <= column_dimension_i;
        column_count_q <= column_count_i;
        column_token_count_q <= column_token_count_i;
        column_data_q <= '0;
        column_valid_q <= 1'b0;
      end

      if (column_capture_valid_q) begin
        for (int unsigned bank = 0; bank < BankCount; bank++) begin
          automatic int unsigned token =
              unsigned'(column_capture_group_q) * BankCount + bank;
          if (token < unsigned'(column_token_count_q)) begin
            for (int unsigned column = 0;
                 column < AkvV2ColumnPanelWidth; column++) begin
              if (column < unsigned'(column_count_q)) begin
                automatic int unsigned dimension =
                    unsigned'(column_dimension_q[3:0]) + column;
                column_data_q[column][token*16 +: 16] <=
                    bank_rdata[bank][dimension*16 +: 16];
              end
            end
          end
        end
        if (unsigned'(column_capture_group_q) + 1 ==
            unsigned'(column_group_count)) begin
          column_valid_q <= 1'b1;
        end
      end
    end
  end

  assign row_data_o = bank_rdata[row_bank_index_q];

`ifndef SYNTHESIS
  logic probe_column_valid_q;

  initial begin
    assert (AkvV2TileTokens == 64);
    assert (AkvV2TokenBanks == 8);
    assert (WordsPerSlot == 8);
    assert (BankDepth == 128);
    assert (MacroCount == 2);
  end

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      probe_column_valid_q <= 1'b0;
    end else begin
      probe_column_valid_q <= column_valid_q;
      if ($test$plusargs("AKV_V2_TOKEN_PROBE") && column_valid_q &&
          !probe_column_valid_q &&
          unsigned'(column_token_count_q) > 5) begin
        $display("[AKV_V2_TOKEN_GATHER] t=%0t stream=%0d dim=%0d count=%0d token5=%h",
                 $time, column_stream_q, column_dimension_q,
                 column_token_count_q, column_data_q[0][5*16 +: 16]);
      end
      if (write_valid_i) begin
        assert (write_stream_i inside {AKV_STREAM_K, AKV_STREAM_V});
        assert (unsigned'(write_token_i) < AkvV2TileTokens);
        assert (write_offset_i[3:0] == '0);
      end
      if (row_read_i) begin
        assert (row_stream_i inside {AKV_STREAM_K, AKV_STREAM_V});
        assert (unsigned'(row_token_i) < AkvV2TileTokens);
        assert (unsigned'(row_word_i) < WordsPerSlot);
      end
      if (column_start_i) begin
        assert (column_stream_i inside {AKV_STREAM_K, AKV_STREAM_V});
        assert (unsigned'(column_dimension_i) < AkvMaxHeadDim);
        assert (column_count_i inside {3'd1, 3'd4});
        assert (unsigned'(column_dimension_i) +
                    unsigned'(column_count_i) <= AkvMaxHeadDim);
        if (column_count_i == AkvV2ColumnPanelWidth) begin
          assert (column_dimension_i[1:0] == '0);
          assert (unsigned'(column_dimension_i[3:0]) +
                      AkvV2ColumnPanelWidth <= 16);
        end
        assert (column_token_count_i inside {[1:AkvV2TileTokens]});
        assert (!column_busy_o);
      end
      assert (!conflict_o)
        else $fatal(1, "AKV-v2 context received conflicting bank operations");
      if (row_bank_q)
        assert (!column_capture_valid_q);
    end
  end
`endif

endmodule : akv_v2_context
