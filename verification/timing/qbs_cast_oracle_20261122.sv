module qbs_cast_oracle_20261122(output bit done);
  import fpnew_pkg::*;
  logic clk = 0, rst_n = 0, valid;
  always #5 clk = ~clk;
  logic [31:0] operand;
  logic [3:0] tag;
  wire [1:0] ready, out_valid, busy;
  wire [31:0] result[2];
  wire [4:0] status[2];
  wire [3:0] out_tag[2];
  cast_before a(clk, rst_n, valid, operand, tag, ready[0], out_valid[0],
                busy[0], result[0], status[0], out_tag[0]);
  cast_after b(clk, rst_n, valid, operand, tag, ready[1], out_valid[1],
               busy[1], result[1], status[1], out_tag[1]);
  bit pending;
  logic [31:0] expected;
  logic [4:0] expected_status;
  logic [3:0] expected_tag;
  int checks, exact_count, inexact_count, consecutive, bubbles;
  logic [15:0] tags_seen;
  logic [31:0] seed = 32'h0c0123ab;

  // Integer-only signed INT32 -> binary32 RNE; no simulator floating arithmetic.
  function automatic logic [36:0] rne(input logic [31:0] x);
    bit sign_bit;
    logic [63:0] magnitude, mantissa, remainder_bits, halfway;
    logic [31:0] bits32;
    int exponent, shift;
    sign_bit = x[31];
    magnitude = sign_bit ? ((~{32'b0,x} + 1) & 64'hffffffff) : {32'b0,x};
    if (!magnitude) return '0;
    exponent = 0;
    for (int k = 0; k < 32; k++) if (magnitude[k]) exponent = k;
    shift = exponent > 23 ? exponent - 23 : 0;
    remainder_bits = magnitude & ((64'd1 << shift) - 1);
    mantissa = shift ? magnitude >> shift : magnitude << (23 - exponent);
    halfway = shift ? 64'd1 << (shift - 1) : 0;
    if (shift && (remainder_bits > halfway ||
                  (remainder_bits == halfway && mantissa[0]))) mantissa++;
    if (mantissa[24]) begin mantissa >>= 1; exponent++; end
    bits32 = {sign_bit, 8'(exponent + 127), mantissa[22:0]};
    return {bits32, 4'b0, (remainder_bits != 0)};
  endfunction

  always @(posedge clk) begin
    if (!rst_n) pending = 0;
    else begin
      assert ({ready[0],out_valid[0],busy[0]} === {ready[1],out_valid[1],busy[1]})
        else $fatal(1,"Cast handshake/busy mismatch");
      assert (out_valid[0] === pending)
        else $fatal(1,"Cast changed one-cycle latency");
      if (pending) begin
        for (int m = 0; m < 2; m++) begin
          assert ({result[m],status[m],out_tag[m]} ===
                  {expected,expected_status,expected_tag})
            else $fatal(1,"RNE oracle mismatch port=%0d result=%h status=%h tag=%h expected=%h/%h/%h",
                         m,result[m],status[m],out_tag[m],expected,expected_status,expected_tag);
        end
        checks++;
        tags_seen[expected_tag] = 1;
        if (expected_status[0]) inexact_count++; else exact_count++;
      end
      if (pending && valid) consecutive++;
      if (!valid) bubbles++;
      pending = valid && ready[0];
      if (valid) begin
        assert (ready[0]) else $fatal(1,"Unexpected cast backpressure");
        {expected,expected_status} = rne(operand);
        expected_tag = tag;
      end
    end
  end

  initial begin
    done = 0; valid = 0; operand = 0; tag = 0;
    repeat (3) @(negedge clk);
    rst_n = 1;
    for (int i = 0; i < 4096; i++) begin
      @(negedge clk);
      seed = seed * 32'd1664525 + 32'd1013904223;
      valid = i < 1024 || i % 7 != 0;
      tag = 4'(i);
      case (i % 16)
        0: operand = 32'h01000000 + 32'(i % 512);
        1: operand = -(32'h01000000 + 32'(i % 512));
        2: operand = 32'h7fffffff;
        3: operand = 32'h80000000;
        4: operand = 0;
        5: operand = 32'hffffffff;
        6: operand = 32'h01000001;
        7: operand = 32'h01000003;
        8: operand = 32'hfeffffff;
        9: operand = 32'hfefffffd;
        10: operand = (32'd1 << (i % 31)) + 1;
        11: operand = -((32'd1 << (i % 31)) + 1);
        default: operand = seed;
      endcase
    end
    @(negedge clk); valid = 0;
    repeat (3) @(negedge clk);
    assert (checks > 3500 && exact_count > 0 && inexact_count > 0 &&
            tags_seen == 16'hffff && consecutive > 1000 && bubbles > 100)
      else $fatal(1,"Missing direct cast coverage");
    $display("CAST_ORACLE_PASS checks=%0d exact=%0d inexact=%0d tags=%h consecutive=%0d bubbles=%0d",
             checks,exact_count,inexact_count,tags_seen,consecutive,bubbles);
    done = 1;
  end
endmodule
