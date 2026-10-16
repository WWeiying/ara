"""Join physical census and timing paths without inferring routed signoff."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def owner(name):
    for prefix, label in (("i_dram_wrapper/", "c1"),
                          ("gen_ddr2.i_dram_wrapper_c2/", "c2")):
        if not name.startswith(prefix):
            continue
        rest = name[len(prefix):]
        if rest.startswith("gen_ethernet.i_eth_loader/i_loader/loader_bd_i/"):
            rest = rest.split("loader_bd_i/", 1)[1]
            if rest.startswith("ddr_fabric/inst/"):
                return label + "/loader/fabric/" + rest.split("/")[2]
            return label + "/loader/" + rest.split("/")[0]
        if rest.startswith("gen_ethernet.i_eth_shared_ddr/"):
            return label + "/shared/" + rest.split("/")[1]
        if rest.startswith("gen_cdc.i_axi_cdc_mig/"):
            parts = rest.split("/")
            return label + "/cdc/" + "/".join(parts[1:3])
        return label + "/" + rest.split("/")[0]
    if ".i_ara/" in name and ".i_lane/" in name:
        return "ara/" + name.split(".i_ara/", 1)[1].split("/")[0]
    if name.startswith("i_cheshire_soc/"):
        return "/".join(name.split("/")[:3])
    return name.split("/")[0]


def primitive_kind(ref):
    for prefix, kind in (("FD", "ff"), ("LUT", "lut"), ("RAMB", "bram"),
                         ("DSP", "dsp"), ("URAM", "uram")):
        if ref.startswith(prefix):
            return kind
    return "other"


def read_tsv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream, delimiter="\t")


def analyze(cells, paths):
    locations = {}
    populations = defaultdict(Counter)
    for row in cells:
        name = row["name"]
        if name in locations:
            raise ValueError("Duplicate primitive: " + name)
        locations[name] = (row["region"], row["slr"], row["loc"])
        populations[(owner(name), row["region"], row["slr"])][primitive_kind(row["ref"])] += 1
    results = {}
    for kind, rows in paths.items():
        grouped = {}
        crossings = Counter()
        starts = Counter()
        count = 0
        for row in rows:
            count += 1
            src = row["STARTPOINT_PIN"].rsplit("/", 1)[0]
            dst = row["ENDPOINT_PIN"].rsplit("/", 1)[0]
            sr, ss, _ = locations.get(src, ("", "", ""))
            dr, ds, _ = locations.get(dst, ("", "", ""))
            cross = ("unknown" if not sr or not dr else
                     "cross_slr" if ss != ds else
                     "cross_region" if sr != dr else "same_region")
            crossings[cross] += 1
            starts[src] += 1
            key = (owner(dst), row["STARTPOINT_CLOCK"], row["ENDPOINT_CLOCK"])
            if key not in grouped:
                grouped[key] = dict(endpoints=0, worst_slack_ns=0.0,
                                    exported_slack_sum_ns=0.0, crossings=Counter(),
                                    region_pairs=Counter())
            group = grouped[key]
            slack = float(row["SLACK"])
            group["endpoints"] += 1
            group["exported_slack_sum_ns"] += slack
            group["crossings"][cross] += 1
            group["region_pairs"][f"{sr}->{dr}"] += 1
            if slack < group["worst_slack_ns"]:
                group["worst_slack_ns"] = slack
                group["worst_path"] = row
        ordered = []
        for (module, sc, dc), group in grouped.items():
            ordered.append(dict(module=module, source_clock=sc, dest_clock=dc, **group))
        ordered.sort(key=lambda group: group["exported_slack_sum_ns"])
        results[kind] = dict(endpoints=count, crossings=crossings, groups=ordered,
                             frequent_startpoints=starts.most_common(30))
    return dict(scope="placed estimates, not routed signoff; sums are exported samples, not authoritative TNS",
                primitives=len(locations), timing=results,
                populations=[dict(module=m, region=r, slr=s, primitives=dict(counts))
                             for (m, r, s), counts in sorted(populations.items())])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root
    result = analyze(read_tsv(root / "cells.tsv"),
                     {kind: read_tsv(root / f"{kind}_paths.tsv") for kind in ("setup", "hold")})
    with (root / "analysis.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    for kind, timing in result["timing"].items():
        print(kind, timing["endpoints"], dict(timing["crossings"]))
        for group in timing["groups"][:20]:
            print(group["module"], group["endpoints"], round(group["worst_slack_ns"], 3),
                  dict(group["crossings"]))


if __name__ == "__main__":
    main()
