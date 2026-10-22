`timescale 1ns/1ps

module fp16_int8_cast_tb;
  import fpnew_pkg::*;

  localparam fmt_logic_t FpFormats = 6'b111000;
  localparam ifmt_logic_t IntFormats =
      get_conv_lane_int_formats(64, FpFormats, 4'b1111, 0);
  localparam status_t Exact = '0;
  localparam status_t Inexact = '{NX: 1'b1, default: 1'b0};
  localparam status_t Invalid = '{NV: 1'b1, default: 1'b0};

  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;

  logic [63:0] operand, result;
  roundmode_e rm;
  fp_format_e src_fmt;
  int_format_e int_fmt;
  logic unsigned_cast, in_valid, in_ready, out_valid, mask_in, mask_out;
  logic [7:0] tag_in, tag_out;
  status_t status;
  int cases = 0;
  int failures = 0;
  int csv, first_failure;

  fpnew_cast_multi #(
    .FpFmtConfig(FpFormats),
    .IntFmtConfig(IntFormats),
    .NumPipeRegs(3),
    .PipeConfig(DISTRIBUTED),
    .TagType(logic [7:0]),
    .AuxType(logic)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .operands_i(operand), .is_boxed_i('1),
    .rnd_mode_i(rm), .op_i(F2I), .op_mod_i(unsigned_cast),
    .src_fmt_i(src_fmt), .dst_fmt_i(src_fmt), .int_fmt_i(int_fmt),
    .tag_i(tag_in), .mask_i(mask_in), .aux_i(1'b0),
    .in_valid_i(in_valid), .in_ready_o(in_ready), .flush_i(1'b0),
    .result_o(result), .status_o(status), .extension_bit_o(),
    .tag_o(tag_out), .mask_o(mask_out), .aux_o(),
    .out_valid_o(out_valid), .out_ready_i(1'b1), .busy_o()
  );

  // One transaction at a time keeps the internal rounding probes associated
  // with the returned tag. Vector cases check packed bits; scalar cases also
  // check sign extension across the full cast-core output width.
  task automatic check_cast(
      input string name,
      input logic [63:0] bits,
      input fp_format_e source_format,
      input int_format_e integer_format,
      input logic is_unsigned,
      input roundmode_e rounding,
      input logic [63:0] expected,
      input status_t expected_flags,
      input logic active = 1'b1,
      input logic full_width = 1'b1
  );
    logic [63:0] result_mask;
    bit failed;
    string record;
    @(negedge clk);
    operand = bits;
    src_fmt = source_format;
    int_fmt = integer_format;
    unsigned_cast = is_unsigned;
    rm = rounding;
    mask_in = active;
    tag_in = 8'(cases);
    in_valid = 1;
    do @(posedge clk); while (!in_ready);
    @(negedge clk);
    in_valid = 0;
    do @(posedge clk); while (!out_valid);

    result_mask = full_width ? '1 :
        64'hffff_ffff_ffff_ffff >> (64 - int_width(integer_format));
    failed = ((result & result_mask) !== expected) ||
             (status !== expected_flags) || (mask_out !== active) ||
             (tag_out !== tag_in);
    record = $sformatf(
        "case=%0d name=%s src=%016h src_fmt=%0d int_width=%0d unsigned=%0b rm=%0d mask=%0b result=%016h expected=%016h flags=%02h expected_flags=%02h exp=%0d of_before=%0b of_after=%0b rs=%02b rounded_abs=%016h rounded_int=%016h special=%0b tag=%0d mask_out=%0b full_width=%0b raw_result=%016h",
        cases, name, bits, source_format, int_width(integer_format), is_unsigned,
        rounding, active, result & result_mask, expected, status, expected_flags,
        $signed(dut.input_exp_q), dut.of_before_round, dut.of_after_round,
        dut.int_round_sticky_bits, dut.rounded_abs, dut.rounded_int_res,
        dut.int_result_is_special, tag_out, mask_out, full_width, result);
    $display("%s %s", failed ? "FAIL" : "PASS", record);
    $fdisplay(csv, "%0d,%s,%016h,%0d,%0d,%0b,%0d,%0b,%016h,%016h,%02h,%02h,%0d,%0b,%0b,%02b,%016h,%016h,%0b,%0b,%0b,%016h",
        cases, name, bits, source_format, int_width(integer_format), is_unsigned,
        rounding, active, result & result_mask, expected, status, expected_flags,
        $signed(dut.input_exp_q), dut.of_before_round, dut.of_after_round,
        dut.int_round_sticky_bits, dut.rounded_abs, dut.rounded_int_res,
        dut.int_result_is_special, failed, full_width, result);
    if (failed) begin
      if (failures == 0) begin
        $display("FIRST_FAILURE %s", record);
        $fdisplay(first_failure, "%s", record);
        $fflush(first_failure);
      end
      failures++;
    end
    cases++;
    $fflush(csv);
  endtask

  task automatic half_cast(
      input string name, input logic [15:0] bits, input logic is_unsigned,
      input roundmode_e rounding, input logic [7:0] expected,
      input status_t expected_flags, input logic active = 1'b1
  );
    check_cast(name, {48'hffff_ffff_ffff, bits}, FP16, INT8, is_unsigned,
               rounding, {56'b0, expected}, expected_flags, active, 0);
  endtask

  initial begin
    csv = $fopen("results.csv", "w");
    first_failure = $fopen("first_failure.log", "w");
    if (!csv || !first_failure) $fatal(1, "Cannot open evidence files");
    $fdisplay(csv, "case,name,src,src_fmt,int_width,unsigned,rm,mask,result,expected,flags,expected_flags,exp,of_before,of_after,rs,rounded_abs,rounded_int,special,failed,full_width,raw_result");
    if (!IntFormats[INT8] || FpFormats[FP8] || FpFormats[FP8ALT])
      $fatal(1, "Expected scoped FP16/INT8 support without FP8");
    $display("CONFIG fp_formats=%b int_formats=%b pipe_regs=3 distributed=1 flags_order=NV_DZ_OF_UF_NX", FpFormats, IntFormats);
    operand = '0;
    src_fmt = FP16;
    int_fmt = INT8;
    unsigned_cast = 0;
    rm = RNE;
    mask_in = 1;
    tag_in = '0;
    in_valid = 0;
    repeat (3) @(negedge clk);
    rst_n = 1;

    half_cast("s_min_exact_rtz", 16'hd800, 0, RTZ, 8'h80, Exact);
    half_cast("s_min_exact_rdn", 16'hd800, 0, RDN, 8'h80, Exact);
    half_cast("s_min_exact_rne", 16'hd800, 0, RNE, 8'h80, Exact);
    half_cast("s_min_exact_rup", 16'hd800, 0, RUP, 8'h80, Exact);
    half_cast("s_min_quarter_rtz", 16'hd802, 0, RTZ, 8'h80, Inexact);
    half_cast("s_min_quarter_rdn", 16'hd802, 0, RDN, 8'h80, Invalid);
    half_cast("s_min_quarter_rne", 16'hd802, 0, RNE, 8'h80, Inexact);
    half_cast("s_min_quarter_rup", 16'hd802, 0, RUP, 8'h80, Inexact);

    half_cast("s_positive_tie_rtz", 16'h57f8, 0, RTZ, 8'h7f, Inexact);
    half_cast("s_positive_tie_rdn", 16'h57f8, 0, RDN, 8'h7f, Inexact);
    half_cast("s_positive_tie_rne", 16'h57f8, 0, RNE, 8'h7f, Invalid);
    half_cast("s_positive_tie_rup", 16'h57f8, 0, RUP, 8'h7f, Invalid);
    half_cast("u_positive_tie_rtz", 16'h5bfc, 1, RTZ, 8'hff, Inexact);
    half_cast("u_positive_tie_rdn", 16'h5bfc, 1, RDN, 8'hff, Inexact);
    half_cast("u_positive_tie_rne", 16'h5bfc, 1, RNE, 8'hff, Invalid);
    half_cast("u_positive_tie_rup", 16'h5bfc, 1, RUP, 8'hff, Invalid);

    half_cast("s_positive_inf", 16'h7c00, 0, RNE, 8'h7f, Invalid);
    half_cast("s_negative_inf", 16'hfc00, 0, RNE, 8'h80, Invalid);
    half_cast("u_positive_inf", 16'h7c00, 1, RNE, 8'hff, Invalid);
    half_cast("u_negative_inf", 16'hfc00, 1, RNE, 8'h00, Invalid);
    half_cast("s_negative_tie_inside", 16'hd7f8, 0, RNE, 8'h80, Inexact);
    half_cast("s_min_half_rne", 16'hd804, 0, RNE, 8'h80, Inexact);
    half_cast("s_min_three_quarters_rne", 16'hd806, 0, RNE, 8'h80, Invalid);
    half_cast("s_negative_overflow", 16'hd808, 0, RTZ, 8'h80, Invalid);
    half_cast("s_positive_overflow", 16'h5800, 0, RTZ, 8'h7f, Invalid);
    half_cast("u_negative_fraction_rtz", 16'hb400, 1, RTZ, 8'h00, Inexact);
    half_cast("u_negative_fraction_rdn", 16'hb400, 1, RDN, 8'h00, Invalid);
    half_cast("u_negative_wrap_rne", 16'hdbfc, 1, RNE, 8'h00, Invalid);
    half_cast("u_negative_zero", 16'h8000, 1, RNE, 8'h00, Exact);
    half_cast("s_negative_zero", 16'h8000, 0, RDN, 8'h00, Exact);
    half_cast("s_min_exact_rmm", 16'hd800, 0, RMM, 8'h80, Exact);
    half_cast("s_min_half_rmm", 16'hd804, 0, RMM, 8'h80, Invalid);
    // The cast core forwards masks; the SIMD wrapper, not this unit, suppresses flags.
    half_cast("inactive_raw_negative_inf", 16'hfc00, 0, RNE, 8'h80, Invalid, 0);

    check_cast("s_int16_min_exact", 64'hc0e0_0000_0000_0000, FP64, INT16, 0, RTZ,
               64'hffff_ffff_ffff_8000, Exact);
    check_cast("s_int32_min_exact", 64'hc1e0_0000_0000_0000, FP64, INT32, 0, RTZ,
               64'hffff_ffff_8000_0000, Exact);
    check_cast("s_int64_min_exact", 64'hc3e0_0000_0000_0000, FP64, INT64, 0, RTZ,
               64'h8000_0000_0000_0000, Exact);

    if ($test$plusargs("CAST_EXTRA_BOUNDARIES")) begin
      // Adjacent FP64 values at these magnitudes are integral: all five
      // architectural rounding modes must preserve the same result and flags.
      for (int mode = 0; mode <= 4; mode++) begin
        half_cast($sformatf("extra_u_negative_zero_rm%0d", mode), 16'h8000,
                  1, roundmode_e'(mode), 8'h00, Exact);
        half_cast($sformatf("extra_u_positive_zero_rm%0d", mode), 16'h0000,
                  1, roundmode_e'(mode), 8'h00, Exact);
        check_cast($sformatf("extra_s64_min_exact_rm%0d", mode),
                   64'hc3e0_0000_0000_0000, FP64, INT64, 0, roundmode_e'(mode),
                   64'h8000_0000_0000_0000, Exact);
        check_cast($sformatf("extra_s64_min_inside_rm%0d", mode),
                   64'hc3df_ffff_ffff_ffff, FP64, INT64, 0, roundmode_e'(mode),
                   64'h8000_0000_0000_0400, Exact);
        check_cast($sformatf("extra_s64_min_outside_rm%0d", mode),
                   64'hc3e0_0000_0000_0001, FP64, INT64, 0, roundmode_e'(mode),
                   64'h8000_0000_0000_0000, Invalid);
        check_cast($sformatf("extra_s64_positive_inside_rm%0d", mode),
                   64'h43df_ffff_ffff_ffff, FP64, INT64, 0, roundmode_e'(mode),
                   64'h7fff_ffff_ffff_fc00, Exact);
        check_cast($sformatf("extra_s64_positive_outside_rm%0d", mode),
                   64'h43e0_0000_0000_0000, FP64, INT64, 0, roundmode_e'(mode),
                   64'h7fff_ffff_ffff_ffff, Invalid);
        check_cast($sformatf("extra_u64_positive_inside_rm%0d", mode),
                   64'h43ef_ffff_ffff_ffff, FP64, INT64, 1, roundmode_e'(mode),
                   64'hffff_ffff_ffff_f800, Exact);
        check_cast($sformatf("extra_u64_positive_outside_rm%0d", mode),
                   64'h43f0_0000_0000_0000, FP64, INT64, 1, roundmode_e'(mode),
                   64'hffff_ffff_ffff_ffff, Invalid);
        check_cast($sformatf("extra_u64_negative_large_rm%0d", mode),
                   64'hc3ef_ffff_ffff_ffff, FP64, INT64, 1, roundmode_e'(mode),
                   64'h0000_0000_0000_0000, Invalid);
      end
    end

    $fclose(csv);
    $fclose(first_failure);
    $display("SUMMARY fp16_int8_cast cases=%0d failures=%0d", cases, failures);
    if (failures != 0) $fatal(1, "fp16_int8_cast mismatches; see first_failure.log and results.csv");
    $display("PASS fp16_int8_cast");
    $finish;
  end

  initial begin
    #20000;
    $fatal(1, "fp16_int8_cast watchdog timeout");
  end
endmodule
