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

  // Fixed-throughput decode and product stages keep the SRAM/format muxes,
  // multiplication, and reduction tree in separate clock periods.
  logic quant_valid_q, product_valid_q;
  logic [2:0] quant_m_q, product_m_q;
  logic [2:0] quant_rows_q, product_rows_q;
  logic [15:0] quant_stream_valid_q, product_stream_valid_q;
  logic signed [7:0] weight_quant_q [4][8], activation_quant_q [4][8];
  logic signed [15:0] product_d [4][8], product_q [4][8];
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
    for (int row = 0; row < 4; row++) begin
      for (int slot = 0; slot < 8; slot++) begin
        automatic int unsigned ctx;
        automatic int unsigned lane;
        ctx = 0;
        lane = slot;
        if (quant_m_q == 2) begin
          ctx = slot >> 2;
          lane = slot & 3;
        end else if (quant_m_q >= 3) begin
          ctx = slot >> 1;
          lane = slot & 1;
        end
        product_d[row][slot] =
            weight_quant_q[row][lane] * activation_quant_q[ctx][lane];
      end
    end
  end

  always_comb begin
    oct_sum_d = '{default: '0};
    stream_sum_d = '{default: '0};

    // All modes retain the same 32 products. Carry-save compression propagates
    // carry only once on the M1/M2 reduction paths.
    for (int row = 0; row < 4; row++) begin
      for (int slot = 0; slot < 8; slot++)
        product_ext[row][slot] = {{3{product_q[row][slot][15]}}, product_q[row][slot]};

      for (int pair = 0; pair < 4; pair++) begin
        pair_sum_d[row][pair] =
            $signed({product_q[row][2 * pair][15],
                     product_q[row][2 * pair]}) +
            $signed({product_q[row][2 * pair + 1][15],
                     product_q[row][2 * pair + 1]});
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

      if (product_valid_q && row < product_rows_q) begin
        unique case (product_m_q)
          3'd1: stream_sum_d[row * 4] = oct_sum_d[row];
          3'd2: begin
            stream_sum_d[row * 4] = quad_sum_d[row][0];
            stream_sum_d[row * 4 + 1] = quad_sum_d[row][1];
          end
          default: begin
            for (int ctx = 0; ctx < 4; ctx++) begin
              if (ctx < product_m_q)
                stream_sum_d[row * 4 + ctx] = pair_sum_d[row][ctx];
            end
          end
        endcase
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      quant_valid_q <= 1'b0;
      product_valid_q <= 1'b0;
      quant_m_q <= '0;
      product_m_q <= '0;
      quant_rows_q <= '0;
      product_rows_q <= '0;
      quant_stream_valid_q <= '0;
      product_stream_valid_q <= '0;
      for (int row = 0; row < 4; row++) begin
        for (int slot = 0; slot < 8; slot++) begin
          weight_quant_q[row][slot] <= '0;
          activation_quant_q[row][slot] <= '0;
          product_q[row][slot] <= '0;
        end
      end
      valid_o <= 1'b0;
      stream_valid_o <= '0;
      for (int stream = 0; stream < 16; stream++) stream_sum_o[stream] <= '0;
    end else begin
      quant_valid_q <= valid_i;
      product_valid_q <= quant_valid_q;
      if (valid_i) begin
        quant_m_q <= m_i;
        quant_rows_q <= row_count_i;
        quant_stream_valid_q <= stream_valid_i;
        weight_quant_q <= weight_quant_i;
        activation_quant_q <= activation_quant_i;
      end
      if (quant_valid_q) begin
        product_m_q <= quant_m_q;
        product_rows_q <= quant_rows_q;
        product_stream_valid_q <= quant_stream_valid_q;
        product_q <= product_d;
      end
      valid_o <= product_valid_q;
      stream_valid_o <= product_valid_q ? product_stream_valid_q : '0;
      for (int stream = 0; stream < 16; stream++)
        stream_sum_o[stream] <= stream_sum_d[stream];
    end
  end

endmodule : qbs_dot_array
