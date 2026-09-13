// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module simd_mul_equivalence_case import ara_pkg::*; import rvv_pkg::*; #(
  parameter int Sew = 0, Pipes = 0, Fixed = 1
)(input logic clk_i, output logic done_o);
  localparam int Width = 8 << Sew;
  localparam logic [63:0] ElemMask = 64'hffff_ffff_ffff_ffff >> (64-Width);
  logic rst_ni = 0;
  elen_t operand_a_i = 0, operand_b_i = 0, operand_c_i = 0;
  logic [7:0] mask_i = 0;
  ara_op_e op_i = VMUL;
  vxrm_t vxrm_i = 0;
  logic valid_i = 0, ready_i = 0;
  elen_t result_o, ref_result;
  logic [7:0] mask_o, ref_mask;
  vxsat_t vxsat_o, ref_sat;
  logic ready_o, valid_o, ref_ready, ref_valid;
  int checks, retired;
  int unsigned rng = 32'h70c812ad ^ (Sew << 16) ^ (Pipes << 8) ^ Fixed;
  ara_op_e ops [9] = '{VMUL, VMULH, VMULHU, VMULHSU, VMACC, VMADD, VNMSAC, VNMSUB, VSMUL};
  typedef struct packed {
    ara_op_e op;
    logic [63:0] a, b, c;
    logic [7:0] mask;
  } transaction_t;
  transaction_t pending[$];
  simd_mul #(.ElementWidth(vew_e'(Sew)), .NumPipeRegs(Pipes),
             .FixPtSupport(fixpt_support_e'(Fixed))) dut (.*);
  simd_mul_reference #(.ElementWidth(vew_e'(Sew)), .NumPipeRegs(Pipes),
             .FixPtSupport(fixpt_support_e'(Fixed))) reference (
    .result_o(ref_result), .mask_o(ref_mask), .vxsat_o(ref_sat),
    .valid_o(ref_valid), .ready_o(ref_ready), .*
  );

  function automatic int unsigned random_word();
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng;
  endfunction
  function automatic logic [63:0] edge_value(int index);
    case (index)
      0: return 0;
      1: return 1;
      2: return ElemMask;
      3: return ElemMask - 1;
      4: return 64'h1 << (Width-1);
      5: return (64'h1 << (Width-1))-1;
      6: return (64'h1 << (Width-1))+1;
      default: return 64'h5555_5555_5555_5555 & ElemMask;
    endcase
  endfunction
  function automatic logic [63:0] replicate_element(logic [63:0] value);
    logic [63:0] result;
    result = 0;
    for (int e = 0; e < 64/Width; e++) result |= value << (e*Width);
    return result;
  endfunction

  // Independent integer arithmetic model. VXRM remains live at the output,
  // as in the existing unit; this retiming does not alter its CSR contract.
  function automatic logic [71:0] expected(transaction_t t, vxrm_t rm);
    logic [63:0] value, sat, a, b, c, v;
    logic signed [65:0] sa, sb;
    logic signed [131:0] product;
    logic inc;
    value = 0;
    sat = 0;
    for (int e = 0; e < 64/Width; e++) begin
      a = (t.a >> (e*Width)) & ElemMask;
      b = (t.b >> (e*Width)) & ElemMask;
      c = (t.c >> (e*Width)) & ElemMask;
      sa = $signed({2'b0, a});
      sb = $signed({2'b0, b});
      if (t.op inside {VMULH, VSMUL} && a[Width-1]) sa -= 66'sd1 << Width;
      if (t.op inside {VMULH, VMULHSU, VSMUL} && b[Width-1]) sb -= 66'sd1 << Width;
      product = sa * sb;
      v = 0;
      case (t.op)
        VMUL: v = 64'(product);
        VMULH, VMULHU, VMULHSU: v = 64'(product >>> Width);
        VMACC, VMADD: v = 64'(product) + c;
        VNMSAC, VNMSUB: v = c - 64'(product);
        VSMUL: begin
          case (rm)
            0: inc = product[Width-2];
            1: inc = product[Width-2] &&
                (product[Width-1] || (product[Width-3:0] != 0));
            2: inc = 0;
            3: inc = !product[Width-1] && (product[Width-2:0] != 0);
          endcase
          if (a == (64'h1 << (Width-1)) && b == a) begin
            v = (64'h1 << (Width-1))-1;
            sat |= ((64'h1 << (Width/8))-1) << (e*(Width/8));
          end else v = 64'(product >>> (Width-1)) + 64'(inc);
        end
        default: ;
      endcase
      value |= (v & ElemMask) << (e*Width);
    end
    return {sat[7:0], value};
  endfunction

  always @(posedge clk_i) begin
    if (!rst_ni) pending.delete();
    else begin
      // Push first also handles the zero-register combinational instance.
      if (valid_i && ready_o)
        pending.push_back('{op_i, operand_a_i, operand_b_i, operand_c_i, mask_i});
      if (valid_o && ready_i) begin
        transaction_t t;
        assert (pending.size() > 0) else $fatal(1, "unexpected MUL result");
        t = pending.pop_front();
        assert ({vxsat_o, result_o} === expected(t, vxrm_i) && mask_o === t.mask)
          else $fatal(1, "MUL arithmetic sew=%0d pipes=%0d op=%0d got=%h/%h expected=%h",
                      Sew, Pipes, t.op, vxsat_o, result_o, expected(t, vxrm_i));
        retired++;
      end
    end
    #1;
    if (rst_ni) begin
      assert ({valid_o, ready_o, mask_o, vxsat_o, result_o} ===
              {ref_valid, ref_ready, ref_mask, ref_sat, ref_result})
        else $fatal(1, "MUL cycle equivalence sew=%0d pipes=%0d fixed=%0d check=%0d",
                    Sew, Pipes, Fixed, checks);
      checks++;
    end
  end

  initial begin
    done_o = 0;
    repeat (3) @(negedge clk_i);
    rst_ni = 1;
    for (int op = 0; op < (Fixed ? 9 : 8); op++)
      for (int rm = 0; rm < 4; rm++)
        for (int a = 0; a < 8; a++)
          for (int b = 0; b < 8; b++) begin
            @(negedge clk_i);
            ready_i = 1;
            valid_i = 1;
            op_i = ops[op];
            vxrm_i = vxrm_t'(rm);
            operand_a_i = replicate_element(edge_value(a));
            operand_b_i = replicate_element(edge_value(b));
            operand_c_i = replicate_element(edge_value((a+b)%8));
            mask_i = 8'(random_word());
          end
    for (int i = 0; i < 6000; i++) begin
      @(negedge clk_i);
      if (i == 3000) rst_ni = 0;
      if (i == 3002) rst_ni = 1;
      ready_i = i % 53 >= 13 && 1'(random_word());
      valid_i = i % 47 >= 5 && 1'(random_word());
      op_i = ops[random_word() % (Fixed ? 9 : 8)];
      vxrm_i = vxrm_t'(random_word());
      operand_a_i = {random_word(), random_word()};
      operand_b_i = {random_word(), random_word()};
      operand_c_i = {random_word(), random_word()};
      mask_i = 8'(random_word());
    end
    @(negedge clk_i);
    valid_i = 0;
    ready_i = 1;
    repeat (Pipes+3) @(negedge clk_i);
    assert (pending.size() == 0) else $fatal(1, "MUL did not drain");
    $display("SIMD MUL case PASS sew=%0d pipes=%0d fixed=%0d checks=%0d retired=%0d",
             Width, Pipes, Fixed, checks, retired);
    done_o = 1;
  end
endmodule

module simd_mul_equivalence_tb;
  logic clk_i = 0;
  always #5 clk_i = ~clk_i;
  logic [23:0] done;
  for (genvar s = 0; s < 4; s++)
    for (genvar p = 0; p < 3; p++)
      for (genvar f = 0; f < 2; f++) begin : gen_case
        simd_mul_equivalence_case #(.Sew(s), .Pipes(p), .Fixed(f)) i_case (
          .clk_i, .done_o(done[6*s+2*p+f])
        );
      end
  initial begin
    wait (&done);
    $display("SIMD MUL equivalence PASS configurations=24");
    $finish;
  end
  initial begin
    #2000000;
    $fatal(1, "SIMD MUL test watchdog");
  end
endmodule
