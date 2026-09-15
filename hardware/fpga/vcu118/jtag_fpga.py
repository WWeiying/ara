"""Reviewed FPGA-only J53 sampled TAP and reset integration.

The upstream TAP state/shift logic is retained. Only its clocking and DMI
transport change. J53 is a data input: <=1 MHz, >=400 ns high and low, with
TMS/TDI changed on falling TCK. The SoC clock must remain >=50 MHz.
"""
import hashlib


def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise RuntimeError("FPGA JTAG/reset integration source changed: " + old[:70])
    return text.replace(old, new)


def patch_jtag(text):
    if hashlib.sha256(text.encode()).hexdigest() != \
            "a3dbcd4190586d11821b798853a17da4a5276a4d9c56b8007340b7919dc58d0b":
        raise RuntimeError("FPGA JTAG integration requires the reviewed dmi_jtag source")
    text = replace(text, "  logic tck;", """  // FPGA J53 is an asynchronous data input, never a fabric clock.
  // Three independent single-bit synchronizers; TMS/TDI are stable across
  // the sampled rising edge (>=400 ns TCK phases at >=50 MHz clk_i).
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) logic [2:0] fpga_tck_sync_q;
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) logic [2:0] fpga_tms_sync_q;
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) logic [2:0] fpga_tdi_sync_q;
  (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) logic [2:0] fpga_reset_q;
  wire fpga_arst_n = rst_ni & trst_ni;
  wire fpga_rst_n = fpga_reset_q[2];
  logic fpga_tck_q;
  wire fpga_rise = fpga_tck_sync_q[2] & ~fpga_tck_q;
  wire fpga_fall = ~fpga_tck_sync_q[2] & fpga_tck_q;
  always_ff @(posedge clk_i or negedge fpga_arst_n) begin
    if (!fpga_arst_n) fpga_reset_q <= '0;
    else fpga_reset_q <= {fpga_reset_q[1:0], 1'b1};
  end
  always_ff @(posedge clk_i or negedge fpga_rst_n) begin
    if (!fpga_rst_n) begin
      fpga_tck_sync_q <= '0;
      fpga_tms_sync_q <= '1;
      fpga_tdi_sync_q <= '0;
      fpga_tck_q <= 1'b0;
    end else begin
      fpga_tck_sync_q <= {fpga_tck_sync_q[1:0], tck_i};
      fpga_tms_sync_q <= {fpga_tms_sync_q[1:0], tms_i};
      fpga_tdi_sync_q <= {fpga_tdi_sync_q[1:0], td_i};
      fpga_tck_q <= fpga_tck_sync_q[2];
    end
  end""")
    text = replace(text, "always_ff @(posedge tck or negedge trst_ni)",
                   "always_ff @(posedge clk_i or negedge fpga_rst_n)", 2)
    text = replace(text, "if (!trst_ni) begin", "if (!fpga_rst_n) begin", 2)
    text = replace(text, """    .tck_i,
    .tms_i,
    .trst_ni,
    .td_i,""", """    .clk_i,
    .fpga_rise_i    ( fpga_rise        ),
    .fpga_fall_i    ( fpga_fall        ),
    .tms_i         ( fpga_tms_sync_q[2] ),
    .trst_ni       ( fpga_rst_n       ),
    .td_i          ( fpga_tdi_sync_q[2] ),""")
    text = replace(text, "    .tck_o          ( tck              ),", "    .tck_o          (                  ),")
    start = text.index("  // ---------\n  // CDC\n")
    end = text.index("\nendmodule : dmi_jtag", start)
    return text[:start] + """  // TAP and DM now share clk_i. Keep DMI valid/ready active even when
  // external TCK stops. The existing DTM FSM holds request/response state.
  assign dmi_req_o = dmi_req;
  assign dmi_req_valid_o = dmi_req_valid & ~dmi_clear & dmi_rst_no;
  assign dmi_req_ready = dmi_req_ready_i & ~dmi_clear & dmi_rst_no;
  assign dmi_resp = dmi_resp_i;
  assign dmi_resp_valid = dmi_resp_valid_i & ~dmi_clear & dmi_rst_no;
  assign dmi_resp_ready_o = dmi_resp_ready & ~dmi_clear & dmi_rst_no;
  // Registered synchronous flush of the DM response FIFO. Isolate both
  // handshakes on the clear event and throughout the following flush cycle.
  always_ff @(posedge clk_i or negedge fpga_rst_n) begin
    if (!fpga_rst_n) dmi_rst_no <= 1'b0;
    else dmi_rst_no <= ~dmi_clear;
  end
""" + text[end:]


def patch_tap(text):
    if hashlib.sha256(text.encode()).hexdigest() != \
            "7fe8d372125983237b6dd6c76137f10958b2e1222471f82105fe5f8fea935a8a":
        raise RuntimeError("FPGA JTAG integration requires the reviewed TAP source")
    text = replace(text, "  input  logic        tck_i,    // JTAG test clock pad", """  input  logic        clk_i,    // FPGA SoC clock, not the J53 pad
  input  logic        fpga_rise_i,
  input  logic        fpga_fall_i,""")
    text = text.replace("posedge tck_i", "posedge clk_i")
    for field in ("jtag_ir_shift_q <= jtag_ir_shift_d;", "tap_state_q <= tap_state_d;"):
        text = replace(text, "end else begin\n      " + field,
                       "end else if (fpga_rise_i) begin\n      " + field)
    start = text.index("  // ----------------\n  // DFT\n")
    end = text.index("  // ----------------\n  // TAP FSM", start)
    text = text[:start] + """  // Update TDO only on the sampled falling edge. No inverted fabric
  // clock or ASIC DFT BUFGMUX; testmode_i is unused in the FPGA build.
  always_ff @(posedge clk_i or negedge trst_ni) begin : p_tdo_regs
    if (!trst_ni) begin
      td_o <= 1'b0;
      tdo_oe_o <= 1'b0;
    end else if (fpga_fall_i) begin
      td_o <= tdo_mux;
      tdo_oe_o <= (shift_ir | shift_dr);
    end
  end
""" + text[end:]
    text = replace(text, "assign tck_o = tck_i;", "assign tck_o = clk_i;")
    for output, value in (("update_o", "update_dr"), ("shift_o", "shift_dr"),
                          ("capture_o", "capture_dr"), ("dmi_clear_o", "test_logic_reset")):
        text = replace(text, f"assign {output} = {value};",
                       f"assign {output} = fpga_rise_i & {value};")
    return text


def patch_reset_sync(text):
    if hashlib.sha256(text.encode()).hexdigest() != \
            "07979859589da1471289a89c5bbe9bed5c67701bc117c0bc1c9ec673c6e21484":
        raise RuntimeError("FPGA reset integration requires the reviewed rstgen source")
    return replace(text, "    logic [NumRegs-1:0] synch_regs_q;", """    // FPGA reset assertion is asynchronous, release traverses every stage.
    (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *)
    logic [NumRegs-1:0] synch_regs_q;""")


OLD_READY = """  // Common asynchronous assertion, separately synchronized deassertion.
  assign fabric_ready_o = ~sys_rst_i & ~dram_rst_o & calib_complete;"""
NEW_READY = """  // Synchronize system-reset release before using it in the UI domain.
  logic ui_por_n;
  rstgen i_ui_por (
    .clk_i(dram_axi_clk), .rst_ni(~sys_rst_i), .test_mode_i(1'b0),
    .rst_no(ui_por_n), .init_no()
  );
  // A single UI-domain register crosses to the SoC reset/status chains.
  // System reset asserts this low even if the DDR UI clock is stopped.
  always_ff @(posedge dram_axi_clk or negedge ui_por_n) begin
    if (!ui_por_n) fabric_ready_o <= 1'b0;
    else fabric_ready_o <= ~dram_rst_o & calib_complete;
  end"""


def patch_ready(text):
    return replace(text, OLD_READY, NEW_READY)
