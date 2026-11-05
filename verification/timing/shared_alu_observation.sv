// SPDX-License-Identifier: SHL-0.51
// Simulation-only observation rule. Never hide a known-bit disagreement.
module shared_alu_observation import ara_pkg::*; import rvv_pkg::*; (
  input elen_t operand_a_i, operand_b_i, actual_result, expected_result,
  input vxsat_t actual_sat, expected_sat,
  input logic [7:0] rm, observed_be_i,
  input logic narrowing_select_i,
  input ara_op_e op_i,
  input vew_e vew_i,
  output logic check_ok,
  output logic [7:0] inactive_x_bytes
);
  function automatic logic [63:0] low_mask(int width);
    return 64'hffff_ffff_ffff_ffff >> (64-width);
  endfunction
  always_comb begin
    automatic logic shift_op = op_i inside {VSLL,VSRL,VSRA,VSSRL,VSSRA,VNSRL,VNSRA,VNCLIP,VNCLIPU};
    automatic logic narrow = op_i inside {VNSRL,VNSRA,VNCLIP,VNCLIPU};
    automatic logic rounded_op = op_i inside {VSSRL,VSSRA,VNCLIP,VNCLIPU};
    automatic int width = 8 << int'(vew_i);
    automatic int source_width = narrow ? 2*width : width;
    check_ok = 1'b1;
    inactive_x_bytes = '0;
    if ($isunknown({op_i,vew_i,narrowing_select_i})) check_ok = 1'b0;
    if (shift_op && $isunknown(observed_be_i)) check_ok = 1'b0;
    for (int b = 0; b < 8; b++) begin
      automatic int destination_element = b/(width/8);
      automatic int source_element = narrow ? destination_element/2 : destination_element;
      automatic int offset = source_element*source_width;
      automatic logic eligible = shift_op && source_width <= 64 &&
          (!narrow || (destination_element%2 == int'(narrowing_select_i)));
      automatic logic unknown_source = eligible &&
          ($isunknown((operand_a_i >> offset) & low_mask(int'(vew_i)+3+int'(narrow))) ||
           $isunknown((operand_b_i >> offset) & low_mask(source_width)) ||
           (rounded_op && $isunknown(rm[source_element])));
      automatic logic inactive_unknown = eligible && unknown_source && observed_be_i[b] === 1'b0;
      if (shift_op && observed_be_i[b] === 1'b1 &&
          $isunknown({actual_result[8*b+:8],expected_result[8*b+:8],actual_sat[b],expected_sat[b]}))
        check_ok = 1'b0;
      for (int bitpos = 0; bitpos < 9; bitpos++) begin
        automatic logic got = bitpos == 8 ? actual_sat[b] : actual_result[8*b+bitpos];
        automatic logic want = bitpos == 8 ? expected_sat[b] : expected_result[8*b+bitpos];
        if (got !== want) begin
          if (inactive_unknown && $isunknown({got,want})) inactive_x_bytes[b] = 1'b1;
          else check_ok = 1'b0;
        end
      end
    end
  end
endmodule
