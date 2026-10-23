#!/usr/bin/env python3
"""Check split-K seed continuation against the unchanged command-vector oracle.

The bench derives from the normal compute-engine test, retaining all reference
outputs/counters and fault checks. It splits at each original K-block boundary,
restores raw partial sums, and accounts for every prefix's flags and counters.
No ISA, lane route or speedup is asserted by this compute-level gate.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess

from run_half_scale_soc import ROOT, atomic_json, hashes
from run_tile_context_engine import run_command


DECLARATIONS = """
  bit split_k;
  logic command_seed = 0, seed_valid = 0, seed_ready, seed_done = 0;
  logic [3:0] seed_row = 0;
  logic [7:0] seed_mask = 0;
  logic [31:0] seed_data [8], checkpoint [128];
  logic [4:0] prefix_flags = 0;
  int prefix_count = 0;
  logic [31:0] prefix_counters [9];

  task automatic continue_after_prefix;
    int ticks;
    ticks = 0;
    while (!result_valid && ticks < 8192) begin @(negedge clk); ticks++; end
    assert (result_valid) else $fatal(1, "Prefix did not finish");
    prefix_flags |= result_fflags;
    prefix_counters[0] += tiles_computed;
    prefix_counters[1] += weight_bytes;
    prefix_counters[2] += activation_bytes;
    prefix_counters[3] += useful_pairs;
    prefix_counters[4] += pair_capacity;
    prefix_counters[5] += dot_active_cycles;
    prefix_counters[6] += fp_uops;
    prefix_counters[7] += accumulator_updates;
    for (int r = 0; r < 16; r++) begin
      result_bank_row = 4'(r); #1;
      for (int b = 0; b < 8; b++) begin
        if (r / (command_m>4 ? 2:4) < int'(command_m) &&
            (r % (command_m>4 ? 2:4))*8+b < int'(command_n))
          assert (result_bank_valid[b] === 1'b1 && !$isunknown(result_bank_data[b]))
            else $fatal(1, "Prefix exposed unknown or missing active accumulator");
        checkpoint[r*8+b] = result_bank_data[b];
      end
    end
    @(negedge clk); result_consumed = 1;
    @(negedge clk); result_consumed = 0;
    assert (command_ready) else $fatal(1, "Prefix owner not retired");
    command_seed = 1; command_k_blocks = 1; command_valid = 1;
    @(negedge clk); command_valid = 0;
    ticks = 0;
    while (!seed_ready && ticks < 32) begin @(negedge clk); ticks++; end
    assert (seed_ready && !activation_needed && !weight_needed && !result_valid)
      else $fatal(1, "Compute did not wait for restored seeds");
    for (int r = 0; r < 16; r++) begin
      seed_mask = 0;
      for (int b = 0; b < 8; b++) begin
        seed_data[b] = checkpoint[r*8+b];
        if (r / (command_m>4 ? 2:4) < int'(command_m) &&
            (r % (command_m>4 ? 2:4))*8+b < int'(command_n)) seed_mask[b] = 1;
      end
      if (|seed_mask) begin
        seed_row = 4'(r); seed_valid = 1;
        // Both legal completion timings: coincident last write and next cycle.
        if (r == (int'(command_m)-1)*(command_m>4 ? 2:4)+(int'(command_n)-1)/8 &&
            prefix_count % 2 == 0) seed_done = 1;
        do @(posedge clk); while (!seed_ready);
        @(negedge clk); seed_valid = 0;
      end
    end
    if (!seed_done) begin
      seed_done = 1;
      @(negedge clk);
    end
    seed_done = 0;
    prefix_count++;
  endtask

  task automatic seed_fault_or_reset(input bit do_reset);
    int ticks;
    while (!command_ready) @(negedge clk);
    @(negedge clk);
    command_profile = QBS_WEIGHT_PROFILE_Q4_K;
    command_activation_profile = QBS_ACTIVATION_PROFILE_Q8_K;
    command_weight_layout = QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR;
    command_activation_layout = QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED;
    command_m = 4; command_n = 7; command_k_blocks = 1;
    command_seed = 1; command_valid = 1; seed_done = 0;
    @(negedge clk); command_valid = 0;
    ticks = 0;
    while (!seed_ready && ticks < 32) begin @(negedge clk); ticks++; end
    assert (seed_ready && !activation_needed && !weight_needed && !result_valid)
      else $fatal(1, "Seed fault fixture did not enter restore phase");
    seed_row = 0; seed_mask = 8'h7f; seed_valid = 1;
    for (int b = 0; b < 8; b++) seed_data[b] = 32'h7f800001 ^ 32'(b);
    @(negedge clk); seed_valid = 0;
    if (do_reset) begin
      rst_n = 0;
      #1; assert (!seed_ready && !result_valid) else $fatal(1, "Seed ready survived reset");
      repeat (2) @(negedge clk);
      rst_n = 1;
      @(negedge clk);
    end else begin
      fault = 1; seed_valid = 1;
      #1; assert (!seed_ready && !result_valid) else $fatal(1, "Seed accepted during fault");
      ticks = 0;
      while (!fault_done && ticks < 64) begin
        @(negedge clk); ticks++;
        assert (!result_valid) else $fatal(1, "Fault exposed partial seed");
      end
      assert (fault_done) else $fatal(1, "Seed fault failed to drain");
      seed_valid = 0; fault = 0;
      @(negedge clk);
    end
    command_seed = 0;
    assert (command_ready && !seed_ready && !result_valid && result_fflags === 0)
      else $fatal(1, "Seed cancellation retained state");
    $display("QBS_SEED_CANCEL_PASS reset=%0d", do_reset);
  endtask
"""


def bench_source(text):
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError("Compute bench anchor changed: " + old[:80])
        text = text.replace(old, new)
    replace("module qbs_compute_engine_tb;", "module qbs_compute_continue_tb;")
    replace("endmodule : qbs_compute_engine_tb", "endmodule : qbs_compute_continue_tb")
    replace("  qbs_compute_engine dut (", DECLARATIONS + "\n  qbs_compute_engine #(.SeedRestoreEnable(1'b1)) dut (")
    for old, new in ((".command_seed_i                 (1'b0)", ".command_seed_i                 (command_seed)"),
                     (".seed_valid_i                   (1'b0)", ".seed_valid_i                   (seed_valid)"),
                     (".seed_ready_o                   ()", ".seed_ready_o                   (seed_ready)"),
                     (".seed_row_i                     ('0)", ".seed_row_i                     (seed_row)"),
                     (".seed_mask_i                    ('0)", ".seed_mask_i                    (seed_mask)"),
                     (".seed_data_i                    ('{default:'0})", ".seed_data_i                    (seed_data)"),
                     (".seed_done_i                    (1'b0)", ".seed_done_i                    (seed_done)")):
        replace(old, new)
    replace("    total_errors = 0;", "    total_errors = 0; split_k = $test$plusargs(\"SPLIT_K\");")
    replace("      command_k_blocks = k_blocks[8:0];", """      command_k_blocks = split_k ? 9'd1 : k_blocks[8:0];
      command_seed = 0; prefix_flags = 0;
      for (int i = 0; i < 9; i++) prefix_counters[i] = 0;""")
    replace("        while (!(busy && (activation_needed || weight_needed))) @(posedge clk);", """        if (split_k && expected_k > 0 && expected_row == 0) continue_after_prefix();
        while (!(busy && (activation_needed || weight_needed))) @(posedge clk);""")
    replace("        if (expected_k_block !== expected_k ||", "        if (expected_k_block !== (split_k ? 0 : expected_k) ||")
    replace("                   (tile + 1) * (m > 4 ? 2 : 1) &&", "                   (split_k ? tile % ((n+3)/4) + 1 : tile + 1) * (m > 4 ? 2 : 1) &&")
    replace("      if (result_fflags !== expected_flags[4:0] ||", "      if ((result_fflags | prefix_flags) !== expected_flags[4:0] ||")
    fields = (("tiles_computed", "expected_tiles"), ("weight_bytes", "expected_weight_bytes"),
              ("activation_bytes", "expected_activation_bytes"), ("useful_pairs", "expected_useful_pairs"),
              ("pair_capacity", "expected_pair_capacity"), ("dot_active_cycles", "expected_dot_cycles"),
              ("fp_uops", "expected_fp_uops"), ("accumulator_updates", "expected_updates"))
    for index, (field, expected) in enumerate(fields):
        replace(f"{field} !== {expected}", f"{field} + prefix_counters[{index}] !== {expected}")
    replace("    // Directed atomic-abort check while a command is waiting for data.", """    command_seed = 0;
    seed_fault_or_reset(0);
    seed_fault_or_reset(1);
    // Directed atomic-abort check while a command is waiting for data.""")
    replace("    $fclose(fd);", """    $display("QBS_CONTINUATION_ACCEPT split=%0d prefixes=%0d", split_k, prefix_count);
    $fclose(fd);""")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    directory = ROOT / "verification/qbs"
    query = ["make", "-s", "--no-print-directory", "-C", str(directory),
             "--eval=print-continue-sources:;@printf '%s\\n' $(RTL_SOURCES)", "print-continue-sources"]
    sources = [Path(line) for line in subprocess.check_output(query, text=True).splitlines()]
    bench = out / "qbs_compute_continue_tb.sv"
    template = directory / "qbs_compute_engine_tb.sv"
    bench.write_text(bench_source(template.read_text()))
    pins = hashes([*sources, bench, template, Path(__file__), directory / "Makefile",
        directory / "run_half_scale_soc.py", directory / "run_tile_context_engine.py",
        directory / "qbs_command_vectors.c", directory / "qbs_ref.c", directory / "qbs_ref.h",
        *ROOT.glob("apps/common/qbs*.h"),
        *ROOT.glob("hardware/deps/common_cells/include/**/*.svh"),
        *ROOT.glob("hardware/deps/axi/include/**/*.svh")])
    atomic_json(out / "manifest.json", pins)
    state = dict(state="BUILDING", pid=os.getpid(), child_pid=None)
    def save():
        atomic_json(out / "status.json", state)
    def started(pid):
        state["child_pid"] = pid
        save()
    save()
    try:
        generator = out / "vectors"
        cc = ["gcc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-ffp-contract=off",
              "-frounding-math", str(directory / "qbs_command_vectors.c"),
              str(directory / "qbs_ref.c"), "-lm", "-o", str(generator)]
        if run_command(cc, out / "generator-compile.log", 120, os.environ.copy(), started):
            raise RuntimeError("Command oracle compile failed")
        vectors = out / "vectors.txt"
        if run_command([str(generator), str(vectors)], out / "generator.log", 120, os.environ.copy(), started):
            raise RuntimeError("Command oracle generation failed")
        pins.update(hashes([generator, vectors])); atomic_json(out / "manifest.json", pins)
        expected_cases = int(vectors.read_text().splitlines()[0].split()[1])
        expected_prefixes = sum(int(line.split()[7])-1 for line in vectors.read_text().splitlines() if line.startswith("CMD "))
        command = ["vcs", "-full64", "-sverilog", "-timescale=1ns/1ps", "+lint=TFIPC-L",
                   "+incdir+" + str(ROOT / "hardware/deps/common_cells/include"),
                   "+incdir+" + str(ROOT / "hardware/deps/axi/include"), *map(str, sources),
                   str(bench), "-top", "qbs_compute_continue_tb", "-o", str(out / "simv")]
        atomic_json(out / "build-command.json", command)
        if run_command(command, out / "compile.log", 300, os.environ.copy(), started):
            raise RuntimeError("Compute continuation compile failed")
        state["state"] = "RUNNING"; save()
        results = []
        for split in (0, 1):
            run = out / f"split{split}"; run.mkdir()
            argv = [str(out / "simv"), "-l", str(run / "run.log"), "+QBS_COMMAND_VECTOR_FILE="+str(vectors)]
            if split: argv.append("+SPLIT_K")
            if run_command(argv, run / "console.log", 300, os.environ.copy(), started):
                raise RuntimeError(f"Compute continuation split={split} failed")
            text = (run / "run.log").read_text()
            got = re.findall(r"^QBS command case (\d+) PASS profile=(\d+) M=(\d+) N=(\d+) Kb=(\d+) layouts=(\d+)/(\d+)$", text, re.M)
            prefix = expected_prefixes if split else 0
            if (len(got) != expected_cases or {int(x[0]) for x in got} != set(range(expected_cases)) or
                text.splitlines().count(f"QBS_CONTINUATION_ACCEPT split={split} prefixes={prefix}") != 1 or
                text.splitlines().count(f"QBS command engine PASS: {expected_cases} functional cases") != 1 or
                text.count("QBS command fault discard PASS") != 1 or
                text.splitlines().count("QBS_SEED_CANCEL_PASS reset=0") != 1 or
                text.splitlines().count("QBS_SEED_CANCEL_PASS reset=1") != 1 or
                len(re.findall(r"^QBS pipeline fault stage [0-3] PASS drain_cycles=\d+$", text,re.M)) != 4 or
                re.search(r"Fatal:|Error:", text)):
                raise ValueError(f"Incomplete command acceptance split={split}")
            results.append(dict(split=split, cases=expected_cases, prefixes=prefix, logs_sha256=hashes([run / "run.log"])))
        if hashes(map(Path,pins)) != pins: raise ValueError("Execution input drift")
        state["state"] = "PASS"
        atomic_json(out / "result.json", dict(state="PASS", runs=results,
            scope="Compute-only: independent command-vector oracle, no ISA/lane/SoC/performance closure"))
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc)); raise
    finally:
        state["child_pid"] = None; save()


if __name__ == "__main__":
    main()
