// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_dot_array (
  input  logic               clk_i,
  input  logic               rst_ni,
  input  logic               valid_i,
  input  logic [2:0]         m_i,
  input  logic [2:0]         row_count_i,
  input  logic [15:0]        stream_valid_i,
  input  logic signed [7:0]  weight_quant_i [4][8],
  input  logic signed [7:0]  activation_quant_i [4][8],
  output logic               valid_o,
  output logic [15:0]        stream_valid_o,
  output logic signed [17:0] stream_sum_o [16]
);

  logic signed [17:0] stream_sum_d [16];

  always_comb begin
    for (int stream = 0; stream < 16; stream++) stream_sum_d[stream] = '0;

    // Four row clusters, each with eight physical low-bit x INT8 pairs.
    // The slot-to-context mapping changes with M, but the multiplier count
    // remains exactly 32.
    for (int row = 0; row < 4; row++) begin
      for (int slot = 0; slot < 8; slot++) begin
        automatic int unsigned ctx;
        automatic int unsigned lane;
        automatic logic signed [15:0] product;
        ctx = 0;
        lane = slot;
        if (m_i == 2) begin
          ctx = slot >> 2;
          lane = slot & 3;
        end else if (m_i >= 3) begin
          ctx = slot >> 1;
          lane = slot & 1;
        end
        product = weight_quant_i[row][lane] * activation_quant_i[ctx][lane];
        if (valid_i && row < row_count_i && ctx < m_i)
          stream_sum_d[row * 4 + ctx] =
              stream_sum_d[row * 4 + ctx] + product;
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      valid_o <= 1'b0;
      stream_valid_o <= '0;
      for (int stream = 0; stream < 16; stream++) stream_sum_o[stream] <= '0;
    end else begin
      valid_o <= valid_i;
      stream_valid_o <= valid_i ? stream_valid_i : '0;
      for (int stream = 0; stream < 16; stream++)
        stream_sum_o[stream] <= stream_sum_d[stream];
    end
  end

endmodule : qbs_dot_array
