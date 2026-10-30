module qbacc_abi_tb;
  import qbs_pkg::*;
  int unsigned vlens[9] = '{0, 32, 128, 512, 1023, 1024, 1025, 2048, 4096};
  logic [63:0] got, expected;
  logic [31:0] instruction, legacy_instruction;
  int unsigned encodings;
  bit expected_enable;
  initial begin
    expected_enable = 0;
`ifdef ARA_QBS_ENABLE
`ifdef ARA_QBS_VRF_CONTINUATION
    expected_enable = 1;
`endif
`endif
    if (QbsVrfContinuationEnable !== expected_enable ||
        QbsMMinusOneBits !== 3 || QbsQbaccFunct7Bit !== 3 ||
        QbsVrfContinuationCapabilityIndex !== 4 ||
        QbsVrfContinuationCapabilityBit !== 0 ||
        QbsVrfContinuationVlenBits !== 1024)
      $fatal(1, "ABI constants");
    foreach (vlens[v]) begin
      for (int unsigned i = 0; i < 256; i++) begin
        got = qbs_capability_word(64'(i), vlens[v]);
        expected = qbacc_legacy_pkg::qbs_capability_word(64'(i), vlens[v]);
        if (i == 4) expected = expected_enable && vlens[v] == 1024 ? 64'd1 : 64'd0;
        if (got !== expected)
          $fatal(1, "capability index=%0d vlen=%0d got=%h expected=%h",
                 i, vlens[v], got, expected);
      end
      if (qbs_capability_word(64'hffff_ffff_ffff_ffff, vlens[v]) !== 64'd0)
        $fatal(1, "unknown index");
    end
    encodings = 0;
    for (int unsigned m = 1; m <= 8; m++)
      for (int unsigned vd = 0; vd < 32; vd++)
        for (int unsigned rs1 = 0; rs1 < 32; rs1++)
          for (int unsigned rs2 = 0; rs2 < 32; rs2++) begin
            // No RTL encoder exists: exercise the public field constants.
            legacy_instruction = {7'(m-1), 5'(rs2), 5'(rs1),
                                  QbsQbexecFunct3, 5'(vd), QbsOpcodeCustom2};
            instruction = legacy_instruction | (32'd1 << (25 + QbsQbaccFunct7Bit));
            if (legacy_instruction !==
                (32'h5b | (vd << 7) | (rs1 << 15) | (rs2 << 20) | ((m-1) << 25)))
              $fatal(1, "legacy encoding");
            if (instruction !== (legacy_instruction | 32'h10000000) ||
                instruction[27:25] !== 3'(m-1) || instruction[31:29] !== 3'b0)
              $fatal(1, "QBACC encoding");
            encodings++;
          end
    if (encodings !== 262144) $fatal(1, "encoding count");
    $display("QBACC_ABI_SV_PASS encodings=262144 capabilities=2304");
    $finish;
  end
endmodule
