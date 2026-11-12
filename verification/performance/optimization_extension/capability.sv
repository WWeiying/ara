module extension_capability_tb;
  import qbs_pkg::*;
  initial begin
    for (int v = 32; v <= 2048; v += 32) begin
      for (int enable = 0; enable < 2; enable++) begin
        if (qbs_capability_word(QbsCooperativeCapabilityIndex, v, 1'(enable)) !==
            ((QbsEnable && enable && v == 1024) ? 64'd1 : 64'd0))
          $fatal(1, "Cooperative capability overclaim vlen=%0d enable=%0d", v, enable);
        if (qbs_capability_word(QbsCooperativeCapabilityIndex, v) !== 64'd0)
          $fatal(1, "Legacy caller must remain conservative");
        for (int index = 0; index < 256; index++)
          if (index != QbsCooperativeCapabilityIndex &&
              qbs_capability_word(64'(index), v, 1'(enable)) !== qbs_capability_word(64'(index), v))
            $fatal(1, "Existing capability changed index=%0d", index);
      end
    end
    $display("EXT_CAPABILITY_PASS widths=64 policies=2 old_words_unchanged=1");
    $finish;
  end
endmodule
