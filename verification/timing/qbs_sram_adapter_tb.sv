// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps

module qbs_sram_adapter_tb;
  import qbs_pkg::*;
  logic clk_i = 0;
  always #5 clk_i = ~clk_i;
  logic rst_ni = 0;
  logic clear_weight_i, clear_activation_i;
  qbs_weight_profile_e weight_profile_i;
  qbs_activation_profile_e activation_profile_i;
  logic [2:0] weight_row_count_i;
  qbs_activation_layout_e activation_layout_i;
  logic [3:0] m_i;
  logic weight_write_valid_i, weight_write_group_i;
  logic [1:0] weight_write_row_i;
  logic [9:0] weight_write_offset_i;
  logic [127:0] weight_write_data_i;
  logic [15:0] weight_write_strb_i;
  logic activation_write_valid_i;
  logic [1:0] activation_write_context_i;
  logic [11:0] activation_write_offset_i;
  logic [127:0] activation_write_data_i;
  logic [15:0] activation_write_strb_i;
  logic [31:0] weight_bytes [2], activation_bytes [2];
  logic all_weight [2], all_activation [2];

  logic [1:0] wready, aready;
  logic [1:0] wpending, apending;
  logic weight_read_i = 0, activation_read_i = 0;
  logic [7:0] read_k_i = 0;
  for (genvar bank = 0; bank < 2; bank++) begin : gen_adapter
    assign wpending[bank] = i_dut.weight_pending_q_valid;
    assign apending[bank] = i_dut.activation_pending_q_valid;
    qbs_block_adapter #(.ActivationContextBase(bank * 4)) i_dut (
      .weight_write_ready_o(wready[bank]), .activation_write_ready_o(aready[bank]),
      .weight_write_valid_i(weight_write_valid_i && (&wready)),
      .activation_write_valid_i(activation_write_valid_i && (&aready)),
      .activation_read_i(activation_read_i && (bank == 0 || m_i > 4)),
      .weight_block_o(), .activation_block_o(), .weight_complete_o(),
      .activation_complete_o(), .all_weight_complete_o(all_weight[bank]),
      .all_activation_complete_o(all_activation[bank]),
      .accepted_weight_bytes_o(weight_bytes[bank]),
      .accepted_activation_bytes_o(activation_bytes[bank]), .*
    );
  end

  bit seen_weight [4 * QbsMaxWeightBlockBytes];
  bit seen_activation [QbsMaxM * QbsMaxActivationBlockBytes];
  int expected_weight, expected_activation;
  int cycles, cases, simultaneous, duplicates, clear_collisions, idle_cycles;
  int stream_cases, stream_stalls, discontinuous_stalls;
  logic last_wfire, last_afire;
  int trace_file;

  // The scoreboard counts unique source bytes, independently of the RTL's
  // row/context steering. M8 padding is part of the packed source payload.
  task automatic tick(input bit drain = 1);
    int index, wlen, alen, old_total, drain_cycles;
    logic saved_w, saved_a;
    wlen = qbs_weight_block_bytes(weight_profile_i);
    alen = qbs_activation_block_bytes(activation_profile_i);
    @(posedge clk_i);
    last_wfire = weight_write_valid_i && (&wready);
    last_afire = activation_write_valid_i && (&aready);
    old_total = expected_weight + expected_activation;
    if (clear_weight_i) begin
      foreach (seen_weight[i]) seen_weight[i] = 0;
      expected_weight = 0;
    end else if (last_wfire) begin
      for (int lane = 0; lane < 16; lane++) if (weight_write_strb_i[lane]) begin
        index = unsigned'(weight_write_offset_i) + lane;
        if (!weight_write_group_i) index += unsigned'(weight_write_row_i) * wlen;
        if (index < unsigned'(weight_row_count_i) * wlen && !seen_weight[index]) begin
          seen_weight[index] = 1;
          expected_weight++;
        end
      end
    end
    if (clear_activation_i) begin
      foreach (seen_activation[i]) seen_activation[i] = 0;
      expected_activation = 0;
    end else if (last_afire) begin
      for (int lane = 0; lane < 16; lane++) if (activation_write_strb_i[lane]) begin
        index = unsigned'(activation_write_offset_i) + lane;
        if (activation_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR)
          index += unsigned'(activation_write_context_i) * alen;
        if (!seen_activation[index]) begin
          seen_activation[index] = 1;
          expected_activation++;
        end
      end
    end
    if (weight_write_valid_i && activation_write_valid_i &&
        !clear_weight_i && !clear_activation_i) simultaneous++;
    if (!weight_write_valid_i && !activation_write_valid_i) idle_cycles++;
    if ((clear_weight_i && weight_write_valid_i) ||
        (clear_activation_i && activation_write_valid_i)) clear_collisions++;
    if (!clear_weight_i && !clear_activation_i &&
        (weight_write_valid_i || activation_write_valid_i) &&
        old_total == expected_weight + expected_activation &&
        (|weight_write_strb_i || |activation_write_strb_i)) duplicates++;
    #1;
    saved_w = weight_write_valid_i;
    saved_a = activation_write_valid_i;
    weight_write_valid_i = 0;
    activation_write_valid_i = 0;
    // Ready permits write merging; it no longer means pending is empty.
    drain_cycles = 0;
    while (drain && (|wpending || |apending)) begin
      @(posedge clk_i);
      #1;
      drain_cycles++;
      assert (drain_cycles <= 2) else $fatal(1, "SRAM write failed to drain");
    end
    cycles++;
    assert (weight_bytes[0] <= expected_weight && weight_bytes[1] <= expected_weight &&
        activation_bytes[0] + activation_bytes[1] <= expected_activation)
      else $fatal(1, "committed-byte count exceeds accepted unique bytes");
    if (!(|wpending || |apending))
      assert (weight_bytes[0] == expected_weight && weight_bytes[1] == expected_weight &&
          activation_bytes[0] + activation_bytes[1] == expected_activation)
      else $fatal(1, "unique byte count mismatch cycle=%0d W=%0d/%0d A=%0d/%0d",
                  cycles, weight_bytes[0], expected_weight,
                  activation_bytes[0] + activation_bytes[1], expected_activation);
    if (cases == 0 && cycles <= 64)
      $fdisplay(trace_file, "%0d,%0d,%0d,%0d,%0d,%0h,%0d,%0h,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
          cycles, clear_weight_i, clear_activation_i, weight_write_valid_i,
          weight_write_offset_i, weight_write_strb_i, activation_write_offset_i,
          activation_write_strb_i, activation_write_valid_i, weight_bytes[0],
          activation_bytes[0], activation_bytes[1], all_weight[0],
          all_activation[0], all_activation[1]);
    @(negedge clk_i);
    #1;
    weight_write_valid_i = saved_w;
    activation_write_valid_i = saved_a;
  endtask

  task automatic read_windows;
    weight_write_valid_i = 0;
    activation_write_valid_i = 0;
    tick();
    weight_read_i = 1;
    activation_read_i = 1;
    for (int k = 0; k < qbs_weight_block_elements(weight_profile_i);
         k += (m_i == 1 ? 8 : m_i == 2 ? 4 : 2)) begin
      read_k_i = 8'(k);
      tick();
    end
    weight_read_i = 0;
    activation_read_i = 0;
    tick();
  endtask

  task automatic stream_case;
    int wp, ap, wlen, alen, wtotal, atotal, wn, an, stalls;
    wlen = qbs_weight_block_bytes(weight_profile_i);
    alen = qbs_activation_block_bytes(activation_profile_i);
    wtotal = unsigned'(weight_row_count_i) * wlen;
    atotal = (activation_layout_i == QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED
        ? 8 : unsigned'(m_i)) * alen;
    clear_weight_i = 1;
    clear_activation_i = 1;
    weight_write_valid_i = 0;
    activation_write_valid_i = 0;
    tick();
    clear_weight_i = 0;
    clear_activation_i = 0;
    wp = 0;
    ap = 0;
    stalls = 0;
    while (wp < wtotal || ap < atotal) begin
      wn = wtotal - wp;
      if (wn > 16) wn = 16;
      if (!weight_write_group_i && wn > wlen - wp % wlen) wn = wlen - wp % wlen;
      an = atotal - ap;
      if (an > 16) an = 16;
      if (activation_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR &&
          an > alen - ap % alen) an = alen - ap % alen;
      weight_write_valid_i = wn > 0;
      activation_write_valid_i = an > 0;
      weight_write_row_i = weight_write_group_i ? 0 : 2'(wp / wlen);
      weight_write_offset_i = weight_write_group_i ? 10'(wp) : 10'(wp % wlen);
      activation_write_context_i = activation_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR
          ? 2'(ap / alen) : 0;
      activation_write_offset_i = activation_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR
          ? 12'(ap % alen) : 12'(ap);
      weight_write_strb_i = 16'((1 << wn) - 1);
      activation_write_strb_i = 16'((1 << an) - 1);
      for (int lane = 0; lane < 16; lane++) begin
        weight_write_data_i[8*lane +: 8] = 8'(wp + lane + 113);
        activation_write_data_i[8*lane +: 8] = 8'(ap + lane + 157);
      end
      tick(0);
      if (last_wfire) wp += wn;
      else if (wn > 0) stalls++;
      if (last_afire) ap += an;
      else if (an > 0) stalls++;
      assert (stalls < 100) else $fatal(1, "stream did not advance");
    end
    read_windows();
    assert (all_weight[0] && all_weight[1] && all_activation[0] && all_activation[1]);
    assert (stalls == 0) else $fatal(1, "contiguous stream stalled: %0d", stalls);
    stream_stalls += stalls;
    stream_cases++;
    $display("QBS SRAM stream PASS profile=%0d M=%0d layout=%0d stalls=%0d",
             weight_profile_i, m_i, activation_layout_i, stalls);
  endtask

  task automatic run_case(input qbs_weight_profile_e profile, input int config_id);
    int wlen, alen, wp, ap, wtotal, atotal, wtake, atake;
    logic [15:0] wm, am, pattern;
    weight_profile_i = profile;
    activation_profile_i = qbs_default_activation_profile(profile);
    weight_write_group_i = config_id >= 2 && config_id != 7;
    weight_row_count_i = config_id >= 7 ? 2 : config_id == 0 ? 1 : config_id == 1 ? 3 : 4;
    m_i = config_id >= 7 ? 2 : config_id == 0 ? 1 : config_id == 1 ? 3 : 4'(config_id + 2);
    activation_layout_i = config_id < 2 || config_id >= 7 ? QBS_ACTIVATION_LAYOUT_ROW_MAJOR :
        config_id == 2 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED :
                         QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED;
    wlen = qbs_weight_block_bytes(profile);
    alen = qbs_activation_block_bytes(activation_profile_i);
    wtotal = unsigned'(weight_row_count_i) * wlen;
    atotal = (activation_layout_i == QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED
        ? 8 : unsigned'(m_i)) * alen;
    stream_case();
    weight_write_row_i = 0;
    activation_write_context_i = 0;
    weight_write_offset_i = 0;
    activation_write_offset_i = 0;
    weight_write_valid_i = 1;
    activation_write_valid_i = 1;
    weight_write_strb_i = '1;
    activation_write_strb_i = '1;
    clear_weight_i = 1;
    clear_activation_i = 1;
    tick();
    clear_weight_i = 0;
    clear_activation_i = 0;
    weight_write_strb_i = 0;
    activation_write_strb_i = 0;
    tick();

    wp = 0;
    ap = 0;
    while (wp < wtotal || ap < atotal) begin
      // Unequal beat lengths exercise simultaneous traffic, independent
      // completion, unaligned boundaries and both M8 context banks.
      wtake = wtotal - wp;
      if (wtake > 13) wtake = 13;
      if (!weight_write_group_i && wtake > wlen - (wp % wlen))
        wtake = wlen - (wp % wlen);
      atake = atotal - ap;
      if (atake > 11) atake = 11;
      if (activation_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR &&
          atake > alen - (ap % alen)) atake = alen - (ap % alen);
      weight_write_valid_i = wtake != 0;
      activation_write_valid_i = atake != 0;
      weight_write_row_i = weight_write_group_i ? 0 : 2'(wp / wlen);
      weight_write_offset_i = weight_write_group_i ? 10'(wp) : 10'(wp % wlen);
      activation_write_context_i = activation_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR
          ? 2'(ap / alen) : 0;
      activation_write_offset_i = activation_layout_i == QBS_ACTIVATION_LAYOUT_ROW_MAJOR
          ? 12'(ap % alen) : 12'(ap);
      wm = 16'((1 << wtake) - 1);
      am = 16'((1 << atake) - 1);
      for (int pass = 0; pass < 3; pass++) begin
        pattern = pass == 0 ? 16'h5a5a : pass == 1 ? 16'ha5a5 : 16'hffff;
        weight_write_strb_i = wm & pattern;
        activation_write_strb_i = am & pattern;
        for (int lane = 0; lane < 16; lane++) begin
          weight_write_data_i[lane*8 +: 8] = 8'(wp + lane + 53 * pass + cases);
          activation_write_data_i[lane*8 +: 8] = 8'(ap + lane + 97 * pass + cases);
        end
        tick();
      end
      wp += wtake;
      ap += atake;
      weight_write_valid_i = 0;
      activation_write_valid_i = 0;
      tick();
    end
    assert (all_weight[0] && all_weight[1] && all_activation[0] && all_activation[1])
      else $fatal(1, "block completion mismatch profile=%0d config=%0d", profile, config_id);
    assert (expected_weight == wtotal && expected_activation == atotal)
      else $fatal(1, "full payload count mismatch");
    $display("QBS adapter case PASS profile=%0d M=%0d rows=%0d group=%0b layout=%0d W=%0d A=%0d",
             profile, m_i, weight_row_count_i, weight_write_group_i,
             activation_layout_i, wtotal, atotal);
    weight_write_valid_i = 0;
    activation_write_valid_i = 0;
    weight_read_i = 1;
    activation_read_i = 1;
    for (int k = 0; k < qbs_weight_block_elements(profile);
         k += (m_i == 1 ? 8 : m_i == 2 ? 4 : 2)) begin
      read_k_i = 8'(k);
      tick();
    end
    weight_read_i = 0;
    activation_read_i = 0;
    tick();
    // Cancel pending payload, including an unrelated read-domain clear.
    weight_write_valid_i = 1;
    activation_write_valid_i = 1;
    weight_write_row_i = 0;
    weight_write_offset_i = 10'(wlen > 100 ? 42 : 2);
    activation_write_context_i = 0;
    activation_write_offset_i = 12'(alen > 100 ? 28 : 2);
    weight_write_strb_i = 16'hffff;
    activation_write_strb_i = 16'hffff;
    if (weight_profile_i inside {QBS_WEIGHT_PROFILE_Q5_0})
      weight_write_offset_i = 6;
    @(posedge clk_i);
    #1;
    clear_weight_i = 1;
    clear_activation_i = 1;
    weight_write_valid_i = 0;
    activation_write_valid_i = 0;
    tick();
    clear_weight_i = 0;
    clear_activation_i = 0;
    tick();
    // Clear one domain while a duplicate beat is presented to the other.
    clear_weight_i = 1;
    activation_write_valid_i = 1;
    activation_write_context_i = 0;
    activation_write_offset_i = 0;
    activation_write_strb_i = '1;
    tick();
    clear_weight_i = 0;
    clear_activation_i = 1;
    activation_write_valid_i = 0;
    tick();
    clear_activation_i = 0;
    cases++;
  endtask

  task automatic discontinuous_case;
    int offsets [6] = '{24, 88, 96, 100, 24, 32};
    bit wdone, adone;
    int wlen, alen;
    weight_profile_i = QBS_WEIGHT_PROFILE_Q6_K;
    activation_profile_i = QBS_ACTIVATION_PROFILE_Q8_K;
    weight_row_count_i = 2;
    m_i = 2;
    activation_layout_i = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
    weight_write_valid_i = 0;
    activation_write_valid_i = 0;
    clear_weight_i = 1;
    clear_activation_i = 1;
    tick();
    clear_weight_i = 0;
    clear_activation_i = 0;
    wlen = qbs_weight_block_bytes(weight_profile_i);
    alen = qbs_activation_block_bytes(activation_profile_i);
    for (int seq = 0; seq < 12; seq++) begin
      weight_write_group_i = seq == 11;
      weight_write_row_i = 2'(seq / 6);
      activation_write_context_i = 2'(seq / 6);
      weight_write_offset_i = 10'(offsets[seq % 6] + (seq == 11 ? wlen : 0));
      activation_write_offset_i = 12'(offsets[seq % 6] + 4);
      weight_write_strb_i = seq % 6 == 3 ? 16'h5a5a : 16'hffff;
      activation_write_strb_i = seq % 6 == 3 ? 16'ha5a5 : 16'hffff;
      for (int lane = 0; lane < 16; lane++) begin
        weight_write_data_i[8*lane +: 8] = 8'(31*seq + lane);
        activation_write_data_i[8*lane +: 8] = 8'(73*seq + lane);
      end
      wdone = 0;
      adone = 0;
      while (!wdone || !adone) begin
        weight_write_valid_i = !wdone;
        activation_write_valid_i = !adone;
        tick(0);
        if (weight_write_valid_i && !last_wfire) discontinuous_stalls++;
        if (activation_write_valid_i && !last_afire) discontinuous_stalls++;
        wdone |= last_wfire;
        adone |= last_afire;
      end
    end
    weight_write_valid_i = 0;
    activation_write_valid_i = 0;
    tick();
    // Fill only missing bytes, so the read-window comparison also verifies
    // the newer duplicate values written while an older beat was pending.
    weight_write_group_i = 0;
    for (int row = 0; row < 2; row++) begin
      weight_write_row_i = 2'(row);
      activation_write_context_i = 2'(row);
      for (int off = 0; off < alen; off += 16) begin
        weight_write_offset_i = 10'(off);
        activation_write_offset_i = 12'(off);
        weight_write_strb_i = 0;
        activation_write_strb_i = 0;
        for (int lane = 0; lane < 16; lane++) begin
          if (off + lane < wlen && !seen_weight[row*wlen+off+lane])
            weight_write_strb_i[lane] = 1;
          if (off + lane < alen && !seen_activation[row*alen+off+lane])
            activation_write_strb_i[lane] = 1;
          weight_write_data_i[8*lane +: 8] = 8'(off + lane + row);
          activation_write_data_i[8*lane +: 8] = 8'(off + lane + row + 41);
        end
        weight_write_valid_i = |weight_write_strb_i;
        activation_write_valid_i = |activation_write_strb_i;
        tick();
      end
    end
    assert (discontinuous_stalls > 0) else $fatal(1, "missing capacity backpressure test");
    read_windows();
    $display("QBS SRAM discontinuous/duplicate PASS stalls=%0d", discontinuous_stalls);
  endtask

  task automatic all_strobes;
    weight_profile_i = QBS_WEIGHT_PROFILE_Q4_K;
    activation_profile_i = QBS_ACTIVATION_PROFILE_Q8_K;
    weight_row_count_i = 1;
    m_i = 1;
    activation_layout_i = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
    weight_write_group_i = 0;
    weight_write_row_i = 0;
    activation_write_context_i = 0;
    weight_write_offset_i = 0;
    activation_write_offset_i = 0;
    for (int mask = 0; mask < 65536; mask++) begin
      clear_weight_i = 1;
      clear_activation_i = 1;
      weight_write_valid_i = 0;
      activation_write_valid_i = 0;
      tick();
      clear_weight_i = 0;
      clear_activation_i = 0;
      weight_write_valid_i = 1;
      activation_write_valid_i = 1;
      weight_write_strb_i = 16'(mask);
      activation_write_strb_i = 16'(mask);
      tick();
    end
    weight_write_valid_i = 0;
    activation_write_valid_i = 0;
    tick();
  endtask

  initial begin
    clear_weight_i = 0;
    clear_activation_i = 0;
    weight_profile_i = QBS_WEIGHT_PROFILE_Q4_K;
    activation_profile_i = QBS_ACTIVATION_PROFILE_Q8_K;
    weight_row_count_i = 1;
    activation_layout_i = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
    m_i = 1;
    weight_write_valid_i = 0;
    activation_write_valid_i = 0;
    weight_write_group_i = 0;
    weight_write_row_i = 0;
    activation_write_context_i = 0;
    weight_write_offset_i = 0;
    activation_write_offset_i = 0;
    weight_write_strb_i = 0;
    activation_write_strb_i = 0;
    weight_write_data_i = 0;
    activation_write_data_i = 0;
    trace_file = $fopen("adapter_cycles.csv", "w");
    if (!trace_file) $fatal(1, "cannot open adapter trace");
    $fdisplay(trace_file, "cycle,clear_w,clear_a,wvalid,woff,wstrb,aoff,astrb,avalid,wbytes,a0bytes,a1bytes,wcomplete,a0complete,a1complete");
    repeat (3) @(negedge clk_i);
    #1;
    rst_ni = 1;
    for (int profile = 1; profile <= 9; profile++)
      for (int config_id = 0; config_id < 9; config_id++)
        run_case(qbs_weight_profile_e'(profile), config_id);
    discontinuous_case();
    all_strobes();
    assert (simultaneous > 0 && duplicates > 0 && clear_collisions > 0 && idle_cycles > 0)
      else $fatal(1, "missing adapter corner coverage");
    $display("QBS SRAM adapter PASS cases=%0d strobe_masks=65536 cycles=%0d simultaneous=%0d duplicates=%0d clear_collisions=%0d idle=%0d",
             cases, cycles, simultaneous, duplicates, clear_collisions, idle_cycles);
    assert (stream_cases == 81 && stream_stalls == 0);
    $display("QBS SRAM streaming PASS cases=%0d stalls=%0d", stream_cases, stream_stalls);
    $fclose(trace_file);
    $finish;
  end
endmodule
