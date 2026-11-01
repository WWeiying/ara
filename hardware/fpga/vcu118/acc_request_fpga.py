"""Version-pinned FPGA request timing overlay; mainline remains unchanged."""
import hashlib

UPSTREAM = "6aa6fa74eaca4fd9981c4e9849bb4594df016ba4262d47295696aead82eeb117"
OVERLAY = "009785c3998bf3d85199183fcf9dabf72c64233582d03cf7fc9eb987a5e98ce6"
OLD = """  // Keep both non-flushable slots, but avoid a bubble when the channel is empty.
  // Authorization remains at acc_req_valid, before this ownership boundary.
  fall_through_register_v1 #(
      .T(accelerator_req_t),
      .DEPTH(2)
  ) i_accelerator_req_register (
      .clk_i  (clk_i),
      .rst_ni (rst_ni),
      .clr_i  (1'b0),
      .testmode_i(1'b0),
"""
NEW = """  // FPGA timing boundary: retain two non-flushable slots and one request/cycle,
  // but register forward data/valid to break the CSR-to-Ara-to-scoreboard path.
  // Authorization remains at acc_req_valid; accepted requests survive flushes.
  spill_register #(
      .T(accelerator_req_t),
      .Bypass(1'b0)
  ) i_accelerator_req_register (
      .clk_i  (clk_i),
      .rst_ni (rst_ni),
"""


def patch_acc_request(text):
    digest = hashlib.sha256(text.encode()).hexdigest()
    if digest == OVERLAY:
        return text
    if digest != UPSTREAM or text.count(OLD) != 1:
        raise RuntimeError("Unreviewed CVA6 accelerator request source")
    result = text.replace(OLD, NEW, 1)
    if hashlib.sha256(result.encode()).hexdigest() != OVERLAY:
        raise RuntimeError("FPGA request overlay differs from tested RTL")
    return result
