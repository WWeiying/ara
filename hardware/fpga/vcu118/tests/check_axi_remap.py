#!/usr/bin/env python3
"""Cycle equivalence plus preparation of an isolated, paired Vivado synthesis."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from axi_remap_fpga import restore_axi_remap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vcs", default="vcs")
    parser.add_argument("--baseline-shared", type=Path,
                        help="Compare this shared-DDR source against current, keeping candidate remap in both")
    parser.add_argument("--loader-adapter-constants", action="store_true",
                        help="Model constant ID/address/user connections from ara_eth_loader")
    parser.add_argument("--baseline-remap", type=Path,
                        help="Use this previous remap snapshot for OOC baseline only")
    parser.add_argument("--static-ids", action="store_true",
                        help="Compare dynamic baseline with static ID partition candidate")
    parser.add_argument("--single-loader-id", action="store_true",
                        help="Compare generic/fixed-ID protection with static partition in BOTH variants")
    args = parser.parse_args()
    if args.single_loader_id and (not args.loader_adapter_constants or args.static_ids or
                                 args.baseline_shared or args.baseline_remap):
        parser.error("--single-loader-id requires adapter constants and no other baseline options")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    package = HERE.parent / "ara_dsa_vcu118"
    manifest = json.loads((package / "manifest.json").read_text())
    names = [p for p in manifest["files"] if p.startswith(("rtl/common_cells/", "rtl/axi/"))]
    includes = [package / p for p in manifest["include_dirs"]]
    remap = "rtl/axi/src/axi_id_remap.sv"
    old = restore_axi_remap((package / remap).read_text())
    reference = re.sub(r"\baxi_id_remap(_table)?\b", r"axi_id_remap\1_reference", old)
    (output / "reference.sv").write_text(reference)
    sources = [package / p for p in names] + [output / "reference.sv", HERE / "tests/axi_remap_equivalence_tb.sv"]
    command = [args.vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "+define+SYNTHESIS+VCS",
               *["+incdir+" + str(p) for p in includes], "-top", "tb", *map(str, sources), "-o", "simv"]
    for name, cmd, timeout in (("compile", command, 180), ("run", [str(output / "simv")], 30)):
        with (output / (name + ".log")).open("w") as log:
            subprocess.run(cmd, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)
    result = (output / "run.log").read_text()
    print(result)
    if "PASS: remap cycle equivalence" not in result:
        raise RuntimeError("Missing equivalence completion")
    (output / "result.json").write_text(json.dumps({
        "scope": "Cycle equivalence, not physical timing acceptance",
        "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    }, indent=2) + "\n")
    # Portable snapshot for Vivado 2020.1 on Windows; never opens the full project.
    ooc = output / "ooc"
    ooc.mkdir()
    for sub in ("rtl/axi", "rtl/common_cells"):
        shutil.copytree(package / sub, ooc / sub)
    for name in ("ara_eth_shared_ddr.sv",):
        shutil.copyfile(HERE / "rtl" / name, ooc / name)
    wrapper = (HERE / "tests/eth_shared_timing_top.sv").read_text()
    if not args.single_loader_id:
        # Older captured shared-DDR baselines predate the specialization.
        wrapper = wrapper.replace(".LoaderSingleId(LoaderSingleId), ", "")
    (ooc / "eth_shared_timing_top.sv").write_text(wrapper)
    (ooc / "baseline_remap.sv").write_text(args.baseline_remap.read_text() if args.baseline_remap else old)
    if args.baseline_shared:
        shutil.copyfile(args.baseline_shared, ooc / "baseline_shared.sv")
    (ooc / "clock.xdc").write_text("create_clock -name ui_clk -period 3.333 [get_ports clk_i]\n")
    lines = ["set root [file dirname [file normalize [info script]]]", "cd $root",
             "foreach variant {baseline candidate} {",
             "  create_project -in_memory -part xcvu9p-flga2104-2L-e",
             "  set_param general.maxThreads 4",
             "  set_property include_dirs [list [file join $root rtl/axi/include] [file join $root rtl/common_cells/include]] [current_fileset]",
             "  set_property verilog_define {SYNTHESIS} [current_fileset]"]
    for name in names:
        if name == remap and not args.single_loader_id and (args.baseline_remap or not args.baseline_shared):
            lines.append('  if {$variant eq "baseline"} { read_verilog -sv baseline_remap.sv } else { read_verilog -sv {' + name + '} }')
        else:
            lines.append("  read_verilog -sv {" + name + "}")
    if args.baseline_shared:
        lines.append('  if {$variant eq "baseline"} { read_verilog -sv baseline_shared.sv } else { read_verilog -sv ara_eth_shared_ddr.sv }')
    else:
        lines.append("  read_verilog -sv ara_eth_shared_ddr.sv")
    lines += ["  read_verilog -sv eth_shared_timing_top.sv",
              "  read_xdc clock.xdc",
              "  set generics [list LoaderAdapterConstants=" + str(int(args.loader_adapter_constants)) + "]",
              ('  if {$variant eq "candidate"} { lappend generics StaticIdPartition=1 }' if args.static_ids else ""),
              ('  lappend generics StaticIdPartition=1 LoaderSingleId=[expr {$variant eq "candidate"}]'
               if args.single_loader_id else ""),
              "  synth_design -top eth_shared_timing_top -mode out_of_context -flatten_hierarchy rebuilt -generic $generics",
              "  file mkdir $variant",
              "  report_timing_summary -file $variant/timing_summary.rpt",
              "  report_timing -delay_type max -max_paths 20 -file $variant/setup_paths.rpt",
              "  report_utilization -file $variant/utilization.rpt",
              "  write_checkpoint $variant/synth.dcp", "  close_project", "}", "exit"]
    (ooc / "compare.tcl").write_text("\n".join(lines) + "\n")
    (ooc / "inputs.json").write_text(json.dumps({
        "scope": "Isolated synthesis comparison only; no full-design timing acceptance",
        "changed_blocks": (["shared_ddr.LoaderSingleId"] if args.single_loader_id else
                           (["shared_ddr"] if args.baseline_shared or args.static_ids else []) +
                           (["remap"] if args.baseline_remap or not args.baseline_shared else [])),
        "loader_adapter_constants": args.loader_adapter_constants,
        "static_id_partition_candidate": args.static_ids,
        "single_loader_id_candidate": args.single_loader_id,
        "sha256": {str(p.relative_to(ooc)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(ooc.rglob("*")) if p.is_file()},
    }, indent=2) + "\n")
    print("OOC_READY", ooc)


if __name__ == "__main__":
    main()
