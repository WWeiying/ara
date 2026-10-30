  logic command_seed = 0;
  logic [3:0] seed_lane_valid = 0, seed_lane_ready;
  logic [63:0] seed_lane_data [4];
  int source_words, owner_cycles = 0, functional_count = 0;
  logic [3:0] delayed_final;
  bit fault_while_source_pending;
  logic router_owner, router_done = 0;
  logic [3:0] router_valid, router_ready, router_store_valid, router_seed_valid;
  logic [3:0] router_store_ready, router_seed_ready;
  qbs_seed_stream_router router_check (
    .seed_owner_i(router_owner), .lane_valid_i(router_valid), .lane_ready_o(router_ready),
    .store_valid_o(router_store_valid), .store_ready_i(router_store_ready),
    .seed_valid_o(router_seed_valid), .seed_ready_i(router_seed_ready)
  );
  initial begin
    for (int own = 0; own < 2; own++)
      for (int v = 0; v < 16; v++)
        for (int sr = 0; sr < 16; sr++)
          for (int qr = 0; qr < 16; qr++) begin
            router_owner = 1'(own); router_valid = 4'(v);
            router_store_ready = 4'(sr); router_seed_ready = 4'(qr); #1;
            assert (router_ready === 4'(own ? qr:sr) &&
                    router_store_valid === 4'(own ? 0:v) && router_seed_valid === 4'(own ? v:0))
              else $fatal(1, "Store/seed ownership route failed");
          end
    router_done = 1;
    $display("QBS_SEED_ROUTER_PASS combinations=8192");
  end

  always @(posedge clk) begin
    owner_cycles++;
    if (owner_cycles > 1000000) $fatal(1, "Seed owner watchdog");
    if (!rst_n || command_valid && command_ready) source_words <= 0;
    else if (&seed_lane_valid && &seed_lane_ready) source_words <= source_words + 1;
    if (rst_n && |seed_lane_ready)
      assert (&seed_lane_valid && &seed_lane_ready) else $fatal(1, "Partial source beat consumed");
    if (rst_n && command_seed && (success_valid || fault_valid))
      assert (source_words == int'(command_m)*4)
        else $fatal(1, "Terminal before complete seed drain");
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) delayed_final <= 0;
    else delayed_final <= (delayed_final | (ldu_result_req & ldu_result_gnt)) & ~ldu_result_final_gnt;
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n || score_reset) fault_while_source_pending <= 0;
    else if (dut.read_fault_valid && dut.seeded_q && !dut.seed_done)
      fault_while_source_pending <= 1;
  end

  function automatic logic [31:0] raw_seed(input int index);
    return 32'h3f000000 + 32'(index)*32'h1000;
  endfunction

  task automatic source_stream(input int m, input int n, input bit delay_last);
    int phase;
    logic [3:0] present;
    for (int word_index = 0; word_index < m*4; word_index++) begin
      phase = 0; present = 0;
      for (int l = 0; l < 4; l++) begin
        int row, col, stride;
        row = word_index/4; col = word_index%4*8+l; stride=m>4 ? 16:32;
        seed_lane_data[l][31:0] = col < n ? raw_seed(row*stride+col) : 32'h7f800001;
        seed_lane_data[l][63:32] = col+4 < n ? raw_seed(row*stride+col+4) : 32'h7f800001;
      end
      if (delay_last && word_index == m*4-1) begin
        repeat (24) begin
          assert (!fault_valid && !success_valid) else $fatal(1, "Early fault leaked ownership");
          @(negedge clk);
        end
      end
      while (1) begin
        for (int l = 0; l < 4; l++) if (phase >= l) present[l] = 1;
        seed_lane_valid = present;
        @(posedge clk);
        if (&seed_lane_ready) begin
          @(negedge clk); seed_lane_valid = 0;
          break;
        end
        @(negedge clk); phase++;
      end
    end
  endtask

  task automatic setup(input int profile, input int m, input int n, input bit seeded);
    int layout;
    memory.delete();
    layout=m>4 ? QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED :
           m==4 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED : QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
    install_descriptor(64'h1000,64'h2000,QbsDescriptorVersion,profile,
                       m==1 ? QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR:QBS_WEIGHT_LAYOUT_ROW_MAJOR,layout,n,1);
    command_seed=seeded;
    score_commit=1; score_m=m; score_n=n; score_vd=8; score_id=3;
    for (int i = 0; i < 128; i++) begin
      expected_output[i]=seeded ? raw_seed(i) : 0;
      expected_output_valid[i]=i/(m>4 ? 16:32)<m && i%(m>4 ? 16:32)<n;
    end
    reset_scoreboard();
  endtask

  task automatic run_zero_case(input int profile, input int m, input int n, input bit seeded);
    setup(profile,m,n,seeded);
    fork
      send_command(3,8,m,64'h1000,64'h10000);
      if (seeded) source_stream(m,n,0);
    join
    wait_success(functional_count);
    assert (result_fflags === 0 && accumulator_updates === 32'(m*n) &&
            source_words == (seeded ? m*4:0) && unexpected_write_count == 0 &&
            commit_word_count == 32'(m*(m>4 ? (n+7)/8:4)))
      else $fatal(1, "Seed result accounting failed");
    repeat (4) begin
      @(negedge clk);
      assert (success_valid && !command_ready) else $fatal(1, "Terminal ownership not retained");
    end
    acknowledge_terminal();
    functional_count++;
  endtask

  task automatic run_fault_case(input int kind);
    logic [63:0] address;
    int m,n;
    m=kind==7 ? 1:4; n=kind==7 ? 1:7;
    setup(QBS_WEIGHT_PROFILE_Q4_K,m,n,1);
    score_commit=0;
    address=kind==7 ? 64'h2000 : kind<4 ? 64'h1000 : 64'h10000;
    inject_fault_start=address; inject_fault_end=address+16;
    if (kind==0)
      install_descriptor(64'h1000,64'h2000,QbsDescriptorVersion+1,QBS_WEIGHT_PROFILE_Q4_K,
                         QBS_WEIGHT_LAYOUT_ROW_MAJOR,QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,7,1);
    inject_mmu_fault=kind==1 || kind==4 || kind==7;
    translation_enable=inject_mmu_fault;
    inject_axi_fault=kind==2 || kind==5;
    inject_pma_fault=kind==3 || kind==6;
    fork
      send_command(3,8,m,64'h1000,64'h10000);
      source_stream(m,n,1);
    join
    expect_fault(kind==0,kind==0 ? QBS_VALIDATION_DESCRIPTOR_VERSION:QBS_VALIDATION_OK,
                 kind==0 ? QBS_READ_FAULT_NONE :
                 kind==1 || kind==4 || kind==7 ? QBS_READ_FAULT_MMU :
                 kind==2 || kind==5 ? QBS_READ_FAULT_AXI_RESPONSE:QBS_READ_FAULT_PMA,address);
    inject_mmu_fault=0; translation_enable=0; inject_axi_fault=0; inject_pma_fault=0;
    assert (source_words==m*4 && !busy && command_ready) else $fatal(1, "Fault left stream ownership");
    if (kind==7) begin
      assert (fault_while_source_pending) else $fatal(1, "Lookahead fault did not overlap owned source");
      $display("QBS_SEED_OWNER_FAULT_PENDING_PASS");
    end
    $display("QBS_SEED_OWNER_FAULT_PASS kind=%0d",kind);
    run_zero_case(QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,4,7,0);
  endtask

  task automatic partial_reset;
    setup(QBS_WEIGHT_PROFILE_Q4_K,4,7,1);
    score_commit=0;
    fork
      send_command(3,8,4,64'h1000,64'h10000);
      begin
        for (int l = 0; l < 4; l++) seed_lane_data[l]={raw_seed(l+4),raw_seed(l)};
        seed_lane_valid=4'hf;
        do @(posedge clk); while (!(&seed_lane_ready));
        @(negedge clk); seed_lane_valid=0;
      end
    join
    repeat (3) @(negedge clk);
    assert (busy && !fault_valid && !success_valid) else $fatal(1, "Reset fixture did not retain partial seed");
    rst_n=0; seed_lane_valid=0;
    repeat (3) @(negedge clk);
    rst_n=1;
    @(negedge clk);
    assert (!busy && command_ready && !fault_valid && !success_valid && seed_lane_ready==0)
      else $fatal(1, "Reset retained seed transaction");
    $display("QBS_SEED_OWNER_RESET_PASS source_flushed=1");
    run_zero_case(QBS_WEIGHT_PROFILE_Q8_0_WEIGHT,4,7,0);
  endtask
