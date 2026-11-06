`timescale 1ns/1ps
module qbs_mixed_reader_tb;
  import axi_pkg::*;
  import qbs_pkg::*;
  `include "axi/typedef.svh"
  typedef logic [63:0] addr_t;
  typedef logic [255:0] data_t;
  typedef logic [0:0] id_t;
  typedef logic [0:0] user_t;
  typedef logic [7:0] tag_t;
  typedef struct packed { logic [63:0] cause, tval; logic valid; } exception_t;
  `AXI_TYPEDEF_AR_CHAN_T(ar_t, addr_t, id_t, user_t)
  `AXI_TYPEDEF_R_CHAN_T(r_t, data_t, id_t, user_t)
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, rv = 0, rr;
  addr_t va = 0;
  logic [15:0] bytes = 0;
  tag_t tag = 0;
  size_t size = 4;
  logic dv, dr = 1, cv, cr = 1, fv, fr = 0, busy;
  data_t data;
  logic [31:0] strb;
  logic [15:0] offset;
  tag_t dt, ct, ft;
  qbs_read_fault_e fk;
  addr_t fva;
  exception_t fexc;
  logic pv, pa, av, ardy, iv, irdy;
  addr_t paddr;
  logic [12:0] pbytes;
  ar_t ar;
  r_t rsp;
  logic [31:0] ranges, ars, beats, payload;
  logic [1:0] max_outstanding;
  logic [63:0] ticks = 0;
  bit normal_check = 0, hold_responses = 0, deny_wide_footprint = 0, inject_error = 0;
  bit hold_second_ar = 0;
  int cases = 0, fault_cases = 0, footprints = 0;
  addr_t ref_va [2];
  int ref_bytes [2], ref_size [2], received [2], completed [2];
  addr_t slave_addr [2];
  int slave_len [2], slave_size [2];
  bit slave_rd = 0, slave_wr = 0;
  int slave_count = 0, slave_beat = 0;

  qbs_read_engine #(.AxiDataWidth(256), .AxiAddrWidth(64), .VAddrWidth(64),
    .PAddrWidth(64), .PerRangeTransferSize(1'b1), .axi_ar_t(ar_t), .axi_r_t(r_t),
    .tag_t(tag_t), .exception_t(exception_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .range_valid_i(rv), .range_ready_o(rr),
    .range_vaddr_i(va), .range_bytes_i(bytes), .range_tag_i(tag),
    .range_cache_i(4'b0011), .range_prot_i(3'b000), .range_size_i(size),
    .data_valid_o(dv), .data_ready_i(dr), .data_o(data), .data_strb_o(strb),
    .data_offset_o(offset), .data_tag_o(dt), .completion_valid_o(cv),
    .completion_ready_i(cr), .completion_tag_o(ct), .fault_valid_o(fv), .fault_ready_i(fr),
    .fault_kind_o(fk), .fault_vaddr_o(fva), .fault_tag_o(ft), .fault_mmu_exception_o(fexc),
    .core_st_pending_i(1'b0), .en_ld_st_translation_i(1'b0), .mmu_req_o(),
    .mmu_vaddr_o(), .mmu_is_store_o(), .mmu_valid_i(1'b0), .mmu_paddr_i(64'b0),
    .mmu_exception_valid_i(1'b0), .mmu_exception_i(exception_t'('0)),
    .physical_check_valid_o(pv), .physical_check_addr_o(paddr), .physical_check_bytes_o(pbytes),
    .physical_range_allowed_i(pa), .axi_ar_o(ar), .axi_ar_valid_o(av), .axi_ar_ready_i(ardy),
    .axi_r_i(rsp), .axi_r_valid_i(iv), .axi_r_ready_o(irdy), .counters_clear_i(1'b0),
    .range_count_o(ranges), .translation_count_o(), .ar_count_o(ars), .r_beat_count_o(beats),
    .payload_byte_count_o(payload), .store_wait_cycles_o(), .r_backpressure_cycles_o(),
    .outstanding_occupancy_sum_o(), .outstanding_max_o(max_outstanding),
    .outstanding_full_cycles_o(), .busy_o(busy)
  );

  function automatic byte mem_byte(input addr_t at);
    return at[7:0] ^ at[15:8] ^ at[23:16] ^ 8'h5a;
  endfunction
  function automatic int ref_index(input tag_t at);
    if (at == 8'h11) return 0;
    if (at == 8'h22) return 1;
    $fatal(1, "Unexpected normal tag %h", at);
    return 0;
  endfunction

  assign pa = !(deny_wide_footprint && paddr == 64'h2000 && pbytes == 32);
  assign ardy = slave_count < 2 && ticks % 5 != 1 && !(hold_second_ar && ars != 0);
  assign iv = slave_count != 0 && !hold_responses;
  always_comb begin
    addr_t cursor, word;
    int width;
    rsp = '0;
    cursor = slave_addr[slave_rd] + addr_t'(slave_beat << slave_size[slave_rd]);
    word = cursor & ~64'd31;
    width = 1 << slave_size[slave_rd];
    for (int b = 0; b < 32; b++)
      rsp.data[8*b +: 8] = word+b >= cursor && word+b < cursor+width ? mem_byte(word+b) : 8'hc7;
    rsp.last = slave_beat == slave_len[slave_rd];
    rsp.resp = inject_error && slave_beat == 0 ? RESP_SLVERR : RESP_OKAY;
  end

  always @(posedge clk) begin
    if (!rst_n) begin
      slave_count <= 0;
      slave_rd <= 0;
      slave_wr <= 0;
      slave_beat <= 0;
    end else begin
      case ({av && ardy, iv && irdy && rsp.last})
        2'b10: slave_count <= slave_count + 1;
        2'b01: slave_count <= slave_count - 1;
        default: ;
      endcase
      if (av && ardy) begin
        slave_addr[slave_wr] <= ar.addr;
        slave_size[slave_wr] <= int'(ar.size);
        slave_len[slave_wr] <= int'(ar.len);
        slave_wr <= !slave_wr;
        if ((int'(ar.addr[11:0]) + ((int'(ar.len)+1) << ar.size)) > 4096)
          $fatal(1, "AXI page crossing");
        if (normal_check && int'(ar.size) != ref_size[ref_index(dut.ar_tag_q)])
          $fatal(1, "Range size lost before AR");
      end
      if (iv && irdy) begin
        if (rsp.last) begin slave_rd <= !slave_rd; slave_beat <= 0; end
        else slave_beat <= slave_beat + 1;
      end
    end
  end

  bit stalled = 0;
  ar_t stalled_ar;
  always @(posedge clk) begin
    ticks = ticks + 1;
    if (!rst_n) stalled <= 0;
    else begin
      if (stalled && (!av || ar !== stalled_ar)) $fatal(1, "Stalled mixed-size AR changed");
      stalled <= av && !ardy;
      stalled_ar <= ar;
      if (pv) begin
        if (pbytes == 0 || int'(paddr[11:0])+int'(pbytes) > 4096)
          $fatal(1, "Incorrect permission footprint");
        footprints++;
      end
      if (normal_check) begin
        if (fv) $fatal(1, "Unexpected normal fault");
        if (dv && dr) begin
          int index, count;
          index = ref_index(dt);
          count = $countones(strb);
          if (offset != received[index] || count < 1 || count > (1 << ref_size[index]) ||
              (strb & (strb + 32'd1)) != 0) $fatal(1, "Payload tag/offset/size mismatch");
          for (int b = 0; b < count; b++)
            if (data[8*b +: 8] !== mem_byte(ref_va[index]+offset+b))
              $fatal(1, "Payload byte mismatch tag=%h offset=%0d byte=%0d", dt, offset, b);
          received[index] += count;
        end
        if (cv && cr) begin
          int index;
          index = ref_index(ct);
          if (received[index] != ref_bytes[index] || completed[index] != 0)
            $fatal(1, "Premature/duplicate range completion");
          completed[index]++;
        end
      end
    end
  end
  always @(negedge clk) begin
    dr = ticks % 7 != 2 && ticks % 7 != 3;
    cr = ticks % 11 != 6;
  end

  task automatic reset_case;
    @(negedge clk);
    rv = 0;
    normal_check = 0;
    hold_responses = 0;
    deny_wide_footprint = 0;
    inject_error = 0;
    hold_second_ar = 0;
    fr = 0;
    rst_n = 0;
    repeat (2) @(negedge clk);
    rst_n = 1;
    for (int i = 0; i < 2; i++) begin received[i] = 0; completed[i] = 0; end
  endtask
  task automatic send_range(input addr_t start, input int length, transfer_size, input tag_t identity);
    int bound;
    @(negedge clk);
    va = start; bytes = 16'(length); size = size_t'(transfer_size); tag = identity; rv = 1;
    bound = 0;
    do begin
      @(posedge clk);
      bound++;
      if (bound > 100) $fatal(1, "Range input timeout");
    end while (!rr);
    @(negedge clk);
    rv = 0;
  endtask
  task automatic service_counts(input addr_t start, input int length, transfer_size,
                                 output int expected_ars, expected_beats);
    int todo, take, head_bytes, width, burst_beats;
    addr_t cursor;
    todo = length; cursor = start; width = 1 << transfer_size;
    expected_ars = 0; expected_beats = 0;
    while (todo != 0) begin
      head_bytes = int'(cursor % width);
      take = todo;
      if (take > 4096-int'(cursor[11:0])) take = 4096-int'(cursor[11:0]);
      if (take > 256*width-head_bytes) take = 256*width-head_bytes;
      burst_beats = (head_bytes+take+width-1)/width;
      expected_beats += burst_beats;
      expected_ars++;
      cursor += take;
      todo -= take;
    end
  endtask
  task automatic normal_pair(input int first_size, phase, long_case);
    int bound, expected_ars, expected_beats, a, b;
    reset_case();
    ref_va[0] = long_case ? 64'h8ff0+phase : 64'h8000+phase;
    ref_va[1] = 64'h1ff0+phase;
    ref_bytes[0] = long_case ? 4113 : 33+phase;
    ref_bytes[1] = 840;
    ref_size[0] = first_size;
    ref_size[1] = first_size == 5 ? 4 : 5;
    normal_check = 1;
    hold_responses = phase % 4 == 0;
    send_range(ref_va[0], ref_bytes[0], ref_size[0], 8'h11);
    send_range(ref_va[1], ref_bytes[1], ref_size[1], 8'h22);
    bound = 0;
    while (hold_responses && ars < 2) begin
      @(negedge clk);
      bound++;
      if (bound > 100) $fatal(1, "Two-outstanding setup timeout");
    end
    hold_responses = 0;
    bound = 0;
    while (completed[0] != 1 || completed[1] != 1 || busy || slave_count != 0) begin
      @(negedge clk);
      bound++;
      if (bound > 15000) $fatal(1, "Normal pair drain timeout");
    end
    service_counts(ref_va[0], ref_bytes[0], ref_size[0], expected_ars, expected_beats);
    service_counts(ref_va[1], ref_bytes[1], ref_size[1], a, b);
    if (ranges != 2 || ars != expected_ars+a || beats != expected_beats+b ||
        payload != ref_bytes[0]+ref_bytes[1]) $fatal(1, "Mixed reader counters differ from independent geometry");
    if (phase % 4 == 0 && max_outstanding != 2) $fatal(1, "Missing two-outstanding coverage");
    cases++;
  endtask
  task automatic finish_fault(input qbs_read_fault_e kind, input tag_t identity, input addr_t expected_va);
    int bound;
    bound = 0;
    while (!fv) begin
      @(negedge clk);
      bound++;
      if (bound > 1000) $fatal(1, "Fault drain timeout");
    end
    if (fk != kind || ft != identity || fva != expected_va || slave_count != 0 || av)
      $fatal(1, "Fault identity/drain mismatch");
    repeat (3) begin
      @(negedge clk);
      if (!fv || !busy) $fatal(1, "Fault response not retained");
    end
    fr = 1;
    @(negedge clk);
    fr = 0;
    fault_cases++;
  endtask

  initial begin
    repeat (3) @(negedge clk);
    for (int s = 0; s <= 5; s++) begin
      for (int phase = 0; phase < 32; phase++) normal_pair(s, phase, 0);
      $display("MIXED_READER_SIZE_PASS size=%0d cases=%0d", s, cases);
    end
    for (int s = 4; s <= 5; s++)
      for (int phase = 0; phase < 32; phase++) normal_pair(s, phase, 1);

    reset_case();
    send_range(64'h9010, 32, 6, 8'h33);
    finish_fault(QBS_READ_FAULT_REQUEST, 8'h33, 64'h9010);
    if (ars != 0 || payload != 0) $fatal(1, "Invalid-size request issued memory work");

    reset_case();
    deny_wide_footprint = 1;
    send_range(64'h2010, 16, 5, 8'h33);
    finish_fault(QBS_READ_FAULT_PMA, 8'h33, 64'h2010);
    if (ars != 0 || payload != 0) $fatal(1, "Denied wide footprint issued memory work");

    reset_case();
    deny_wide_footprint = 1;
    ref_va[0] = 64'h2010; ref_va[1] = 64'h3003;
    ref_bytes[0] = 16; ref_bytes[1] = 61;
    ref_size[0] = 4; ref_size[1] = 5;
    normal_check = 1;
    send_range(ref_va[0], ref_bytes[0], ref_size[0], 8'h11);
    send_range(ref_va[1], ref_bytes[1], ref_size[1], 8'h22);
    for (int bound = 0; completed[0] != 1 || completed[1] != 1 || busy; bound++) begin
      @(negedge clk);
      if (bound > 500) $fatal(1, "Legal narrow permission control timed out");
    end
    cases++;

    for (int stalled_fault = 0; stalled_fault < 2; stalled_fault++) begin
      reset_case();
      hold_responses = 1;
      hold_second_ar = stalled_fault != 0;
      send_range(64'h8003, 61, 4, 8'h11);
      send_range(64'h9007, 65, 5, 8'h22);
      for (int bound = 0; !((stalled_fault == 0 && ars == 2) ||
                            (stalled_fault == 1 && av && ars == 1)); bound++) begin
        @(negedge clk);
        if (bound > 100) $fatal(1, "Mixed fault fixture setup timed out");
      end
      inject_error = 1;
      hold_responses = 0;
      repeat (5) @(negedge clk);
      if (stalled_fault && (!av || ar.size != 5)) $fatal(1, "Wide stalled AR lost across older narrow fault");
      hold_second_ar = 0;
      finish_fault(QBS_READ_FAULT_AXI_RESPONSE, 8'h11, 64'h8003);
      if (payload != 0) $fatal(1, "Faulting response leaked payload");
    end
    normal_pair(5, 31, 0);
    $display("MIXED_READER_COMPONENT_PASS cases=%0d faults=%0d footprint_checks=%0d", cases, fault_cases, footprints);
    $finish;
  end
  initial begin
    #100000000;
    $fatal(1, "Mixed reader bench watchdog");
  end
endmodule
