#!/usr/bin/env python3
"""Generate dispatcher types and a state checker from the actual RTL interfaces."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]


def layout_checks(before, after, output):
    # Reuse the FPGA port's directed vectors, but extract both DUTs from the
    # current ASIC working tree and its pre-edit snapshot.
    sys.path.insert(0, str(ROOT / "hardware/fpga/vcu118/tests"))
    from check_dispatcher_layout import (
        BENCH, FIRST_SEGMENT, NEW_UPDATE, OLD_UPDATE, layout_module, repair_stimulus)
    update = NEW_UPDATE.replace("fpga_active_registers", "active_register_mask")
    if OLD_UPDATE not in before or update.replace("ara_req_d", "layout_req") not in after:
        raise ValueError("layout checker does not match the actual EEW update blocks")
    (output / "layout.sv").write_text(
        layout_module(before, "layout_before", OLD_UPDATE) +
        layout_module(after, "layout_after", update) +
        BENCH.replace("FPGA layout", "Dispatcher layout"))
    bench = (ROOT / "verification/timing/dispatcher_equivalence_tb.sv").read_text()
    bench = bench.replace("  int seed=", "  int fpga_trial, fpga_phase;\n"
                          "  int layout_checks=0, segment_first=0, segment_later=0;\n"
                          "  int seed=")
    bench = bench.replace("  task automatic compare_outputs;", """  task automatic compare_outputs;
    if (dut.ara_req_valid_d && dut.ara_req_d.use_vd && ara_req_ready_i &&
        dut.state_q != dut.OVERLAP_PREFIX_FIXUP) begin
      layout_checks++;
      if (dut.is_segment_mem_op && !dut.illegal_insn &&
          dut.i_segment_sequencer.gen_segment_support.state_q == 0) segment_first++;
      if (dut.i_segment_sequencer.gen_segment_support.state_q == 1) segment_later++;
      assert ({dut.layout_req.vl, dut.layout_req.vstart, dut.layout_req.vd,
               dut.layout_req.emul, dut.layout_req.vtype.vsew,
               dut.single_register_result(dut.layout_req.op)} ===
              {dut.ara_req_d.vl, dut.ara_req_d.vstart, dut.ara_req_d.vd,
               dut.ara_req_d.emul, dut.ara_req_d.vtype.vsew,
               dut.single_register_result(dut.ara_req_d.op)})
        else $fatal(1,"EEW geometry differs at write cycle=%0d",checks);
    end
""")
    bench = bench.replace("    foreach (state_visits[i])\n",
                          repair_stimulus() + FIRST_SEGMENT + "\n    foreach (state_visits[i])\n")
    bench = bench.replace("    $finish;", """    assert (layout_checks>100 && segment_first>0 && segment_later>0)
      else $fatal(1,"insufficient EEW geometry coverage");
    $display("EEW metadata PASS checks=%0d first_segment=%0d later_segment=%0d",
             layout_checks,segment_first,segment_later);
    $finish;""")
    (output / "dispatcher_equivalence_tb.sv").write_text(bench)


def interface_package():
    source = (ROOT / "hardware/src/ara.sv").read_text()
    start = source.index("  // Interfaces between Ara's dispatcher and Ara's backend\n")
    end = source.index("  } ara_resp_t;", start) + len("  } ara_resp_t;")
    types = source[start:end]
    return (
        "package dispatcher_check_pkg;\n"
        "  import ara_pkg::*; import rvv_pkg::*;\n"
        "  localparam config_pkg::cva6_cfg_t CVA6Cfg = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);\n"
        "  localparam int VLEN=1024, NrLanes=4;\n"
        "  typedef logic[$clog2(VLEN+1)-1:0] vlen_t;\n"
        '  `include "ara/intf_typedef.svh"\n'
        "  `CVA6_TYPEDEF_EXCEPTION(exception_t, CVA6Cfg)\n"
        "  `CVA6_INTF_TYPEDEF_ACC_REQ(accelerator_req_t, CVA6Cfg, fpnew_pkg::roundmode_e)\n"
        "  `CVA6_INTF_TYPEDEF_ACC_RESP(accelerator_resp_t, CVA6Cfg, exception_t)\n"
        + types + "\nendpackage\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--segment-before", type=Path)
    parser.add_argument("--layout", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "dispatcher_check_pkg.sv").write_text(interface_package())
    previous = args.before.read_text()
    (args.output / "ara_dispatcher_reference.sv").write_text(
        re.sub(r"\bsegment_sequencer\b", "segment_sequencer_reference",
               re.sub(r"\bara_dispatcher\b", "ara_dispatcher_reference", previous)))
    segment_before = args.segment_before or args.before.with_name("segment_sequencer.sv")
    (args.output / "segment_sequencer_reference.sv").write_text(
        re.sub(r"\bsegment_sequencer\b", "segment_sequencer_reference",
               segment_before.read_text()))
    current = (ROOT / "hardware/src/ara_dispatcher.sv").read_text()
    if args.layout:
        layout_checks(previous, current, args.output)
    else:
        (args.output / "dispatcher_equivalence_tb.sv").write_text(
            (ROOT / "verification/timing/dispatcher_equivalence_tb.sv").read_text())
    states = set(re.findall(r"^\s*(\w+_q[q]?)\s*<=", current, re.M))
    states.update(re.findall(r"`FF\(\s*(\w+_q)\s*,", current))
    segment = (ROOT / "hardware/src/segment_sequencer.sv").read_text()
    segment_states = set(re.findall(r"^\s*(\w+_q)\s*<=", segment, re.M))
    segment_states.update(("segment_cnt_q", "vstart_cnt_q"))
    states.update("i_segment_sequencer.gen_segment_support." + name
                  for name in segment_states)
    # Include every current registered state, including verification identity.
    checks = []
    for name in sorted(states):
        checks += [f"    assert (dut.{name} === reference.{name})",
                   f'      else $fatal(1, "dispatcher state {name} cycle=%0d insn=%h", checks, acc_req_i.insn);']
    (args.output / "dispatcher_state_check.svh").write_text("\n".join(checks) + "\n")
    print(f"generated dispatcher checker for {len(states)} state signals")


if __name__ == "__main__":
    main()
