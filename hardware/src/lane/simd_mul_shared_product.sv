// Experimental full-product core. Not enabled in the production lane.
// Four SEW modes share bit partial products and one carry-save tree.
module simd_mul_shared_product (
  input logic [63:0] a_i, b_i,
  input logic [1:0] sew_i,
  input logic signed_a_i, signed_b_i,
  output logic [127:0] product_o
);
  wire [63:0] pp [64];
  wire [127:0] rows [64];
  for (genvar i = 0; i < 64; i++) begin : gen_row
    wire [127:0] mode_row [4];
    for (genvar j = 0; j < 64; j++) begin : gen_bit
      assign pp[i][j] = a_i[i] & b_i[j];
    end
    for (genvar s = 0; s < 4; s++) begin : gen_mode
      localparam int N = 8 << s;
      localparam int Base = (i / N) * N;
      // A row contains one element's contribution only; all routing is static.
      for (genvar k = 0; k < 128; k++) begin : gen_position
        if (k >= 2*Base + i-Base && k < 2*Base + i-Base + N) begin
          localparam int J = Base + k - (2*Base + i-Base);
          assign mode_row[s][k] = pp[i][J];
        end else begin
          assign mode_row[s][k] = 1'b0;
        end
      end
    end
    assign rows[i] = mode_row[sew_i];
  end

  wire [127:0] unsigned_product;
  simd_mul_shared_csa #(.Count(64)) i_tree (
    .rows_i(rows), .sum_o(unsigned_product)
  );
  wire [127:0] corrected [4];
  wire [63:0] packed_hi [4], correction_a [4], correction_b [4];
  wire [63:0] high_once, high_corrected;
  simd_mul_partition_add correct_a (
    .a_i(packed_hi[sew_i]), .b_i(~correction_a[sew_i]),
    .sew_i, .carry_i(8'hff), .sum_o(high_once)
  );
  simd_mul_partition_add correct_b (
    .a_i(high_once), .b_i(~correction_b[sew_i]),
    .sew_i, .carry_i(8'hff), .sum_o(high_corrected)
  );
  for (genvar s = 0; s < 4; s++) begin : gen_sign
    localparam int N = 8 << s;
    for (genvar e = 0; e < 64/N; e++) begin : gen_element
      wire [N-1:0] a = a_i[e*N +: N];
      wire [N-1:0] b = b_i[e*N +: N];
      assign packed_hi[s][e*N+:N] = unsigned_product[e*2*N+N +: N];
      assign correction_a[s][e*N+:N] = (signed_a_i && a[N-1]) ? b : N'(0);
      assign correction_b[s][e*N+:N] = (signed_b_i && b[N-1]) ? a : N'(0);
      // Signed product modulo 2^(2N): subtract B*2^N and/or A*2^N.
      // Keeping the correction local prevents carry between SIMD elements.
      assign corrected[s][e*2*N +: N] = unsigned_product[e*2*N +: N];
      assign corrected[s][e*2*N+N +: N] = high_corrected[e*N+:N];
    end
  end
  assign product_o = corrected[sew_i];
endmodule

module simd_mul_shared_csa #(parameter int Count = 64) (
  input wire [127:0] rows_i [Count],
  output wire [127:0] sum_o
);
  if (Count == 2) begin : gen_final
    assign sum_o = rows_i[0] + rows_i[1];
  end else begin : gen_reduce
    localparam int Groups = Count / 3;
    localparam int Remainder = Count % 3;
    localparam int NextCount = 2*Groups + Remainder;
    wire [127:0] next_rows [NextCount];
    for (genvar g = 0; g < Groups; g++) begin : gen_compressor
      assign next_rows[2*g] = rows_i[3*g] ^ rows_i[3*g+1] ^ rows_i[3*g+2];
      assign next_rows[2*g+1] = ((rows_i[3*g] & rows_i[3*g+1]) |
          (rows_i[3*g] & rows_i[3*g+2]) |
          (rows_i[3*g+1] & rows_i[3*g+2])) << 1;
    end
    for (genvar r = 0; r < Remainder; r++) begin : gen_remainder
      assign next_rows[2*Groups+r] = rows_i[3*Groups+r];
    end
    simd_mul_shared_csa #(.Count(NextCount)) i_next (
      .rows_i(next_rows), .sum_o
    );
  end
endmodule
