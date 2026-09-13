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
  output logic signed [18:0] stream_sum_o [16]
);

  logic signed [15:0] product_d [4][8];
  logic signed [16:0] pair_sum_d [4][4];
  logic signed [17:0] quad_sum_d [4][2];
  logic signed [18:0] oct_sum_d [4];
  logic signed [18:0] stream_sum_d [16];
  logic [18:0] product_ext [4][8];
  logic [18:0] quad_sum_bits [4][2], quad_carry_bits [4][2];
  logic [18:0] oct_sum_bits [4], oct_carry_bits [4];

  // The low half is sum, the high half is the already shifted carry.
  function automatic logic [37:0] compress3(
      input logic [18:0] a, b, c);
    return {19'(((a & b) | (a & c) | (b & c)) << 1), a ^ b ^ c};
  endfunction

  always_comb begin
    // Fixed-bound loops fully assign the multidimensional intermediates below.
    oct_sum_d = '{default: '0};
    stream_sum_d = '{default: '0};

    // Keep 32 multipliers and the existing output register. Carry-save
    // compression lets the M1/M2 paths propagate carry only once, instead
    // of once at every level of the pair/quad/oct reduction.
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
        product_ext[row][slot] = {{3{product_d[row][slot][15]}}, product_d[row][slot]};
      end

      for (int pair = 0; pair < 4; pair++) begin
        pair_sum_d[row][pair] =
            $signed({product_d[row][2 * pair][15],
                     product_d[row][2 * pair]}) +
            $signed({product_d[row][2 * pair + 1][15],
                     product_d[row][2 * pair + 1]});
      end

      for (int quad = 0; quad < 2; quad++) begin
        automatic logic [37:0] first;
        first = compress3(product_ext[row][4*quad], product_ext[row][4*quad+1],
                          product_ext[row][4*quad+2]);
        {quad_carry_bits[row][quad], quad_sum_bits[row][quad]} =
            compress3(first[18:0], first[37:19], product_ext[row][4*quad+3]);
        quad_sum_d[row][quad] = 18'(quad_sum_bits[row][quad] + quad_carry_bits[row][quad]);
      end
      begin
        automatic logic [37:0] first;
        first = compress3(quad_sum_bits[row][0], quad_carry_bits[row][0],
                          quad_sum_bits[row][1]);
        {oct_carry_bits[row], oct_sum_bits[row]} =
            compress3(first[18:0], first[37:19], quad_carry_bits[row][1]);
      end
      // Eight (-128)*(-128) products total +131072, beyond signed 18 bits.
      oct_sum_d[row] = oct_sum_bits[row] + oct_carry_bits[row];

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
