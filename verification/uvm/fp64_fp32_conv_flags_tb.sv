`timescale 1ns/1ps

module fp64_fp32_conv_flags_tb;
  import fpnew_pkg::*;
  localparam fmt_logic_t Formats = 6'b111000;
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  logic [num_operands(CONV)-1:0][63:0] operands;
  logic [63:0] result;
  logic [3:0] mask;
  logic [7:0] tag_in, tag_out;
  logic in_valid, in_ready, out_valid, out_ready, busy;
  status_t status;
  logic [31:0] expected_data [32];
  status_t expected_flags [32];
  string names [32];
  int cycle = 0, sent = 0, received = 0, failures = 0;
  int first_failure, probes;
  bit stall_mode = 0, held = 0;
  logic [63:0] held_result;
  status_t held_status;
  logic [7:0] held_tag;

  fpnew_opgroup_multifmt_slice #(
    .OpGroup(CONV), .Width(64), .FpFmtConfig(Formats), .IntFmtConfig(4'b1111),
    .EnableVectors(1), .NumPipeRegs(2), .PipeConfig(DISTRIBUTED),
    .TagType(logic [7:0])
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .hart_id_i('0), .operands_i(operands),
    .is_boxed_i('1), .rnd_mode_i(RNE), .op_i(F2F), .op_mod_i(1'b0),
    .src_fmt_i(FP64), .dst_fmt_i(FP32), .int_fmt_i(INT32),
    .vectorial_op_i(1'b1), .tag_i(tag_in), .simd_mask_i(mask),
    .in_valid_i(in_valid), .in_ready_o(in_ready), .flush_i(1'b0),
    .result_o(result), .status_o(status), .extension_bit_o(), .tag_o(tag_out),
    .out_valid_o(out_valid), .out_ready_i(out_ready), .busy_o(busy)
  );

  task automatic fail(input string reason);
    if (failures == 0) begin
      $display("FIRST_FAILURE cycle=%0d %s", cycle, reason);
      $fdisplay(first_failure, "cycle=%0d %s", cycle, reason);
      $fflush(first_failure);
    end
    failures++;
    $display("FAIL cycle=%0d %s", cycle, reason);
  endtask

  // The real two-stage CONV path receives adjacent micro-ops without a drain.
  task automatic send(input string name, input logic [63:0] bits,
                      input logic [3:0] enables, input logic [31:0] data,
                      input status_t flags);
    @(negedge clk);
    names[sent] = name;
    expected_data[sent] = data;
    expected_flags[sent] = flags;
    operands[0] = bits;
    operands[1] = '0;
    mask = enables;
    tag_in = 8'(sent);
    in_valid = 1;
    do @(posedge clk); while (!in_ready);
    sent++;
  endtask

  always @(negedge clk)
    out_ready = !stall_mode || (cycle % 7 >= 3);

  always @(posedge clk) begin
    if (rst_n) begin
      cycle++;
      if (cycle > 300) $fatal(1, "bounded unit timeout");
      if (held && (!out_valid || result !== held_result ||
                   status !== held_status || tag_out !== held_tag))
        fail("output changed under backpressure");
      held = out_valid && !out_ready;
      held_result = result;
      held_status = status;
      held_tag = tag_out;
      if (out_valid && out_ready) begin
        if (tag_out !== 8'(received))
          fail($sformatf("output order tag=%0d expected=%0d", tag_out, received));
        if (result[31:0] !== expected_data[received] ||
            status !== expected_flags[received])
          fail($sformatf("case=%s tag=%0d data=%h expected=%h flags=%h expected_flags=%h",
               names[received], tag_out, result[31:0], expected_data[received],
               status, expected_flags[received]));
        $display("RESULT cycle=%0d tag=%0d name=%s result=%h flags=%h expected=%h masks=%b valids=%b",
                 cycle, tag_out, names[received], result, status,
                 expected_flags[received], dut.lane_masks, dut.lane_out_valid);
        received++;
      end
    end
  end

  for (genvar l = 0; l < 4; l++) begin : probe_lane
    initial $display("CONFIG lane=%0d active_formats=%b conv_formats=%b width=%0d",
                     l, dut.gen_num_lanes[l].ACTIVE_FORMATS,
                     dut.gen_num_lanes[l].CONV_FORMATS,
                     dut.gen_num_lanes[l].LANE_WIDTH);
    always @(posedge clk) begin
      if (rst_n && (in_valid || out_valid || busy)) begin
        $fdisplay(probes,
          "%0t,%0d,%0d,%b,%b,%0d,%0d,%b,%h,%b,%b,%0d,%h,%h,%h,%0d,%b,%b,%h",
          $time, cycle, l, in_valid, in_ready, tag_in, FP64, mask,
          dut.gen_num_lanes[l].active_lane.local_operands[0],
          dut.gen_num_lanes[l].active_lane.in_valid, dut.lane_out_valid[l],
          dut.lane_tags[l], dut.gen_num_lanes[l].active_lane.op_status,
          dut.lane_status[l], dut.lane_aux[l], dut.result_fmt,
          dut.lane_masks[l], out_ready, status);
        $fflush(probes);
      end
    end
  end

  initial begin
    first_failure = $fopen("first_failure.log", "w");
    probes = $fopen("lane_probes.csv", "w");
    if (!first_failure || !probes) $fatal(1, "cannot open evidence files");
    $fdisplay(probes, "time,cycle,lane,in_valid,in_ready,in_tag,srcfmt,in_mask,local_operand,lane_in_valid,lane_out_valid,lane_tag,raw_status,lane_status,aux,result_fmt,lane_mask,out_ready,merged_status");
    operands = '0;
    mask = '0;
    tag_in = '0;
    in_valid = 0;
    out_ready = 1;
    repeat (3) @(negedge clk);
    rst_n = 1;
    for (int phase = 0; phase < 2; phase++) begin
      stall_mode = (phase != 0);
      send("masked_snan_prefix", 64'h7ff0000000000001, 4'b0000, 32'h7fc00000, '0);
      send("active_1p5_after_prefix", 64'h3ff8000000000000, 4'b0011, 32'h3fc00000, '0);
      send("active_1p5_tail", 64'h3ff8000000000000, 4'b0011, 32'h3fc00000, '0);
      send("active_snan_control", 64'h7ff0000000000001, 4'b0011, 32'h7fc00000, 5'h10);
      send("masked_snan_after_nv", 64'h7ff0000000000001, 4'b0000, 32'h7fc00000, '0);
      send("active_1p5_after_nv", 64'h3ff8000000000000, 4'b0011, 32'h3fc00000, '0);
      send("cpk_lane1_mask_only", 64'h7ff0000000000001, 4'b0010, 32'h7fc00000, '0);
      send("all_mask_bits_active_1p5", 64'h3ff8000000000000, 4'b1111, 32'h3fc00000, '0);
    end
    @(negedge clk);
    in_valid = 0;
    wait (received == sent);
    repeat (5) @(negedge clk);
    if (busy || out_valid || sent != 16) fail("unit did not drain correctly");
    $display("SUMMARY sent=%0d received=%0d failures=%0d", sent, received, failures);
    $fclose(probes);
    $fclose(first_failure);
    if (failures) $fatal(1, "CONV slice flags mismatch");
    $display("PASS fp64_fp32_conv_flags");
    $finish;
  end
endmodule
