`timescale 1ns/1ps
module stage2_borrow_tb;
  import ara_pkg::*; import rvv_pkg::*;
  logic clk=0,rst=0,lease=0,quiet=0,owned,valid=0,ready;
  always #5 clk=~clk;
  logic [15:0] weight=0;
  logic [63:0] activation=0,mul_a,mul_b;
  logic mul_request,mul_ready,mul_result_valid,mul_result_ready,result_valid;
  logic [127:0] product;
  logic signed [16:0] pairs[4];
  qbs_lane_mul_borrow dut (
    .clk_i(clk),.rst_ni(rst),.lease_i(lease),.native_quiescent_i(quiet),
    .owned_o(owned),.valid_i(valid),.ready_o(ready),.weight_i(weight),.activation_i(activation),
    .mul_valid_o(mul_request),.mul_a_o(mul_a),.mul_b_o(mul_b),
    .mul_ready_i(mul_ready),.mul_valid_i(mul_result_valid),.mul_product_i(product),
    .mul_ready_o(mul_result_ready),.result_valid_o(result_valid),.result_pair_o(pairs));
  simd_mul #(.ElementWidth(EW8),.NumPipeRegs(0)) multiplier (
    .clk_i(clk),.rst_ni(rst),.operand_a_i(mul_a),.operand_b_i(mul_b),.operand_c_i('0),
    .product_i('0),.op_i(VMULH),.mask_i('1),.vxrm_i(vxrm_t'(0)),
    .valid_i(mul_request),.ready_o(mul_ready),.ready_i(mul_result_ready),.valid_o(mul_result_valid),
    .result_o(),.product_o(product),.mask_o(),.vxsat_o());

  typedef struct packed { int due; logic [67:0] value; } expected_t;
  expected_t pending[$];
  int cycle=0,accepted=0,returned=0,flushed=0,blocked=0,withdrawals=0,resets=0;
  int unsigned rng=32'h805371c9;
  function automatic int unsigned randword();
    rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;
  endfunction
  function automatic logic [67:0] model(logic [15:0] w, logic [63:0] x);
    logic [67:0] expected;
    int signed w0,w1,a0,a1,total;
    w0=$signed(w[7:0]);w1=$signed(w[15:8]);expected=0;
    for(int context_index=0;context_index<4;context_index++) begin
      a0=$signed(x[16*context_index+:8]);a1=$signed(x[16*context_index+8+:8]);
      total=w0*a0+w1*a1;
      expected[17*context_index+:17]=17'(total);
    end
    return expected;
  endfunction
  always @(posedge clk) begin
    expected_t e;
    logic [67:0] observed;
    cycle++;
    if(!rst) begin
      flushed+=pending.size();pending.delete();
    end else begin
      assert(ready===(owned && lease)) else $fatal(1,"borrow ready contract");
      if(!owned) begin
        assert(!ready && !mul_request && !result_valid && pending.size()==0)
          else $fatal(1,"unowned activity");
      end
      if(lease && !quiet && !owned) blocked++;
      if(!lease && pending.size()>0)
        assert(owned) else $fatal(1,"owner released before drain");
      if(valid && ready) begin
        pending.push_back('{cycle+3,model(weight,activation)});accepted++;
      end
      if(result_valid) begin
        assert(pending.size()>0) else $fatal(1,"unsolicited borrowed result");
        e=pending.pop_front();
        for(int context_index=0;context_index<4;context_index++)
          observed[17*context_index+:17]=pairs[context_index];
        assert(cycle==e.due && observed===e.value)
          else $fatal(1,"borrow result cycle=%0d due=%0d observed=%h expected=%h",cycle,e.due,observed,e.value);
        returned++;
      end else if(pending.size()>0)
        assert(pending[0].due>cycle) else $fatal(1,"missing fixed-latency result");
    end
  end
  task automatic tick;
    @(negedge clk);
  endtask
  task automatic acquire;
    valid=0;lease=1;quiet=0;
    repeat(8) begin
      tick();
      assert(!owned && !ready) else $fatal(1,"native nonquiescent acquisition");
    end
    quiet=1;repeat(2) tick();
    assert(owned && ready) else $fatal(1,"missing acquisition");
  endtask
  task automatic release_and_check;
    lease=0;withdrawals++;
    // valid may remain high: revoked lease must stop admission immediately.
    #1;assert(!ready) else $fatal(1,"lease revoke admitted a beat");
    repeat(6) tick();
    assert(!owned && !result_valid && pending.size()==0)
      else $fatal(1,"lease revoke failed to drain/release");
    valid=0;quiet=0;
  endtask
  function automatic logic [7:0] edge_byte(int index);
    case(index)
      0:return 8'h80;1:return 8'hff;2:return 0;3:return 1;default:return 8'h7f;
    endcase
  endfunction
  initial begin
    int start_count;
    logic [67:0] boundary;
    repeat(3) tick();rst=1;
    acquire();
    start_count=accepted;
    for(int i=0;i<256;i++) begin
      valid=1;weight=16'(randword());activation={randword(),randword()};tick();
    end
    assert(accepted-start_count==256) else $fatal(1,"borrow II1 failed");
    // Revoke with all three stages occupied; no result-ready shortcut exists.
    release_and_check();
    acquire();
    for(int w0=0;w0<5;w0++) for(int w1=0;w1<5;w1++)
      for(int a0=0;a0<5;a0++) for(int a1=0;a1<5;a1++) begin
        valid=1;weight={edge_byte(w1),edge_byte(w0)};
        for(int c=0;c<4;c++) activation[c*16+:16]={edge_byte((a1+c)%5),edge_byte((a0+c)%5)};
        tick();
      end
    valid=1;weight=16'h8080;activation=64'h8080808080808080;tick();
    valid=0;repeat(4) tick();
    // Explicitly exercise the +32768 pair, which cannot fit in signed 16 bits.
    boundary=model(16'h8080,64'h8080808080808080);
    assert(boundary[16:0]==17'd32768)
      else $fatal(1,"bad independent boundary model");
    release_and_check();
    for(int epoch=0;epoch<8;epoch++) begin
      acquire();
      for(int n=0;n<1000;n++) begin
        valid=randword()%4!=0;weight=16'(randword());activation={randword(),randword()};tick();
      end
      if(epoch%2==0) begin
        valid=1;weight=16'h8080;activation='1;repeat(3) tick();
        rst=0;resets++;valid=0;
        #1;assert(!owned && !ready && !result_valid) else $fatal(1,"asynchronous reset failed");
        repeat(2) tick();lease=0;quiet=0;rst=1;repeat(2) tick();
        assert(pending.size()==0 && !result_valid) else $fatal(1,"reset leaked a result");
      end else release_and_check();
    end
    assert(accepted==returned+flushed && returned>6000 && flushed>0 && blocked>=80 && withdrawals==6 && resets==4)
      else $fatal(1,"borrow accounting/coverage");
    $display("STAGE2_BORROW_PASS accepted=%0d returned=%0d flushed=%0d blocked=%0d withdrawals=%0d resets=%0d latency=3",
      accepted,returned,flushed,blocked,withdrawals,resets);
    $finish;
  end
  initial begin #200000;$fatal(1,"borrow watchdog");end
endmodule
