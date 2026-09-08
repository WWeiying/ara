// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module simd_alu_equivalence_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  elen_t operand_a_i, operand_b_i, result_o, ref_result;
  logic valid_i = 1, vm_i = 1, narrowing_select_i = 0;
  logic [7:0] mask_i = '1, rm;
  ara_op_e op_i;
  vew_e vew_i;
  vxrm_t vxrm_i;
  vxsat_t vxsat_o, ref_sat;
  longint unsigned checks = 0;
  int seed = 32'h6a09e667;
  ara_op_e operations [6] = '{VAADD, VAADDU, VASUB, VASUBU, VNCLIP, VNCLIPU};

  fixed_p_rounding i_rounding (.r_o(rm), .*);
  simd_alu i_dut (.*);
  simd_alu_reference i_reference (.result_o(ref_result), .vxsat_o(ref_sat), .*);

  function automatic logic [63:0] width_mask(int width);
    return 64'hffff_ffff_ffff_ffff >> (64 - width);
  endfunction

  task automatic check_result;
    logic [63:0] expected, expected_sat, a, b, mask;
    logic signed [65:0] wide_a, wide_b, value, minimum, maximum;
    logic increment;
    int width, source_width, shift, destination;
    #1;
    checks++;
    assert ({result_o, vxsat_o} === {ref_result, ref_sat})
      else $fatal(1, "ALU equivalence op=%0d sew=%0d a=%h b=%h vxrm=%0d select=%0d got=%h/%h ref=%h/%h",
          op_i, vew_i, operand_a_i, operand_b_i, vxrm_i, narrowing_select_i,
          result_o, vxsat_o, ref_result, ref_sat);
    expected = '0;
    expected_sat = '0;
    width = 8 << unsigned'(vew_i);
    mask = width_mask(width);
    if (valid_i && op_i inside {VAADD, VAADDU, VASUB, VASUBU}) begin
      for (int lane = 0; lane < 64 / width; lane++) begin
        a = (operand_a_i >> (lane * width)) & mask;
        b = (operand_b_i >> (lane * width)) & mask;
        wide_a = $signed({2'b0, a});
        wide_b = $signed({2'b0, b});
        if (op_i inside {VAADD, VASUB}) begin
          if (a[width-1]) wide_a -= 66'sd1 << width;
          if (b[width-1]) wide_b -= 66'sd1 << width;
        end
        value = op_i inside {VAADD, VAADDU} ? wide_b + wide_a : wide_b - wide_a;
        case (vxrm_i)
          0: increment = value[0];
          1: increment = value[0] && value[1];
          2: increment = 0;
          3: increment = value[0] && !value[1];
        endcase
        value = (value >>> 1) + $signed({65'b0, increment});
        expected |= (64'(value) & mask) << (lane * width);
      end
    end else if (valid_i && op_i inside {VNCLIP, VNCLIPU}) begin
      source_width = 2 * width;
      for (int lane = 0; lane < 64 / source_width; lane++) begin
        b = (operand_b_i >> (lane * source_width)) & width_mask(source_width);
        shift = int'(operand_a_i >> (lane * source_width)) & (source_width - 1);
        value = $signed({2'b0, b});
        if (op_i == VNCLIP && b[source_width-1]) value -= 66'sd1 << source_width;
        value = (value >>> shift) + $signed({65'b0, rm[lane]});
        minimum = op_i == VNCLIP ? -(66'sd1 << (width - 1)) : 66'sd0;
        maximum = op_i == VNCLIP ? (66'sd1 << (width - 1)) - 1 : (66'sd1 << width) - 1;
        destination = (2 * lane + int'(narrowing_select_i)) * width;
        if (value < minimum || value > maximum)
          expected_sat |= width_mask(width / 8) << (destination / 8);
        if (value < minimum) value = minimum;
        if (value > maximum) value = maximum;
        expected |= (64'(value) & mask) << destination;
      end
    end
    assert ({result_o, vxsat_o} === {expected, expected_sat[7:0]})
      else $fatal(1, "ALU arithmetic model mismatch op=%0d sew=%0d a=%h b=%h rm=%h vxrm=%0d got=%h/%h expected=%h/%h",
          op_i, vew_i, operand_a_i, operand_b_i, rm, vxrm_i,
          result_o, vxsat_o, expected, expected_sat[7:0]);
  endtask

  task automatic check_edges;
    logic [63:0] values [8];
    logic [63:0] a, b;
    int width, source_width;
    for (int sew = 0; sew < 4; sew++) begin
      width = 8 << sew;
      vew_i = vew_e'(sew);
      for (int op = 0; op < (sew == 3 ? 4 : 6); op++) begin
        op_i = operations[op];
        source_width = op < 4 ? width : 2 * width;
        values = '{64'd0, 64'd1, width_mask(source_width),
            width_mask(source_width) - 1, 64'h1 << (width - 1),
            (64'h1 << (width - 1)) - 1, width_mask(source_width) ^ width_mask(width - 1),
            (width_mask(source_width) ^ width_mask(width - 1)) - 1};
        for (int mode = 0; mode < 4; mode++) begin
          vxrm_i = vxrm_t'(mode);
          for (int ai = 0; ai < (op < 4 ? 8 : source_width); ai++)
            for (int bi = 0; bi < 8; bi++)
              for (int select = 0; select < 2; select++) begin
                a = op < 4 ? values[ai] : 64'(ai);
                b = values[bi];
                operand_a_i = '0;
                operand_b_i = '0;
                for (int lane = 0; lane < 64 / source_width; lane++) begin
                  operand_a_i |= a << (lane * source_width);
                  operand_b_i |= b << (lane * source_width);
                end
                narrowing_select_i = 1'(select);
                check_result();
              end
        end
      end
    end
  endtask

  initial begin
    seed = $urandom(seed);
    check_edges();
    if ($test$plusargs("EDGES_ONLY")) begin
      $display("SIMD ALU equivalence PASS directed_checks=%0d", checks);
      $finish;
    end
    // Exhaust every 8-bit averaging operand pair and all rounding modes.
    vew_i = EW8;
    for (int op = 0; op < 4; op++) begin
      op_i = operations[op];
      for (int mode = 0; mode < 4; mode++) begin
        vxrm_i = vxrm_t'(mode);
        for (int a = 0; a < 256; a++)
          for (int b = 0; b < 256; b++) begin
            operand_a_i = {8{8'(a)}};
            operand_b_i = {8{8'(b)}};
            check_result();
          end
      end
    end
    $display("ALU exhaustive EW8 averaging PASS checks=%0d", checks);
    // All 16-bit narrowing inputs, legal shifts and rounding modes.
    for (int op = 4; op < 6; op++) begin
      op_i = operations[op];
      for (int mode = 0; mode < 4; mode++) begin
        vxrm_i = vxrm_t'(mode);
        for (int shift = 0; shift < 16; shift++)
          for (int b = 0; b < 65536; b++) begin
            narrowing_select_i = 1'(b ^ shift);
            operand_a_i = {4{16'(shift)}};
            operand_b_i = {4{16'(b)}};
            check_result();
          end
      end
    end
    $display("ALU exhaustive EW8 narrowing PASS checks=%0d", checks);
    for (int sew = 0; sew < 4; sew++) begin
      vew_i = vew_e'(sew);
      for (int op = 0; op < (sew == 3 ? 4 : 6); op++) begin
        op_i = operations[op];
        for (int trial = 0; trial < 20000; trial++) begin
          operand_a_i = {$urandom, $urandom};
          operand_b_i = {$urandom, $urandom};
          vxrm_i = vxrm_t'(trial % 4);
          narrowing_select_i = 1'(trial);
          valid_i = trial % 17 != 0;
          vm_i = 1'($urandom);
          mask_i = 8'($urandom);
          check_result();
        end
      end
    end
    $display("SIMD ALU equivalence PASS checks=%0d", checks);
    $finish;
  end
endmodule
