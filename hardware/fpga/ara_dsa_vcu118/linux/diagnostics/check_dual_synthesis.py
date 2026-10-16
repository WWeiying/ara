"""Defer only baseline-equivalent physical estimates, never routed failures."""
import argparse
import csv
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from check_rebuild_reports import summary, clock_violations


def canonical(clock):
    # The second identical MIG gets a generated-clock suffix. Do not normalize
    # arbitrary clock names or collapse unrelated source/destination clocks.
    return re.sub(r"^((?:pll_clk\[[0-2]\]|mmcm_clkout[0-6]))_1$", r"\1", clock)


def reviewed_c2(directory, current):
    """Authorize only the measured, internal C2 synthesis estimates for a trial."""
    prefix = "gen_ddr2.i_dram_wrapper_c2/gen_channel_c2.i_dram/inst/"
    directory = Path(directory)
    if not (directory / "review_complete.txt").is_file():
        raise ValueError("Incomplete C2 review")
    with (directory / "clocks.tsv").open() as f:
        clocks = defaultdict(list)
        for row in csv.DictReader(f, delimiter="\t"):
            clocks[row['clock']].append(row['source'])
    for name in ('mmcm_clkout0', 'mmcm_clkout6'):
        if len(clocks[name]) != 1 or not clocks[name][0].startswith(prefix):
            raise ValueError("C2 clock identity mismatch: " + name)
    allowed = {
        ('mmcm_clkout0', 'mmcm_clkout0'): (581, Decimal('-.403'), Decimal('-.402')),
        ('mmcm_clkout0', 'mmcm_clkout6'): (1, Decimal('-.174'), Decimal('-.173')),
    }
    groups = defaultdict(list)
    seen = set()
    with (directory / "paths.tsv").open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            key = row['from'], row['to']
            if key not in allowed:
                raise ValueError("Unreviewed C2 clock pair")
            if not all(row[k].startswith(prefix) for k in ('source', 'destination')):
                raise ValueError("C2 path leaves MIG")
            unique = key, row['destination']
            if unique in seen:
                raise ValueError("Duplicate C2 endpoint")
            seen.add(unique)
            slack = Decimal(row['slack'])
            if not slack.is_finite() or not allowed[key][1] <= slack < 0:
                raise ValueError("C2 slack outside reviewed synthesis envelope")
            groups[key].append(slack)
    measured = clock_violations(current)
    result = {}
    for pair, (count, lower, reported) in allowed.items():
        if len(groups[pair]) != count or abs(min(groups[pair]) - reported) > Decimal('.001'):
            raise ValueError("C2 path inventory changed")
        key = ('Intra Clock Table', (pair[0],), 'WHS(ns)') if pair[0] == pair[1] else (
            'Inter Clock Table', pair, 'WHS(ns)')
        if measured.get(key) != (reported, Decimal(count)):
            raise ValueError("C2 inventory does not match synthesis report")
        result[key] = {"paths": count, "worst": str(reported),
                       "reason": "internal C2 MIG estimate; must close during implementation"}
    return result


def check(current, baseline, review=None):
    values = summary(current)
    if values[0] < 0 or values[1] != 0 or values[2] != 0:
        raise ValueError("Synthesis setup failed")
    old = clock_violations(baseline)
    new = clock_violations(current)
    reviewed = reviewed_c2(review, current) if review is not None else {}
    counts = defaultdict(int)
    details = []
    for key, (slack, count) in new.items():
        if key in reviewed:
            details.append({"group": key, "physical_trial_review": reviewed[key]})
            continue
        clocks = tuple(canonical(c).replace("/gen_ethernet.i_eth_loader/", "/i_eth_loader/") for c in key[1])
        normalized = (key[0], clocks, key[2])
        if normalized not in old or slack < old[normalized][0]:
            raise ValueError(f"New/worse synthesis physical group: {key}: {slack}")
        counts[normalized] += count
        details.append({"group": key, "baseline_group": normalized,
                        "slack": str(slack), "failing": int(count)})
    for key, count in counts.items():
        mig = all(re.fullmatch(r"pll_clk\[[0-2]\]|mmcm_clkout[0-6]", c) for c in key[1])
        if key[0] == "Inter Clock Table" or key[2] == "WPWS(ns)":
            if count > old[key][1] * (2 if mig else 1):
                raise ValueError(f"Expanded physical group: {key}")
    for offset, label in ((4, "WHS(ns)"), (8, "WPWS(ns)")):
        if sum(c for k, (_, c) in new.items() if k[2] == label) != values[offset+2]:
            raise ValueError("Incomplete physical inventory: " + label)
    return {"passed": True, "eligible_for_implementation": True,
            "synthesis_timing_clean": not new, "deferred": details,
            "routed_checks_relaxed": False,
            "report_sha256": hashlib.sha256(current.encode()).hexdigest()}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("current", type=Path)
    p.add_argument("baseline", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--physical-review", type=Path)
    a = p.parse_args()
    try:
        report = check(a.current.read_text(), a.baseline.read_text(), a.physical_review)
    except (OSError, ValueError) as exc:
        report = {"passed": False, "error": str(exc)}
    a.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    raise SystemExit(0 if report["passed"] else 1)
