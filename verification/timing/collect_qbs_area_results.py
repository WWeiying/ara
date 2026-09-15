#!/usr/bin/env python3
"""Archive completed byte-routing tests and require identical engine cycles."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from summarize_sram_results import compare_cases, completed, sha, write_csv

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True,
                        help="completed pre-routing ingress-pipeline experiment")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run, baseline, out = (path.resolve() for path in (args.run, args.baseline, args.output))
    new, old = run / "engine_results", baseline / "after_fixed_results"
    for directory in (new, old):
        state = json.loads((directory / "status.json").read_text())
        if state["state"] != "PASS" or sha(Path(state["simv"])) != state["simv_sha256"]:
            raise ValueError(f"incomplete or changed simulator: {directory}")
    if sha(new / "commands.vectors") != sha(old / "commands.vectors"):
        raise ValueError("command stimuli changed")
    marker = "QBS engine PASS: 33 functional cases plus four fault classes"
    commands = compare_cases(completed(old / "commands.log", marker),
                             completed(new / "commands.log", marker))
    if len(commands) != 33 or any(row[-2] != 0 for row in commands):
        raise ValueError("command count or cycle parity mismatch")
    logs = {"commands_before": old / "commands.log", "commands_after": new / "commands.log"}
    inputs = {"commands": sha(new / "commands.vectors")}
    real = []
    for name in ("q4_decode_m1n32", "q4_m4n32", "q4_m8n16", "q4_m7n16",
                 "q6_m4n32", "q6_m8n16", "q6_m7n16"):
        if name == "q4_decode_m1n32":
            before, after = baseline / "decode_after/run.log", new / "decode_functional.log"
            inputs[name] = sha(baseline / "decode.vectors")
        else:
            before, after = old / "real" / f"{name}.log", new / "real" / f"{name}.log"
            vectors = new / "real" / f"{name}.vectors"
            if sha(vectors) != sha(old / "real" / vectors.name):
                raise ValueError(f"real model data changed: {name}")
            inputs[name] = sha(vectors)
        before_text = completed(before, "QBS engine PASS: 1 functional cases")
        after_text = completed(after, "QBS engine PASS: 1 functional cases")
        comparison, = compare_cases(before_text, after_text)
        if comparison[-2] != 0:
            raise ValueError(f"engine cycle parity mismatch: {name}")
        bt = [line for line in before_text.splitlines() if line.startswith("QBS traffic ")]
        at = [line for line in after_text.splitlines() if line.startswith("QBS traffic ")]
        if at != bt:
            raise ValueError(f"engine work/traffic mismatch: {name}")
        real.append([name, *comparison])
        logs[f"{name}_before"], logs[f"{name}_after"] = before, after
    for label, path in (("adapter_before", run / "before/sram/run_stride257.log"),
                        ("adapter_after", run / "after/sram/run_stride257.log"),
                        ("macro", run / "macro/sram/run.log")):
        text = completed(path, "QBS SRAM adapter PASS cases=81 strobe_masks=256")
        for marker in ("QBS SRAM streaming PASS cases=81 stalls=0",
                       "QBS SRAM discontinuous/duplicate PASS stalls=4",
                       "QBS SRAM full-ingress clear PASS"):
            if marker not in text:
                raise ValueError(f"missing coverage marker: {label}: {marker}")
        logs[label] = path
    for bank in (0, 4):
        name = f"sram_adapter_{bank}.csv"
        if (run / "before/sram" / name).read_bytes() != (run / "after/sram" / name).read_bytes():
            raise ValueError(f"cycle trace changed: bank {bank}")
    logs["generic"] = run / "generic/payload/run.log"
    completed(logs["generic"], "QBS payload equivalence PASS checks=110592")
    logs["handoff"] = run / "handoff/latest/console.log"
    completed(logs["handoff"], "QBS/AKV handoff smoke: PASS traps=0")
    handoff = (run / "handoff/latest/summary.txt").read_text().splitlines()
    if not all(item in handoff for item in ("status=PASS", "qbs_commands=4", "akv_commands=10")):
        raise ValueError("incomplete handoff")
    soc = json.loads((run / "soc/status.json").read_text())
    if soc["state"] != "PASS":
        raise ValueError("ordinary RVV regression did not pass")
    for name, expected in soc["source_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"source changed since verification: {name}")
    out.mkdir(parents=True, exist_ok=False)
    columns = ["case", "profile", "m", "n", "k_blocks", "weight_layout", "activation_layout",
               "before_cycles", "after_cycles", "delta_cycles", "delta_percent"]
    write_csv(out / "commands.csv", columns, commands)
    write_csv(out / "real.csv", ["name", *columns], real)
    evidence = {}
    for name, source in logs.items():
        dest = out / f"{name}.log"
        shutil.copy2(source, dest)
        evidence[name] = {"source": str(source), "sha256": sha(dest)}
    for bank in (0, 4):
        source = run / "after/sram" / f"sram_adapter_{bank}.csv"
        shutil.copy2(source, out / source.name)
    (out / "rtl.patch").write_bytes(subprocess.check_output(
        ["git", "diff", "HEAD", "--", "hardware/src", "hardware/include"], cwd=ROOT))
    summary = {"state": "PASS", "recorded": datetime.now(timezone.utc).isoformat(),
               "command_cases": 33, "real_slices": 7, "cycle_parity": True,
               "cycle_trace_parity": True, "macro_timing_checks": False,
               "formal_equivalence": False, "source_sha256": soc["source_sha256"],
               "input_sha256": inputs, "evidence": evidence,
               "ordinary_rvv": {key: soc[key] for key in ("state", "tests", "finished")}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"PASS: 33 commands, 7 real slices, identical cycles; evidence={out}")


if __name__ == "__main__":
    main()
