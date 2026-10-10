// Standalone forwarding arithmetic audit; no CVA6/retirement model.
module vsetvl_preview_check #(
  parameter int unsigned VLEN = 1024,
  parameter int unsigned ELEN = 64,
  parameter int unsigned XLEN = 64
) (
  output bit done_o,
  output int unsigned cases_o,
  output int unsigned errors_o
);
  timeunit 1ns;
  timeprecision 1ps;
  logic valid_i, valid_o;
  logic [31:0] insn_i;
  logic [XLEN-1:0] avl_i, vl_o;
  typedef logic [XLEN-1:0] xlen_t;

  vsetvl_preview #(.VLEN(VLEN), .ELEN(ELEN), .XLEN(XLEN)) dut (.*);

  // Rational LMUL avoids sharing the DUT's signed exponent arithmetic.
  function automatic int unsigned numerator(input logic [2:0] lmul);
    case (lmul)
      0: return 1;
      1: return 2;
      2: return 4;
      3: return 8;
      default: return 1;
    endcase
  endfunction

  function automatic int unsigned denominator(input logic [2:0] lmul);
    case (lmul)
      5: return 8;
      6: return 4;
      7: return 2;
      default: return 1;
    endcase
  endfunction

  task automatic check(input logic [31:0] insn, input xlen_t avl, input bit valid);
    int unsigned sew, num, den, vlmax;
    bit expected_valid;
    xlen_t expected_vl;
    sew = 8 << insn[25:23];
    num = numerator(insn[22:20]);
    den = denominator(insn[22:20]);
    vlmax = (VLEN * num) / (sew * den);
    expected_valid = valid && insn[6:0] == 7'h57 && insn[14:12] == 7 &&
        insn[31:28] == 0 && insn[19:15] != 0 && insn[11:7] != 0 &&
        insn[22:20] != 4 && sew <= ELEN && ELEN * num >= sew * den;
    expected_vl = avl < xlen_t'(vlmax) ? avl : xlen_t'(vlmax);
    insn_i = insn;
    avl_i = avl;
    valid_i = valid;
    #1;
    cases_o++;
    if (valid_o !== expected_valid || (expected_valid && vl_o !== expected_vl)) begin
      if (errors_o < 8)
        $display("FAIL VLEN=%0d ELEN=%0d XLEN=%0d insn=%h avl=%h valid=%b got=%b/%h expected=%b/%h",
                 VLEN, ELEN, XLEN, insn, avl, valid, valid_o, vl_o,
                 expected_valid, expected_vl);
      errors_o++;
    end
  endtask

  initial begin
    logic [31:0] insn;
    int unsigned vlmax;
    done_o = 0;
    cases_o = 0;
    errors_o = 0;
    // All immediate/function encodings, including vsetvl and vsetivli exclusions.
    for (int unsigned upper = 0; upper < 4096; upper++) begin
      insn = (upper << 20) | (3 << 15) | (7 << 12) | (5 << 7) | 'h57;
      vlmax = (VLEN * numerator(insn[22:20])) /
          ((8 << insn[25:23]) * denominator(insn[22:20]));
      check(insn, 0, 1);
      check(insn, 1, 1);
      check(insn, xlen_t'(vlmax == 0 ? 0 : vlmax - 1), 1);
      check(insn, xlen_t'(vlmax), 1);
      check(insn, xlen_t'(vlmax + 1), 1);
      check(insn, xlen_t'(2 * vlmax - 1), 1);
      check(insn, xlen_t'(2 * vlmax), 1);
      check(insn, xlen_t'(1) << (XLEN - 1), 1);
      check(insn, '1, 1);
      check(insn, '1, 0);
    end
    // Every rs1/rd pair, including rd == rs1 and all x0 forms.
    for (int unsigned rs1 = 0; rs1 < 32; rs1++)
      for (int unsigned rd = 0; rd < 32; rd++) begin
        insn = (rs1 << 15) | (7 << 12) | (rd << 7) | 'h57;
        check(insn, 7, 1);
      end
    for (int unsigned opcode = 0; opcode < 128; opcode++)
      for (int unsigned funct3 = 0; funct3 < 8; funct3++) begin
        insn = (3 << 15) | (funct3 << 12) | (5 << 7) | opcode;
        check(insn, 7, 1);
      end
    $display("RESULT VLEN=%0d ELEN=%0d XLEN=%0d cases=%0d errors=%0d",
             VLEN, ELEN, XLEN, cases_o, errors_o);
    done_o = 1;
  end
endmodule

module vsetvl_preview_tb;
  timeunit 1ns;
  timeprecision 1ps;
  wire [3:0] done;
  wire [31:0] cases [4];
  wire [31:0] errors [4];
  vsetvl_preview_check a (.done_o(done[0]), .cases_o(cases[0]), .errors_o(errors[0]));
  vsetvl_preview_check #(.VLEN(128), .XLEN(32)) b (
    .done_o(done[1]), .cases_o(cases[1]), .errors_o(errors[1]));
  vsetvl_preview_check #(.VLEN(65536)) c (
    .done_o(done[2]), .cases_o(cases[2]), .errors_o(errors[2]));
  vsetvl_preview_check #(.ELEN(32)) d (
    .done_o(done[3]), .cases_o(cases[3]), .errors_o(errors[3]));
  initial begin
    wait (&done);
    if (errors[0] + errors[1] + errors[2] + errors[3] != 0)
      $fatal(1, "vsetvl_preview audit failed");
    $display("PASS cases=%0d vsetvl_preview arithmetic/decode audit",
             cases[0] + cases[1] + cases[2] + cases[3]);
    $finish;
  end
  initial begin
    #100000;
    $fatal(1, "vsetvl_preview audit timeout");
  end
endmodule
