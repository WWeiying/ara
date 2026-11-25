module shared_mul_product_tb;
  logic [63:0] a, b;
  logic [1:0] sew;
  logic sa, sb;
  wire [127:0] product;
  int checks = 0;
  int unsigned rng = 32'h372910ab;
  simd_mul_shared_product dut(a,b,sew,sa,sb,product);
  function automatic logic [31:0] random_word();
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng;
  endfunction
  task automatic check;
    logic [127:0] expected, mask;
    logic signed [128:0] x, y, p;
    int n;
    n = 8 << sew;
    mask = (128'd1 << n) - 1;
    expected = '0;
    for (int e = 0; e < 64/n; e++) begin
      x = {1'b0, ((128'(a) >> (e*n)) & mask)};
      y = {1'b0, ((128'(b) >> (e*n)) & mask)};
      if (sa && x[n-1]) x -= 129'd1 << n;
      if (sb && y[n-1]) y -= 129'd1 << n;
      p = x*y;
      if (n == 64) expected = p[127:0];
      else expected |= (p[127:0] & ((128'd1 << (2*n))-1)) << (e*2*n);
    end
    #1;
    assert(product === expected) else
      $fatal(1,"sew=%d sa=%b sb=%b a=%h b=%h got=%h expected=%h",
             sew,sa,sb,a,b,product,expected);
    checks++;
  endtask
  initial begin
    for (int s=0;s<4;s++) begin
      sew=2'(s);
      for (int signs=0;signs<4;signs++) begin
        {sa,sb}=2'(signs);
        a='0;b='0;check();
        a='1;b='1;check();
        for (int bitno=0;bitno<64;bitno++) begin
          a=64'd1<<bitno;b='1;check();
          a='1;b=64'd1<<bitno;check();
        end
        for (int t=0;t<1024;t++) begin
          a={random_word(),random_word()};
          b={random_word(),random_word()};check();
        end
      end
    end
    sew=0;
    for (int signs=0;signs<4;signs++) begin
      {sa,sb}=2'(signs);
      for (int x=0;x<256;x++)
        for (int y=0;y<256;y++) begin
          a={8{8'(x)}};b={8{8'(y)}};check();
        end
    end
    $display("PASS shared_mul_product checks=%0d",checks);
    $finish;
  end
endmodule
