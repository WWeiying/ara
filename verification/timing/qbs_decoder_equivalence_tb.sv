// SPDX-License-Identifier: SHL-0.51
module qbs_decoder_equivalence_tb import qbs_pkg::*; ();
  qbs_weight_profile_e profile;
  qbs_activation_profile_e activation_profile;
  logic [2:0] m, rows;
  logic [7:0] k;
  logic [255:0] weight_window [4][2], activation_window [4];
  logic [127:0] narrow_weight_window [4][2];
  logic [7:0] weight_side [4][20], activation_side [4][36];
  wire [7:0] unused_weight [4][QbsMaxWeightBlockBytes];
  wire [7:0] unused_activation [4][QbsMaxActivationBlockBytes];
  logic [3:0] k_per [2], group_index [2];
  logic group_end [2];
  logic [15:0] valid [2];
  logic signed [7:0] weight_quant [2][4][8], activation_quant [2][4][8];
  logic signed [7:0] scale [2][16];
  logic [7:0] minimum [2][16];
  logic signed [15:0] aux [2][16];
  logic [15:0] d [2][4], dmin [2][4];
  logic [31:0] ad [2][4];
  int cases = 0;

  for (genvar row = 0; row < 4; row++) begin : gen_window
    wire short_payload = profile inside {
        QBS_WEIGHT_PROFILE_Q4_0, QBS_WEIGHT_PROFILE_Q5_0, QBS_WEIGHT_PROFILE_IQ4_NL};
    assign narrow_weight_window[row][0] = (k[4] && !short_payload)
        ? weight_window[row][0][255:128] : weight_window[row][0][127:0];
    assign narrow_weight_window[row][1] = k[4]
        ? weight_window[row][1][255:128] : weight_window[row][1][127:0];
  end

  for (genvar version = 0; version < 2; version++) begin : gen_decoder
    if (version == 0) begin : gen_dut
      qbs_profile_decoder #(.CompactRead(1)) i_decoder (
        .profile_i(profile), .activation_profile_i(activation_profile), .m_i(m),
        .row_count_i(rows), .k_base_i(k), .weight_block_i(unused_weight),
        .activation_block_i(unused_activation), .weight_window_i(narrow_weight_window),
        .activation_window_i(activation_window), .weight_side_i(weight_side),
        .activation_side_i(activation_side), .k_per_context_o(k_per[version]),
        .group_index_o(group_index[version]), .group_end_o(group_end[version]),
        .stream_valid_o(valid[version]), .weight_quant_o(weight_quant[version]),
        .activation_quant_o(activation_quant[version]), .group_scale_o(scale[version]),
        .group_min_o(minimum[version]), .group_aux_o(aux[version]),
        .weight_d_o(d[version]), .weight_dmin_o(dmin[version]), .activation_d_o(ad[version]));
    end else begin : gen_reference
      qbs_profile_decoder_reference #(.CompactRead(1)) i_decoder (
        .profile_i(profile), .activation_profile_i(activation_profile), .m_i(m),
        .row_count_i(rows), .k_base_i(k), .weight_block_i(unused_weight),
        .activation_block_i(unused_activation), .weight_window_i(weight_window),
        .activation_window_i(activation_window), .weight_side_i(weight_side),
        .activation_side_i(activation_side), .k_per_context_o(k_per[version]),
        .group_index_o(group_index[version]), .group_end_o(group_end[version]),
        .stream_valid_o(valid[version]), .weight_quant_o(weight_quant[version]),
        .activation_quant_o(activation_quant[version]), .group_scale_o(scale[version]),
        .group_min_o(minimum[version]), .group_aux_o(aux[version]),
        .weight_d_o(d[version]), .weight_dmin_o(dmin[version]), .activation_d_o(ad[version]));
    end
  end

  task automatic compare();
    assert ({k_per[0], group_index[0], group_end[0], valid[0]} ===
            {k_per[1], group_index[1], group_end[1], valid[1]})
      else $fatal(1, "decoder control mismatch profile=%0d m=%0d k=%0d", profile, m, k);
    for (int row = 0; row < 4; row++) begin
      assert ({d[0][row], dmin[0][row], ad[0][row]} ===
              {d[1][row], dmin[1][row], ad[1][row]})
        else $fatal(1, "decoder scale mismatch profile=%0d row=%0d", profile, row);
      for (int lane = 0; lane < 8; lane++)
        assert ({weight_quant[0][row][lane], activation_quant[0][row][lane]} ===
                {weight_quant[1][row][lane], activation_quant[1][row][lane]})
          else $fatal(1, "decoder quant mismatch profile=%0d m=%0d k=%0d row=%0d lane=%0d w=%0d/%0d a=%0d/%0d",
                      profile, m, k, row, lane, weight_quant[0][row][lane],
                      weight_quant[1][row][lane], activation_quant[0][row][lane],
                      activation_quant[1][row][lane]);
    end
    for (int stream = 0; stream < 16; stream++)
      assert ({scale[0][stream], minimum[0][stream], aux[0][stream]} ===
              {scale[1][stream], minimum[1][stream], aux[1][stream]})
        else $fatal(1, "decoder group metadata mismatch profile=%0d k=%0d stream=%0d", profile, k, stream);
    cases++;
  endtask

  initial begin
    for (int pattern = 0; pattern < 8; pattern++) begin
      for (int row = 0; row < 4; row++) begin
        for (int word = 0; word < 8; word++) begin
          activation_window[row][word*32 +: 32] = pattern == 0 ? 0 : pattern == 1 ? '1 : $urandom;
          for (int plane = 0; plane < 2; plane++)
            weight_window[row][plane][word*32 +: 32] = pattern == 0 ? 0 : pattern == 1 ? '1 : $urandom;
        end
        for (int b = 0; b < 20; b++) weight_side[row][b] = pattern == 0 ? 0 : pattern == 1 ? '1 : 8'($urandom);
        for (int b = 0; b < 36; b++) activation_side[row][b] = pattern == 0 ? 0 : pattern == 1 ? '1 : 8'($urandom);
      end
      for (int f = 1; f <= 9; f++) begin
        profile = qbs_weight_profile_e'(f);
        activation_profile = qbs_default_activation_profile(profile);
        for (int count = 1; count <= 4; count++) begin
          m = 3'(count);
          for (int r = 1; r <= 4; r++) begin
            rows = 3'(r);
            // The issue cursor starts at zero and advances by k_per_context;
            // these issues never span two 16-byte SRAM words.
            for (int element = 0; element < qbs_weight_block_elements(profile);
                 element += (count == 1 ? 8 : count == 2 ? 4 : 2)) begin
              k = 8'(element);
              #1;
              compare();
            end
          end
        end
      end
    end
    $display("QBS decoder equivalence PASS cases=%0d", cases);
    $finish;
  end
endmodule
