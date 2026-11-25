// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps

// Compile the immutable DC adapter with only its module name changed to
// qbs_block_adapter_reference, plus qbs_sram_adapter_tb.sv. Run this top with
// +define+QBS_UNIQUE_INPUT_BYTES (also repeat with +define+SYNTHESIS).
module qbs_activation_credit_equivalence #(parameter bit NativeView = 1'b1);
  import qbs_pkg::*;
  qbs_sram_adapter_tb stimulus();
  defparam stimulus.gen_adapter[0].i_dut.NativeView = NativeView;
  defparam stimulus.gen_adapter[1].i_dut.NativeView = NativeView;
  int cycles = 0;
  int dual_slot_cycles [2];
  int residual_cycles [2];
  int clear_credit_cycles [2];

  for (genvar bank = 0; bank < 2; bank++) begin : gen_reference
    wire clk_i = stimulus.clk_i;
    wire rst_ni = stimulus.rst_ni;
    logic wready, aready, all_weight, all_activation;
    logic [3:0] wcomplete, acomplete;
    logic [31:0] wbytes, abytes;
    logic [7:0] wblock [4][QbsMaxWeightBlockBytes];
    logic [7:0] ablock [4][QbsMaxActivationBlockBytes];
    logic [127:0] wwindow [4][2];
    logic [255:0] awindow [4];
    logic [7:0] wside [4][20], aside [4][36];
    int expected [4];

    qbs_block_adapter_reference #(
      .ActivationContextBase(bank * 4), .NativeView(NativeView), .UniqueInputBytes(1'b1)
    ) reference_dut (
      .clk_i, .rst_ni,
      .clear_weight_i(stimulus.clear_weight_i),
      .clear_activation_i(stimulus.clear_activation_i),
      .weight_profile_i(stimulus.weight_profile_i),
      .activation_profile_i(stimulus.activation_profile_i),
      .weight_row_count_i(stimulus.weight_row_count_i),
      .activation_layout_i(stimulus.activation_layout_i), .m_i(stimulus.m_i),
      .weight_write_valid_i(stimulus.weight_write_valid_i && (&stimulus.wready)),
      .weight_write_ready_o(wready),
      .weight_write_group_i(stimulus.weight_write_group_i),
      .weight_write_row_i(stimulus.weight_write_row_i),
      .weight_write_offset_i(stimulus.weight_write_offset_i),
      .weight_write_data_i(stimulus.weight_write_data_i),
      .weight_write_strb_i(stimulus.weight_write_strb_i),
      .activation_write_valid_i(stimulus.activation_write_valid_i && (&stimulus.aready)),
      .activation_write_ready_o(aready),
      .activation_write_context_i(stimulus.activation_write_context_i),
      .activation_write_offset_i(stimulus.activation_write_offset_i),
      .activation_write_data_i(stimulus.activation_write_data_i),
      .activation_write_strb_i(stimulus.activation_write_strb_i),
      .weight_read_i(stimulus.weight_read_i),
      .activation_read_i(stimulus.activation_read_i && (bank == 0 || stimulus.m_i > 4)),
      .read_k_i(stimulus.read_k_i),
      .weight_block_o(wblock), .activation_block_o(ablock),
      .weight_window_o(wwindow), .activation_window_o(awindow),
      .weight_side_o(wside), .activation_side_o(aside),
      .weight_complete_o(wcomplete), .activation_complete_o(acomplete),
      .all_weight_complete_o(all_weight), .all_activation_complete_o(all_activation),
      .accepted_weight_bytes_o(wbytes), .accepted_activation_bytes_o(abytes)
    );

`define DUT stimulus.gen_adapter[bank].i_dut
    always @(posedge clk_i) begin
      for (int row = 0; row < 4; row++) begin
        if (!rst_ni || stimulus.clear_activation_i) expected[row] = 0;
        else for (int b = 0; b < 32; b++)
          if (`DUT.activation_consumed[b] && `DUT.activation_contexts[b] == 2'(row))
            expected[row]++;
      end
      if (rst_ni) begin
        if ((|`DUT.activation_consumed[15:0]) && (|`DUT.activation_consumed[31:16]))
          dual_slot_cycles[bank]++;
        if (`DUT.activation_pending_multiword) residual_cycles[bank]++;
        if (stimulus.clear_activation_i && (|`DUT.activation_committed_q[0]))
          clear_credit_cycles[bank]++;
      end
      #2;
      if (rst_ni) for (int row = 0; row < 4; row++)
        assert (`DUT.activation_committed_q[row] === expected[row][
                    $clog2(QbsMaxActivationBlockBytes+1)-1:0])
          else $fatal(1, "commit oracle mismatch bank=%0d row=%0d", bank, row);
    end

    always @(negedge clk_i) if (rst_ni) begin
      #0.1;
      assert ({wready, aready, all_weight, all_activation, wcomplete, acomplete,
               wbytes, abytes, reference_dut.activation_write_pending,
               reference_dut.activation_consumed} ===
              {`DUT.weight_write_ready_o, `DUT.activation_write_ready_o,
               `DUT.all_weight_complete_o, `DUT.all_activation_complete_o,
               `DUT.weight_complete_o, `DUT.activation_complete_o,
               `DUT.accepted_weight_bytes_o, `DUT.accepted_activation_bytes_o,
               `DUT.activation_write_pending, `DUT.activation_consumed})
        else $fatal(1, "cycle-visible contract mismatch bank=%0d", bank);
      for (int row = 0; row < 4; row++) begin
        assert (`DUT.activation_committed_q[row] === reference_dut.activation_committed_q[row])
          else $fatal(1, "reference commit mismatch bank=%0d row=%0d", bank, row);
        if (stimulus.activation_read_i && (bank == 0 || stimulus.m_i > 4)) begin
          assert (`DUT.activation_window_o[row] === awindow[row])
            else $fatal(1, "activation read mismatch bank=%0d row=%0d", bank, row);
          for (int b = 0; b < 36; b++)
            assert (`DUT.activation_side_o[row][b] === aside[row][b])
              else $fatal(1, "activation side mismatch bank=%0d row=%0d", bank, row);
        end
      end
    end
`undef DUT
  end

  always @(posedge stimulus.clk_i) cycles++;
  initial begin
    #100000000;
    $fatal(1, "activation credit equivalence watchdog");
  end
  final begin
    assert (dual_slot_cycles[0] > 0 && residual_cycles[0] > 0 && clear_credit_cycles[0] > 0)
      else $error("missing dual-slot/residual/clear coverage");
    $display("QBS activation credit equivalence completed cycles=%0d dual=%0d residual=%0d clears=%0d",
             cycles, dual_slot_cycles[0], residual_cycles[0], clear_credit_cycles[0]);
  end
endmodule
