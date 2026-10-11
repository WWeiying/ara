#!/usr/bin/env python3
"""Count settled, rising-edge scalar activity in a focused RCE FP64 VCD.

Use fsdb2vcd with the RCE gen_fp64_add/i_add scope and a bounded window.
This measures neither glitches nor power. Expanded array/struct aliases are
deliberately excluded: some FSDB conversions do not update those aliases.
"""

import argparse
import hashlib
import json
from pathlib import Path


SIGNALS = ("mantissa_b", "mantissa_c", "sum_raw", "regular_result")
SCOPE_SUFFIX = ".gen_rce.i_rce.gen_fp64_add.i_add"


def profile(path):
    scope, ids, widths, values, previous = [], {}, {}, {}, {}
    counts = {name: {"cycles": 0, "bits": 0, "unknown_samples": 0}
              for name in SIGNALS}
    samples = valid = unknown_valid = 0
    rising = False
    timestamp = None
    first_sample = last_sample = None
    timescale = []
    in_timescale = False

    def sample():
        nonlocal samples, valid, unknown_valid, first_sample, last_sample
        if not rising:
            return
        samples += 1
        first_sample = timestamp if first_sample is None else first_sample
        last_sample = timestamp
        enable = values.get(ids["in_valid_i"], "x")
        valid += enable == "1"
        unknown_valid += enable not in ("0", "1")
        for name in SIGNALS:
            bits = values.get(ids[name], "x").lower()
            current = int(bits, 2) if set(bits) <= {"0", "1"} else None
            old = previous.get(name)
            counts[name]["unknown_samples"] += current is None
            if old is not None and current is not None:
                counts[name]["cycles"] += old != current
                counts[name]["bits"] += bin(old ^ current).count("1")
            previous[name] = current

    with path.open() as stream:
        for raw in stream:
            line = raw.strip()
            if line.startswith("$timescale"):
                in_timescale = True
            if in_timescale:
                timescale.append(line)
                if "$end" in line:
                    in_timescale = False
                continue
            if line.startswith("$scope"):
                scope.append(line.split()[2])
            elif line.startswith("$upscope"):
                scope.pop()
            elif line.startswith("$var") and ".".join(scope).endswith(SCOPE_SUFFIX):
                fields = line.split()
                name = fields[4]
                if name in (*SIGNALS, "clk_i", "in_valid_i"):
                    if name in ids and (ids[name], widths[name]) != (fields[3], int(fields[2])):
                        raise ValueError("Ambiguous scalar signal: " + name)
                    ids[name], widths[name] = fields[3], int(fields[2])
            elif line.startswith("$enddefinitions"):
                missing = set((*SIGNALS, "clk_i", "in_valid_i")) - ids.keys()
                if missing:
                    raise ValueError("Missing RCE FP64 signals: " + str(missing))
            elif line.startswith("#"):
                sample()
                rising = False
                timestamp = int(line[1:])
            elif line and line[0] in "bB":
                value, code = line[1:].split()
                values[code] = value
            elif line and line[0] in "01xXzZ":
                value, code = line[0].lower(), line[1:]
                if code == ids.get("clk_i"):
                    rising |= values.get(code) == "0" and value == "1"
                values[code] = value
    sample()
    if not samples:
        raise ValueError("No rising edges in VCD")
    return {
        "vcd": str(path),
        "vcd_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "timescale": " ".join(timescale),
        "sample_timestamp_range": [first_sample, last_sample],
        "samples": samples,
        "adjacent_sample_pairs": samples - 1,
        "fp64_valid_cycles": valid,
        "unknown_valid_samples": unknown_valid,
        "signals": counts,
        "signal_widths": widths,
        "method": "Sample after all VCD updates at each rising-edge timestamp; compare adjacent known values.",
        "limits": "Selected scalar RTL signals only; excludes within-cycle glitches, capacitance, clocks and other cones; not power.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vcd", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.write_text(json.dumps(profile(args.vcd), indent=2) + "\n")
