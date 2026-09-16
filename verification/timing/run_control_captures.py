#!/usr/bin/env python3
"""Replay archived real Qwen slices with cycle/traffic checks against their baseline."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from collect_context_area_results import compare_slice


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-summary", type=Path, required=True)
    parser.add_argument("--simv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline_summary.read_text())
    root = Path(baseline["run"])
    out, simv = args.output.resolve(), args.simv.resolve()
    out.mkdir(parents=True, exist_ok=False)
    status = {"state": "RUNNING", "started": datetime.now(timezone.utc).isoformat(),
              "simv": str(simv), "simv_sha256": sha(simv),
              "baseline_summary": str(args.baseline_summary.resolve()),
              "baseline_sha256": sha(args.baseline_summary), "results": []}

    def save():
        (out / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    save()
    try:
        if baseline["state"] != "PASS" or len(baseline["real_cases"]) != 8:
            raise RuntimeError("expected eight passing real-capture baseline cases")
        for case in baseline["real_cases"]:
            name = case["case"]
            if "decode" in name:
                vector = root / "decode" / (case["profile"] + ".vectors")
                old_log = root / "decode" / case["profile"] / "run.log"
            else:
                vector = root / "real_after" / (name + ".vectors")
                old_log = root / "real_after" / (name + ".log")
            if (sha(vector) != baseline["input_sha256"][str(vector)] or
                    sha(old_log) != baseline["real_log_sha256"][str(old_log)]):
                raise RuntimeError(f"baseline input or output changed: {name}")
            work = out / name
            work.mkdir()
            local_vector = work / "input.vectors"
            shutil.copy2(vector, local_vector)
            with (work / "console.log").open("w") as log:
                subprocess.run([str(simv), "-l", "run.log", "+QBS_FUNCTIONAL_ONLY",
                                f"+QBS_COMMAND_VECTOR_FILE={local_vector}"], cwd=work,
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
            result = compare_slice(old_log, work / "run.log")
            status["results"].append({**case, "cycles": result["cycles"],
                                      "input_sha256": sha(local_vector), "log_sha256": sha(work / "run.log")})
            print(f"PASS {name}: cycles={result['cycles']} delta=0; phase/traffic unchanged", flush=True)
            save()
        status["state"] = "PASS"
        with (out / "summary.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(status["results"][0]))
            writer.writeheader()
            writer.writerows(status["results"])
    except Exception as exc:
        status.update(state="FAIL", error=str(exc))
        raise
    finally:
        status["finished"] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    main()
