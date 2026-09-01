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

  logic signed [15:0] product_d [4][8];
  logic signed [16:0] pair_sum_d [4][4];
  logic signed [17:0] quad_sum_d [4][2];
  logic signed [17:0] oct_sum_d [4];
  logic signed [17:0] stream_sum_d [16];

  always_comb begin
    product_d = '{default: '{default: '0}};
    pair_sum_d = '{default: '{default: '0}};
    quad_sum_d = '{default: '{default: '0}};
    oct_sum_d = '{default: '0};
    stream_sum_d = '{default: '0};

    // Four row clusters, each with eight physical low-bit x INT8 pairs. Keep
    // the 32 multipliers, but use a balanced reduction tree rather than the
    // loop-carried accumulation that synthesized as a serial adder chain.
    for (int row = 0; row < 4; row++) begin
      for (int slot = 0; slot < 8; slot++) begin
        automatic int unsigned ctx;
        automatic int unsigned lane;
        ctx = 0;
        lane = slot;
        if (m_i == 2) begin
          ctx = slot >> 2;
          lane = slot & 3;
        end else if (m_i >= 3) begin
          ctx = slot >> 1;
          lane = slot & 1;
        end
        product_d[row][slot] =
            weight_quant_i[row][lane] * activation_quant_i[ctx][lane];
      end

      for (int pair = 0; pair < 4; pair++) begin
        pair_sum_d[row][pair] =
            $signed({product_d[row][2 * pair][15],
                     product_d[row][2 * pair]}) +
            $signed({product_d[row][2 * pair + 1][15],
                     product_d[row][2 * pair + 1]});
      end

      quad_sum_d[row][0] =
          $signed({pair_sum_d[row][0][16], pair_sum_d[row][0]}) +
          $signed({pair_sum_d[row][1][16], pair_sum_d[row][1]});
      quad_sum_d[row][1] =
          $signed({pair_sum_d[row][2][16], pair_sum_d[row][2]}) +
          $signed({pair_sum_d[row][3][16], pair_sum_d[row][3]});
      oct_sum_d[row] = quad_sum_d[row][0] + quad_sum_d[row][1];

      if (valid_i && row < row_count_i) begin
        unique case (m_i)
          3'd1: stream_sum_d[row * 4] = oct_sum_d[row];
          3'd2: begin
            stream_sum_d[row * 4] = quad_sum_d[row][0];
            stream_sum_d[row * 4 + 1] = quad_sum_d[row][1];
          end
          default: begin
            for (int ctx = 0; ctx < 4; ctx++) begin
              if (ctx < m_i)
                stream_sum_d[row * 4 + ctx] = pair_sum_d[row][ctx];
            end
          end
        endcase
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
