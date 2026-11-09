`timescale 1ns/1ps
module resident_payload_tb;
  logic clk=0;
  always #5 clk=~clk;
  logic rst=0, cancel=0, valid=0, ready, kind=0, out_kind, empty;
  logic [3:0] active=0, out_valid, take=0;
  logic [3:0][63:0] data='0, out_data;
  resident_payload_fanout dut(clk, rst, cancel, valid, ready, active,
    kind, data, out_valid, take, out_kind, out_data, empty);
  int writes, reads[4], cancels, simultaneous, partials, stalled;
  int total_beats, expected_id[4][$], expected_kind[4][$];
  bit [3:0] held;
  logic [3:0][63:0] held_data;
  bit held_kind;
  bit source_held;
  bit [3:0] source_mask;
  int dummy;
  function automatic logic [63:0] payload(int id, int lane);
    return {32'(id), 32'(lane ^ id ^ 'h5a5a)};
  endfunction
  task automatic cycle(bit send, bit [3:0] mask, bit [3:0] rdy, bit flush);
    @(negedge clk);
    valid=source_held || send; active=source_held ? source_mask : mask;
    take=rdy; cancel=flush; kind=writes[0];
    for (int l=0;l<4;l++) data[l]=payload(writes,l);
    @(posedge clk);
    if (flush) begin
      if (out_valid != 0 || ready) $fatal(1,"Transfer on cancellation");
      for (int l=0;l<4;l++) begin
        cancels+=expected_id[l].size(); expected_id[l].delete(); expected_kind[l].delete();
      end
      held=0; source_held=0;
    end else begin
      for (int l=0;l<4;l++) begin
        if (held[l] && (!out_valid[l] || out_data[l] !== held_data[l] || out_kind != held_kind))
          $fatal(1,"Backpressured payload changed lane %0d",l);
        if (out_valid[l] && take[l]) begin
          if (expected_id[l].size()==0) $fatal(1,"Duplicate/unexpected beat lane %0d",l);
          if (out_data[l] !== payload(expected_id[l][0],l) || out_kind != expected_kind[l][0])
            $fatal(1,"Payload ordering/content mismatch lane %0d",l);
          dummy=expected_id[l].pop_front(); dummy=expected_kind[l].pop_front(); reads[l]++;
        end
      end
      if (valid && ready) begin
        for(int l=0;l<4;l++) if(active[l]) begin
          expected_id[l].push_back(writes); expected_kind[l].push_back(kind); total_beats++;
        end
        writes++;
      end
      if ((out_valid & take) != 0 && (out_valid & ~take) != 0) partials++;
      if (valid && !ready) stalled++;
      if (valid && ready && (out_valid & take)!=0) simultaneous++;
      held=out_valid & ~take; held_data=out_data; held_kind=out_kind;
      source_held=valid && !ready; source_mask=active;
    end
  endtask
  initial begin
    repeat(3) @(negedge clk); rst=1;
    // Steady state: no mandatory bubble while all lanes accept every cycle.
    for(int i=0;i<100;i++) cycle(1,15,15,0);
    if(writes!=100) $fatal(1,"Unexpected steady-state input bubble");
    for(int mask=1;mask<16;mask++)
      for(int pattern=0;pattern<16;pattern++) begin
        cycle(1,4'(mask),4'(pattern),0);
        cycle(1,4'(16-mask),4'(~pattern),0);
        cycle(1,4'(mask),1,0);
        cycle(0,0,14,0);
        cycle(0,0,15,0);
      end
    // Cancel partially delivered beats, then reuse storage with new payloads.
    repeat(8) begin
      cycle(1,15,0,0); cycle(1,15,1,0); cycle(1,15,2,0);
      cycle(1,15,15,1); cycle(1,15,15,0);
    end
    repeat(4) cycle(0,0,15,0);
    for(int l=0;l<4;l++) if(expected_id[l].size()!=0) $fatal(1,"Missing beat");
    if(!empty || total_beats != reads[0]+reads[1]+reads[2]+reads[3]+cancels)
      $fatal(1,"Conservation failure");
    if(partials==0 || stalled==0 || simultaneous==0 || cancels==0) $fatal(1,"Vacuous coverage");
    $display("PAYLOAD_PASS packets=%0d beats=%0d delivered=%0d cancelled=%0d partial=%0d blocked=%0d concurrent=%0d",
      writes,total_beats,total_beats-cancels,cancels,partials,stalled,simultaneous);
    $finish;
  end
  initial begin #100000; $fatal(1,"Watchdog"); end
endmodule
