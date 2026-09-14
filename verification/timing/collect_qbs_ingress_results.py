#!/usr/bin/env python3
"""Archive only completed ingress-pipeline checks and matched before/after work."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess

from summarize_sram_results import compare_cases, completed, sha, write_csv

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run, out = args.run.resolve(), args.output.resolve()
    before, after = run / "before_results", run / "after_fixed_results"
    for directory in (before, after):
        status = json.loads((directory / "status.json").read_text())
        if status["state"] != "PASS":
            raise ValueError(f"incomplete regression: {directory}")
        if sha(Path(status["simv"])) != status["simv_sha256"]:
            raise ValueError(f"simulator changed: {directory}")
    if sha(before / "commands.vectors") != sha(after / "commands.vectors"):
        raise ValueError("command inputs differ")
    marker = "QBS engine PASS: 33 functional cases plus four fault classes"
    commands = compare_cases(completed(before / "commands.log", marker),
                             completed(after / "commands.log", marker))
    if len(commands) != 33:
        raise ValueError("incomplete command matrix")

    logs = {"commands_before": before / "commands.log",
            "commands_after": after / "commands.log",
            "macro_functional": run / "adapter_macro_functional/sram/run.log",
            "payload_equivalence": run / "payload/payload/run.log"}
    macro = completed(logs["macro_functional"], "QBS SRAM streaming PASS cases=81 stalls=0")
    if "QBS SRAM full-ingress clear PASS" not in macro:
        raise ValueError("missing full-queue independent-clear check")
    strobe_masks = int(re.search(r"strobe_masks=(\d+)", macro)[1])
    completed(logs["payload_equivalence"], "QBS payload equivalence PASS")

    real = []
    inputs = {"commands": sha(before / "commands.vectors")}
    for vectors in sorted((before / "real").glob("*.vectors")):
        name = vectors.stem
        if sha(vectors) != sha(after / "real" / vectors.name):
            raise ValueError(f"real-capture inputs differ: {name}")
        inputs[name] = sha(vectors)
        bl, al = before / "real" / f"{name}.log", after / "real" / f"{name}.log"
        bt = completed(bl, "QBS engine PASS: 1 functional cases")
        at = completed(al, "QBS engine PASS: 1 functional cases")
        comparison, = compare_cases(bt, at)
        traffic = r"QBS traffic case=0 weight=(\d+) activation=(\d+) payload=(\d+) ranges=(\d+) dot=(\d+) prefetch_wait=(\d+)"
        btraffic, atraffic = re.search(traffic, bt), re.search(traffic, at)
        if btraffic is None or atraffic is None or btraffic.groups() != atraffic.groups():
            raise ValueError(f"traffic/dot work differs: {name}")
        real.append([name, *comparison, *map(int, atraffic.groups())])
        logs[f"real_before_{name}"], logs[f"real_after_{name}"] = bl, al
    if len(real) != 6:
        raise ValueError("expected six complete real-capture slices")
    bl, al = run / "decode_before/run.log", run / "decode_after/run.log"
    bt = completed(bl, "QBS engine PASS: 1 functional cases")
    at = completed(al, "QBS engine PASS: 1 functional cases")
    comparison, = compare_cases(bt, at)
    btraffic, atraffic = re.search(traffic, bt), re.search(traffic, at)
    if btraffic is None or atraffic is None or btraffic.groups() != atraffic.groups():
        raise ValueError("Decode traffic/dot work differs")
    real.append(["q4_decode_m1n32", *comparison, *map(int, atraffic.groups())])
    inputs["q4_decode_m1n32"] = sha(run / "decode.vectors")
    logs["real_before_decode"], logs["real_after_decode"] = bl, al
    logs["handoff"] = run / "handoff_final/latest/console.log"
    completed(logs["handoff"], "QBS/AKV handoff smoke: PASS traps=0")
    handoff = (run / "handoff_final/latest/summary.txt").read_text()
    if not all(line in handoff.splitlines() for line in
               ("status=PASS", "qbs_commands=4", "akv_commands=10")):
        raise ValueError("missing QBS/AKV command handoffs")

    soc = json.loads((run / "soc_final/status.json").read_text())
    if soc["state"] != "PASS":
        raise ValueError("current-RTL ordinary RVV regression did not pass")
    for name, expected in soc["source_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"RTL changed since regression: {name}")
    for record in json.loads((run / "dc_after/manifest.json").read_text())["sources"]:
        if sha(ROOT / record["path"]) != record["sha256"]:
            raise ValueError(f"local DC sources changed: {record['path']}")

    out.mkdir(parents=True, exist_ok=True)
    header = ["case", "profile", "m", "n", "k_blocks", "weight_layout", "activation_layout",
              "before_cycles", "after_cycles", "delta_cycles", "delta_percent"]
    write_csv(out / "commands.csv", header, commands)
    write_csv(out / "real.csv", ["name", *header, "weight_bytes", "activation_bytes",
                                "payload_bytes", "ranges", "dot_cycles", "prefetch_wait"], real)
    evidence = {}
    for name, source in logs.items():
        target = out / f"{name}.log"
        shutil.copy2(source, target)
        evidence[name] = {"source": str(source), "sha256": sha(target)}
    dc = {name: json.loads((run / name / "status.json").read_text())
          for name in ("dc_before", "dc_after")}
    summary = {"recorded_utc": datetime.now(timezone.utc).isoformat(), "run": str(run),
               "command_cases": len(commands), "real_slices": len(real),
               "macro_functional_strobe_masks": strobe_masks,
               "macro_timing_checks": False, "formal_equivalence": False,
               "integrated_timing_measured": False, "local_dc": dc,
               "ordinary_rvv": {key: soc[key] for key in ("state", "tests", "finished")},
               "source_sha256": soc["source_sha256"], "input_sha256": inputs,
               "evidence": evidence}
    (out / "rtl.patch").write_bytes(subprocess.check_output(
        ["git", "diff", "HEAD", "--", "hardware/src", "hardware/include", "scripts/gen_qbs_abi.py"],
        cwd=ROOT))
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"archived {len(commands)} commands, {len(real)} real slices; local DC "
          + ", ".join(f"{key}={value['state']}" for key, value in dc.items()))


if __name__ == "__main__":
    main()
