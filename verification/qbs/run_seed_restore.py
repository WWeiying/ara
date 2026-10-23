#!/usr/bin/env python3
"""Generate/test a raw-FP32 restore port; production RTL stays untouched."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from run_half_scale_soc import ROOT, atomic_json, hashes
from run_tile_context_engine import run_command


def prototype(text):
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1: raise ValueError("Accumulator anchor changed: " + old[:50])
        text = text.replace(old, new)
    replace("module qbs_fp_accumulator\n", "module qbs_fp_accumulator_seeded\n")
    replace("  output logic                 update_valid_o,", """  input logic raw_seed_valid_i,
  output logic raw_seed_ready_o,
  input logic [3:0] raw_seed_row_i,
  input logic [7:0] raw_seed_mask_i,
  input logic [31:0] raw_seed_data_i [8],

  output logic                 update_valid_o,""")
    replace("  assign request_ready_o = !clear_i", """  wire raw_seed_fire = raw_seed_valid_i && raw_seed_ready_o;
  assign raw_seed_ready_o = rst_ni && !clear_i && !busy_o;
  assign request_ready_o = !raw_seed_valid_i && !clear_i""")
    replace("        if (bank_write && write_index[6:3] == 4'(row))\n          accumulator_data_q[bank][row] <= fp_result;", """        if (raw_seed_fire && raw_seed_mask_i[bank] && raw_seed_row_i == 4'(row))
          accumulator_data_q[bank][row] <= raw_seed_data_i[bank];
        else if (bank_write && write_index[6:3] == 4'(row))
          accumulator_data_q[bank][row] <= fp_result;""")
    replace("      end else begin\n        if (busy_o) begin", """      end else begin
        if (raw_seed_fire) begin
          for (int bank = 0; bank < 8; bank++)
            accumulator_valid_q[{raw_seed_row_i, 3'(bank)}] <= raw_seed_mask_i[bank];
        end
        if (busy_o) begin""")
    replace("endmodule : qbs_fp_accumulator", "endmodule : qbs_fp_accumulator_seeded")
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    source = ROOT / "hardware/src/vlsu/qbs/qbs_fp_accumulator.sv"
    bench = ROOT / "verification/qbs/qbs_seed_restore_tb.sv"
    directory = ROOT / "verification/qbs"
    query = ["make", "-s", "--no-print-directory", "-C", str(directory),
             "--eval=print-seed-sources:;@printf '%s\\n' $(RTL_SOURCES)", "print-seed-sources"]
    sources = [Path(line) for line in subprocess.check_output(query, text=True).splitlines()]
    pins = hashes([source, bench, Path(__file__), directory / "Makefile",
        directory / "run_half_scale_soc.py", directory / "run_tile_context_engine.py", *sources,
        *ROOT.glob("hardware/deps/common_cells/include/**/*.svh"),
        *ROOT.glob("hardware/deps/axi/include/**/*.svh")])
    candidate = out / "qbs_fp_accumulator_seeded.sv"
    candidate.write_text(prototype(source.read_text()))
    pins.update(hashes([candidate])); atomic_json(out / "manifest.json", pins)
    state = dict(state="BUILDING", pid=os.getpid(), child_pid=None,
                 scope="Accumulator raw-bit port prototype only, no ISA/VLSU integration or performance claim")
    def save(): atomic_json(out / "status.json", state)
    def started(pid): state["child_pid"] = pid; save()
    save()
    try:
        command = ["vcs", "-full64", "-sverilog", "-timescale=1ns/1ps", "+lint=TFIPC-L",
                   "+incdir+" + str(ROOT / "hardware/deps/common_cells/include"),
                   "+incdir+" + str(ROOT / "hardware/deps/axi/include"), *map(str,sources),
                   str(candidate), str(bench), "-top", "qbs_seed_restore_tb", "-o", str(out / "simv")]
        atomic_json(out / "build-command.json", command)
        if run_command(command, out / "compile.log", 300, os.environ.copy(), started):
            raise RuntimeError("Seed prototype compile failed")
        state["state"] = "RUNNING"; save()
        if run_command([str(out / "simv"), "-l", str(out / "run.log")],
                       out / "console.log", 120, os.environ.copy(), started):
            raise RuntimeError("Seed prototype failed")
        log = (out / "run.log").read_text()
        marker = "QBS_SEED_RESTORE_PASS profiles=9 raw_words=128 compared=2432 witness=3f800000 stripe2=cc000000"
        if log.splitlines().count(marker) != 1 or "Fatal:" in log or "Error:" in log or hashes(map(Path,pins)) != pins:
            raise ValueError("Incomplete seed acceptance or input drift")
        state["state"] = "PASS"
        atomic_json(out / "result.json", dict(state="PASS", profiles=9, raw_words=128, comparisons=2432,
            scope=state["scope"], evidence_sha256=hashes([out / "run.log", out / "manifest.json", candidate])))
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc)); raise
    finally: state["child_pid"] = None; save()


if __name__ == "__main__": main()
