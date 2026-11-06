  // Observation-only probe in the frozen experimental generic-SRAM SoC.
`ifdef TARGET_SRAM_MC
  initial $fatal(1, "WIDE_SOC_PROBE_REQUIRES_GENERIC_MEMORY");
`else
  localparam int WideProbeExpectedBytes = 16 * 1024 * 1024;
  integer wide_probe_read_count = 0, wide_probe_write_count = 0;
  integer wide_probe_upper_write_count = 0, wide_probe_full_ar_count = 0;
  integer wide_probe_return_count = 0, wide_probe_run = 0, wide_probe_max_run = 0;
  logic wide_probe_prev_req = 1'b0;
  logic wide_probe_prev_read = 1'b0;
  initial begin
    assert (NrLanes == 4 && VLEN == 1024 && AxiDataWidth inside {128, 256} &&
            L2NumWords * (AxiDataWidth/8) == WideProbeExpectedBytes &&
            $bits(i_dram.init_val[0]) == AxiDataWidth &&
            $size(i_dram.init_val) == L2NumWords &&
            $bits(l2_rdata) == AxiDataWidth && $bits(l2_wdata) == AxiDataWidth)
      else $fatal(1, "WIDE_SOC_PHYSICAL_MEMORY_GEOMETRY");
    $display("WIDE_SOC_PLATFORM bits=%0d lanes=%0d vlen=%0d words=%0d bytes=%0d memory_width=%0d",
             AxiDataWidth, NrLanes, VLEN, L2NumWords, WideProbeExpectedBytes,
             $bits(i_dram.init_val[0]));
  end
  always @(posedge clk_i) begin
    if (!rst_ni) begin
      wide_probe_prev_req = 1'b0;
      wide_probe_prev_read = 1'b0;
      wide_probe_run = 0;
    end else begin
      assert (l2_rvalid === wide_probe_prev_req)
        else $fatal(1, "WIDE_SOC_MEMORY_RESPONSE_LATENCY");
      if (wide_probe_prev_read && l2_rvalid) begin
        wide_probe_return_count++;
        wide_probe_run++;
        if (wide_probe_run > wide_probe_max_run) wide_probe_max_run = wide_probe_run;
      end else wide_probe_run = 0;
      wide_probe_prev_req = l2_req;
      wide_probe_prev_read = l2_req && !l2_we;
      if (l2_req && !l2_we) wide_probe_read_count++;
      if (l2_req && l2_we) begin
        wide_probe_write_count++;
        if ((l2_be >> (AxiDataWidth/16)) != 0) wide_probe_upper_write_count++;
      end
      if (l2mem_wide_axi_req_wo_atomics.ar_valid &&
          l2mem_wide_axi_resp_wo_atomics.ar_ready &&
          l2mem_wide_axi_req_wo_atomics.ar.size == $clog2(AxiDataWidth/8))
        wide_probe_full_ar_count++;
    end
  end
  final begin
    $display("WIDE_SOC_MEMORY bits=%0d reads=%0d writes=%0d upper_writes=%0d full_ar=%0d returns=%0d max_read_run=%0d",
             AxiDataWidth, wide_probe_read_count, wide_probe_write_count,
             wide_probe_upper_write_count, wide_probe_full_ar_count,
             wide_probe_return_count, wide_probe_max_run);
  end
`endif
