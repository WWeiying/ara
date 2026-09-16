// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module qbs_payload_equivalence_tb;
  import qbs_pkg::*;
  logic clk_i = 0;
  always #5 clk_i = ~clk_i;
  logic rst_ni = 0;
  qbs_weight_profile_e weight_profile_i;
  qbs_activation_profile_e activation_profile_i;
  logic [1:0] weight_valid_i, activation_valid_i;
  logic [31:0] weight_mask_i, activation_mask_i;
  logic [1:0] weight_row_i [32], activation_context_i [32];
  logic [7:0] weight_offset_i [32];
  logic [8:0] activation_offset_i [32];
  logic [255:0] weight_data_i, activation_data_i;
  logic weight_read_i, activation_read_i;
  logic [7:0] read_k_i;
  logic [31:0] wc, ac, ref_wc, ref_ac;
  logic weight_pending_multiword_o, activation_pending_multiword_o;
  logic [7:0] wview [4][QbsMaxWeightBlockBytes];
  logic [7:0] aview [4][QbsMaxActivationBlockBytes];
  logic [7:0] ref_wview [4][QbsMaxWeightBlockBytes];
  logic [7:0] ref_aview [4][QbsMaxActivationBlockBytes];
  int checks;
  int trials = 4096;
  int unsigned rng = 32'h1b84b36d;

  function automatic int unsigned random_word();
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng;
  endfunction

  qbs_payload_buffer dut (
    .weight_source_phase_i('{default:'0}), .activation_source_phase_i('{default:'0}),
    .activation_layout_i(QBS_ACTIVATION_LAYOUT_ROW_MAJOR),
    .weight_location_i(), .activation_location_i(),
    .weight_window_o(), .activation_window_o(), .weight_side_o(), .activation_side_o(),
    .weight_consumed_o(wc), .activation_consumed_o(ac),
    .weight_view_o(wview), .activation_view_o(aview), .*
  );
  qbs_payload_buffer_reference ref_dut (
    .weight_consumed_o(ref_wc), .activation_consumed_o(ref_ac),
    .weight_view_o(ref_wview), .activation_view_o(ref_aview), .*
  );

  task automatic compare(input bit read_visible = 0);
    if (weight_valid_i[0])
      assert (weight_pending_multiword_o === (|(weight_mask_i[15:0] & ~ref_wc[15:0])))
        else $fatal(1, "weight pending capacity mismatch");
    if (activation_valid_i[0])
      assert (activation_pending_multiword_o === (|(activation_mask_i[15:0] & ~ref_ac[15:0])))
        else $fatal(1, "activation pending capacity mismatch");
    assert (wc === ref_wc && ac === ref_ac)
      else $fatal(1, "consumed mismatch profile=%0d check=%0d", weight_profile_i, checks);
    for (int slot = 0; slot < 2; slot++)
      for (int p = 0; p < 3; p++)
        for (int r = 0; r < 4; r++) begin
          assert (dut.write_req[slot][p][r] === ref_dut.write_req[slot][p][r])
            else $fatal(1, "write req mismatch");
          if (dut.write_req[slot][p][r]) begin
            assert (dut.write_addr[slot][p][r] === ref_dut.write_addr[slot][p][r] &&
                    dut.write_be[slot][p][r] === ref_dut.write_be[slot][p][r])
              else $fatal(1, "write address/enable mismatch");
            for (int b = 0; b < 32; b++) if (dut.write_be[slot][p][r][b])
              assert (dut.write_data[slot][p][r][8*b +: 8] ===
                      ref_dut.write_data[slot][p][r][8*b +: 8])
                else $fatal(1, "write data priority mismatch");
          end
        end
    for (int r = 0; r < 4; r++) begin
      // SRAM idle/write output behavior is unspecified; compare payload only
      // after a read, when the contract makes the addressed window visible.
      if (read_visible && weight_read_i)
        for (int b = 0; b < QbsMaxWeightBlockBytes; b++)
          assert (wview[r][b] === ref_wview[r][b]) else $fatal(1, "weight view mismatch");
      if (read_visible && activation_read_i)
        for (int b = 0; b < QbsMaxActivationBlockBytes; b++)
          assert (aview[r][b] === ref_aview[r][b]) else $fatal(1, "activation view mismatch");
    end
    checks++;
  endtask

  initial begin
    if ($value$plusargs("PAYLOAD_TRIALS=%d", trials))
      assert (trials > 0) else $fatal(1, "PAYLOAD_TRIALS must be positive");
    weight_valid_i = 0;
    activation_valid_i = 0;
    weight_read_i = 0;
    activation_read_i = 0;
    weight_mask_i = 0;
    activation_mask_i = 0;
    repeat (2) @(negedge clk_i);
    rst_ni = 1;
    for (int profile = 1; profile <= 9; profile++) begin
      weight_profile_i = qbs_weight_profile_e'(profile);
      activation_profile_i = profile inside {3, 6, 8, 9}
          ? QBS_ACTIVATION_PROFILE_Q8_0 : QBS_ACTIVATION_PROFILE_Q8_K;
      $display("QBS payload profile=%0d trials=%0d time=%0t", profile, trials, $time);
      for (int trial = 0; trial < trials; trial++) begin
        int wlen, alen, wb, ab;
        logic [31:0] old_wc, old_ac;
        wlen = qbs_weight_block_bytes(weight_profile_i);
        alen = qbs_activation_block_bytes(activation_profile_i);
        weight_valid_i = 2'(trial);
        activation_valid_i = 2'(trial >> 2);
        weight_read_i = weight_valid_i == 0;
        activation_read_i = activation_valid_i == 0;
        read_k_i = 8'(random_word() % qbs_weight_block_elements(weight_profile_i));
        weight_mask_i = random_word();
        activation_mask_i = random_word();
        wb = int'(random_word() % wlen);
        ab = int'(random_word() % alen);
        for (int b = 0; b < 32; b++) begin
          // Include continuous, scattered and duplicate-byte traffic.
          weight_offset_i[b] = 8'(trial % 3 == 0 ? (wb + b) % wlen :
              trial % 3 == 1 ? random_word() % wlen : wb);
          activation_offset_i[b] = 9'(trial % 3 == 0 ? (ab + b) % alen :
              trial % 3 == 1 ? random_word() % alen : ab);
          weight_row_i[b] = trial % 3 == 1 ? 2'(random_word()) : 2'(trial >> 4);
          activation_context_i[b] = trial % 3 == 1 ? 2'(random_word()) : 2'(trial >> 6);
          weight_data_i[8*b +: 8] = 8'(random_word());
          activation_data_i[8*b +: 8] = 8'(random_word());
        end
        #1;
        compare();
        old_wc = wc;
        old_ac = ac;
        // Incoming traffic must not feed back into pending consumption/ready.
        weight_mask_i[31:16] = ~weight_mask_i[31:16];
        activation_mask_i[31:16] = ~activation_mask_i[31:16];
        #1;
        compare();
        assert (wc[15:0] === old_wc[15:0] && ac[15:0] === old_ac[15:0])
          else $fatal(1, "new input changed pending consumption");
        @(posedge clk_i);
        #1;
        compare(1);
        @(negedge clk_i);
      end
    end
    $display("QBS payload equivalence PASS checks=%0d", checks);
    $finish;
  end
endmodule
