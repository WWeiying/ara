// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// Top level testbench module.

import "DPI-C" function void read_elf (input string filename);
import "DPI-C" function byte get_section (output longint address, output longint len);
import "DPI-C" context function byte read_section(input longint address, inout byte buffer[]);

`define STRINGIFY(x) `"x`"

module ara_tb;
  /*****************
   *  Definitions  *
   *****************/

//  `ifndef VERILATOR
//  timeunit      1ns;
//  timeprecision 1ps;
//  `endif

  initial begin
    string testcase;
    $fsdbDumpfile("ara_tb.fsdb");
    $fsdbDumpvars(0, ara_tb);
    $fsdbDumpMDA(0, ara_tb);
    $fsdbDumpvars("+all");

    void'($value$plusargs("TESTCASE=%s", testcase));
    
    `ifdef SAIF
    if(testcase != "") begin
        $dumpfile($sformatf("../vcd/%s.vcd", testcase));
    end else begin
        $dumpfile("../vcd/default.vcd");
    end
    $dumpvars(0, dut.i_ara_soc);
    `endif
  end

  `ifdef NR_LANES
  localparam NrLanes = `NR_LANES;
  `else
  localparam NrLanes = 8;
  `endif

  `ifdef VLEN
  localparam VLEN = `VLEN;
  `else
  localparam VLEN = 256;
  `endif

  localparam ClockPeriod  = 1ns;
  // Axi response delay [ps]
  localparam int unsigned AxiRespDelay = 200;

  localparam AxiAddrWidth      = 64;
  localparam AxiWideDataWidth  = 64 * NrLanes / 2;
  localparam AxiWideBeWidth    = AxiWideDataWidth / 8;
  localparam AxiWideByteOffset = $clog2(AxiWideBeWidth);

  localparam DRAMAddrBase = 64'h8000_0000;
  localparam DRAMLength   = 64'h4000_0000; // 1GByte of DDR (split between two chips on Genesys2)

  /********************************
   *  Clock and Reset Generation  *
   ********************************/

  logic clk;
  logic rst_n;

  // Controlling the reset
  initial begin
    clk   = 1'b0;
    rst_n = 1'b0;

    // Synch reset for TB memories
    repeat (10) #(ClockPeriod/2) clk = ~clk;
    clk = 1'b0;

    // Asynch reset for main system
    repeat (5) #(ClockPeriod);
    rst_n = 1'b1;
    repeat (5) #(ClockPeriod);

    // Start the clock
    forever #(ClockPeriod/2) clk = ~clk;
  end

  /*********
   *  DUT  *
   *********/

  logic [63:0] exit;

  // This TB must be implemented in C for integration with Verilator.
  // In order to Verilator to understand that the ara_testharness module is the top-level,
  // we do not instantiate it when Verilating this module.
  `ifndef VERILATOR
  ara_testharness #(
    .NrLanes     (NrLanes         ),
    .VLEN        (VLEN            ),
    .AxiAddrWidth(AxiAddrWidth    ),
    .AxiDataWidth(AxiWideDataWidth),
    .AxiRespDelay(AxiRespDelay    )
  ) dut (
    .clk_i (clk  ),
    .rst_ni(rst_n),
    .exit_o(exit )
  );
  `endif

  `ifdef TARGET_SRAM_MC
  localparam DRAMNumBanks=16;
  localparam DRAMWordsPerBank=8192;
  localparam DRAMBankSizeBytes=8192*AxiWideBeWidth;

  /*************************
   *  DRAM Initialization  *
   *************************/
  typedef logic [AxiAddrWidth-1:0] addr_t;
  typedef logic [AxiWideDataWidth-1:0] data_t;

  initial begin : dram_init
    automatic data_t mem_row;
    byte buffer [];
    addr_t address;
    addr_t length;
    string binary;
    addr_t word_addr;
    int bank_index;
    addr_t bank_offset;
    int word_index;
    data_t bank_data [DRAMNumBanks][DRAMWordsPerBank];

    for (int i = 0; i < DRAMNumBanks; i++) begin
        for (int j = 0; j < DRAMWordsPerBank; j++) begin
            bank_data[i][j] = '0;
        end
    end

    // tc_sram is initialized with zeros. We need to overwrite this value.
    repeat (2)
      #ClockPeriod;

    // Initialize memories
    void'($value$plusargs("PRELOAD=%s", binary));
    if (binary != "") begin
      // Read ELF
      read_elf(binary);
      $display("Loading ELF file %s", binary);
      while (get_section(address, length)) begin
        // Read sections
        automatic int nwords = (length + AxiWideBeWidth - 1)/AxiWideBeWidth;
        $display("Loading section %x of length %x", address, length);
        buffer = new[nwords * AxiWideBeWidth];
        void'(read_section(address, buffer));

        // Initializing memories
        for (int w = 0; w < nwords; w++) begin
          mem_row = '0;
          for (int b = 0; b < AxiWideBeWidth; b++) begin
            mem_row[8 * b +: 8] = buffer[w * AxiWideBeWidth + b];
          end

          word_addr = address + (w << AxiWideByteOffset);
          
          if (word_addr >= DRAMAddrBase && word_addr < DRAMAddrBase + (DRAMNumBanks * DRAMBankSizeBytes)) begin
            bank_index = (word_addr - DRAMAddrBase) / DRAMBankSizeBytes;
            bank_offset = (word_addr - DRAMAddrBase) % DRAMBankSizeBytes;
            word_index = bank_offset >> AxiWideByteOffset;
            
            if (bank_index < DRAMNumBanks && word_index < DRAMWordsPerBank) begin
              bank_data[bank_index][word_index] = mem_row;
            end else begin
              $display("Error: Address %x maps to invalid bank(%0d) or word(%0d)", 
                       word_addr, bank_index, word_index);
            end
          end else begin
                $display("Cannot initialize address %x, which doesn't fall into the L2 region.", word_addr);
          end
        end
      end

      for (int i = 0; i < DRAMNumBanks; i++) begin
        automatic string temp_file = $sformatf("temp_bank_%0d.dat", i);
        automatic int fd = $fopen(temp_file, "w");
        
        if (!fd) begin
          $error("Failed to open temporary file for bank %0d: %s", i, temp_file);
          $finish;
        end

        for (int w = 0; w < DRAMWordsPerBank; w++) begin
//          $fwriteh(fd, "%032h\n", {bank_data[i][w][7  :  0], bank_data[i][w][15 :  8], bank_data[i][w][23 : 16], bank_data[i][w][31 : 24],
//                                   bank_data[i][w][39 : 32], bank_data[i][w][47 : 40], bank_data[i][w][55 : 48], bank_data[i][w][63 : 56],
//                                   bank_data[i][w][71 : 64], bank_data[i][w][79 : 72], bank_data[i][w][87 : 80], bank_data[i][w][95 : 88],
//                                   bank_data[i][w][103: 96], bank_data[i][w][111:104], bank_data[i][w][119:112], bank_data[i][w][127:120]
//                                  });
          //$fwriteh(fd, "%032h\n", bank_data[i][w]);
          $fdisplay(fd,  "%032h", bank_data[i][w]);
        end

        $fclose(fd);

        $display("Initializing bank %0d with file %s", i, temp_file);
        case (i)
          0:  dut.i_ara_soc.gen_dram[0 ].i_dram.preloadData(temp_file);
          1:  dut.i_ara_soc.gen_dram[1 ].i_dram.preloadData(temp_file);
          2:  dut.i_ara_soc.gen_dram[2 ].i_dram.preloadData(temp_file);
          3:  dut.i_ara_soc.gen_dram[3 ].i_dram.preloadData(temp_file);
          4:  dut.i_ara_soc.gen_dram[4 ].i_dram.preloadData(temp_file);
          5:  dut.i_ara_soc.gen_dram[5 ].i_dram.preloadData(temp_file);
          6:  dut.i_ara_soc.gen_dram[6 ].i_dram.preloadData(temp_file);
          7:  dut.i_ara_soc.gen_dram[7 ].i_dram.preloadData(temp_file);
          8:  dut.i_ara_soc.gen_dram[8 ].i_dram.preloadData(temp_file);
          9:  dut.i_ara_soc.gen_dram[9 ].i_dram.preloadData(temp_file);
          10: dut.i_ara_soc.gen_dram[10].i_dram.preloadData(temp_file);
          11: dut.i_ara_soc.gen_dram[11].i_dram.preloadData(temp_file);
          12: dut.i_ara_soc.gen_dram[12].i_dram.preloadData(temp_file);
          13: dut.i_ara_soc.gen_dram[13].i_dram.preloadData(temp_file);
          14: dut.i_ara_soc.gen_dram[14].i_dram.preloadData(temp_file);
          15: dut.i_ara_soc.gen_dram[15].i_dram.preloadData(temp_file);
          default: $display("Invalid bank index: %0d", bank_index);
        endcase
        //$system($sformatf("rm -f %s", temp_file));
      end

    end else begin
      $error("Expecting a firmware to run, none was provided!");
      $finish;
    end
  end : dram_init

  `else
  /*************************
   *  DRAM Initialization  *
   *************************/
  typedef logic [AxiAddrWidth-1:0] addr_t;
  typedef logic [AxiWideDataWidth-1:0] data_t;

  initial begin : dram_init
    automatic data_t mem_row;
    byte buffer [];
    addr_t address;
    addr_t length;
    string binary;

    // tc_sram is initialized with zeros. We need to overwrite this value.
    repeat (2)
      #ClockPeriod;

    // Initialize memories
    void'($value$plusargs("PRELOAD=%s", binary));
    if (binary != "") begin
      // Read ELF
      read_elf(binary);
      $display("Loading ELF file %s", binary);
      while (get_section(address, length)) begin
        // Read sections
        automatic int nwords = (length + AxiWideBeWidth - 1)/AxiWideBeWidth;
        $display("Loading section %x of length %x", address, length);
        buffer = new[nwords * AxiWideBeWidth];
        void'(read_section(address, buffer));
        // Initializing memories
        for (int w = 0; w < nwords; w++) begin
          mem_row = '0;
          for (int b = 0; b < AxiWideBeWidth; b++) begin
            mem_row[8 * b +: 8] = buffer[w * AxiWideBeWidth + b];
          end
          if (address >= DRAMAddrBase && address < DRAMAddrBase + DRAMLength)
            // This requires the sections to be aligned to AxiWideByteOffset,
            // otherwise, they can be over-written.
              dut.i_ara_soc.i_dram.init_val[(address - DRAMAddrBase + (w << AxiWideByteOffset)) >> AxiWideByteOffset] = mem_row;
          else
            $display("Cannot initialize address %x, which doesn't fall into the L2 region.", address);
        end
      end
    end else begin
      $error("Expecting a firmware to run, none was provided!");
      $finish;
    end
  end : dram_init
  `endif


`ifndef TARGET_GATESIM

  /*************************
   *  PRINT STORED VALUES  *
   *************************/

  // This is useful to check that the ideal dispatcher simulation was correct

`ifndef IDEAL_DISPATCHER
  localparam OutResultFile = "../gold_results.txt";
`else
  localparam OutResultFile = "../id_results.txt";
`endif

  int fd;

  data_t                     ara_w;
  logic [AxiWideBeWidth-1:0] ara_w_strb;
  logic                      ara_w_valid;
  logic                      ara_w_ready;

  // Avoid dumping what it's not measured, e.g. cache warming
  logic dump_en_mask;

  initial begin
    fd = $fopen(OutResultFile, "w");
    $display("Dump results on %s", OutResultFile);
  end

  assign ara_w       = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w.data;
  assign ara_w_strb  = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w.strb;
  assign ara_w_valid = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w_valid;
  assign ara_w_ready = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.w_ready;

`ifndef IDEAL_DISPATCHER
  assign dump_en_mask = dut.i_ara_soc.hw_cnt_en_o[0];
`else
  // Ideal-Dispatcher system does not warm the scalar cache
  assign dump_en_mask = 1'b1;
`endif
  always_ff @(posedge clk)
    if (dump_en_mask)
      if (ara_w_valid && ara_w_ready)
        for (int b = 0; b < AxiWideBeWidth; b++)
          if (ara_w_strb[b])
            $fdisplay(fd, "%0x", ara_w[b*8 +: 8]);

`endif

  /*********
   *  EOC  *
   *********/

  always @(posedge clk) begin
    if (exit[0]) begin
      if (exit >> 1) begin
        $warning("Core Test ", $sformatf("*** FAILED *** (tohost = %0d)", (exit >> 1)));
      end else begin
        // Print vector HW runtime
`ifndef TARGET_GATESIM
        $display("[hw-cycles]: %d", int'(dut.runtime_buf_q));
        $display("[cva6-d$-stalls]: %d", int'(dut.dcache_stall_buf_q));
        $display("[cva6-i$-stalls]: %d", int'(dut.icache_stall_buf_q));
        $display("[cva6-sb-full]: %d", int'(dut.sb_full_buf_q));
`endif
        $info("Core Test ", $sformatf("*** SUCCESS *** (tohost = %0d)", (exit >> 1)));
      end

`ifndef TARGET_GATESIM
      $fclose(fd);
`endif

`ifdef SAIF
   $dumpoff;
   $dumpflush;
`endif
      $finish(exit >> 1);
    end
  end

// Dump VCD with a SW trigger
`ifdef VCD_DUMP

  /****************
  *  VCD DUMPING  *
  ****************/

`ifdef VCD_PATH
  string vcd_path = `STRINGIFY(`VCD_PATH);
`else
  string vcd_path = "../vcd/last_sim.vcd";
`endif

  localparam logic [63:0] VCD_TRIGGER_ON  = 64'h0000_0000_0000_0001;
  localparam logic [63:0] VCD_TRIGGER_OFF = 64'hFFFF_FFFF_FFFF_FFFF;

  event start_dump_event;
  event stop_dump_event;

  logic [63:0] event_trigger_reg;
  logic        dumping = 1'b0;

  assign event_trigger_reg =
           dut.i_ara_soc.i_ctrl_registers.event_trigger_o;

  initial begin
    $display("VCD_DUMP successfully defined\n");
  end

  always_ff @(posedge clk) begin
    if(event_trigger_reg == VCD_TRIGGER_ON && !dumping) begin
       $display("[TB - VCD] START DUMPING\n");
       -> start_dump_event;
       dumping = 1'b1;
    end
    if(event_trigger_reg == VCD_TRIGGER_OFF) begin
       -> stop_dump_event;
       $display("[TB - VCD] STOP DUMPING\n");
    end
  end

  initial begin
    @(start_dump_event);
    $vcdplusfile(vcd_path);
    $vcdpluson(0, dut.i_ara_soc);

    #1 $display("[TB - VCD] DUMPING...\n");

    @(stop_dump_event)
    $vcdplusclose;
    $finish;
  end

`endif

endmodule : ara_tb
