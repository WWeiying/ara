#!/usr/bin/env python3
"""Frozen correctness regressions, scheduled on at most five VCS workers."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("shards", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    verify_root = root.parent / "ara_dsa_signoff_integration"
    image, out, shards = (p.resolve() for p in (args.image, args.output, args.shards))
    simv = image / "sim/simv"
    if out.exists():
        parser.error(f"refusing existing output: {out}")
    for report in ("source_check.json", "uvm_result.json"):
        if json.loads((image / report).read_text())["status"] != "PASS":
            parser.error(f"image gate failed: {report}")
    if not simv.is_file():
        parser.error("missing simv")
    bundle = json.loads((shards / "manifest.json").read_text())
    if bundle["status"] != "PASS" or bundle["partition"]["status"] != "PASS":
        parser.error("shard oracle/partition gate failed")
    if bundle["shard_count"] != 8:
        parser.error("expected the eight-shard conversion matrix")
    for row in bundle["shards"] + [bundle["smoke"]]:
        if row["spike_status"] != "PASS" or \
                hashlib.sha256((shards / row["elf"]).read_bytes()).hexdigest() != row["sha256"]:
            parser.error(f"shard golden/input mismatch: {row['name']}")

    inputs = {"numeric": root / "apps/bin/rv64uv-ara-vstore_lookahead"}
    for name in ("fault", "handoff", "masked"):
        inputs[name] = root / f"verification/out/store-lookahead-{name}-20260925-01/work/input.elf"
    for name in ("vfncvt", "vfwcvt", "vfredmax", "vstore_axi_error", "vfwcvt_int8"):
        inputs[name] = root / f"apps/bin/rv64uv-ara-{name}"
    for i in range(8):
        inputs[f"narrow_shard_{i}"] = shards / f"inputs/shard_{i}.elf"
    inputs["narrow_smoke"] = shards / "inputs/smoke.elf"
    for path in inputs.values():
        if not path.is_file():
            parser.error(f"missing ELF: {path}")

    (out / "inputs").mkdir(parents=True)
    manifest = {}
    for name, source in inputs.items():
        frozen = out / f"inputs/{name}.elf"
        shutil.copy2(source, frozen)
        digest = hashlib.sha256(frozen.read_bytes()).hexdigest()
        if digest != hashlib.sha256(source.read_bytes()).hexdigest():
            raise RuntimeError(f"input changed: {source}")
        manifest[name] = {"source": str(source), "elf": str(frozen), "sha256": digest}
    (out / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.copy2(shards / "manifest.json", out / "shard_manifest.json")

    tasks = []
    for group, index in ((401, 0), (301, 4), (201, 1)):
        name = f"control{group}"
        tasks.append((name, ["python3", "verification/verify.py", "replay-failed-rvv",
            "--summary", f"verification/out/integrated-final-control{group}-replay-20260925-01/summary.json",
            "--case", f"ara_dsa_rvv1_short_control_cross_{index}", "--output", str(out / name),
            "--simv", str(simv), "--spike",
            "/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike",
            "--spike-isa", "rv64gcv_zvfh_zvl1024b", "--jobs", "1", "--timeout", "600",
            "--spike-timeout", "30", "--watchdog-cycles", "1000000"], True))
    for name in inputs:
        tasks.append((name, ["bash", str(root / "verification/uvm/run_store_b_focused_case.sh"),
                            str(simv), manifest[name]["elf"], str(out / name)], False))

    def run(task):
        name, command, replay = task
        start = time.monotonic()
        env = dict(os.environ, ARA_FOCUSED_TIMEOUT_SECONDS="900")
        if name == "vstore_axi_error":
            # This directed program creates vector data with vmv, not loads.
            env["ARA_FOCUSED_AXI_READ_REQUIRED"] = "0"
        with (out / f"{name}.driver.log").open("w") as log:
            rc = subprocess.run(command, cwd=verify_root, env=env, stdout=log,
                                stderr=subprocess.STDOUT).returncode
        status = "FAIL"
        report = out / name / ("summary.json" if replay else "uvm_result.json")
        if rc == 0 and report.is_file():
            payload = json.loads(report.read_text())
            passed = (len(payload) == 1 and all(r["status"] == "PASS" for r in payload)) if replay \
                     else payload["status"] == "PASS"
            if passed:
                status = "PASS"
        if name == "numeric" and status == "PASS":
            if "[VSET_PREVIEW_FORWARD]" not in (out / name / "work/run.vcs.log").read_text():
                status = "NO_PREVIEW_EXERCISED"
        result = {"name": name, "status": status, "returncode": rc,
                  "elapsed_s": round(time.monotonic() - start, 2), "report": str(report)}
        print(json.dumps(result), flush=True)
        return result

    smoke = next(task for task in tasks if task[0] == "narrow_smoke")
    results = [run(smoke)]
    (out / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    if results[0]["status"] != "PASS":
        (out / "completion.json").write_text(json.dumps({"status": "FAIL",
            "expected_tests": len(tasks), "finished_tests": 1,
            "reason": "smoke gate failed; full matrix not launched"}, indent=2) + "\n")
        return 1
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for future in concurrent.futures.as_completed(
                [pool.submit(run, t) for t in tasks if t[0] != "narrow_smoke"]):
            results.append(future.result())
            (out / "summary.json").write_text(
                json.dumps(sorted(results, key=lambda r: r["name"]), indent=2) + "\n")
    changed = [name for name, item in manifest.items()
               if hashlib.sha256(Path(item["elf"]).read_bytes()).hexdigest() != item["sha256"]]
    passed = not changed and len(results) == len(tasks) and all(r["status"] == "PASS" for r in results)
    (out / "completion.json").write_text(json.dumps({"status": "PASS" if passed else "FAIL",
        "expected_tests": len(tasks), "finished_tests": len(results), "changed_inputs": changed}, indent=2) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
