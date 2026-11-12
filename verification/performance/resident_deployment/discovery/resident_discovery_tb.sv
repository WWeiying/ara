module resident_discovery_tb;
  import akv_pkg::*;
  `include "discovery_fpu.svh"
  int unsigned NrLanes, VLEN;
  fpu_support_e FPUSupport;
  bit akv_implementation_supported, akv_v2_implementation_supported;
  bit akv_resident_pv_implementation_supported, akv_resident_qk_implementation_supported;
  bit EnableResidentPv, EnableResidentQk, ResidentPvSupported, ResidentQkSupported;
  int unsigned flags;
  logic [63:0] words [5];
  logic [63:0] index;

  initial begin
    flags = 0;
`ifdef ARA_AKV_ENABLE
    flags |= 1;
`endif
`ifdef ARA_AKV_V2_ENABLE
    flags |= 2;
`endif
`ifdef ARA_AKV_RESIDENT_PV_ENABLE
    flags |= 4;
`endif
`ifdef ARA_AKV_RESIDENT_QK_ENABLE
    flags |= 8;
`endif
    for (int l = 0; l < 5; l++) begin
      NrLanes = 1 << l;
      for (int v = 0; v < 3; v++) begin
        VLEN = 512 << v;
        for (int f = 0; f < 8; f++) begin
          // All eight named FPU configurations, using the real enum/functions.
          case (f)
            0: FPUSupport = FPUSupportNone;
            1: FPUSupport = FPUSupportHalf;
            2: FPUSupport = FPUSupportSingle;
            3: FPUSupport = FPUSupportHalfSingle;
            4: FPUSupport = FPUSupportDouble;
            5: FPUSupport = FPUSupportSingleDouble;
            6: FPUSupport = FPUSupportHalfSingleDouble;
            7: FPUSupport = FPUSupportAll;
          endcase
          `include "discovery_dispatcher_gates.svh"
          if ((akv_resident_pv_implementation_supported &&
               !(EnableResidentPv && ResidentPvSupported)) ||
              (akv_resident_qk_implementation_supported &&
               !(EnableResidentQk && ResidentQkSupported)))
            $fatal(1, "Dispatcher advertises an absent lane/VLSU implementation");
          for (int i = 0; i < 5; i++) begin
            words[i] = akv_capability_word(64'(i), akv_implementation_supported) |
                akv_v2_capability_word(64'(i), akv_v2_implementation_supported) |
                akv_resident_pv_capability_word(64'(i), akv_resident_pv_implementation_supported) |
                akv_resident_qk_capability_word(64'(i), akv_resident_qk_implementation_supported);
          end
          if (words[0] !== (64'h000e010808400101 |
                            (64'(akv_implementation_supported) << 48)) ||
              words[1] !== 64'h00000000006b1a5b ||
              words[2] !== (64'h000001fe06084002 |
                            (64'(akv_v2_implementation_supported) << 32)) ||
              words[3] !== 64'h0000000001803e5b)
            $fatal(1, "Legacy capability words changed");
          $display("VECTOR %0d %0d %0d %0d %016h %016h %016h %016h %016h",
              NrLanes, VLEN, FPUSupport, flags,
              words[0], words[1], words[2], words[3], words[4]);
        end
      end
    end
    for (int i = 0; i < 8; i++) begin
      index = 64'(i);
      if (i != 4 && (akv_resident_pv_capability_word(index, 1'b1) != 0 ||
                     akv_resident_qk_capability_word(index, 1'b1) != 0))
        $fatal(1, "Resident helper changed another capability index");
      if (akv_resident_pv_capability_word(index, 1'b0) != 0 ||
          akv_resident_qk_capability_word(index, 1'b0) != 0)
        $fatal(1, "Disabled implementation advertised");
    end
    if (akv_resident_pv_capability_word(64'h100000004, 1'b1) != 0 ||
        akv_resident_qk_capability_word(64'hffffffffffffffff, 1'b1) != 0)
      $fatal(1, "High index bits ignored");
    $display("resident_discovery_tb: PASS");
    $finish;
  end
endmodule
