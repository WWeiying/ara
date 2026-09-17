"""Reviewed, FPGA-only request isolation and speculative EEW geometry.

These paired edits preserve the transferred request and all state transitions.
Pin the reviewed input versions: a changed decoder needs a fresh path review.
"""
import hashlib
import re

from dispatcher_fpga import UPSTREAM_DISPATCHER_SHA256


UPSTREAM_SEGMENT_SHA256 = "5b443bf1aa3bb2e64d21e6661c2aee4b0edaaeeb6c3a5d92eb99a6923cc33552"


ARCH_GATE = """state_q == NORMAL_OPERATION || state_q == OVERLAP_ISSUE_ORIGINAL ||
        (state_q == WAIT_IDLE && !ara_req_valid_o && ara_idle_i) ||
        (state_q == WAIT_IDLE_FLUSH && lsu_ex_state_q == LSU_FLUSH_DONE)"""

BACKEND = """  ara_req_t ara_req, ara_req_d, ara_req_idle, ara_req_committed;
  // Keep repair-uop arithmetic out of the architectural layout checks.
  ara_req_t fpga_maintenance_req, fpga_backend_req, fpga_eew_req;
  logic fpga_arch_decode, fpga_maintenance_valid, fpga_backend_valid;
  logic decode_blocked;
  logic     ara_req_valid, ara_req_valid_d;
  assign fpga_backend_req = fpga_arch_decode ? ara_req : fpga_maintenance_req;
  assign fpga_backend_valid = fpga_arch_decode ? ara_req_valid : fpga_maintenance_valid;
  assign ara_req_committed = decode_blocked ? ara_req_idle : fpga_backend_req;"""

GEOMETRY = """    // Speculate only EEW geometry. The dispatcher still qualifies every write
    // with the real output handshake. In IDLE this removes valid/ready from
    // the first-element interval calculation; request outputs are unchanged.
    always_comb begin
      fpga_eew_req_o = fpga_eew_req_i;
      case (state_q)
        IDLE: begin
          if (is_segment_mem_op_i && !illegal_insn_i)
            fpga_eew_req_o.vl = fpga_eew_req_i.vstart + 1'b1;
        end
        SEGMENT_MICRO_OPS: begin
          fpga_eew_req_o.vl = next_vstart_cnt;
          fpga_eew_req_o.vstart = vstart_cnt_q;
          fpga_eew_req_o.vd = fpga_eew_req_i.vd + fpga_eew_reg_offset;
        end
        default:;
      endcase
    end

"""


def replace(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("Unexpected FPGA control patch context: " + old[:90])
    return text.replace(old, new, 1)


def dispatcher_edits(text, reverse=False):
    pairs = [
        ("  ara_req_t ara_req, ara_req_d, ara_req_idle, ara_req_committed;\n"
         "  logic decode_blocked;\n"
         "  assign ara_req_committed = decode_blocked ? ara_req_idle : ara_req;\n"
         "  logic     ara_req_valid, ara_req_valid_d;", BACKEND),
        ("  always_comb begin: p_decoder\n",
         "  assign fpga_arch_decode = " + ARCH_GATE + ";\n\n"
         "  always_comb begin: p_decoder\n"),
        ("    if (" + ARCH_GATE + ") begin", "    if (fpga_arch_decode) begin"),
        ("    ara_req_idle = ara_req;\n", "    ara_req_idle = ara_req;\n"
         "    fpga_maintenance_req = ara_req;\n"),
        ("\n    ara_req_valid = 1'b0;\n", "\n    ara_req_valid = 1'b0;\n"
         "    fpga_maintenance_valid = 1'b0;\n"),
        ("    .ara_req_valid_i(ara_req_valid),",
         "    .fpga_eew_req_i(fpga_backend_req),\n"
         "    .fpga_eew_req_o(fpga_eew_req),\n"
         "    .ara_req_valid_i(fpga_backend_valid),"),
        ("    ara_req_idle.token = ara_req.token;",
         "    fpga_maintenance_req.token = ara_req.token;\n"
         "    ara_req_idle.token = ara_req.token;"),
    ]
    # Rewrite only the geometry of the final EEW update, never its write guard.
    start = text.index("      automatic vlmul_e destination_lmul = single_register_result(",
                       text.index("    // Update only registers intersecting"))
    end = text.index("\n    // Any valid non-config instruction", start)
    region = text[start:end]
    a, b = ("fpga_eew_req", "ara_req_d") if reverse else ("ara_req_d", "fpga_eew_req")
    text = text[:start] + re.sub(r"\b" + a + r"\b", b, region) + text[end:]
    start = text.index("    // Special states\n")
    end = text.index("    // Only these states can enter", start)
    region = text[start:end]
    names = {"ara_req": "fpga_maintenance_req", "ara_req_valid": "fpga_maintenance_valid"}
    if reverse:
        names = {v: k for k, v in names.items()}
    region = re.sub(r"\b(" + "|".join(names) + r")\b", lambda m: names[m[0]], region)
    text = text[:start] + region + text[end:]
    # Keep the opt-in maintenance traces attached to the actual selected uop.
    start = text.index("  longint unsigned debug_reshuffle_idle_cycle_q;")
    end = text.index("  // We need to know if the source operands", start)
    names = {"ara_req": "fpga_backend_req", "ara_req_valid": "fpga_backend_valid"}
    if reverse:
        names = {v: k for k, v in names.items()}
    region = re.sub(r"\b(" + "|".join(names) + r")\b", lambda m: names[m[0]], text[start:end])
    text = text[:start] + region + text[end:]
    for old, new in reversed(pairs) if reverse else pairs:
        text = replace(text, new, old) if reverse else replace(text, old, new)
    return text


def segment_edits(text, reverse=False):
    pairs = [
        ("    output ara_req_t  ara_req_o,", "    output ara_req_t  ara_req_o,\n"
         "    // FPGA-only sideband, meaningful only on an EEW-writing transfer.\n"
         "    input  ara_req_t  fpga_eew_req_i,\n"
         "    output ara_req_t  fpga_eew_req_o,"),
        ("    logic [4:0] segment_reg_offset;", "    logic [4:0] segment_reg_offset;\n"
         "    logic [4:0] fpga_eew_reg_offset;"),
        ("    counter #(\n      .WIDTH($bits(ara_req_i.nf)),",
         "    always_comb begin\n"
         "      case (fpga_eew_req_i.emul)\n"
         "        LMUL_2: fpga_eew_reg_offset = 5'(segment_cnt_q << 1);\n"
         "        LMUL_4: fpga_eew_reg_offset = 5'(segment_cnt_q << 2);\n"
         "        LMUL_8: fpga_eew_reg_offset = 5'(segment_cnt_q << 3);\n"
         "        default: fpga_eew_reg_offset = 5'(segment_cnt_q);\n"
         "      endcase\n"
         "    end\n\n"
         "    counter #(\n      .WIDTH($bits(ara_req_i.nf)),"),
        ("    always_comb begin\n      state_d = state_q;",
         GEOMETRY + "    always_comb begin\n      state_d = state_q;"),
        ("    assign ara_req_o        = ara_req_i;",
         "    assign ara_req_o        = ara_req_i;\n"
         "    assign fpga_eew_req_o   = fpga_eew_req_i;"),
    ]
    for old, new in reversed(pairs) if reverse else pairs:
        text = replace(text, new, old) if reverse else replace(text, old, new)
    return text


def patch(text, transform, digest, marker):
    if marker in text:
        original = transform(text, reverse=True)
        if hashlib.sha256(original.encode()).hexdigest() == digest and transform(original) == text:
            return text
    elif hashlib.sha256(text.encode()).hexdigest() == digest:
        return transform(text)
    raise RuntimeError("Unreviewed FPGA control source: " + marker)


def patch_dispatcher_control(text):
    if hashlib.sha256(text.encode()).hexdigest() == UPSTREAM_DISPATCHER_SHA256:
        return text
    return patch(text, dispatcher_edits,
                 "c3aee27113948b3005a50f7e7db853c510154c7cc3b563e1af442126293dc250",
                 "  assign fpga_arch_decode = ")


def patch_segment_geometry(text):
    if hashlib.sha256(text.encode()).hexdigest() == UPSTREAM_SEGMENT_SHA256:
        return text
    return patch(text, segment_edits,
                 "fe8d7256650bd56c710138071f6f8541f33fc0a9aa7ed567e6c0d8f9a12e4cf7",
                 "    input  ara_req_t  fpga_eew_req_i,")
