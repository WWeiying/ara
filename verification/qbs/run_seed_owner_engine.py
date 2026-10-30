#!/usr/bin/env python3
"""Validate seeded QBS controller ownership with the existing AXI/MMU fixture."""
import argparse
import os
from pathlib import Path
import re
import subprocess
from run_half_scale_soc import ROOT,atomic_json,hashes
from run_tile_context_engine import run_command


def bench_source(text,scenarios):
    anchor="  initial begin : run_tests\n"
    if text.count(anchor)!=1: raise ValueError("Engine main boundary changed")
    old_main=text[text.index(anchor):]
    begin=old_main.index("    clk = 1'b0;")
    end=old_main.index("    if (!$value$plusargs(\"QBS_COMMAND_VECTOR_FILE")
    initialization=old_main[begin:end]
    # Keep the original local declarations for its existing initialization.
    declarations=old_main[len(anchor):begin]
    prefix=text[:text.index(anchor)]
    prefix=prefix.replace("module qbs_engine_tb;","module qbs_seed_owner_engine_tb;")
    split=scenarios.index("  logic router_owner")
    ports,routines=scenarios[:split],scenarios[split:]
    prefix=prefix.replace("  qbs_engine #(\n",ports+"\n  qbs_engine #(\n    .SeedRestoreEnable(1'b1),\n")
    replacements={".command_seed_i                  (1'b0)":".command_seed_i                  (command_seed)",
        ".seed_lane_valid_i               ('0)":".seed_lane_valid_i               (seed_lane_valid)",
        ".seed_lane_ready_o               ()":".seed_lane_ready_o               (seed_lane_ready)",
        ".seed_lane_data_i                ('{default:'0})":".seed_lane_data_i                (seed_lane_data)",
        "  assign ldu_result_final_gnt = ldu_result_req;":
        "  assign ldu_result_final_gnt = (delayed_final | ldu_result_req) & {4{owner_cycles % 5 == 0}};"}
    for old,new in replacements.items():
        if prefix.count(old)!=1: raise ValueError("Seed fixture boundary changed: "+old)
        prefix=prefix.replace(old,new)
    main="""
    repeat (4) @(negedge clk); rst_n=1;
    for (int profile=1;profile<=9;profile++) begin
      run_zero_case(profile,1,1,1);
      run_zero_case(profile,3,17,1);
      run_zero_case(profile,4,32,1);
      run_zero_case(profile,5,7,1);
      run_zero_case(profile,8,15,1);
      run_zero_case(profile,8,16,1);
    end
    for (int kind=0;kind<8;kind++) run_fault_case(kind);
    partial_reset();
    assert (functional_count==63 && router_done) else $fatal(1,"Incomplete seed owner matrix");
    $display("QBS_SEED_OWNER_PASS functional=63 faults=8 reset=1");
    $finish;
  end
endmodule
"""
    return prefix+routines+anchor+declarations+initialization+main


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    here=ROOT/"verification/qbs"
    sources=[Path(x) for x in subprocess.check_output(["make","-s","--no-print-directory","-C",str(here),
        "--eval=print-seed-owner-sources:;@printf '%s\\n' $(RTL_SOURCES)","print-seed-owner-sources"],text=True).splitlines()]
    template=here/"qbs_engine_tb.sv"; scenarios=here/"qbs_seed_owner_scenarios.svh"
    bench=out/"qbs_seed_owner_engine_tb.sv"; bench.write_text(bench_source(template.read_text(),scenarios.read_text()))
    pins=hashes([*sources,bench,template,scenarios,Path(__file__),here/"Makefile",here/"run_half_scale_soc.py",
        here/"run_tile_context_engine.py",*ROOT.glob("hardware/deps/common_cells/include/**/*.svh"),
        *ROOT.glob("hardware/deps/axi/include/**/*.svh")])
    atomic_json(out/"manifest.json",pins); state=dict(state="BUILDING",pid=os.getpid(),child_pid=None)
    def save(): atomic_json(out/"status.json",state)
    def started(pid): state["child_pid"]=pid; save()
    save()
    try:
        command=["vcs","-full64","-sverilog","-timescale=1ns/1ps","+lint=TFIPC-L",
            "+incdir+"+str(ROOT/"hardware/deps/common_cells/include"),
            "+incdir+"+str(ROOT/"hardware/deps/axi/include"),*map(str,sources),str(bench),
            "-top","qbs_seed_owner_engine_tb","-o",str(out/"simv")]
        atomic_json(out/"build-command.json",command)
        if run_command(command,out/"compile.log",600,os.environ.copy(),started): raise RuntimeError("Seed owner compile failed")
        state["state"]="RUNNING"; save()
        if run_command([str(out/"simv"),"-l",str(out/"run.log")],out/"console.log",300,os.environ.copy(),started):
            raise RuntimeError("Seed owner simulation failed")
        log=(out/"run.log").read_text()
        if (log.splitlines().count("QBS_SEED_OWNER_PASS functional=63 faults=8 reset=1")!=1 or
            log.splitlines().count("QBS_SEED_ROUTER_PASS combinations=8192")!=1 or
            set(map(int,re.findall(r"^QBS_SEED_OWNER_FAULT_PASS kind=(\d+)$",log,re.M)))!=set(range(8)) or
            log.splitlines().count("QBS_SEED_OWNER_FAULT_PENDING_PASS")!=1 or
            log.splitlines().count("QBS_SEED_OWNER_RESET_PASS source_flushed=1")!=1 or
            re.search(r"Fatal:|Error:",log) or hashes(map(Path,pins))!=pins): raise ValueError("Incomplete seed ownership acceptance")
        state["state"]="PASS"
        atomic_json(out/"result.json",dict(state="PASS",functional=63,faults=8,reset=1,router_combinations=8192,
            scope="Actual QBS controller/compute/mapper, modeled Lane StA delivery; no ISA/SoC or speedup claim",
            evidence_sha256=hashes([out/"manifest.json",out/"run.log"])))
    except BaseException as exc: state.update(state="FAIL",error=repr(exc)); raise
    finally: state["child_pid"]=None; save()


if __name__=="__main__":main()
