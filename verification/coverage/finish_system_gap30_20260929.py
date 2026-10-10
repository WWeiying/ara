#!/usr/bin/env python3
"""Export reviewed full-hierarchy PASS coverage after the Gap30 service exits."""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UNIT = "ara-system-gap30-20260929-01.service"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve(strict=True)
    # This is an independent postprocessing service, not a simulation poller.
    for _ in range(120):
        state = subprocess.check_output(
            ["systemctl", "--user", "show", UNIT, "-p", "ActiveState", "--value"], text=True).strip()
        if state not in ("active", "activating"):
            break
        time.sleep(60)
    else:
        raise RuntimeError("Gap30 service did not finish within two hours")
    checkpoint = json.loads((output / "checkpoint.json").read_text())
    if checkpoint["status"] not in ("PASS", "COMPLETE_WITH_FAILURES"):
        raise RuntimeError("Campaign did not complete; do not publish partial coverage")
    collection = json.loads((output / "passed-only/collection.json").read_text())
    if collection["purpose"] != "INDEPENDENT_PASS_ONLY":
        raise RuntimeError("Not an independently checked PASS-only input set")
    report = output / "passed-only-hierarchy"
    subprocess.run([sys.executable, str(HERE / "run_reviewed_dve_20260929.py"), str(report),
                    "--inputs-file", str(output / "passed-only/inputs.txt")], check=True)
    if json.loads((report / "waiver_status.json").read_text())["status"] != "APPLIED":
        raise RuntimeError("Reviewed native waivers were not applied")
    previous = ROOT / "verification/out/full-recollection-20260928-02/dve/summary.csv"
    names = {"ara_tb", "i_ara", "i_ariane", "csr_regfile_i", "controller_i",
             "gen_mmu.i_cva6_mmu", "i_ptw", "i_qbs_engine", "i_akv_engine"}
    old = {r["Name"]: r for r in csv.DictReader(previous.open()) if r["Name"] in names}
    rows = []
    for r in csv.DictReader((report / "summary.csv").open()):
        if r["Name"] not in old:
            continue
        for metric in ("Line", "Condition", "Branch", "FSM", "Toggle"):
            before, after = old[r["Name"]][metric], r[metric]
            delta = (f"{float(after.rstrip('%')) - float(before.rstrip('%')):.2f}"
                     if before != "NA" and after != "NA" else "NA")
            rows.append({"Module": r["Name"], "Metric": metric,
                         "Before_raw": before, "After_raw": after, "Delta_pp": delta})
    with (output / "coverage_delta.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"status": checkpoint["status"], "counts": checkpoint["counts"],
                      "coverage": str(report), "delta": str(output / "coverage_delta.csv")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
