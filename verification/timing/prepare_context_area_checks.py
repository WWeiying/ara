#!/usr/bin/env python3
"""Generate cycle miters against a saved pre-edit QBS/AKV RTL snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MODULES = {
    "qbs_activation_context": "qbs",
    "qbs_profile_engine_int": "qbs",
    "qbs_fp_accumulator": "qbs",
    "akv_context": "akv",
    "akv_v2_context": "akv",
}


def context_miter(name, source):
    header = source[source.index("module "):source.index(");") + 2]
    ports = []
    for line in header.splitlines():
        match = re.fullmatch(r"\s*(input|output)\s+(.+?)\s+(\w+)\s*,?\s*", line)
        if match:
            ports.append(match.groups())
        elif re.match(r"\s*(input|output)\b", line):
            raise ValueError(f"unsupported port declaration: {line}")
    outputs = [(kind, port) for direction, kind, port in ports if direction == "output"]
    if not outputs:
        raise ValueError(f"no outputs parsed for {name}")
    result = re.sub(r"\b" + name + r"\b", name + "_area_check", header, count=1)
    result = re.sub(r"\boutput\b", "input", result) + "\n"
    for kind, port in outputs:
        result += f"  {kind} ref_{port};\n"
    result += f"  {name}_reference i_reference (\n"
    result += "".join(f"    .{port}(ref_{port}),\n" for _, port in outputs) + "    .*\n  );\n"
    if name != "qbs_activation_context":
        request = ("replay_read_i && !write_busy_o" if name == "akv_context"
                   else "row_read_i && !write_valid_i && !column_busy_o")
        result += ("  logic read_pending_q;\n"
                   "  always_ff @(posedge clk_i or negedge rst_ni)\n"
                   "    if (!rst_ni) read_pending_q <= 1'b0;\n"
                   f"    else read_pending_q <= {request};\n")
    result += "  always @(negedge clk_i) if (rst_ni) begin\n"
    for _, port in outputs:
        cond = "1'b1"
        if name == "qbs_activation_context":
            if port == "replay_data_o":
                result += ("    if (replay_data_valid_o) for (int b = 0; b < 16; b++)\n"
                           "      if (replay_strb_o[b])\n"
                           "        assert (replay_data_o[8*b +: 8] === ref_replay_data_o[8*b +: 8])\n"
                           "          else $fatal(1, \"QBS context replay byte/cycle mismatch\");\n")
                continue
            if port in {"replay_strb_o", "replay_offset_o", "replay_last_o"}:
                cond = "replay_data_valid_o"
        elif port in {"replay_data_o", "row_data_o"}:
            cond = "read_pending_q"
        elif port == "column_data_o":
            cond = "column_valid_o"
        result += (f"    if ({cond}) assert ({port} === ref_{port})\n"
                   f"      else $fatal(1, \"{name} {port} cycle mismatch\");\n")
    result += f"  end\nendmodule\nbind {name} {name}_area_check i_area_check (.*);\n"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    miters = []
    for name, group in MODULES.items():
        relative = Path(f"hardware/src/vlsu/{group}/{name}.sv")
        source = (args.before / relative).read_text()
        reference = re.sub(r"\b" + name + r"\b", name + "_reference", source)
        (args.output / f"{name}_reference.sv").write_text(reference)
        records.append({"path": str(relative),
                        "before_sha256": hashlib.sha256(source.encode()).hexdigest(),
                        "after_sha256": hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()})
        if name.endswith("context"):
            miter = context_miter(name, source)
            (args.output / f"{name}_miter.sv").write_text(miter)
            miters.append(miter)
    (args.output / "context_miters.sv").write_text("\n".join(miters))
    # Both snapshots have the same compact-window interface. Unlike the older
    # pre-pipeline miter, this comparison must cover production CompactRead=1.
    checker = (ROOT / "verification/timing/qbs_equivalence.sv").read_text()
    assert "if (!CompactRead)" in checker
    checker = checker.replace("if (!CompactRead)", "if (1'b1)")
    checker = checker.replace("qbs_profile_engine_int_reference i_reference",
                              "qbs_profile_engine_int_reference #(.CompactRead(CompactRead)) i_reference")
    (args.output / "qbs_miters.sv").write_text(checker)
    (args.output / "manifest.json").write_text(json.dumps(records, indent=2) + "\n")
    print(f"generated five cycle miters in {args.output}")


if __name__ == "__main__":
    main()
