#!/usr/bin/env python3
"""Check the captured feedback cone and the FPGA fault LUT in one bounded test.

This is a Boolean proof and an RTL expression simulation, not Vivado synthesis.
"""
import argparse
from itertools import product
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export import patch_qbs_fault_decode
from prepare import ROOT

PACKAGE = ROOT / "hardware/fpga/ara_dsa_vcu118"
PREFIX = "i_cheshire_soc/gen_cva6_cores[0].gen_ara.i_ara/i_vlsu/i_qbs_engine/"


def read_luts(path):
    cells = {}
    for line in path.read_text().splitlines():
        if line.startswith("CELL "):
            match = re.fullmatch(r"CELL (.+) REF_NAME=(.*)", line)
            cell = {"ref": match[2], "inputs": {}}
            cells[match[1].removeprefix(PREFIX)] = cell
        elif line.startswith("  INIT=") and "'h" in line:
            cell["init"] = int(line.split("'h")[1], 16)
        elif line.startswith("  PIN "):
            match = re.fullmatch(r"  PIN (.+) (IN|OUT|INOUT) NETS=(.*)", line)
            pin, direction = match[1].rsplit("/", 1)[1], match[2]
        elif line.startswith("    DRIVERS=") and direction == "IN":
            cell["inputs"][pin] = line.split("=", 1)[1].replace(PREFIX, "")
    return cells


def prove_feedback(cells):
    boundaries = [f"state_q_reg[{i}]/Q" for i in range(4)]
    boundaries += [f"i_compute_engine/phase_{name}_o_INST_0/O" for name in
                   ("activation_load", "weight_load", "compute", "drain")]
    boundaries += ["i_read_engine/busy_o_INST_0/O", "i_read_engine/fault_valid_o_INST_0/O"]
    feedback = "i_read_engine_i_224/O"

    def evaluate(pin, values):
        if pin in values:
            return values[pin]
        name, output = pin.rsplit("/", 1)
        cell = cells[name]
        if output != "O" or not re.fullmatch(r"LUT[1-6]", cell["ref"]):
            raise RuntimeError(f"Unexpected cone boundary: {pin}")
        index = sum(evaluate(cell["inputs"][f"I{i}"], values) << i
                    for i in range(int(cell["ref"][3:])))
        return (cell["init"] >> index) & 1

    internal_sensitive = 0
    for bits in product((0, 1), repeat=len(boundaries)):
        values = dict(zip(boundaries, bits))
        outputs = [evaluate("i_compute_engine_i_2/O", values | {feedback: b}) for b in (0, 1)]
        if outputs[0] != outputs[1]:
            raise RuntimeError(f"Feedback affects compute_fault: {values}")
        internal = [evaluate("i_compute_engine_i_166/O", values | {feedback: b}) for b in (0, 1)]
        internal_sensitive += internal[0] != internal[1]
    if not internal_sensitive:
        raise RuntimeError("Test did not exercise the captured internal feedback edge")
    print(f"PASS: 1024 boundary combinations; feedback affects internal LUT in "
          f"{internal_sensitive} cases, compute_fault in zero cases")


def expression_test(source, patched):
    enum = re.search(r"  typedef enum logic \[3:0\] \{[^}]+\} qbs_engine_state_e;", source)[0]
    original = re.search(r"  assign compute_fault = .*?;", source, re.S)[0]
    start = patched.index("  // FPGA-only: one preserved LUT")
    end = patched.index("\n  );", start) + len("\n  );")
    return f"""
// Truth-table model only; Vivado uses its own UNISIM primitive.
module LUT5 #(parameter logic [31:0] INIT = '0) (
    input I0, I1, I2, I3, I4, output O);
  timeunit 1ns; timeprecision 1ps;
  assign O = INIT[{{I4, I3, I2, I1, I0}}];
endmodule
module original(input logic [3:0] state_q, input logic read_fault_valid,
                output logic compute_fault);
  timeunit 1ns; timeprecision 1ps;
{enum}
{original}
endmodule
module patched(input logic [3:0] state_q, input logic read_fault_valid,
               output logic compute_fault);
  timeunit 1ns; timeprecision 1ps;
{enum}
{patched[start:end]}
endmodule
module tb;
  timeunit 1ns; timeprecision 1ps;
  logic [3:0] state_q;
  logic read_fault_valid, old_fault, new_fault;
  original before_patch(state_q, read_fault_valid, old_fault);
  patched after_patch(state_q, read_fault_valid, new_fault);
  initial begin
    // All encodings, including unused states, and both fault values.
    for (int value = 0; value < 32; value++) begin
      {{read_fault_valid, state_q}} = 5'(value);
      #1;
      if (old_fault !== new_fault)
        $fatal(1, "Fault decode changed for input %0d", value);
    end
    if (after_patch.FpgaComputeFaultInit !== 32'h00600040)
      $fatal(1, "Unexpected fault truth table");
    $display("PASS: all 32 binary fault inputs, no clock or added latency");
    $finish;
  end
endmodule
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New independent test directory")
    parser.add_argument("--vcs", default="vcs")
    args = parser.parse_args()
    report = PACKAGE / "reports/inspect_9a3426f975cc/loop_fanin.rpt"
    cells = read_luts(report)
    prove_feedback(cells)
    # Negative control: a direct copy of the inner LUT must fail the proof.
    cells["i_compute_engine_i_2"]["init"] = 0xCCCCCCCCCCCCCCCC
    try:
        prove_feedback(cells)
    except RuntimeError as error:
        if not str(error).startswith("Feedback affects compute_fault:"):
            raise
    else:
        raise RuntimeError("Feedback proof did not reject the negative control")

    source = (ROOT / "hardware/src/vlsu/qbs/qbs_engine.sv").read_text()
    patched = patch_qbs_fault_decode(source)
    exported = (PACKAGE / "rtl/ara/hardware/src/vlsu/qbs/qbs_engine.sv").read_text()
    # Verify the shipped decode, even when unrelated upstream RTL is newer.
    if expression_test(source, patched) != expression_test(source, exported):
        raise RuntimeError("Exported fault decode differs from export transformation")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "tb.sv").write_text(expression_test(source, exported))
    with (output / "compile.log").open("w") as log:
        subprocess.run([args.vcs, "-full64", "-sverilog", "-top", "tb", "tb.sv", "-o", "simv"],
                       cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    with (output / "run.log").open("w") as log:
        subprocess.run([str(output / "simv")], cwd=output, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=30)
    result = (output / "run.log").read_text()
    print(result)
    if "PASS: all 32 binary fault inputs" not in result:
        raise RuntimeError("Missing test completion marker")


if __name__ == "__main__":
    main()
