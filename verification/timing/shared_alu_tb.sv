// SPDX-License-Identifier: SHL-0.51
// Frozen RTL miter plus an independent integer arithmetic model.
module shared_alu_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  elen_t operand_a_i, operand_b_i;
  logic valid_i, vm_i, narrowing_select_i;
  logic [7:0] mask_i, rm;
  ara_op_e op_i;
  vew_e vew_i;
  vxrm_t vxrm_i;
  elen_t result [2], reference [2];
  vxsat_t sat [2], ref_sat [2];
  longint unsigned checks = 0, model_checks = 0;
  int seed = 32'h1984a5c3;
  ara_op_e arithmetic_ops [32] = '{VADD, VADC, VMADC, VSUB, VSBC, VMSBC,
      VRSUB, VSADD, VSADDU, VSSUB, VSSUBU, VAADD, VAADDU, VASUB, VASUBU,
      VREDSUM, VWREDSUM, VWREDSUMU, VMIN, VMINU, VMAX, VMAXU,
      VREDMIN, VREDMINU, VREDMAX, VREDMAXU, VMSEQ, VMSNE, VMSLT, VMSLTU,
      VMSLE, VMSGT};
  fixed_p_rounding i_rounding (.r_o(rm), .*);
  for (genvar fixed_point = 0; fixed_point < 2; fixed_point++) begin : gen_config
    simd_alu #(.FixPtSupport(fixpt_support_e'(fixed_point))) i_dut
        (.result_o(result[fixed_point]), .vxsat_o(sat[fixed_point]), .*);
    simd_alu_reference #(.FixPtSupport(fixpt_support_e'(fixed_point))) i_reference
        (.result_o(reference[fixed_point]), .vxsat_o(ref_sat[fixed_point]), .*);
  end

  function automatic logic [63:0] width_mask(int width);
    return 64'hffff_ffff_ffff_ffff >> (64-width);
  endfunction

  task automatic check;
    logic modeled, fixed_op, signed_op, inc, condition, overflow;
    logic [63:0] expected, a, b, mask, value_bits;
    logic [7:0] expected_sat;
    logic signed [65:0] aa, bb, value, low, high;
    int width;
    #1;
    checks++;
    for (int cfg = 0; cfg < 2; cfg++) begin
      assert ({result[cfg], sat[cfg]} === {reference[cfg], ref_sat[cfg]})
        else $fatal(1, "ALU_MITER cfg=%0d op=%0d sew=%0d a=%h b=%h mask=%h vm=%b vxrm=%0d valid=%b got=%h/%h ref=%h/%h",
            cfg, op_i, vew_i, operand_a_i, operand_b_i, mask_i, vm_i, vxrm_i,
            valid_i, result[cfg], sat[cfg], reference[cfg], ref_sat[cfg]);
      modeled = op_i inside {VADD, VADC, VMADC, VSUB, VSBC, VMSBC, VRSUB,
          VSADD, VSADDU, VSSUB, VSSUBU, VAADD, VAADDU, VASUB, VASUBU,
          VREDSUM, VWREDSUM, VWREDSUMU, VMIN, VMINU, VMAX, VMAXU,
          VREDMIN, VREDMINU, VREDMAX, VREDMAXU, VMSEQ, VMSNE, VMSLT, VMSLTU,
          VMSLE, VMSLEU, VMSGT, VMSGTU};
      if (!modeled) continue;
      expected = 0;
      expected_sat = 0;
      width = 8 << unsigned'(vew_i);
      mask = width_mask(width);
      fixed_op = op_i inside {VSADD, VSADDU, VSSUB, VSSUBU, VAADD, VAADDU, VASUB, VASUBU};
      signed_op = op_i inside {VSADD, VSSUB, VAADD, VASUB, VMIN, VMAX,
          VREDMIN, VREDMAX, VMSLT, VMSLE, VMSGT};
      if (valid_i && vew_i <= EW64 && (!fixed_op || cfg)) begin
        for (int e = 0; e < 64/width; e++) begin
          a = (operand_a_i >> (e*width)) & mask;
          b = (operand_b_i >> (e*width)) & mask;
          aa = $signed({2'b0, a});
          bb = $signed({2'b0, b});
          if (signed_op) begin
            if (a[width-1]) aa -= 66'sd1 << width;
            if (b[width-1]) bb -= 66'sd1 << width;
          end
          value = bb + aa;
          inc = !vm_i && mask_i[e*(width/8)];
          case (op_i)
            VADC, VMADC: value = value + 66'(inc);
            VSUB, VSSUB, VSSUBU, VASUB, VASUBU: value = bb - aa;
            VSBC, VMSBC: value = bb - aa - 66'(inc);
            VRSUB: value = aa - bb;
            default:;
          endcase
          if (op_i inside {VMADC, VMSBC}) value = 66'd2 | 66'(value[width]);
          if (op_i inside {VAADD, VAADDU, VASUB, VASUBU}) begin
            case (vxrm_i)
              0: inc = value[0];
              1: inc = value[0] & value[1];
              2: inc = 0;
              3: inc = value[0] & !value[1];
            endcase
            value = (value >>> 1) + 66'(inc);
          end
          if (op_i inside {VSADD, VSADDU, VSSUB, VSSUBU}) begin
            low = signed_op ? -(66'sd1 << (width-1)) : 66'sd0;
            high = signed_op ? (66'sd1 << (width-1))-1 : (66'sd1 << width)-1;
            overflow = value < low || value > high;
            if (overflow) expected_sat |= 8'((op_i == VSSUB ? 64'd1 : width_mask(width/8))
                << (e*(width/8)));
            if (value < low) value = low;
            if (value > high) value = high;
          end
          if (op_i inside {VMIN, VMINU, VREDMIN, VREDMINU}) value = bb < aa ? bb : aa;
          if (op_i inside {VMAX, VMAXU, VREDMAX, VREDMAXU}) value = bb < aa ? aa : bb;
          if (op_i inside {VMSEQ, VMSNE, VMSLT, VMSLTU, VMSLE, VMSLEU, VMSGT, VMSGTU}) begin
            case (op_i)
              VMSEQ: condition = bb == aa;
              VMSNE: condition = bb != aa;
              VMSLT, VMSLTU: condition = bb < aa;
              VMSLE, VMSLEU: condition = bb <= aa;
              default: condition = bb > aa;
            endcase
            value = {64'b0, mask_i[e*(width/8)], condition};
          end
          value_bits = 64'(value) & mask;
          expected |= value_bits << (e*width);
        end
      end
      assert ({result[cfg], sat[cfg]} === {expected, expected_sat})
        else $fatal(1, "ALU_MODEL cfg=%0d op=%0d sew=%0d a=%h b=%h vxrm=%0d got=%h/%h expected=%h/%h",
            cfg, op_i, vew_i, operand_a_i, operand_b_i, vxrm_i,
            result[cfg], sat[cfg], expected, expected_sat);
      model_checks++;
    end
  endtask

  initial begin
    seed = $urandom(seed);
    valid_i = 1; vm_i = 1; mask_i = '1; vxrm_i = 0; narrowing_select_i = 0;
    // Exercise every opcode, including unchanged operations and disabled fixed point.
    for (int sew = 0; sew < 8; sew++) begin
      vew_i = vew_e'(sew);
      for (int op = 0; op < 256; op++) begin
        op_i = ara_op_e'(op);
        for (int trial = 0; trial < 512; trial++) begin
          operand_a_i = {$urandom, $urandom};
          operand_b_i = {$urandom, $urandom};
          if (trial < 128) begin
            operand_a_i = (64'd1 << (trial/2))-1;
            operand_b_i = trial[0] ? '1 : 64'd1;
          end
          valid_i = trial % 19 != 0;
          vm_i = 1'($urandom); mask_i = 8'($urandom);
          vxrm_i = vxrm_t'(trial % 4); narrowing_select_i = 1'(trial);
          check();
        end
      end
    end
    $display("SHARED_ALU_RANDOM_PASS checks=%0d model_checks=%0d", checks, model_checks);
    // Exhaust all 8-bit pairs, packed as distinct elements, with both mask-carry
    // states and all four rounding modes. This also detects cross-element carry.
    vew_i = EW8; valid_i = 1;
    foreach (arithmetic_ops[op]) begin
      op_i = arithmetic_ops[op];
      for (int mode = 0; mode < 4; mode++) begin
        vxrm_i = vxrm_t'(mode);
        vm_i = 0; mask_i = mode[0] ? 8'h55 : 8'haa;
        for (int a_group = 0; a_group < 32; a_group++)
          for (int b = 0; b < 256; b++) begin
            for (int e = 0; e < 8; e++) begin
              operand_a_i[e*8+:8] = 8'(a_group*8+e);
              operand_b_i[e*8+:8] = 8'(b);
            end
            check();
          end
      end
    end
    // Full-width equal-sign extremes and mixed-sign lanes for every arithmetic op.
    for (int sew = 0; sew < 4; sew++) begin
      vew_i = vew_e'(sew);
      foreach (arithmetic_ops[op]) begin
        op_i = arithmetic_ops[op];
        for (int pattern = 0; pattern < 64; pattern++) begin
          for (int e = 0; e < (8 >> sew); e++) begin
            operand_a_i = '0; operand_b_i = '0;
            for (int bitpos = 0; bitpos < 64; bitpos++) begin
              operand_a_i[bitpos] = pattern[0] ^ (bitpos % (8 << sew) == (8 << sew)-1);
              operand_b_i[bitpos] = pattern[1] ^ (bitpos % (8 << sew) == (8 << sew)-1);
            end
            operand_a_i ^= 64'(pattern[2]) << (e*(8 << sew));
            operand_b_i ^= 64'(pattern[3]) << (e*(8 << sew));
            vxrm_i = vxrm_t'(pattern >> 4);
            mask_i = 8'(1 << (e*(1 << sew))); vm_i = 0;
            check();
          end
        end
      end
    end
    $display("SHARED_ALU_PASS checks=%0d model_checks=%0d configurations=2", checks, model_checks);
    $finish;
  end
endmodule
