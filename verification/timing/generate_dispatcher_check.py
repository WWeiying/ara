#!/usr/bin/env python3
"""Generate dispatcher types and a state checker from the actual RTL interfaces."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "dispatcher_check_pkg.sv").write_text(interface_package())
    previous = args.before.read_text()
    (args.output / "ara_dispatcher_reference.sv").write_text(
        re.sub(r"\bara_dispatcher\b", "ara_dispatcher_reference", previous))
    current = (ROOT / "hardware/src/ara_dispatcher.sv").read_text()
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
