#!/usr/bin/env python3
"""Compare DC hierarchical reports without adding parents to their children.

Report deltas are observations, not causal feature costs. In particular, an
unmatched historical report does not establish reduction overhead.
"""
import argparse
import hashlib
import json
from pathlib import Path


def read_report(path):
    raw = path.read_bytes()
    body = raw.decode(errors="replace").split("Hierarchical area distribution", 1)[1]
    rows = {}
    pending = None
    for line in body.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "ara_soc" or fields[0].startswith(("i_", "clk_")):
            pending, fields = fields[0], fields[1:]
        if pending and len(fields) >= 6:
            try:
                values = list(map(float, fields[:5]))
            except ValueError:
                continue
            if pending in rows:
                raise ValueError("duplicate hierarchy: " + pending)
            rows[pending] = dict(zip(("total", "percent", "local_comb", "local_seq", "local_macro"), values))
            pending = None
    if "i_system/i_ara" not in rows:
        raise ValueError("missing Ara hierarchy")
    return rows, hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    old, old_hash = read_report(args.reference)
    new, new_hash = read_report(args.candidate)
    root = "i_system/i_ara"
    prefixes = {
        name: [f"{root}/gen_lanes_{lane}__i_lane/{suffix}" for lane in range(4)]
        for name, suffix in {
            "vmfpu": "i_vfus/i_vmfpu", "valu": "i_vfus/i_valu",
            "operand_requester": "i_operand_requester",
            "lane_sequencer": "i_lane_sequencer", "operand_queues": "i_operand_queues",
            "vrf": "i_vrf",
        }.items()
    }
    for name, suffix in {"rce": "gen_rce_i_rce", "sldu": "i_sldu", "sequencer": "i_sequencer",
                         "dispatcher": "i_dispatcher", "masku": "i_masku", "vlsu": "i_vlsu"}.items():
        prefixes[name] = [root + "/" + suffix]
    shared_path = root + "/i_shared_ordered_adder"
    if shared_path in old or shared_path in new:
        prefixes["shared_ordered_adder"] = [shared_path]
    # Newly introduced engines have no reference instance.
    for name, paths in prefixes.items():
        if name not in ("rce", "shared_ordered_adder") and any(p not in old or p not in new for p in paths):
            raise ValueError("missing nodes in category " + name)
    all_paths = [p for paths in prefixes.values() for p in paths]
    assert not any(a != b and a.startswith(b + "/") for a in all_paths for b in all_paths)
    groups = {}
    for name, paths in prefixes.items():
        a = sum(old.get(p, {}).get("total", 0) for p in paths)
        b = sum(new.get(p, {}).get("total", 0) for p in paths)
        groups[name] = {"reference": a, "candidate": b, "delta": b-a, "paths": paths,
                        "local_comb_delta": sum(new.get(p, {}).get("local_comb", 0) - old.get(p, {}).get("local_comb", 0) for p in paths),
                        "local_seq_delta": sum(new.get(p, {}).get("local_seq", 0) - old.get(p, {}).get("local_seq", 0) for p in paths)}
    a, b = old[root]["total"], new[root]["total"]
    groups["unassigned_glue_and_other"] = {
        "reference": a - sum(v["reference"] for v in groups.values()),
        "candidate": b - sum(v["candidate"] for v in groups.values()),
    }
    rest = groups["unassigned_glue_and_other"]
    rest["delta"] = rest["candidate"] - rest["reference"]
    assert abs(sum(g["delta"] for g in groups.values()) - (b-a)) < 0.01
    # Nested VMFPU breakdown is reported separately; never add it to groups.
    nested = []
    prefix = root + "/gen_lanes_0__i_lane/i_vfus/i_vmfpu/"
    for p in sorted(set(old) | set(new)):
        if p.startswith(prefix) and "/" not in p[len(prefix):] and "clkgate" not in p:
            nested.append({"lane0_child": p[len(prefix):], "reference": old.get(p, {}).get("total", 0),
                           "candidate": new.get(p, {}).get("total", 0)})
    nested_totals = []
    for suffix in ("fpu_gen_i_fpnew_bulk", "fpu_gen_i_fpnew_ordered_fast", "i_fp32_exact_reduction_accum",
                   "i_simd_mul_ew8", "i_simd_mul_ew16", "i_simd_mul_ew32", "i_simd_mul_ew64", "i_simd_div"):
        paths = [f"{root}/gen_lanes_{lane}__i_lane/i_vfus/i_vmfpu/{suffix}" for lane in range(4)]
        a_sub = sum(old.get(p, {}).get("total", 0) for p in paths)
        b_sub = sum(new.get(p, {}).get("total", 0) for p in paths)
        nested_totals.append({"child": suffix, "reference": a_sub, "candidate": b_sub, "delta": b_sub-a_sub})
    result = {"scope": "4-lane historical report comparison; NOT matched causal feature overhead",
              "reports": [{"path": str(p.resolve()), "sha256": h} for p, h in
                          [(args.reference, old_hash), (args.candidate, new_hash)]],
              "soc": {"reference": old["ara_soc"]["total"], "candidate": new["ara_soc"]["total"],
                      "delta": new["ara_soc"]["total"]-old["ara_soc"]["total"]},
              "ara": {"reference": a, "candidate": b, "delta": b-a},
              "disjoint_groups": groups, "nested_vmfpu_lane0_do_not_add": nested,
              "nested_vmfpu_four_lanes_do_not_add": nested_totals}
    with args.out.open("x") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    for name, values in sorted(groups.items(), key=lambda kv: -kv[1]["delta"]):
        print(f"{name:28s} {values['reference']:12.2f} {values['candidate']:12.2f} {values['delta']:+12.2f}")


if __name__ == "__main__":
    main()
