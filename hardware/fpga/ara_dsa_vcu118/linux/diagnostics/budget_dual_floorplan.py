"""Estimate candidate Pblock capacity using the audited physical census.

This is a conservative primitive budget, not a packing/routability guarantee.
"""
import argparse
import csv
import io
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


def in_range(region, bounds):
    match = re.fullmatch(r"X(\d+)Y(\d+)", region)
    if not match:
        return False
    x, y = map(int, match.groups())
    x0, y0, x1, y1 = bounds
    return x0 <= x <= x1 and y0 <= y <= y1


def budget_kind(ref):
    if ref.startswith("FD"):
        return "ff"
    if ref.startswith(("LUT", "RAMD", "RAMS", "SRL")):
        return "lut_upper_bound"
    return "other"


def include_nested_members(groups):
    """Parent capacity must cover all cells bounded by nested regions too."""
    for parent in groups.values():
        x0, y0, x1, y1 = parent["bounds"]
        members = set(parent["members"])
        for child in groups.values():
            a, b, c, d = child["bounds"]
            if x0 <= a <= c <= x1 and y0 <= b <= d <= y1:
                members.update(child["members"])
        parent["budget_members"] = sorted(members)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--out", type=Path, help="New JSON evidence path (never overwritten)")
    args = parser.parse_args()
    source = Path(__file__).with_name("dual_floorplan.tcl")
    text = subprocess.run(["tclsh"], input=f"source {{{source}}}\n"
                          "foreach item [dual_floor::plan] {lassign $item name range members; "
                          "foreach member $members {puts [join [list $name $range $member] \"\\t\"]}}\n",
                          text=True, check=True, capture_output=True).stdout
    groups = {}
    for name, region, member in csv.reader(io.StringIO(text), delimiter="\t"):
        match = re.fullmatch(r"CLOCKREGION_X(\d+)Y(\d+):CLOCKREGION_X(\d+)Y(\d+)", region)
        if not match:
            raise ValueError(region)
        group = groups.setdefault(name, dict(range=region, bounds=tuple(map(int, match.groups())),
                                             members=[], counts=Counter(), sites=0, matches=Counter()))
        group["members"].append(member)
    include_nested_members(groups)
    with (args.audit / "region_capacity.tsv").open() as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["site_type"] not in ("SLICEL", "SLICEM"):
                continue
            for group in groups.values():
                if in_range(row["region"], group["bounds"]):
                    group["sites"] += int(row["sites"])
    with (args.audit / "cells.tsv").open() as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if not row["name"].startswith(("i_dram_wrapper/", "gen_ddr2.i_dram_wrapper_c2/")):
                continue
            for group in groups.values():
                for member in group["budget_members"]:
                    if row["name"].startswith(member + "/"):
                        group["counts"][budget_kind(row["ref"])] += 1
                        group["matches"][member] += 1
                        break
    for name, group in groups.items():
        if any(not group["matches"][member] for member in group["budget_members"]):
            raise ValueError("Missing audited hierarchy in " + name)
        if not group["sites"]:
            raise ValueError("Empty physical region: " + name)
        group["ff_fraction"] = group["counts"]["ff"] / (16 * group["sites"])
        group["lut_upper_fraction"] = group["counts"]["lut_upper_bound"] / (8 * group["sites"])
        if max(group["ff_fraction"], group["lut_upper_fraction"]) > .8:
            raise ValueError("Insufficient budget headroom: " + name)
        print(name, group["range"], dict(group["counts"]),
              f"FF={group['ff_fraction']:.1%} LUT_upper={group['lut_upper_fraction']:.1%}")
    with (args.out or args.audit / "candidate_budget.json").open("x") as stream:
        json.dump(dict(scope="Audited candidate primitives including nested region members; partial overlaps, other logic, "
                       "control sets, BEL packing and routing need placer validation", groups=groups), stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
