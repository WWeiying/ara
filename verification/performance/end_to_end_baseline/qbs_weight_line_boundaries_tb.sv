`timescale 1ns/1ps
module weight_line_boundary_case #(
  parameter int Width = 8,
  localparam int Capacity = 1 << Width
) (output bit done = 0);
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, clear = 0, valid = 0, ready;
  logic [Width-1:0] offset = 0;
  logic [255:0] data = 'x;
  logic [31:0] strb = 0;
  logic last = 0, wr_valid, wr_ready = 0, pending;
  logic [Width-6:0] wr_addr;
  logic [255:0] wr_data;
  logic [31:0] wr_strb;
  bit accepted_map [Capacity], written_map [Capacity];
  byte expected [Capacity], memory [Capacity];
  int ticks = 0, epoch = 0, cases = 0, streams = 0, aborts = 0;
  int accepted_case = 0, written_case = 0, words_case = 0;
  longint unsigned accepted_total = 0, written_total = 0, words_total = 0;
  bit automatic_sink = 0;
  int sink_mode = 0, selected_width = 0;
  string negative;

  qbs_weight_line_assembler #(.ByteAddrWidth(Width)) dut (
    .clk_i(clk), .rst_ni(rst_n), .clear_i(clear), .valid_i(valid), .ready_o(ready),
    .offset_i(offset), .data_i(data), .strb_i(strb), .last_i(last),
    .write_valid_o(wr_valid), .write_ready_i(wr_ready), .write_addr_o(wr_addr),
    .write_data_o(wr_data), .write_strb_o(wr_strb), .pending_o(pending)
  );

  function automatic byte value_at(input int address, generation);
    return 8'((address * 37) ^ (address >> 8) ^ (generation * 53) ^ 8'hb9);
  endfunction

  always @(posedge clk) begin
    ticks++;
    if (rst_n && !clear) begin
      if (valid && ready && negative == "") begin
        for (int b = 0; b < 32; b++) if (strb[b]) begin
          if (int'(offset)+b >= Capacity || accepted_map[int'(offset)+b])
            $fatal(1, "Boundary TB illegal/duplicate input width=%0d", Width);
          accepted_map[int'(offset)+b] = 1;
          expected[int'(offset)+b] = data[8*b +: 8];
          accepted_case++;
          accepted_total++;
        end
      end
      if (wr_valid && wr_ready && negative == "") begin
        words_case++;
        words_total++;
        for (int b = 0; b < 32; b++) if (wr_strb[b]) begin
          if (!accepted_map[32*int'(wr_addr)+b] || written_map[32*int'(wr_addr)+b])
            $fatal(1, "Boundary TB unexpected/duplicate write width=%0d", Width);
          if (wr_data[8*b +: 8] !== expected[32*int'(wr_addr)+b])
            $fatal(1, "Boundary TB data mismatch width=%0d", Width);
          written_map[32*int'(wr_addr)+b] = 1;
          memory[32*int'(wr_addr)+b] = wr_data[8*b +: 8];
          written_case++;
          written_total++;
        end
      end
    end
  end

  always @(negedge clk)
    if (automatic_sink) wr_ready = sink_mode == 0 || (ticks % 11 < 6);

  task automatic scoreboard_epoch;
    epoch++;
    accepted_case = 0;
    written_case = 0;
    words_case = 0;
    for (int a = 0; a < Capacity; a++) begin
      accepted_map[a] = 0;
      written_map[a] = 0;
      expected[a] = 0;
      memory[a] = 8'ha5;
    end
  endtask

  task automatic begin_case;
    @(negedge clk);
    valid = 0;
    clear = 1;
    @(negedge clk);
    if (pending || wr_valid || ready) $fatal(1, "Boundary clear failed");
    scoreboard_epoch();
    clear = 0;
  endtask

  task automatic drive_prefix(input int address, amount, input bit terminal);
    offset = Width'(address);
    strb = amount == 32 ? '1 : (32'd1 << amount) - 1;
    last = terminal;
    data = 'x;
    for (int b = 0; b < amount; b++) data[8*b +: 8] = value_at(address+b, epoch);
    valid = 1;
  endtask

  task automatic check_case(input int base, length);
    int bound;
    bound = 0;
    while (pending) begin
      @(negedge clk);
      bound++;
      if (bound > 64) $fatal(1, "Boundary output timeout width=%0d", Width);
    end
    if (ready || accepted_case != length || written_case != length ||
        words_case != (base % 32 + length + 31)/32)
      $fatal(1, "Boundary final accounting width=%0d base=%0d len=%0d", Width, base, length);
    for (int a = 0; a < Capacity; a++) begin
      if (accepted_map[a] != written_map[a]) $fatal(1, "Boundary dropped byte");
      if (a < base || a >= base+length) begin
        if (memory[a] !== 8'ha5) $fatal(1, "Boundary canary modified");
      end else if (memory[a] !== value_at(a, epoch)) $fatal(1, "Boundary epoch mismatch");
    end
    cases++;
  endtask

  task automatic run_stream(input int base, length, chunk, stall);
    int cursor, amount, bound;
    automatic_sink = 1;
    sink_mode = stall;
    begin_case();
    cursor = 0;
    bound = 0;
    while (cursor < length) begin
      @(negedge clk);
      amount = chunk < length-cursor ? chunk : length-cursor;
      drive_prefix(base+cursor, amount, cursor+amount == length);
      @(posedge clk);
      if (ready) cursor += amount;
      else if (stall == 0) $fatal(1, "Boundary input II != 1 with ready sink");
      bound++;
      if (bound > 4*Capacity+1024) $fatal(1, "Boundary input timeout");
    end
    @(negedge clk);
    valid = 0;
    check_case(base, length);
    streams++;
  endtask

  // Keep both output and last-carry blocked, abort, and immediately reuse the
  // same two byte addresses with a new generation on the first available edge.
  task automatic abort_and_reuse(input bit use_reset);
    automatic_sink = 0;
    wr_ready = 0;
    begin_case();
    @(negedge clk);
    drive_prefix(31, 2, 1);
    @(posedge clk);
    if (!ready) $fatal(1, "Boundary abort fixture not accepted");
    @(negedge clk);
    valid = 0;
    repeat (3) begin
      if (!wr_valid || !pending || !dut.carry_valid_q || !dut.carry_last_q ||
          !dut.output_valid_q || ready || written_case != 0)
        $fatal(1, "Boundary abort did not cover both pending slots");
      @(negedge clk);
    end
    if (use_reset) rst_n = 0;
    else clear = 1;
    valid = 1;
    @(negedge clk);
    if (pending || wr_valid || ready) $fatal(1, "Boundary aborted slots survived");
    scoreboard_epoch();
    rst_n = 1;
    clear = 0;
    drive_prefix(31, 2, 1);
    @(posedge clk);
    if (!ready) $fatal(1, "Boundary immediate new epoch not accepted");
    @(negedge clk);
    valid = 0;
    wr_ready = 1;
    check_case(31, 2);
    aborts++;
  endtask

  initial begin
    int length;
    bit has_negative, has_width;
    has_negative = $value$plusargs("NEGATIVE=%s", negative);
    has_width = $value$plusargs("WIDTH=%d", selected_width);
    repeat (3) @(negedge clk);
    rst_n = 1;
    if (has_negative) begin
      if (has_width && selected_width == Width) begin
        if (negative != "overflow") $fatal(1, "BOUNDARIES_UNKNOWN_NEGATIVE");
        begin_case();
        @(negedge clk);
        drive_prefix(Capacity-1, 2, 1);
        @(posedge clk);
        #1;
        $fatal(1, "BOUNDARIES_NEGATIVE_NOT_REJECTED");
      end
    end else begin
      for (int kind = 0; kind < 5; kind++) begin
        int chunk;
        case (kind)
          0: chunk = 1;
          1: chunk = 3;
          2: chunk = 7;
          3: chunk = 16;
          default: chunk = 31;
        endcase
        length = 3*chunk+5 < Capacity-1 ? 3*chunk+5 : Capacity-1;
        run_stream(1, length, chunk, 0);
        length = 5*chunk+17 < Capacity-17 ? 5*chunk+17 : Capacity-17;
        run_stream(17, length, chunk, 1);
      end
      run_stream(Capacity-1, 1, 1, 1);
      run_stream(Capacity-32, 32, 31, 1);
      run_stream(Capacity-33, 33, 16, 0);
      run_stream(0, Capacity, 31, 1);
      length = 63 < Capacity-(Capacity/2+3) ? 63 : Capacity-(Capacity/2+3);
      run_stream(Capacity/2+3, length, 7, 1);
      abort_and_reuse(0);
      abort_and_reuse(1);
      $display("WEIGHT_LINE_BOUNDARIES_WIDTH_PASS width=%0d cases=%0d streams=%0d aborts=%0d epochs=%0d accepted_bytes=%0d written_bytes=%0d word_writes=%0d",
               Width, cases, streams, aborts, epoch, accepted_total, written_total, words_total);
      done = 1;
    end
  end
endmodule

module qbs_weight_line_boundaries_tb;
  wire [3:0] done;
  weight_line_boundary_case #(.Width(6)) w6(done[0]);
  weight_line_boundary_case #(.Width(7)) w7(done[1]);
  weight_line_boundary_case #(.Width(8)) w8(done[2]);
  weight_line_boundary_case #(.Width(16)) w16(done[3]);
  initial begin
    wait (&done);
    $display("WEIGHT_LINE_BOUNDARIES_PASS widths=4 cases=68 streams=60 aborts=8");
    $finish;
  end
  initial begin
    #10000000;
    $fatal(1, "BOUNDARIES_WATCHDOG");
  end
endmodule
