// Copyright 2026. Solderpad Hardware License, Version 0.51.
// A forwarding-only result: no CSR write, instruction acceptance or retirement.
module vsetvl_preview #(
  parameter int unsigned VLEN = 1024,
  parameter int unsigned ELEN = 64,
  parameter int unsigned XLEN = 64
) (
  input logic valid_i,
  input logic [31:0] insn_i,
  input logic [XLEN-1:0] avl_i,
  output logic valid_o,
  output logic [XLEN-1:0] vl_o
);
  logic legal;
  int signed lmul_log2;
  int unsigned vlmax;

  always_comb begin
    lmul_log2 = int'($signed(insn_i[22:20]));
    vlmax = (VLEN / 8) >> insn_i[25:23];
    if (lmul_log2 >= 0) vlmax = vlmax << lmul_log2;
    else vlmax = vlmax >> -lmul_log2;
    legal = !insn_i[31] && insn_i[6:0] == 7'h57 && insn_i[14:12] == 3'b111 &&
        insn_i[19:15] != '0 && insn_i[11:7] != '0 && insn_i[30:28] == '0 &&
        insn_i[25:23] <= $clog2(ELEN/8) && insn_i[22:20] != 3'b100 &&
        ($clog2(ELEN/8) + lmul_log2 >= int'(insn_i[25:23]));
    valid_o = valid_i && legal;
    vl_o = avl_i < XLEN'(vlmax) ? avl_i : XLEN'(vlmax);
  end
endmodule
