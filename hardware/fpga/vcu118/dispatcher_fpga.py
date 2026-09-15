"""FPGA-only, cycle-preserving dispatcher interval arithmetic."""
import hashlib
import re


HELPERS = """  // FPGA-only: keep the 64-bit modulo-add semantics, but only carry through
  // the VL-sized low word. Upper bits only decide whether saturation applies.
  function automatic vlen_t fpga_slide_bound(
    vlen_t index, elen_t stride, logic decrement, int unsigned capacity
  );
    localparam int W = $bits(vlen_t);
    automatic logic [W:0] sum = {1'b0, index} + {1'b0, stride[W-1:0]};
    automatic logic high_zero = sum[W] ? (&stride[63:W]) : (~|stride[63:W]);
    automatic logic high_one = sum[W] ? (~|stride[63:W]) : (stride[63:W] == 1);
    automatic vlen_t low = sum[W-1:0];
    if (decrement && (!high_zero || low != 0)) begin
      if (low == 0) high_zero = high_one;
      low = low - 1'b1;
    end
    return (!high_zero || unsigned'(low) > capacity) ? vlen_t'(capacity) : low;
  endfunction : fpga_slide_bound

  // Bit r means that relative register r intersects the active interval.
  // Constant register boundaries avoid subtract/shift/count/add chains and
  // variable first-register indexing on the late EEW write-enable path.
  function automatic logic [7:0] fpga_active_registers(
    vlmul_e lmul, vew_e eew, vlen_t vstart, vlen_t vl
  );
    fpga_active_registers = '0;
    for (int unsigned r = 0; r < 8; r++) begin
      if (unsigned'(eew) <= $clog2(VLENB))
        fpga_active_registers[r] = r < lmul_register_count(lmul) && vl > vstart &&
            unsigned'(vstart) < (((r + 1) * VLENB) >> unsigned'(eew)) &&
            unsigned'(vl) > ((r * VLENB) >> unsigned'(eew));
      else
        // The original int first/last indices coerce an unsupported EW's X
        // result to zero. Preserve that fallback, including EEW bookkeeping.
        fpga_active_registers[r] = r == 0 && vl > vstart;
    end
  endfunction : fpga_active_registers

"""

FUNCTIONS = {
    "slidedown_source_start": (
        "cd7454a7c93c87489038a5af53f0e9d15a30a1a0ce5accd8fd71da4987fdb386",
        """  function automatic vlen_t slidedown_source_start(
    vlen_t vstart, elen_t stride, vlmul_e lmul, vew_e eew
  );
    return fpga_slide_bound(vstart, stride, 1'b0, lmul_element_capacity(lmul, eew));
  endfunction : slidedown_source_start"""),
    "slidedown_source_end": (
        "46672d7983c99bc681427278f80e982d8449926d90df690fd4e4ef8ee1d8b6cf",
        """  function automatic vlen_t slidedown_source_end(
    vlen_t vl, elen_t stride, logic use_scalar_op, vlmul_e lmul, vew_e eew
  );
    return fpga_slide_bound(vl, stride, use_scalar_op, lmul_element_capacity(lmul, eew));
  endfunction : slidedown_source_end"""),
    "active_register_count": (
        "7576aaf5bf9d422cae672c1a94a9a25f4b89f3452c3ab32f4e33105ff038385b",
        """  function automatic int unsigned active_register_count(
    vlmul_e lmul, vew_e target_eew, vlen_t vstart, vlen_t vl
  );
    automatic logic [7:0] mask = fpga_active_registers(lmul, target_eew, vstart, vl);
    automatic logic [1:0] n01 = {1'b0, mask[0]} + {1'b0, mask[1]};
    automatic logic [1:0] n23 = {1'b0, mask[2]} + {1'b0, mask[3]};
    automatic logic [1:0] n45 = {1'b0, mask[4]} + {1'b0, mask[5]};
    automatic logic [1:0] n67 = {1'b0, mask[6]} + {1'b0, mask[7]};
    automatic logic [2:0] lo = {1'b0, n01} + {1'b0, n23};
    automatic logic [2:0] hi = {1'b0, n45} + {1'b0, n67};
    return {1'b0, lo} + {1'b0, hi};
  endfunction : active_register_count"""),
    "active_group_needs_reshuffle": (
        "e1646563946d79c9fbed879809e6f298660bb4a3f96c53aa713103419566a15b",
        """  function automatic logic active_group_needs_reshuffle(
    logic [4:0] base, vlmul_e lmul, vew_e target_eew,
    vlen_t vstart, vlen_t vl
  );
    automatic logic [7:0] mask = fpga_active_registers(lmul, target_eew, vstart, vl);
    active_group_needs_reshuffle = 1'b0;
    for (int unsigned r = 0; r < 8; r++) begin
      if (mask[r] && (unsigned'(base) + r) < 32)
        active_group_needs_reshuffle |= eew_valid_q[base + r] &&
            (eew_q[base + r] != target_eew);
    end
  endfunction : active_group_needs_reshuffle"""),
    "active_group_has_mixed_eew": (
        "b2099d606163f3bb37da2436712fee324f089d2f5bc239681cb9475390f41739",
        """  function automatic logic active_group_has_mixed_eew(
    logic [4:0] base, vlmul_e lmul, vew_e element_eew,
    vlen_t vstart, vlen_t vl
  );
    automatic logic [7:0] mask = fpga_active_registers(lmul, element_eew, vstart, vl);
    automatic logic found_reference = 1'b0;
    automatic vew_e reference_eew = EW8;
    active_group_has_mixed_eew = 1'b0;
    for (int unsigned r = 0; r < 8; r++) begin
      if (mask[r] && (unsigned'(base) + r) < 32 && eew_valid_q[base + r]) begin
        if (!found_reference) begin
          found_reference = 1'b1;
          reference_eew = eew_q[base + r];
        end else begin
          active_group_has_mixed_eew |= eew_q[base + r] != reference_eew;
        end
      end
    end
  endfunction : active_group_has_mixed_eew"""),
}

OLD_UPDATE = """      automatic int unsigned first_register = active_first_register(
          ara_req_d.vtype.vsew, ara_req_d.vstart);
      automatic int unsigned register_count = active_register_count(
          destination_lmul, ara_req_d.vtype.vsew, ara_req_d.vstart, ara_req_d.vl);
      for (int unsigned i = 0; i < 8; i++) begin
        if (i < register_count &&
            (unsigned'(ara_req_d.vd) + first_register + i) < 32) begin
          eew_d[ara_req_d.vd + first_register + i]       = ara_req_d.vtype.vsew;
          eew_valid_d[ara_req_d.vd + first_register + i] = 1'b1;
        end
      end"""

NEW_UPDATE = """      automatic logic [7:0] active_registers = fpga_active_registers(
          destination_lmul, ara_req_d.vtype.vsew, ara_req_d.vstart, ara_req_d.vl);
      for (int unsigned i = 0; i < 8; i++) begin
        if (active_registers[i] && (unsigned'(ara_req_d.vd) + i) < 32) begin
          eew_d[ara_req_d.vd + i]       = ara_req_d.vtype.vsew;
          eew_valid_d[ara_req_d.vd + i] = 1'b1;
        end
      end"""


def patch_dispatcher_layout(text):
    """Fail closed on a changed upstream function; never patch main RTL in place."""
    patched = "function automatic vlen_t fpga_slide_bound(" in text
    for name, (digest, replacement) in FUNCTIONS.items():
        matches = list(re.finditer(r"  function automatic [^\n]*\b" + name +
                                  r"\(.*?  endfunction : " + name, text, re.S))
        if len(matches) != 1:
            raise RuntimeError(f"Unexpected dispatcher function: {name}")
        original = matches[0].group()
        if patched:
            if original != replacement:
                raise RuntimeError(f"Modified FPGA dispatcher function: {name}")
        elif hashlib.sha256(original.encode()).hexdigest() != digest:
            raise RuntimeError(f"Upstream dispatcher function changed: {name}")
        else:
            text = text.replace(original, replacement, 1)
    if patched:
        if text.count(HELPERS) != 1 or text.count(NEW_UPDATE) != 1 or OLD_UPDATE in text:
            raise RuntimeError("Modified FPGA dispatcher helpers or EEW update")
        return text
    if text.count(OLD_UPDATE) != 1:
        raise RuntimeError("Upstream dispatcher EEW update changed")
    text = text.replace(OLD_UPDATE, NEW_UPDATE, 1)
    anchor = "  function automatic vlen_t slidedown_source_start("
    return text.replace(anchor, HELPERS + anchor, 1)
