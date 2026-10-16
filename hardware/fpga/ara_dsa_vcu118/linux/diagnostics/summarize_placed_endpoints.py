"""Group Vivado's exported placement paths; never label estimates as signoff."""
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path


def owner(pin):
    for prefix, label in (("gen_ddr2.i_dram_wrapper_c2/", "ddr2"),
                          ("i_dram_wrapper/", "ddr1")):
        if pin.startswith(prefix):
            tail = pin[len(prefix):]
            if tail.startswith("gen_cdc.i_axi_cdc_mig/"):
                parts = tail.split("/")
                return label + "/cdc/" + parts[2]
            return label + "/" + tail.split("/")[0]
    if pin.startswith("i_cheshire_soc/"):
        return "/".join(pin.split("/")[:3])
    return pin.split("/")[0]


def summarize(rows, limit=50000):
    rows = list(rows)
    endpoints = {}
    for row in rows:
        slack = float(row["slack"])
        if not math.isfinite(slack) or slack >= 0:
            raise ValueError("Expected finite violating setup slack")
        key = (row["endpoint"], row["start_clock"], row["end_clock"])
        if key not in endpoints or slack < float(endpoints[key]["slack"]):
            endpoints[key] = row
    groups = defaultdict(list)
    for row in endpoints.values():
        groups[(owner(row["endpoint"]), row["start_clock"], row["end_clock"])].append(row)
    result = []
    for (module, start_clock, end_clock), paths in groups.items():
        worst = min(paths, key=lambda r: float(r["slack"]))
        result.append(dict(module=module, start_clock=start_clock, end_clock=end_clock,
                           endpoint_clock_pairs=len(paths), worst_slack_ns=float(worst["slack"]),
                           sampled_slack_sum_ns=sum(float(p["slack"]) for p in paths),
                           worst_path=worst))
    result.sort(key=lambda r: r["sampled_slack_sum_ns"])
    return dict(scope="placed_estimates_not_routed_signoff", exported_rows=len(rows),
                export_limit_reached=len(rows) >= limit,
                endpoint_clock_pairs=len(endpoints), groups=result,
                warning="Sample sums are not Vivado TNS; exports may be capped and endpoints may have multiple clock pairs.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tsv", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    with args.tsv.open(encoding="utf-8-sig", newline="") as stream:
        result = summarize(csv.DictReader(stream, delimiter="\t"))
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    for group in result["groups"]:
        print(group["endpoint_clock_pairs"], group["worst_slack_ns"], group["module"],
              group["start_clock"], "->", group["end_clock"])


if __name__ == "__main__":
    main()
