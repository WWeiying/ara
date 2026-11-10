  logic command_seed = 0;
  logic [3:0] seed_lane_valid = 0, seed_lane_ready;
  logic [63:0] seed_lane_data [4];
  logic [31:0] gold [4][128], architecture [256], checkpoint [256];
  logic [4:0] gold_flags [4];
  logic [63:0] region_weight [5], region_activation [5];
  int region_blocks [5];
  logic [3:0] delayed_final = 0;
  int cycles = 0, final_wait = 0;
  bit first_write = 0, active = 0, terminal_seen = 0;
  int sequence_id = 0, source_words = 0, seed_rows = 0;
  int enqueued = 0, dequeued = 0, max_queue = 0, held_next = 0;
  int success_count = 0, fault_count = 0, reset_count = 0;
  bit accepted_seed = 0;
`define SC dut.i_engine.i_compute_engine

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      delayed_final <= 0; final_wait <= 0; first_write <= 0;
    end else begin
      delayed_final <= (delayed_final | (ldu_result_req & ldu_result_gnt)) & ~ldu_result_final_gnt;
      if (command_valid && command_ready) begin
        first_write <= 0; final_wait <= 0;
      end else if (|ldu_result_req && !first_write) begin
        first_write <= 1; final_wait <= 12;
      end else if (final_wait != 0) final_wait <= final_wait-1;
    end
  end

  always @(posedge clk) begin
    cycles++;
    if (cycles > 150000) $fatal(1, "SEEDED bounded watchdog");
    if (!rst_n) begin
      if (active) begin
        assert (enqueued > dequeued && source_words == 32)
          else $fatal(1, "SEEDED reset missed queued seeded work");
        $display("SEEDED_RESET seq=%0d enq=%0d deq=%0d flushed=%0d source_words=%0d",
                 sequence_id, enqueued, dequeued, enqueued-dequeued, source_words);
        reset_count++;
      end
      active = 0; terminal_seen = 0;
      source_words = 0; seed_rows = 0; enqueued = 0; dequeued = 0;
      max_queue = 0; held_next = 0;
    end else begin
      if (command_valid && command_ready) begin
        assert (!active && `SC.integer_queue_occupancy == 0 && !`SC.i_fp_accumulator.busy_o)
          else $fatal(1, "SEEDED next admission before old FIFO/FP drain");
        sequence_id++; active = 1; terminal_seen = 0; accepted_seed = command_seed;
        source_words = 0; seed_rows = 0; enqueued = 0; dequeued = 0;
        max_queue = 0; held_next = 0;
      end
      if (&seed_lane_valid && &seed_lane_ready) source_words++;
      if (|seed_lane_ready)
        assert (&seed_lane_valid && &seed_lane_ready)
          else $fatal(1, "SEEDED partial lane source consumption");
      if (`SC.raw_seed_valid && `SC.raw_seed_ready) begin
        assert (`SC.integer_queue_occupancy == 0 && !`SC.i_fp_accumulator.busy_o)
          else $fatal(1, "SEEDED raw seed overlapped FIFO/FP");
        seed_rows++;
      end
      if (`SC.integer_queue_push) enqueued++;
      if (`SC.integer_queue_pop) dequeued++;
      if (int'(`SC.integer_queue_occupancy) > max_queue) max_queue = int'(`SC.integer_queue_occupancy);
      if (command_valid && !command_ready && `SC.integer_queue_occupancy != 0) held_next++;
      if ((success_valid || fault_valid) && !terminal_seen) begin
        assert (active && enqueued == dequeued && `SC.integer_queue_occupancy == 0 &&
                !`SC.i_fp_accumulator.busy_o && source_words == (accepted_seed ? 32:0))
          else $fatal(1, "SEEDED terminal retained source/FIFO/FP work");
        $display("SEEDED_COMMAND seq=%0d seeded=%0d success=%0d fault=%0d source_words=%0d seed_rows=%0d enq=%0d deq=%0d maxq=%0d held_next=%0d updates=%0d flags=%0d",
          sequence_id, accepted_seed, success_valid, fault_valid, source_words, seed_rows,
          enqueued, dequeued, max_queue, held_next, accumulator_updates, result_fflags);
        if (success_valid) success_count++; else fault_count++;
        terminal_seen = 1; active = 0;
      end
      // A test-side architectural image captures only the real accepted writes.
      if (score_commit) for (int lane = 0; lane < 4; lane++) if (ldu_result_req[lane] && ldu_result_gnt[lane]) begin
        automatic int word_index = int'(ldu_result_addr[lane])-score_vd*WordsPerRegister;
        automatic int element = (word_index/WordsPerRegister)*32 + (word_index%WordsPerRegister)*8 + lane;
        if (&ldu_result_be[lane][3:0]) architecture[element] = ldu_result_wdata[lane][31:0];
        if (&ldu_result_be[lane][7:4]) architecture[element+4] = ldu_result_wdata[lane][63:32];
      end
    end
  end

// BEGIN ROUTINES
  task automatic load_seed_vectors;
    string path, token;
    int f, rc, model, index, flags, region, kb, outputs = 0, regions = 0, flag_records = 0;
    logic [63:0] address, w, a;
    logic [15:0] strobe;
    logic [127:0] data;
    logic [31:0] bits_value;
    assert ($value$plusargs("SEEDED_VECTOR=%s", path)) else $fatal(1, "SEEDED missing vector");
    f = $fopen(path, "r"); assert (f != 0);
    rc = $fscanf(f, "%s", token); assert (rc == 1 && token == "S2SEED1");
    while (1) begin
      rc = $fscanf(f, "%s", token); assert (rc == 1) else $fatal(1, "SEEDED incomplete vector");
      if (token == "END") break;
      if (token == "B") begin
        rc = $fscanf(f, "%h %h %h", address, strobe, data);
        assert (rc == 3 && strobe == 16'hffff); put_beat(address, strobe, data);
      end else if (token == "O") begin
        rc = $fscanf(f, "%d %d %h", model, index, bits_value);
        assert (rc == 3 && model == outputs/128 && index == outputs%128);
        gold[model][index] = bits_value; outputs++;
      end else if (token == "F") begin
        rc = $fscanf(f, "%d %d", model, flags);
        assert (rc == 2 && model == flag_records && flags == (model == 0 ? 0:1));
        gold_flags[model] = 5'(flags); flag_records++;
      end else if (token == "R") begin
        rc = $fscanf(f, "%d %h %h %d", region, w, a, kb);
        assert (rc == 4 && region == regions && region < 5);
        region_weight[region] = w; region_activation[region] = a; region_blocks[region] = kb;
        regions++;
      end else $fatal(1, "SEEDED unknown vector token %s", token);
    end
    assert (outputs == 512 && regions == 5 && flag_records == 4);
    $fclose(f);
  endtask

  task automatic configure_case(input int region, input int model, input int n, input bit commit_ok);
    install_descriptor(64'h1000+64'(region)*256, region_weight[region], QbsDescriptorVersion,
      QBS_WEIGHT_PROFILE_Q4_K, QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR,
      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, n, region_blocks[region]);
    score_commit = commit_ok; score_m = 8; score_n = n; score_vd = 8; score_id = 3;
    for (int i = 0; i < 128; i++) begin
      expected_output[i] = gold[model][i]; expected_output_valid[i] = i%16 < n;
    end
    reset_scoreboard();
  endtask

  task automatic source_stream(input int n, input bit from_checkpoint);
    int phase;
    logic [3:0] present;
    for (int word_index = 0; word_index < 32; word_index++) begin
      @(negedge clk); present = 0; phase = 0;
      for (int lane = 0; lane < 4; lane++) begin
        int row, col;
        row = word_index/4; col = word_index%4*8+lane;
        seed_lane_data[lane][31:0] = col < n
          ? (from_checkpoint ? checkpoint[row*32+col] : architecture[row*32+col]) : 32'h7f800001;
        seed_lane_data[lane][63:32] = col+4 < n
          ? (from_checkpoint ? checkpoint[row*32+col+4] : architecture[row*32+col+4]) : 32'h7f800001;
      end
      while (1) begin
        for (int lane = 0; lane < 4; lane++) if (phase >= lane+(word_index%3)) present[lane] = 1;
        seed_lane_valid = present;
        @(posedge clk);
        if (&seed_lane_ready) begin @(negedge clk); seed_lane_valid = 0; break; end
        @(negedge clk); phase++;
      end
    end
  endtask

  task automatic check_success(input int model, input int n, input int kb, input bit seeded);
    wait_success(sequence_id);
    repeat (3) @(negedge clk);
    assert (result_fflags === gold_flags[model] && accumulator_updates == 32'(8*n*kb) &&
            source_words == (seeded ? 32:0) && seed_rows == (seeded ? (n>8 ? 16:8):0) &&
            commit_word_count == 32'(8*((n+7)/8)) && unexpected_write_count == 0 &&
            enqueued == 8*n*kb && dequeued == enqueued && max_queue > 0)
      else $fatal(1, "SEEDED numeric/flags/source/queue work mismatch");
    repeat (12) begin
      @(negedge clk);
      assert (success_valid && !command_ready && delayed_final == 0)
        else $fatal(1, "SEEDED held completion lost ownership");
    end
  endtask

  task automatic run_seeded(input int region, input int model, input int n, input bit from_checkpoint);
    configure_case(region, model, n, 1); command_seed = 1;
    fork
      send_command(3,8,8,64'h1000+64'(region)*256,region_activation[region]);
      source_stream(n,from_checkpoint);
    join
    check_success(model,n,region_blocks[region],1);
    acknowledge_terminal();
  endtask

  task automatic run_directed_seeded;
    int timeout;
    load_seed_vectors();
    for (int i = 0; i < 256; i++) begin architecture[i] = 32'ha5a5a5a5; checkpoint[i] = 0; end
    repeat (4) @(negedge clk); rst_n = 1;
    configure_case(0,0,16,1); command_seed = 0;
    send_command(3,8,8,64'h1000,region_activation[0]);
    timeout = 0;
    while (`SC.integer_queue_occupancy == 0 && timeout < 20000) begin @(negedge clk); timeout++; end
    assert (timeout < 20000) else $fatal(1, "SEEDED prefix never queued");
    // Hold the next request while old integer/FP work and final acknowledgments drain.
    command_seed = 1; command_descriptor_address = 64'h1100;
    command_activation_base = region_activation[1]; command_valid = 1;
    check_success(0,16,1,0);
    assert (held_next > 0) else $fatal(1, "SEEDED held next request missed nonempty FIFO");
    for (int i = 0; i < 256; i++) checkpoint[i] = architecture[i];
    configure_case(1,1,16,1);
    fork
      begin
        acknowledge_terminal();
        do @(posedge clk); while (!command_ready);
        @(negedge clk); command_valid = 0;
      end
      source_stream(16,1);
    join
    check_success(1,16,2,1); acknowledge_terminal();
    run_seeded(2,2,16,0);
    run_seeded(3,3,5,0);

    // A payload fault after earlier K work must publish no architectural writes.
    configure_case(4,1,16,0); command_seed = 1;
    inject_axi_fault = 1;
    inject_fault_start = region_weight[4]+2*4*144; inject_fault_end = inject_fault_start+1;
    fork
      send_command(3,8,8,64'h1400,region_activation[4]);
      source_stream(16,1);
    join
    expect_fault(0,QBS_VALIDATION_OK,QBS_READ_FAULT_AXI_RESPONSE,inject_fault_start);
    assert (max_queue > 0 && enqueued == dequeued) else $fatal(1, "SEEDED fault missed prior queued work");
    inject_axi_fault = 0;
    run_seeded(1,1,16,1);

    configure_case(4,1,16,0); command_seed = 1;
    fork
      send_command(3,8,8,64'h1400,region_activation[4]);
      source_stream(16,1);
    join
    timeout = 0;
    while (`SC.integer_queue_occupancy == 0 && timeout < 20000) begin @(negedge clk); timeout++; end
    assert (timeout < 20000 && unexpected_write_count == 0 && !success_valid && !fault_valid)
      else $fatal(1, "SEEDED reset did not interrupt pending work");
    rst_n = 0; seed_lane_valid = 0;
    repeat (3) @(negedge clk); rst_n = 1;
    @(negedge clk);
    assert (command_ready && !busy && `SC.integer_queue_occupancy == 0 && !`SC.i_fp_accumulator.busy_o);
    run_seeded(1,1,16,1);
    assert (success_count == 6 && fault_count == 1 && reset_count == 1 && sequence_id == 8)
      else $fatal(1, "SEEDED incomplete directed sequence");
    $display("SEEDED_PASS success=6 faults=1 resets=1 commands=8 oracle=original_qbs_ref scope=component_not_isa");
    $finish;
  endtask
`undef SC
