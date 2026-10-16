#!/usr/bin/env python3
"""Bind Vivado's flattened ports for a restricted sequencer diagnostic.

Physical boundary alias inputs are swept, not claimed to be reconstructed.
This harness is not a whole-design equivalence check.
"""
import argparse
from pathlib import Path
import re

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("netlist", type=Path)
p.add_argument("output", type=Path)
a = p.parse_args()
top = a.netlist.read_text().split("endmodule", 1)[0]
ports = re.findall(r"^  (input|output)\s+(?:\[[^\]]+\])?\s*(\\\S+|\w+)\s*;", top, re.M)
if not 150 <= len(ports) <= 220:
    p.error("unexpected exported port count")
aliases = []
connections = []
for direction, name in ports:
    clean = name.lstrip("\\")
    if clean.endswith("_alias"):
        if direction == "input" and re.fullmatch(r"ara_req_o\[vd\]\[[01]\]_repN(?:_\d+)?_alias", clean):
            target = "alias_value"
            aliases.append(clean)
        elif direction == "output" and clean in (
                "pe_req_o[use_vs1]_hold_fix_1_alias", "pe_req_o[vs1][2]_hold_fix_1_alias"):
            target = ""
        else:
            p.error("unreviewed physical boundary port: " + clean)
    else:
        target = re.sub(r"\[([A-Za-z_]\w*)\]", r".\1", clean)
    connections.append(f"    .{name} ({target})")
if len(aliases) != 12:
    p.error("unexpected alias count")
with a.output.open("x") as f:
    f.write("// External replicated vd-bit aliases are swept, not reconstructed.\n")
    f.write("  ara_sequencer dut (\n" + ",\n".join(connections) + "\n  );\n")
print("RESTRICTED_BOUNDARY_ALIAS_SWEEP", len(aliases))
