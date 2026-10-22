#!/usr/bin/env python3
"""Decode bounded actual handshakes; preserve all selected raw pre-edge values."""
import csv
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
import capture_failed as c
import analyze_selected as a
r = c.r
OUT = c.OUT / "cycle"


def main():
    OUT.mkdir(exist_ok=False)
    fsdb = c.OUT / "replay/tests" / c.NAME / "work/failed.fsdb"
    raw = OUT / "failed.vcd"
    command = [str(r.shared.VERDI / "platform/linux64/bin/fsdb2vcd"), str(fsdb), "-o", str(raw),
               "-bt", "18000ns", "-et", "20500ns", "-compacttree"]
    env = dict(r.shared.environment(), LD_LIBRARY_PATH=str(r.shared.VERDI / "etc/lib/libstdc++/linux64"))
    with (OUT / "conversion.log").open("x") as stream:
        subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=90)
    r.p.prepare.save(OUT / "conversion.json", dict(command=command, fsdb_sha256=r.p.prepare.sha(fsdb)))
    events = iter(a.vcd(a.normalize(raw)))
    _, decl = next(events)
    r.p.prepare.save(OUT / "declarations.json", decl)
    clk = decl["ara_tb.clk"]["code"]
    cycle = decl[r.SYSTEM + ".i_ara_commit_monitor.cycle_q"]["code"]
    fields = {n: d["code"] for n, d in decl.items()}
    rows = []
    for timestamp, before, after in events:
        if before.get(clk) != "0" or after.get(clk) != "1":
            continue
        number = int(before.get(cycle, "0"), 2)
        if not 19190 <= number <= 19240:
            continue
        row = dict(cycle=number, time_ns=timestamp/10000)
        row.update({n: int(before[code], 2) if code in before and set(before[code]) <= set("01") else None
                    for n, code in fields.items()})
        rows.append(row)
    r.p.require(len(rows) == 51, "Target interval missing")
    r.p.prepare.save(OUT / "raw_cycles.json", rows)
    with (OUT / "raw_cycles.csv").open("x") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("RAW_PRE_EDGE_CYCLES", len(rows), flush=True)


if __name__ == "__main__":
    main()
