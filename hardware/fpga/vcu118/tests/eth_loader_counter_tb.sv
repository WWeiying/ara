// Check the counter specialization separately at capacity and simultaneous completion.
module tb;
  timeunit 1ns; timeprecision 1ps;
  logic clk=0, rst_n=0, push=0, pop=0, select_port=0;
  always #5 clk=~clk;
  logic [1:0] full, occupied, selected, outstanding;
  localparam int Width=cf_math_pkg::idx_width(32);
  int count=0, checks=0, capacity_visits=0, simultaneous=0, seed=32'h117ac;
  for (genvar g=0; g<2; g++) begin : cases
    localparam int Bits=g==0 ? 8 : 1;
    axi_demux_id_counters #(.AxiIdBits(Bits), .CounterWidth(Width)) dut (
      .clk_i(clk), .rst_ni(rst_n), .lookup_axi_id_i(Bits'(0)),
      .lookup_mst_select_o(selected[g]), .lookup_mst_select_occupied_o(occupied[g]),
      .full_o(full[g]), .push_axi_id_i(Bits'(0)), .push_mst_select_i(select_port),
      .push_i(push), .inject_axi_id_i(Bits'(0)), .inject_i(1'b0),
      .pop_axi_id_i(Bits'(0)), .pop_i(pop), .any_outstanding_trx_o(outstanding[g])
    );
  end
  task automatic check;
    assert ({full[0],occupied[0],selected[0],outstanding[0]} ===
            {full[1],occupied[1],selected[1],outstanding[1]}) else $fatal(1,"counter mismatch");
    assert (full[1] == (count == (2**Width-1)) && occupied[1] == (count != 0) &&
            outstanding[1] == (count != 0)) else $fatal(1,"scoreboard count=%0d",count);
    checks++;
    if (full[1]) capacity_visits++;
  endtask
  task automatic tick(bit up, bit down);
    @(negedge clk); push=up; pop=down;
    if (!count) select_port=~select_port;
    #1; check();
    @(posedge clk); count+=int'(up)-int'(down);
    if (up && down) simultaneous++;
    #1; check();
  endtask
  initial begin
    seed=$urandom(seed);
    repeat (3) @(negedge clk); rst_n=1;
    repeat (2**Width-1) tick(1,0);
    repeat (32) tick(1,1);
    repeat (2**Width-1) tick(0,1);
    for (int i=0;i<2000;i++) begin
      bit up,down;
      down=count>0 && $urandom_range(0,1);
      up=(count < 2**Width-1 || down) && $urandom_range(0,1);
      tick(up,down);
    end
    @(negedge clk); rst_n=0; push=0; pop=0; count=0;
    #1; check();
    assert (capacity_visits>=32 && simultaneous>=32) else $fatal(1,"missing boundary coverage");
    $display("PASS: shared DDR fixed-ID counters checks=%0d capacity=%0d simultaneous=%0d",checks,capacity_visits,simultaneous);
    $finish;
  end
  initial begin #100000; $fatal(1,"counter watchdog"); end
endmodule
