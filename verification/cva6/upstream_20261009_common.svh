  import ariane_pkg::*;
  function automatic config_pkg::cva6_cfg_t configuration();
    config_pkg::cva6_cfg_t c;
    c = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
    c.NrPMPEntries = 0;
    return c;
  endfunction
  localparam config_pkg::cva6_cfg_t CVA6Cfg = configuration();
  `include "upstream_20261009_types.svh"
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  int trace, input_file, id, completed = 0;
  string input_path;
  task automatic observe(string field, logic [63:0] value);
    $fdisplay(trace, "%0d %s %016h", id, field, value);
  endtask
  task automatic reset_dut();
    @(negedge clk); rst_n = 0;
    repeat (3) @(posedge clk);
    @(negedge clk); rst_n = 1;
  endtask
  task automatic open_files();
    if (CVA6Cfg.RVH || CVA6Cfg.XLEN != 64 || CVA6Cfg.PtLevels != 3)
      $fatal(1, "Only RV64 Sv39 no-H is in scope");
    if (!$value$plusargs("CASES=%s", input_path)) $fatal(1, "Missing CASES");
    input_file = $fopen(input_path, "r");
    trace = $fopen("observed.txt", "w");
    if (!input_file || !trace) $fatal(1, "Cannot open evidence files");
  endtask
  task automatic finish_test();
    if (!completed) $fatal(1, "No cases");
    $fclose(input_file); $fclose(trace);
    $display("UPSTREAM_COMPLETE cases=%0d", completed);
    $finish;
  endtask
  initial begin
    #10000000;
    $fatal(1, "Bounded module watchdog");
  end
