// SPDX-License-Identifier: SHL-0.51
// Old/new miter and an independent element-wise shift/round/saturate oracle.
module shared_alu_shift_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  elen_t operand_a_i, operand_b_i;
  logic valid_i = 1, vm_i = 1, narrowing_select_i = 0;
  logic [7:0] mask_i = '1, rm, computed_rm, injected_rm;
  logic inject_rm = 0;
  ara_op_e op_i;
  vew_e vew_i;
  vxrm_t vxrm_i = 0;
  elen_t result [2], reference [2];
  vxsat_t sat [2], ref_sat [2];
  longint unsigned checks = 0;
  int seed = 32'h519ca330;
  ara_op_e operations [9] = '{VSLL, VSRL, VSRA, VNSRL, VNSRA,
      VSSRL, VSSRA, VNCLIP, VNCLIPU};
  fixed_p_rounding i_rounding (.r_o(computed_rm), .*);
  assign rm = inject_rm ? injected_rm : computed_rm;
  for (genvar cfg = 0; cfg < 2; cfg++) begin : gen_config
    simd_alu #(.FixPtSupport(fixpt_support_e'(cfg))) i_dut
        (.result_o(result[cfg]), .vxsat_o(sat[cfg]), .*);
    simd_alu_reference #(.FixPtSupport(fixpt_support_e'(cfg))) i_ref
        (.result_o(reference[cfg]), .vxsat_o(ref_sat[cfg]), .*);
  end

  function automatic logic [63:0] mask_width(int w);
    return 64'hffff_ffff_ffff_ffff >> (64-w);
  endfunction

  task automatic check;
    int w, sw, shift, dest;
    logic narrow, clip, fixed_op, signed_op, inc;
    logic [63:0] bits, expected;
    logic [7:0] expected_sat, expected_rm;
    logic signed [65:0] value, low, high;
    #1;
    checks++;
    w = 8 << unsigned'(vew_i);
    narrow = op_i inside {VNSRL, VNSRA, VNCLIP, VNCLIPU};
    clip = op_i inside {VNCLIP, VNCLIPU};
    fixed_op = clip || (op_i inside {VSSRL, VSSRA});
    signed_op = op_i inside {VSRA, VNSRA, VSSRA, VNCLIP};
    sw = narrow ? 2*w : w;
    for (int cfg = 0; cfg < 2; cfg++) begin
      assert ({result[cfg],sat[cfg]} === {reference[cfg],ref_sat[cfg]})
        else $fatal(1,"SHIFT_MITER cfg=%0d op=%0d sew=%0d a=%h b=%h rm=%h select=%b got=%h/%h ref=%h/%h",
            cfg,op_i,vew_i,operand_a_i,operand_b_i,rm,narrowing_select_i,
            result[cfg],sat[cfg],reference[cfg],ref_sat[cfg]);
      expected = 0; expected_sat = 0; expected_rm = 0;
      if (valid_i && sw <= 64) begin
        for (int e = 0; e < 64/sw; e++) begin
          bits = (operand_b_i >> (e*sw)) & mask_width(sw);
          shift = int'(operand_a_i >> (e*sw)) & (sw-1);
          inc = 0;
          if (shift != 0 && fixed_op) begin
            case (vxrm_i)
              0: inc = bits[shift-1];
              1: inc = bits[shift-1] & (bits[shift] | ((bits & mask_width(shift-1)) != 0));
              2: inc = 0;
              3: inc = !bits[shift] & ((bits & mask_width(shift)) != 0);
            endcase
          end
          expected_rm[e] = inc;
          if (inject_rm) inc = rm[e];
          value = $signed({2'b0,bits});
          if (signed_op && bits[sw-1]) value -= 66'sd1 << sw;
          if (op_i == VSLL) value = value <<< shift;
          else value = value >>> shift;
          if (fixed_op) value += 66'(inc);
          dest = narrow ? (2*e+int'(narrowing_select_i))*w : e*w;
          if (clip) begin
            low = signed_op ? -(66'sd1 << (w-1)) : 66'sd0;
            high = signed_op ? (66'sd1 << (w-1))-1 : (66'sd1 << w)-1;
            if (value < low || value > high)
              expected_sat |= 8'(mask_width(w/8) << (dest/8));
            if (value < low) value = low;
            if (value > high) value = high;
          end
          expected |= (64'(value) & mask_width(w)) << dest;
        end
      end
      if (fixed_op && !cfg) begin expected = 0; expected_sat = 0; end
      assert ({result[cfg],sat[cfg]} === {expected,expected_sat})
        else $fatal(1,"SHIFT_MODEL cfg=%0d op=%0d sew=%0d a=%h b=%h rm=%h select=%b got=%h/%h expected=%h/%h",
            cfg,op_i,vew_i,operand_a_i,operand_b_i,rm,narrowing_select_i,
            result[cfg],sat[cfg],expected,expected_sat);
      assert (computed_rm === expected_rm)
        else $fatal(1,"SHIFT_ROUND op=%0d sew=%0d got=%h expected=%h",op_i,vew_i,computed_rm,expected_rm);
    end
  endtask

  initial begin
    int w, sw;
    logic [63:0] data;
    seed = $urandom(seed);
    // Every legal shift count with unequal per-element amounts and signs,
    // walking bits, clipping boundaries, all modes and both output halves.
    for (int sew = 0; sew < 4; sew++) begin
      vew_i = vew_e'(sew); w = 8 << sew;
      foreach (operations[op]) begin
        op_i = operations[op];
        sw = (op_i inside {VNSRL,VNSRA,VNCLIP,VNCLIPU}) ? 2*w : w;
        if (sw > 64) continue;
        for (int mode = 0; mode < 4; mode++) begin
          vxrm_i = vxrm_t'(mode);
          for (int sh = 0; sh < sw; sh++)
            for (int pattern = 0; pattern < 80; pattern++)
              for (int sel = 0; sel < 2; sel++) begin
                operand_a_i = 0; operand_b_i = 0;
                for (int e = 0; e < 64/sw; e++) begin
                  data = 64'd1 << (pattern%sw);
                  if (pattern >= 64) begin
                    case (pattern%8)
                      0: data = 0;
                      1: data = mask_width(sw);
                      2: data = mask_width(w);
                      3: data = mask_width(w)+1;
                      4: data = (64'd1 << (w-1))-1;
                      5: data = 64'd1 << (w-1);
                      6: data = -(64'd1 << (w-1));
                      7: data = -(64'd1 << (w-1))-1;
                    endcase
                  end
                  if (e%2) data = ~data;
                  operand_b_i |= (data & mask_width(sw)) << (e*sw);
                  operand_a_i |= (64'(sh+3*e) & mask_width(sw)) << (e*sw);
                end
                valid_i = 1; narrowing_select_i = 1'(sel);
                check();
              end
        end
      end
    end
    $display("SHIFT_EDGES_PASS checks=%0d",checks);
    // Exhaust 16-bit narrowing input values at every shift and rounding mode.
    // Four distinct consecutive values per word; both clips and output halves.
    vew_i = EW8;
    for (int op = 0; op < 2; op++) begin
      op_i = op ? VNCLIPU : VNCLIP;
      for (int mode = 0; mode < 4; mode++) begin
        vxrm_i = vxrm_t'(mode);
        for (int sh = 0; sh < 16; sh++)
          for (int group = 0; group < 16384; group++) begin
            for (int e = 0; e < 4; e++) begin
              operand_a_i[16*e+:16] = 16'(sh+16*e);
              operand_b_i[16*e+:16] = 16'(4*group+e);
            end
            narrowing_select_i = 1'(group^sh^mode);
            check();
          end
      end
    end
    $display("SHIFT_EXHAUSTIVE_CLIP_PASS checks=%0d",checks);
    // Arbitrary external round bits also check the complete ALU interface,
    // independent of what the current rounding producer normally supplies.
    for (int sew = 0; sew < 4; sew++) begin
      vew_i = vew_e'(sew);
      foreach (operations[op]) begin
        op_i = operations[op];
        for (int n = 0; n < 4096; n++) begin
          operand_a_i = {$urandom,$urandom}; operand_b_i = {$urandom,$urandom};
          injected_rm = 8'($urandom); inject_rm = n[0];
          valid_i = n%17 != 0; mask_i = 8'($urandom); vm_i = n[1];
          narrowing_select_i = n[2]; vxrm_i = vxrm_t'(n%4);
          check();
        end
      end
    end
    $display("SHARED_ALU_SHIFT_PASS checks=%0d configurations=2",checks);
    $finish;
  end
endmodule
