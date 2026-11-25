`timescale 1ns/1ps
module shared_mul_signed_product_tb;
  logic [63:0] a, b;
  logic [1:0] sew;
  logic sa, sb;
  wire [127:0] product;
  int checks = 0;
  simd_mul_shared_product dut (
    .a_i(a), .b_i(b), .sew_i(sew), .signed_a_i(sa), .signed_b_i(sb),
    .product_o(product)
  );
  task automatic check;
    int n;
    logic [63:0] mask, av, bv;
    logic signed [64:0] ax, bx;
    logic signed [129:0] px;
    logic [127:0] expected;
    n = 8 << sew;
    mask = 64'hffffffffffffffff >> (64-n);
    expected = '0;
    for (int e = 0; e < 64/n; e++) begin
      av = (a >> (e*n)) & mask;
      bv = (b >> (e*n)) & mask;
      ax = $signed({1'b0, av});
      bx = $signed({1'b0, bv});
      if (sa && av[n-1]) ax -= (65'd1 << n);
      if (sb && bv[n-1]) bx -= (65'd1 << n);
      px = ax * bx;
      for (int k = 0; k < 2*n; k++) expected[e*2*n+k] = px[k];
    end
    #1;
    if (product !== expected)
      $fatal(1, "sew=%0d signs=%0b%0b a=%h b=%h got=%h expected=%h",
             n, sa, sb, a, b, product, expected);
    checks++;
  endtask
  initial begin
    int byte_pairs, bit_positions, random_vectors;
    byte_pairs = $test$plusargs("QUICK") ? 16 : 256;
    bit_positions = $test$plusargs("QUICK") ? 16 : 64;
    random_vectors = $test$plusargs("QUICK") ? 512 : 2000;
    // Exhaust every byte pair and both signedness flags. Distinct adjacent
    // elements detect overflow leaking across packed product boundaries.
    sew = 0;
    for (int signs = 0; signs < 4; signs++) begin
      {sa, sb} = 2'(signs);
      for (int x = 0; x < byte_pairs; x++) begin
        for (int y = 0; y < byte_pairs; y++) begin
          for (int e = 0; e < 8; e++) begin
            a[e*8+:8] = 8'(x*(256/byte_pairs) + e*37);
            b[e*8+:8] = 8'(y*(256/byte_pairs) + e*53);
          end
          check();
        end
      end
    end
    for (int s = 0; s < 4; s++) begin
      sew = 2'(s);
      for (int signs = 0; signs < 4; signs++) begin
        {sa, sb} = 2'(signs);
        for (int x = 0; x < bit_positions; x++) begin
          for (int y = 0; y < bit_positions; y++) begin
            a = 64'd1 << (x*(64/bit_positions)); b = 64'd1 << (y*(64/bit_positions)); check();
            a = ~a; b = ~b; check();
          end
        end
        for (int r = 0; r < random_vectors; r++) begin
          a = {$urandom, $urandom}; b = {$urandom, $urandom}; check();
        end
        a = '0; b = '0; check();
        a = '1; b = '1; check();
        a = '1; b = '0; check();
        a = '0; b = '1; check();
      end
    end
    $display("Shared signed product PASS checks=%0d", checks);
    $finish;
  end
endmodule
