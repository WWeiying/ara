module operand_fifo_case #(parameter int Depth=5)(output bit done);
  localparam int AW=Depth>1?$clog2(Depth):1;
  bit clk=0;
  always #5 clk=~clk;
  logic rst_n=0, flush=0, push=0, pop=0;
  logic [63:0] data=0, actual, original;
  logic full, empty, old_full, old_empty;
  logic [AW-1:0] usage, old_usage;
  logic [63:0] model[$];
  logic [Depth-1:0] written='0;
  int cycles=0, writes=0, reads=0, resets=0, flushes=0, both=0, flush_push=0;
  int full_cycles=0, empty_cycles=0;
  int random_state=32'h716ef53a+Depth;

  operand_queue_data_fifo #(.DEPTH(Depth)) dut (.clk_i(clk),.rst_ni(rst_n),.flush_i(flush),
    .data_i(data),.push_i(push),.pop_i(pop),.data_o(actual),.full_o(full),.empty_o(empty),.usage_o(usage));
  fifo_v3 #(.DEPTH(Depth),.DATA_WIDTH(64)) ref_dut (.clk_i(clk),.rst_ni(rst_n),.flush_i(flush),
    .testmode_i(1'b0),.data_i(data),.push_i(push),.pop_i(pop),.data_o(original),
    .full_o(old_full),.empty_o(old_empty),.usage_o(old_usage));

  function automatic int unsigned rng();
    random_state ^= random_state<<13;
    random_state ^= random_state>>17;
    random_state ^= random_state<<5;
    return unsigned'(random_state);
  endfunction
  function automatic logic [63:0] random_word();
    logic [31:0] lo,hi;
    lo=rng(); hi=rng(); return {hi,lo};
  endfunction

  task automatic check_state();
    if ({full,empty,usage} !== {old_full,old_empty,old_usage} ||
        empty !== (model.size()==0) || full !== (model.size()==Depth) ||
        usage !== AW'(model.size()))
      $fatal(1,"FIFO_STATE_MISMATCH depth=%0d cycle=%0d count=%0d",Depth,cycles,model.size());
    if (!empty) begin
      if (actual !== original || actual !== model[0])
        $fatal(1,"FIFO_DATA_MISMATCH depth=%0d cycle=%0d actual=%h old=%h expected=%h",
          Depth,cycles,actual,original,model[0]);
      if (written[dut.read_pointer_q] !== 1'b1)
        $fatal(1,"FIFO_READ_BEFORE_EPOCH_WRITE depth=%0d cycle=%0d",Depth,cycles);
    end
  endtask

  task automatic tick();
    logic [63:0] discarded;
    bit accept_push,accept_pop;
    @(posedge clk);
    check_state();
    accept_push=push&&!full; accept_pop=pop&&!empty;
    full_cycles+=int'(full); empty_cycles+=int'(empty);
    if (!rst_n || flush) begin
      model.delete(); written='0;
      if (flush && rst_n) begin flushes++; flush_push+=int'(accept_push); end
    end else begin
      if (accept_pop) begin discarded=model.pop_front(); written[dut.read_pointer_q]=0; reads++; end
      if (accept_push) begin model.push_back(data); written[dut.write_pointer_q]=1; writes++; end
      both+=int'(accept_push&&accept_pop);
    end
    #1; check_state(); cycles++;
    @(negedge clk);
  endtask

  task automatic reset_now();
    // Assert reset between edges while the payload can contain old data.
    push=0; pop=0; flush=0; #1; rst_n=0; model.delete(); written='0;
    #1; check_state(); tick(); rst_n=1; resets++;
  endtask

  initial begin
    done=0; tick(); tick(); rst_n=1;
    for (int epoch=0;epoch<32;epoch++) begin
      // Fill to capacity, hold full, drain completely, including non-power-of-two wrap.
      for(int n=0;n<Depth;n++) begin push=1; pop=0; data=64'(1)<<((epoch+n)%64); tick(); end
      push=0; pop=0; tick(); tick();
      for(int n=0;n<Depth;n++) begin pop=1; tick(); end
      pop=0; tick();
      // Flush arriving data, then replace slot zero before any valid observation.
      flush=1; push=1; data='1; tick(); flush=0; push=0; tick();
      push=1; data='0; tick(); push=0; pop=1; tick(); pop=0;
      // Asynchronous reset with entries occupied and immediate subsequent refill.
      push=1; data=random_word(); tick(); reset_now();
    end
    for(int n=0;n<50000;n++) begin
      push=!full && (rng()%4!=0);
      pop=!empty && (rng()%3!=0);
      flush=rng()%97==0;
      data=random_word();
      if(n%31==0) data[47:40]='x;
      tick();
      if(n%997==0) reset_now();
    end
    push=0; flush=0;
    while(!empty) begin pop=1; tick(); end
    pop=0; tick();
    if(!writes || !reads || !resets || !flush_push || !full_cycles || !empty_cycles || (Depth>1&&!both))
      $fatal(1,"FIFO_TEST_INCOMPLETE depth=%0d",Depth);
    $display("OPERAND_FIFO_CASE_PASS depth=%0d cycles=%0d writes=%0d reads=%0d resets=%0d flushes=%0d simultaneous=%0d flush_push=%0d",
      Depth,cycles,writes,reads,resets,flushes,both,flush_push);
    done=1;
  end
endmodule

module operand_fifo_tb;
  wire [3:0] done;
  operand_fifo_case #(.Depth(1)) d1(done[0]);
  operand_fifo_case #(.Depth(2)) d2(done[1]);
  operand_fifo_case #(.Depth(3)) d3(done[2]);
  operand_fifo_case #(.Depth(5)) d5(done[3]);
  initial begin wait(&done); $display("OPERAND_FIFO_PASS"); $finish; end
  initial begin #1000000; $fatal(1,"OPERAND_FIFO_WATCHDOG"); end
endmodule
