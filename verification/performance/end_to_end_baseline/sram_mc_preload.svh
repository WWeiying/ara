// Explicit opt-in RTL-hierarchy adapter, never a replacement for a default loader.
// Define SRAM_MC_PRELOAD_ENABLE, _SOC (hierarchy), _WIDTH, _CAPACITY, _RESET_N.
// Bind/verify host manifest artifacts before simulation; supply
// +SRAM_MC_PRELOAD_DIR=<root> with root/w<width>/bank_<bank>_col_<column>.hex.
// Hold reset until sram_mc_preload_done. Do not enable another loader concurrently.
`ifdef SRAM_MC_PRELOAD_ENABLE
localparam int MCPreloadWidth = `SRAM_MC_PRELOAD_WIDTH;
localparam int MCPreloadCapacity = `SRAM_MC_PRELOAD_CAPACITY;
localparam int MCPreloadBanks = MCPreloadCapacity/(8192*(MCPreloadWidth/8));
localparam int MCPreloadColumns = MCPreloadWidth < 128 ? 1 : MCPreloadWidth/128;
wire [MCPreloadBanks*MCPreloadColumns-1:0] sram_mc_preload_loaded;
wire sram_mc_preload_done = &sram_mc_preload_loaded;

initial begin
  if (MCPreloadWidth < 8 || (MCPreloadWidth & (MCPreloadWidth-1)) != 0 ||
      MCPreloadCapacity <= 0 || MCPreloadCapacity % (8192*(MCPreloadWidth/8)) != 0 ||
      MCPreloadBanks < 1 || (MCPreloadBanks & (MCPreloadBanks-1)) != 0 ||
      `SRAM_MC_PRELOAD_SOC.AxiDataWidth != MCPreloadWidth ||
      `SRAM_MC_PRELOAD_SOC.L2NumWords*(MCPreloadWidth/8) != MCPreloadCapacity)
    $fatal(1, "MC_PRELOAD_GEOMETRY_FAIL");
end
`ifdef TSMC_INITIALIZE_FORMAT_BINARY
initial $fatal(1, "MC_PRELOAD_HEX_FORMAT_REQUIRED");
`endif

function automatic string sram_mc_preload_file(int bank, int column);
  string root, path, line;
  int fd, count, code;
  if (!$value$plusargs("SRAM_MC_PRELOAD_DIR=%s", root) || root == "")
    $fatal(1, "MC_PRELOAD_DIRECTORY_REQUIRED");
  path = $sformatf("%s/w%0d/bank_%0d_col_%0d.hex", root, MCPreloadWidth, bank, column);
  if (path.len() > 256) $fatal(1, "MC_PRELOAD_FILENAME_LIMIT_FAIL");
  fd = $fopen(path, "r");
  if (!fd) $fatal(1, "MC_PRELOAD_MISSING_FILE %s", path);
  for (int row = 0; row < 8192; row++) begin
    count = $fgets(line, fd);
    if (count != 33 || line.len() != 33 || line[32] != 8'h0a)
      $fatal(1, "MC_PRELOAD_LINE_FAIL row=%0d file=%s", row, path);
    for (int digit = 0; digit < 32; digit++) begin
      code = line[digit];
      if (!((code >= 48 && code <= 57) || (code >= 97 && code <= 102)))
        $fatal(1, "MC_PRELOAD_HEX_FAIL row=%0d file=%s", row, path);
    end
  end
  if ($fgetc(fd) != -1) $fatal(1, "MC_PRELOAD_EXTRA_DATA_FAIL %s", path);
  $fclose(fd);
  return path;
endfunction

for (genvar mc_bank = 0; mc_bank < MCPreloadBanks; mc_bank++) begin : gen_mc_preload_bank
  begin : primary
    logic done;
    assign sram_mc_preload_loaded[mc_bank*MCPreloadColumns] = done;
    initial begin
      string loadfile;
      done = 0;
      #1;
      if (`SRAM_MC_PRELOAD_RESET_N !== 0) $fatal(1, "MC_PRELOAD_RESET_REQUIRED");
      loadfile = sram_mc_preload_file(mc_bank, 0);
      `SRAM_MC_PRELOAD_SOC.gen_dram[mc_bank].i_dram.preloadData(loadfile);
      done = 1;
      $display("MC_PRELOAD_LOADED width=%0d bank=%0d column=0 words=8192", MCPreloadWidth, mc_bank);
    end
  end
  for (genvar mc_column = 1; mc_column < MCPreloadColumns; mc_column++) begin : extra
    logic done;
    assign sram_mc_preload_loaded[mc_bank*MCPreloadColumns+mc_column] = done;
    initial begin
      string loadfile;
      done = 0;
      #1;
      if (`SRAM_MC_PRELOAD_RESET_N !== 0) $fatal(1, "MC_PRELOAD_RESET_REQUIRED");
      loadfile = sram_mc_preload_file(mc_bank, mc_column);
      `SRAM_MC_PRELOAD_SOC.gen_dram[mc_bank].gen_columns[mc_column].i_dram.preloadData(loadfile);
      done = 1;
      $display("MC_PRELOAD_LOADED width=%0d bank=%0d column=%0d words=8192", MCPreloadWidth, mc_bank, mc_column);
    end
  end
end
`endif
