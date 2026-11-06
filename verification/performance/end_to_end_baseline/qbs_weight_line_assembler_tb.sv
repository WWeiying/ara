`timescale 1ns/1ps
module qbs_weight_line_assembler_tb;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, clear = 0, valid = 0, ready;
  logic [7:0] offset = 0;
  logic [255:0] data = 0;
  logic [31:0] strb = 0;
  logic last = 0, wr_valid, wr_ready = 0, pending;
  logic [2:0] wr_addr;
  logic [255:0] wr_data;
  logic [31:0] wr_strb;
  int sink_mode = 0;
  bit automatic_sink = 0;
  longint unsigned ticks = 0, accepted_total = 0, written_total = 0;
  int cases = 0, words = 0, accepted_case = 0, written_case = 0;
  bit accepted_map [256], written_map [256];
  byte expected [256], memory [256];
  string negative;

  qbs_weight_line_assembler dut (
    .clk_i(clk), .rst_ni(rst_n), .clear_i(clear),
    .valid_i(valid), .ready_o(ready), .offset_i(offset), .data_i(data),
    .strb_i(strb), .last_i(last), .write_valid_o(wr_valid),
    .write_ready_i(wr_ready), .write_addr_o(wr_addr),
    .write_data_o(wr_data), .write_strb_o(wr_strb), .pending_o(pending)
  );

  function automatic byte value_at(input int address, input int salt);
    return 8'((address * 37) ^ (salt * 19) ^ (address >> 2) ^ 8'hd3);
  endfunction

  always @(posedge clk) begin
    ticks = ticks + 1;
    if (rst_n && !clear) begin
      if (valid && ready) begin
        for (int b = 0; b < 32; b++) begin
          if (strb[b]) begin
            if (int'(offset)+b >= 256 && negative == "") $fatal(1, "TB input overflow");
            if (int'(offset)+b < 256) begin
              if (accepted_map[int'(offset)+b] && negative == "") $fatal(1, "TB duplicate input");
              expected[int'(offset)+b] = data[8*b +: 8];
              accepted_map[int'(offset)+b] = 1;
              accepted_case++;
              accepted_total++;
            end
          end
        end
      end
      if (wr_valid && wr_ready) begin
        words++;
        for (int b = 0; b < 32; b++) begin
          if (wr_strb[b]) begin
            if (!accepted_map[32*int'(wr_addr)+b] || written_map[32*int'(wr_addr)+b])
              $fatal(1, "Unexpected/duplicate output byte addr=%0d", 32*int'(wr_addr)+b);
            if (wr_data[8*b +: 8] !== expected[32*int'(wr_addr)+b])
              $fatal(1, "Output byte mismatch addr=%0d", 32*int'(wr_addr)+b);
            written_map[32*int'(wr_addr)+b] = 1;
            memory[32*int'(wr_addr)+b] = wr_data[8*b +: 8];
            written_case++;
            written_total++;
          end
        end
      end
    end
  end

  always @(negedge clk)
    if (automatic_sink)
      wr_ready = sink_mode == 0 || (ticks % 7 != 2 && ticks % 7 != 3);

  task automatic clear_case;
    @(negedge clk);
    valid = 0;
    clear = 1;
    @(negedge clk);
    if (pending || wr_valid) $fatal(1, "Clear retained a previous bank owner");
    clear = 0;
    accepted_case = 0;
    written_case = 0;
    words = 0;
    for (int i = 0; i < 256; i++) begin
      accepted_map[i] = 0;
      written_map[i] = 0;
      expected[i] = 0;
      memory[i] = 8'ha5;
    end
  endtask

  task automatic run_case(input int base, length, mode);
    int cursor, amount, first_amount, bound, input_stalls;
    bit held;
    clear_case();
    sink_mode = mode & 1;
    automatic_sink = 1;
    cursor = 0;
    bound = 0;
    input_stalls = 0;
    held = 0;
    first_amount = (base + length) % 32 + 1;
    while (cursor < length) begin
      @(negedge clk);
      amount = cursor == 0 ? first_amount : 32;
      if (amount > length - cursor) amount = length - cursor;
      valid = held || !(mode >= 2 && ticks % 3 == 0);
      offset = 8'(base + cursor);
      strb = amount == 32 ? '1 : (32'd1 << amount) - 1;
      last = cursor + amount == length;
      for (int b = 0; b < 32; b++) data[8*b +: 8] = value_at(base+cursor+b, cases);
      @(posedge clk);
      if (valid && ready) begin
        cursor += amount;
        held = 0;
      end else if (valid) begin
        held = 1;
        input_stalls++;
      end
      bound++;
      if (bound > 256) $fatal(1, "Input progress timeout");
    end
    @(negedge clk);
    valid = 0;
    bound = 0;
    while (pending) begin
      @(negedge clk);
      bound++;
      if (bound > 32) $fatal(1, "Output drain timeout");
    end
    if (ready) $fatal(1, "Ended bank reopened without clear");
    if (accepted_case != length || written_case != length ||
        words != (base % 32 + length + 31)/32)
      $fatal(1, "Byte/word accounting mismatch base=%0d n=%0d mode=%0d", base, length, mode);
    if (mode == 0 && input_stalls != 0) $fatal(1, "Unstalled sink cannot sustain input II=1");
    for (int i = 0; i < 256; i++) begin
      if (accepted_map[i] != written_map[i]) $fatal(1, "Dropped byte");
      if (i < base || i >= base+length) begin
        if (memory[i] !== 8'ha5) $fatal(1, "Canary overwritten");
      end else if (memory[i] !== value_at(i, cases)) $fatal(1, "End-state data mismatch");
    end
    cases++;
  endtask

  task automatic abort_case(input bit use_reset, full_word);
    clear_case();
    automatic_sink = 0;
    wr_ready = 0;
    @(negedge clk);
    valid = 1;
    offset = 0;
    strb = full_word ? '1 : 32'h7f;
    last = 0;
    data = {8{32'hdeadbeef}};
    @(posedge clk);
    if (!ready) $fatal(1, "Abort fixture not accepted");
    @(negedge clk);
    valid = 0;
    if (!pending) $fatal(1, "Abort fixture has no pending work");
    if (use_reset) rst_n = 0;
    else clear = 1;
    @(negedge clk);
    if (pending || wr_valid) $fatal(1, "Abort failed to discard staged bytes");
    rst_n = 1;
    clear = 0;
    wr_ready = 1;
    repeat (3) begin
      @(negedge clk);
      if (wr_valid) $fatal(1, "Aborted owner leaked an SRAM write");
    end
    for (int i = 0; i < 256; i++) if (memory[i] !== 8'ha5) $fatal(1, "Abort fixture wrote SRAM");
  endtask

  initial begin
    repeat (3) @(negedge clk);
    rst_n = 1;
    if ($value$plusargs("NEGATIVE=%s", negative)) begin
      clear_case();
      @(negedge clk);
      valid = 1;
      last = 0;
      strb = 32'h7f;
      if (negative == "empty") strb = 0;
      else if (negative == "prefix") strb = 32'h5;
      else if (negative == "overflow") begin offset = 250; strb = 32'hffff; end
      else if (negative != "order") $fatal(1, "Unknown negative fixture");
      @(posedge clk);
      @(negedge clk);
      if (negative == "order") begin offset = 9; strb = 1; end
      @(posedge clk);
      #1;
      $fatal(1, "Negative contract fixture was not rejected");
    end
    for (int mode = 0; mode < 4; mode++) begin
      for (int phase = 0; phase < 32; phase++)
        for (int length = 1; length <= 128; length++) run_case(phase, length, mode);
      $display("WEIGHT_LINE_MODE_PASS mode=%0d cases=%0d", mode, cases);
    end
    for (int reset_case = 0; reset_case < 2; reset_case++)
      for (int full = 0; full < 2; full++) abort_case(1'(reset_case), 1'(full));
    run_case(128, 128, 0);
    run_case(255, 1, 1);
    run_case(0, 128, 0);
    $display("WEIGHT_LINE_COMPONENT_PASS cases=%0d abort_cases=4 accepted_bytes=%0d written_bytes=%0d", cases, accepted_total, written_total);
    $finish;
  end
  initial begin
    #100000000;
    $fatal(1, "Weight line bench watchdog");
  end
endmodule
