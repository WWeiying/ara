`timescale 1ns/1ps

module fp16_conv_mask_tb;
  import fpnew_pkg::*;
`ifdef CONV_MASK_FINE8
  localparam fmt_logic_t Formats = 6'b111100;
  localparam bit Fine8 = 1;
`else
  localparam fmt_logic_t Formats = 6'b111000;
  localparam bit Fine8 = 0;
`endif
`ifdef CONV_MASK_SCALAR_ONLY
  localparam bit Vectors = 0;
`else
  localparam bit Vectors = 1;
`endif
  localparam int Lanes = max_num_lanes(64, Formats, 1);
  localparam int MaskBits = max_num_lanes(64, Formats, Vectors);
  typedef logic [MaskBits-1:0] mask_t;
  typedef logic [Lanes-1:0] lane_mask_t;
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  logic [num_operands(CONV)-1:0][63:0] operands;
  logic [63:0] result;
  mask_t mask;
  operation_e op;
  fp_format_e src_fmt, dst_fmt;
  int_format_e int_fmt;
  logic op_mod, vectorial;
  logic [15:0] tag_in, tag_out;
  logic in_valid, in_ready, out_valid, out_ready, busy;
  status_t status;
  status_t [Lanes-1:0] raw_status;
  logic [Lanes-1:0][63:0] raw_operand;
  logic [Lanes-1:0] signalling;
  logic [63:0] expected_data [2048], checked_bits [2048];
  status_t expected_flags [2048];
  lane_mask_t expected_masks [2048];
  bit expected_unknown [2048];
  string names [2048];
  int cycle = 0, sent = 0, received = 0, failures = 0;
  int first_failure, probes;
  int stalls = 0, input_stalls = 0, adjacent = 0;
  bit stall_mode = 0, held = 0, prior_accept = 0;
  bit focused;
  logic [63:0] held_result;
  status_t held_status;
  logic [15:0] held_tag;

  fpnew_opgroup_multifmt_slice #(
    .OpGroup(CONV), .Width(64), .FpFmtConfig(Formats), .IntFmtConfig(4'b1111),
    .EnableVectors(Vectors), .NumPipeRegs(2), .PipeConfig(DISTRIBUTED),
    .TagType(logic [15:0])
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .hart_id_i('0), .operands_i(operands),
    .is_boxed_i('1), .rnd_mode_i(RNE), .op_i(op), .op_mod_i(op_mod),
    .src_fmt_i(src_fmt), .dst_fmt_i(dst_fmt), .int_fmt_i(int_fmt),
    .vectorial_op_i(vectorial), .tag_i(tag_in), .simd_mask_i(mask),
    .in_valid_i(in_valid), .in_ready_o(in_ready), .flush_i(1'b0),
    .result_o(result), .status_o(status), .extension_bit_o(), .tag_o(tag_out),
    .out_valid_o(out_valid), .out_ready_i(out_ready), .busy_o(busy)
  );

  // Test masks are physical finest-16-bit units. The optional FP8 configuration
  // duplicates each physical unit into its two byte positions, not into lanes.
  function automatic mask_t physical16(input logic [3:0] m);
    if (Fine8) return mask_t'({{2{m[3]}}, {2{m[2]}}, {2{m[1]}}, {2{m[0]}}});
    return mask_t'(m);
  endfunction

  task automatic fail(input string reason);
    if (failures == 0) begin
      $display("FIRST_FAILURE cycle=%0d %s", cycle, reason);
      $fdisplay(first_failure, "cycle=%0d %s", cycle, reason);
      $fflush(first_failure);
    end
    failures++;
    $display("FAIL cycle=%0d %s", cycle, reason);
  endtask

  task automatic send(
      input string name, input operation_e operation,
      input fp_format_e sf, df, input int_format_e integer_format,
      input logic [63:0] bits, input mask_t enables,
      input logic [63:0] data, data_mask, input status_t flags,
      input lane_mask_t masks,
      input bit modifier = 0, input bit vec = 1,
      input logic [63:0] b = '0, c = '0, input bit unknown_flags = 0
  );
    @(negedge clk);
    if (sent >= 2048) $fatal(1, "scoreboard capacity");
    names[sent] = name;
    expected_data[sent] = data;
    checked_bits[sent] = data_mask;
    expected_flags[sent] = flags;
    expected_masks[sent] = masks;
    expected_unknown[sent] = unknown_flags;
    operands = {c, b, bits};
    op = operation;
    src_fmt = sf;
    dst_fmt = df;
    int_fmt = integer_format;
    op_mod = modifier;
    vectorial = vec;
    mask = enables;
    tag_in = 16'(sent);
    in_valid = 1;
    do @(posedge clk); while (!in_ready);
    sent++;
  endtask

  always @(negedge clk)
    out_ready = !stall_mode || (cycle % 9 >= 5);

  always @(posedge clk) begin
    if (rst_n) begin
      cycle++;
      if (cycle > 10000) $fatal(1, "bounded unit timeout");
      if (held && (!out_valid || result !== held_result ||
                   status !== held_status || tag_out !== held_tag))
        fail("output changed under backpressure");
      held = out_valid && !out_ready;
      held_result = result;
      held_status = status;
      held_tag = tag_out;
      if (held) stalls++;
      if (in_valid && !in_ready) input_stalls++;
      if (in_valid && in_ready && prior_accept) adjacent++;
      prior_accept = in_valid && in_ready;
      if (out_valid && out_ready) begin
        if (tag_out !== 16'(received))
          fail($sformatf("output order tag=%0d expected=%0d", tag_out, received));
        if ((result & checked_bits[received]) !== expected_data[received])
          fail($sformatf("data name=%s tag=%0d got=%h expected=%h checked=%h",
               names[received], tag_out, result, expected_data[received], checked_bits[received]));
        if (expected_unknown[received] ? !$isunknown(status) : status !== expected_flags[received])
          fail($sformatf("status name=%s tag=%0d got=%h expected=%h expect_x=%b",
               names[received], tag_out, status, expected_flags[received], expected_unknown[received]));
        if ((dut.lane_masks & dut.lane_out_valid) !==
            (expected_masks[received] & dut.lane_out_valid))
          fail($sformatf("mask name=%s tag=%0d got=%b expected=%b valid=%b",
               names[received], tag_out, dut.lane_masks, expected_masks[received], dut.lane_out_valid));
        $display("RESULT cycle=%0d tag=%0d name=%s result=%h flags=%h expected=%h raw0=%h raw1=%h masks=%b valid=%b",
                 cycle, tag_out, names[received], result, status, expected_flags[received],
                 raw_status[0], raw_status[1], dut.lane_masks, dut.lane_out_valid);
        received++;
      end
    end
  end

  for (genvar l = 0; l < Lanes; l++) begin : probe_lane
    if (l == 0 || Vectors) begin : active
      assign raw_status[l] = dut.gen_num_lanes[l].active_lane.op_status;
      assign raw_operand[l] = 64'(dut.gen_num_lanes[l].active_lane.local_operands[0]);
      assign signalling[l] = dut.gen_num_lanes[l].active_lane.lane_instance.i_fpnew_cast_multi.info_q.is_signalling;
    end else begin : inactive
      assign raw_status[l] = '0;
      assign raw_operand[l] = '0;
      assign signalling[l] = 0;
    end
    always @(posedge clk) begin
      if (rst_n && (in_valid || out_valid || busy))
        $fdisplay(probes, "%0t,%0d,%0d,%b,%b,%0d,%0d,%0d,%0d,%0d,%b,%h,%b,%0d,%b,%h,%h,%b,%b,%h",
          $time, cycle, l, in_valid, in_ready, tag_in, op, src_fmt, dst_fmt, int_fmt,
          mask, raw_operand[l], dut.lane_out_valid[l], dut.lane_tags[l], signalling[l],
          raw_status[l], dut.lane_status[l], dut.lane_masks[l], out_ready, status);
    end
  end

  initial begin
    first_failure = $fopen("first_failure.log", "w");
    probes = $fopen("lane_probes.csv", "w");
    if (!first_failure || !probes) $fatal(1, "cannot open evidence files");
    $fdisplay(probes, "time,cycle,lane,in_valid,in_ready,in_tag,op,srcfmt,dstfmt,intfmt,in_mask,input_operand,out_valid,out_tag,out_signalling,raw_status,lane_status,lane_mask,out_ready,merged_status");
    focused = $test$plusargs("CONV_FOCUSED");
    $display("CONFIG fp_formats=%b mask_bits=%0d vectors=%b pipe_regs=2 distributed=1 focused=%b", Formats, MaskBits, Vectors, focused);
    // Real system inputs are unknown before reset propagation at time zero.
    #1;
    operands = '0;
    mask = '0;
    tag_in = '0;
    op = F2F;
    src_fmt = FP32;
    dst_fmt = FP16;
    int_fmt = INT16;
    op_mod = 0;
    vectorial = Vectors;
    in_valid = 0;
    out_ready = 1;
    repeat (3) @(negedge clk);
    rst_n = 1;
    for (int phase = 0; phase < 2; phase++) begin
      stall_mode = (phase != 0);
      if (Vectors) begin
        send("narrow_upper_snan_nv_loss", F2F, FP32, FP16, INT16,
             64'h7f8000013f800000, physical16(4'b0101), 64'h7e003c00, 64'hffffffff, 5'h10, 3);
        send("widen_tail_x_must_be_masked", F2F, FP16, FP32, INT32,
             64'h00000000xxxx3c00, physical16(4'b0011), 64'h3f800000, 64'hffffffff, 0, 1);
        send("widen_tail_snan_must_be_masked", F2F, FP16, FP32, INT32,
             64'h000000007c013c00, physical16(4'b0011), 64'h7fc000003f800000, '1, 0, 1);
        send("widen_active_x_control", F2F, FP16, FP32, INT32,
             64'h00000000xxxx3c00, physical16(4'b0101), 64'h3f800000, 64'hffffffff, 0, 3,
             0, 1, 0, 0, 1);
        for (int m = 0; m < 16; m++) begin
          automatic logic [3:0] pm = 4'(m);
          automatic lane_mask_t pair_mask = lane_mask_t'({pm[2], pm[0]});
          automatic status_t nv_upper = pm[2] ? 5'h10 : 0;
          send($sformatf("narrow_mask_%x", m), F2F, FP32, FP16, INT16,
               64'h7f8000013f800000, physical16(pm), 64'h7e003c00, 64'hffffffff, nv_upper, pair_mask);
          send($sformatf("widen_mask_%x", m), F2F, FP16, FP32, INT32,
               64'h000000007c013c00, physical16(pm), 64'h7fc000003f800000, '1, nv_upper, pair_mask);
          send($sformatf("widen_upper_half_%x", m), F2F, FP16, FP32, INT32,
               64'h7c013c0000000000, physical16(pm), 64'h7fc000003f800000, '1, nv_upper, pair_mask, 1);
          send($sformatf("same_fp32_%x", m), F2F, FP32, FP32, INT32,
               64'h7f8000013f800000, physical16(pm), 64'h7fc000003f800000, '1, nv_upper, pair_mask);
          if (!focused) send($sformatf("same_fp16_%x", m), F2F, FP16, FP16, INT16,
               64'h3c007c013c003c00, physical16(pm), 64'h3c007e003c003c00, '1, nv_upper, lane_mask_t'(pm));
          send($sformatf("subnormal_round_%x", m), F2F, FP32, FP16, INT16,
               64'h3300000100000001, physical16(pm), 64'h00010000, 64'hffffffff,
               (pm[0] || pm[2]) ? 5'h03 : 0, pair_mask);
          send($sformatf("normal_boundary_%x", m), F2F, FP32, FP16, INT16,
               64'h7f800001387fffff, physical16(pm), 64'h7e000400, 64'hffffffff,
               nv_upper | (pm[0] ? 5'h01 : 0), pair_mask);
          if (!focused) begin
          for (int u = 0; u < 2; u++) begin
            send($sformatf("f2i_narrow_u%0d_%x", u, m), F2I, FP32, FP16, INT16,
                 64'h7f8000013f800000, physical16(pm), u ? 64'hffff0001 : 64'h7fff0001,
                 64'hffffffff, nv_upper, pair_mask, 1'(u));
            send($sformatf("f2i_widen_u%0d_%x", u, m), F2I, FP16, FP32, INT32,
                 64'h000000007c013c00, physical16(pm), u ? 64'hffffffff00000001 : 64'h7fffffff00000001,
                 '1, nv_upper, pair_mask, 1'(u));
            send($sformatf("i2f_narrow_u%0d_%x", u, m), I2F, FP32, FP16, INT32,
                 64'h0000080100000001, physical16(pm), 64'h68003c00,
                 64'hffffffff, pm[2] ? 5'h01 : 0, pair_mask, 1'(u));
            send($sformatf("i2f_widen_u%0d_%x", u, m), I2F, FP16, FP32, INT16,
                 64'h0000000000020001, physical16(pm), 64'h400000003f800000,
                 '1, 0, pair_mask, 1'(u));
          end
          send($sformatf("fp16_int8_proxy_%x", m), F2I, FP16, FP16, INT8,
               64'h3c007c013c003c00, physical16(pm), 64'h017f0101, 64'hffffffff, nv_upper, lane_mask_t'(pm));
          send($sformatf("int8_fp16_proxy_%x", m), I2F, FP16, FP16, INT8,
               64'h0000000004030201, physical16(pm), 64'h4400420040003c00, '1, 0, lane_mask_t'(pm));
          // A routing FP format is not the integer output width.
          send($sformatf("f2i_int64_proxy_%x", m), F2I, FP16, FP16, INT64,
               64'h7c017c017c013c00, physical16(pm), 64'h1, '1, 0, lane_mask_t'(pm[0]));
          send($sformatf("fp64_fp32_%x", m), F2F, FP64, FP32, INT32,
               64'h7ff0000000000001, physical16(pm), 64'h7fc00000, 64'hffffffff,
               pm[0] ? 5'h10 : 0, lane_mask_t'(pm[0]));
          send($sformatf("fp32_fp64_%x", m), F2F, FP32, FP64, INT64,
               64'h000000007f800001, physical16(pm), 64'h7ff8000000000000, '1,
               pm[0] ? 5'h10 : 0, lane_mask_t'(pm[0]));
          end
        end
        // CPK consumes separate operands, not successive wider vector elements.
        if (!focused) for (int m = 0; m < 4; m++) begin
          for (int part = 0; part < (Fine8 ? 4 : 2); part++) begin
            automatic logic [63:0] target = 64'h1122334455667788;
            automatic int size = Fine8 ? 8 : 16;
            automatic logic [63:0] pair_bits = Fine8 ? 64'h7e3c : 64'h7e003c00;
            automatic logic [63:0] pair_bits_mask = Fine8 ? 64'hffff : 64'hffffffff;
            automatic logic [63:0] packed_expected =
                (target & ~(pair_bits_mask << (2*size*part))) | (pair_bits << (2*size*part));
            send($sformatf("cpk_part%0d_mask%0d", part, m), part < 2 ? CPKAB : CPKCD,
                 FP64, Fine8 ? FP8 : FP16, INT16, 64'h3ff0000000000000, mask_t'(m),
                 packed_expected, '1, (m & 2) ? 5'h10 : 0, lane_mask_t'(m),
                 1'(part), 1, 64'h7ff0000000000001, target);
          end
        end
      end
      // Exercise scalar mode in both vector-enabled and scalar-only elaborations.
      if (!Vectors || !focused) for (int m = 0; m < (Vectors ? 16 : 2); m++) begin
        send($sformatf("scalar_snan_%x", m), F2F, FP32, FP16, INT16,
             64'h7f800001, physical16(4'(m)), 64'h7e00, 64'hffff,
             (m & 1) ? 5'h10 : 0, lane_mask_t'(m & 1), 0, 0);
      end
    end
    @(negedge clk);
    in_valid = 0;
    wait (received == sent);
    repeat (5) @(negedge clk);
    if (busy || out_valid) fail("unit did not drain");
    if (!adjacent || !stalls || !input_stalls) fail("required adjacency/backpressure not exercised");
    $display("SUMMARY sent=%0d received=%0d failures=%0d adjacent=%0d out_stalls=%0d in_stalls=%0d",
             sent, received, failures, adjacent, stalls, input_stalls);
    $fclose(probes);
    $fclose(first_failure);
    if (failures) $fatal(1, "CONV mask mismatch");
    $display("PASS fp16_conv_mask");
    $finish;
  end
endmodule
