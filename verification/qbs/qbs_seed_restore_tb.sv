module qbs_seed_restore_tb;
  import qbs_pkg::*;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  logic [1:0] clear = '0, req_valid = '0, ready, busy, update;
  logic [1:0] first_block = '0;
  logic [6:0] index[2], update_index[2];
  logic signed [31:0] dot[2], aux[2];
  logic [15:0] scale[2], minimum[2];
  logic [31:0] activation[2], update_data[2], update_count[2];
  logic [4:0] flags[2];
  logic [3:0] read_row = '0;
  logic [7:0] bank_valid[2];
  logic [31:0] bank_data[2][8];
  qbs_weight_profile_e profile = QBS_WEIGHT_PROFILE_Q8_0_WEIGHT;
  qbs_activation_profile_e activation_profile = QBS_ACTIVATION_PROFILE_Q8_0;
  logic seed_valid = 0, seed_ready;
  logic [3:0] seed_row = '0;
  logic [7:0] seed_mask = '0;
  logic [31:0] seed_data[8], saved[128];
  logic [31:0] expected_bits;
  logic [4:0] reference_prefix_flags, resumed_prefix_flags;
  int checks = 0, cycles = 0;
  localparam logic [15:0] HalfEdges[8] = '{
    16'h0000,16'h8000,16'h0001,16'h3c00,16'hbc00,16'h7bff,16'h7c00,16'h7c01};
  localparam logic [31:0] FloatEdges[8] = '{
    32'h00000000,32'h80000000,32'h00000001,32'h3f800000,
    32'hbf800000,32'h7f7fffff,32'h7f800000,32'h7f800001};

`define COMMON_PORTS(I) \
    .clk_i(clk), .rst_ni(rst_n), .clear_i(clear[I]), \
    .request_valid_i(req_valid[I]), .request_ready_o(ready[I]), \
    .request_slot_i(4'(index[I])), .request_profile_i(profile), \
    .request_activation_profile_i(activation_profile), \
    .request_accumulator_index_i(index[I]), .request_first_block_i(first_block[I]), \
    .request_dot_i(dot[I]), .request_aux_i(aux[I]), \
    .request_weight_d_i(scale[I]), .request_weight_dmin_i(minimum[I]), \
    .request_activation_d_i(activation[I]), \
    .read_index_i('0), .read_valid_o(), .read_data_o(), \
    .bank_read_row_i(read_row), .bank_read_valid_o(bank_valid[I]), .bank_read_data_o(bank_data[I]), \
    .update_valid_o(update[I]), .update_index_o(update_index[I]), .update_data_o(update_data[I]), \
    .fflags_o(flags[I]), .busy_o(busy[I]), .fp_uop_issue_o(), .table_occupancy_sum_o(), \
    .table_occupancy_max_o(), .table_full_cycles_o(), .accumulator_updates_o(update_count[I])

  qbs_fp_accumulator reference_dut (`COMMON_PORTS(0));
  qbs_fp_accumulator_seeded candidate_dut (
    `COMMON_PORTS(1),
    .raw_seed_valid_i(seed_valid), .raw_seed_ready_o(seed_ready),
    .raw_seed_row_i(seed_row), .raw_seed_mask_i(seed_mask), .raw_seed_data_i(seed_data)
  );
`undef COMMON_PORTS

  always @(posedge clk) begin
    cycles++;
    if (cycles > 200000) $fatal(1, "Seed restore watchdog");
    if (rst_n && seed_valid && seed_ready)
      assert (!busy[1] && !clear[1] && !(req_valid[1] && ready[1]))
        else $fatal(1, "Seed overlapped arithmetic or clear");
  end

  task automatic erase(input int which);
    while (busy[which]) @(negedge clk);
    @(negedge clk); clear[which] = 1;
    @(negedge clk); clear[which] = 0;
    assert (flags[which] === 0 && update_count[which] === 0)
      else $fatal(1, "Clear did not reset status");
  endtask

  task automatic seed(input int row, input logic [7:0] mask);
    @(negedge clk); seed_valid = 1; seed_row = 4'(row); seed_mask = mask;
    do @(posedge clk); while (!seed_ready);
    @(negedge clk); seed_valid = 0;
  endtask

  task automatic send(input int which, input int element, input bit first,
                      input logic signed [31:0] value, input int round_index);
    @(negedge clk);
    index[which] = 7'(element); first_block[which] = first;
    dot[which] = value; aux[which] = value ^ 32'h817fe321;
    scale[which] = HalfEdges[(element + round_index) % 8];
    minimum[which] = HalfEdges[(element / 3 + round_index) % 8];
    activation[which] = activation_profile == QBS_ACTIVATION_PROFILE_Q8_0
        ? {16'b0, HalfEdges[(element / 5 + round_index) % 8]}
        : FloatEdges[(element / 5 + round_index) % 8];
    // Exact-integer witness uses unit scales, otherwise exercise all formats.
    if (round_index == 99) begin
      scale[which] = 16'h3c00; minimum[which] = 0; activation[which] = 32'h00003c00;
    end
    req_valid[which] = 1;
    do @(posedge clk); while (!ready[which]);
    @(negedge clk); req_valid[which] = 0;
    while (!update[which]) @(negedge clk);
    assert (update_index[which] === 7'(element)) else $fatal(1, "Wrong update index");
  endtask

  task automatic copy_out;
    while (busy[1]) @(negedge clk);
    for (int row = 0; row < 16; row++) begin
      read_row = 4'(row); #1;
      assert (bank_valid[1] === 8'hff) else $fatal(1, "Incomplete checkpoint");
      for (int bank = 0; bank < 8; bank++) saved[row*8+bank] = bank_data[1][bank];
    end
  endtask

  task automatic restore_all;
    for (int row = 0; row < 16; row++) begin
      for (int bank = 0; bank < 8; bank++) seed_data[bank] = saved[row*8+bank];
      seed(row, 8'hff);
    end
    assert (flags[1] === 0 && update_count[1] === 0)
      else $fatal(1, "Raw seed changed FP flags or arithmetic counters");
  endtask

  initial begin
    for (int i = 0; i < 2; i++) begin
      index[i] = 0; dot[i] = 0; aux[i] = 0; scale[i] = 0; minimum[i] = 0; activation[i] = 0;
    end
    for (int i = 0; i < 8; i++) seed_data[i] = 0;
    repeat (3) @(negedge clk); rst_n = 1;
    erase(0); erase(1);
    // Raw bits, including NaN encodings and signed zero, must not execute FP.
    for (int row = 0; row < 16; row++) begin
      for (int bank = 0; bank < 8; bank++) seed_data[bank] = FloatEdges[bank] ^ (32'(row) << 8);
      seed(row, 8'hff); read_row = 4'(row); #1;
      assert (bank_valid[1] === 8'hff);
      for (int bank = 0; bank < 8; bank++) begin
        assert (bank_data[1][bank] === seed_data[bank]) else $fatal(1, "Raw seed bit loss");
        checks++;
      end
    end
    seed(0, 8'ha5); read_row = 0; #1;
    assert (bank_valid[1] === 8'ha5 && flags[1] === 0 && update_count[1] === 0)
      else $fatal(1, "Mask or raw-copy status failure");

    // Compare monolithic two-block execution with clear/restore continuation.
    for (int kind = 1; kind <= 9; kind++) begin
      profile = qbs_weight_profile_e'(kind);
      activation_profile = qbs_default_activation_profile(profile);
      erase(0); erase(1);
      for (int element = 0; element < 128; element++) begin
        send(0, element, 1, 32'h01000001 ^ (32'(element)*32'd104729), 0);
        send(1, element, 1, 32'h01000001 ^ (32'(element)*32'd104729), 0);
        assert (update_data[1] === update_data[0]) else $fatal(1, "First block differs");
        checks++;
      end
      reference_prefix_flags = flags[0]; resumed_prefix_flags = flags[1];
      assert (reference_prefix_flags === resumed_prefix_flags);
      copy_out(); erase(1); restore_all();
      for (int element = 0; element < 128; element++) begin
        send(0, element, 0, 32'h80000001 ^ (32'(element)*32'd314159), 1);
        send(1, element, 0, 32'h80000001 ^ (32'(element)*32'd314159), 1);
        assert (update_data[1] === update_data[0])
          else $fatal(1, "Continuation differs profile=%0d element=%0d", kind, element);
        checks++;
      end
      assert (flags[0] === (resumed_prefix_flags | flags[1]) &&
              update_count[0] === 256 && update_count[1] === 128)
        else $fatal(1, "Continuation flags/counters differ");
    end

    profile = QBS_WEIGHT_PROFILE_Q8_0_WEIGHT;
    activation_profile = QBS_ACTIVATION_PROFILE_Q8_0;
    erase(0); erase(1);
    send(0, 0, 1, 33554432, 99);
    send(0, 0, 0, -33554432, 99);
    send(0, 0, 0, 1, 99);
    assert (update_data[0] === 32'h3f800000) else $fatal(1, "Sequential witness failed");
    send(1, 0, 1, 33554432, 99); saved[0] = update_data[1]; erase(1);
    seed_data[0] = saved[0]; seed(0, 8'h01);
    send(1, 0, 0, -33554432, 99); send(1, 0, 0, 1, 99);
    assert (update_data[1] === 32'h3f800000) else $fatal(1, "Restored witness failed");
    erase(0); send(0, 0, 1, -33554432, 99); send(0, 0, 0, 1, 99);
    assert (update_data[0] === 32'hcc000000) else $fatal(1, "Split-order witness missing");
    $display("QBS_SEED_RESTORE_PASS profiles=9 raw_words=128 compared=%0d witness=3f800000 stripe2=cc000000", checks);
    $finish;
  end
endmodule
