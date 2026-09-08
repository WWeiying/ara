#!/usr/bin/env python3
"""One isolated, provenance-preserving D256 native performance comparison."""

import argparse
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from run_portability_stage2 import ROOT, command, sha, write_json


def collect(directory, mode, kv):
    spec = importlib.util.spec_from_file_location(
        "attention_summary",
        ROOT / "hardware/scripts/llama_q4km_extract/summarize-ara-attention-core.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runs = [p for p in directory.glob("decode_attention_core_*")
            if p.is_dir() and not p.is_symlink()]
    if len(runs) != 1:
        raise RuntimeError(f"expected one exact run, found {len(runs)}")
    run = runs[0]
    reports = list(run.glob("llm_perf_report_*.log"))
    if len(reports) != 1 or not (run / "complete").exists():
        raise RuntimeError("missing completed run and unique performance report")
    rows = module.parse_run(mode, kv, run, run / "ara.log", reports[0])
    if not rows or any(r["status"] != "PASS" or int(r["mismatches"]) for r in rows):
        raise RuntimeError("incomplete or failed numerical comparison")
    text = (run / "ara.log").read_text()
    if "Core Test *** SUCCESS" not in text:
        raise RuntimeError("simulation did not complete successfully")
    if mode.startswith("akv_v2"):
        if "ATTENTION_DISPATCH native_v2=1 " not in text:
            raise RuntimeError("native execution was not confirmed")
        command_count = 0
        for line in text.splitlines():
            if line.startswith("[AKV_PERF]"):
                command_count += 1
                fields = module.parse_key_values(line)
                if fields.get("success") != "1" or fields.get("fault") != "0":
                    raise RuntimeError("native AKV command fault")
        if command_count == 0:
            raise RuntimeError("native AKV command evidence is missing")
    return rows


def run_smoke(out, sim_dir):
    elf = out / "smoke.elf"
    (ROOT / "apps/bin").mkdir(parents=True, exist_ok=True)
    with (ROOT / "apps/bin/.llama-q4km-operator-build.lock").open("w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        rc = command(["make", "-C", ROOT / "apps", "akv_d256_reuse_smoke", "sim_l2_mb=16"],
                     out / "build.log")
        if rc:
            return rc
        shutil.copy2(ROOT / "apps/bin/akv_d256_reuse_smoke", elf)
    write_json(out / "binaries.json", {"elf_sha256": sha(elf),
                                       "simv_sha256": sha(sim_dir / "simv")})
    rc = command(["bash", ROOT / "hardware/scripts/llama_q4km_extract/check-sim-l2.sh",
                  sim_dir, elf, "akv_v2"], out / "sim-contract.log")
    if rc:
        return rc
    rc = command([sim_dir / "simv", "-no_save", "-l", "vcs.log",
                  f"+PRELOAD={elf}", "+TESTCASE=akv_d256_reuse", "+NO_FSDB",
                  "+NO_INSTR_TRACE", "+AKV_PERF"], out / "ara.log", cwd=out,
                 timeout=10800)
    text = (out / "ara.log").read_text()
    if ("AKV D256 reuse smoke: PASS cases=8 bit_exact=1" not in text or
            "AKV D256 online PV: PASS cases=8 bit_exact=1" not in text or
            "Core Test *** SUCCESS" not in text):
        return 1
    return rc


def capture_model(out):
    specs = json.loads((ROOT / "hardware/scripts/akv/model-generality-manifest.json").read_text())
    model = next(m for m in specs["models"] if m["id"] == "gemma3_1b_q4km")
    binary = Path("/home/wangwy/llama/platforms/cva6-qemu/build/llama-format-capture-host/bin/llama-completion")
    if sha(model["model"]) != model["expected_sha256"]:
        raise RuntimeError("Gemma model SHA-256 does not match the pinned manifest")
    prompt = "Explain how a vector processor uses local data reuse." + " Data reuse matters." * 32
    argv = [binary, "-m", model["model"], "-p", prompt, "-n", "2", "-c", "512",
            "-t", "8", "-tb", "8", "-fa", "on", "-no-cnv", "--load-mode", "mmap",
            "--no-warmup", "--seed", "1", "--temp", "0"]
    env = {"LLAMA_Q4KM_CAPTURE_DIR": str(out), "LLAMA_Q4KM_CAPTURE_LAYER": "0",
           "LLAMA_Q4KM_CAPTURE_PHASE": "decode", "LLAMA_Q4KM_CAPTURE_PROFILE": "attention_core"}
    write_json(out / "capture-provenance.json", {"model": model, "argv": list(map(str, argv)),
               "environment": env, "binary_sha256": sha(binary)})
    rc = command(argv, out / "capture.log", env, timeout=1200)
    if rc:
        return rc
    return command([sys.executable, ROOT / "hardware/scripts/llama_q4km_extract/package_attention_capture.py",
                    out, "--model", model["name"]], out / "package.log")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--kv", type=int)
    parser.add_argument("--sim-dir", type=Path)
    parser.add_argument("--mode", choices=("akv_v2", "akv_v2_portable", "tiled_rvv", "rvv", "smoke", "capture"),
                        required=True)
    args = parser.parse_args()
    if args.mode != "capture" and args.sim_dir is None:
        parser.error("--sim-dir is required for RTL runs")
    if args.mode not in ("capture", "smoke") and (args.capture is None or args.kv is None):
        parser.error("--capture and --kv are required for benchmark runs")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = {"status": "RUNNING", "pid": os.getpid(),
             "started_at": datetime.now(timezone.utc).isoformat(),
             "mode": args.mode, "kv": args.kv,
             "capture": str(args.capture.resolve()) if args.capture else None,
             "sim_dir": str(args.sim_dir.resolve()) if args.sim_dir else None,
             "revision": subprocess.check_output(
                 ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    write_json(out / "stage.json", state)
    rc = 1
    try:
        if args.sim_dir:
            args.sim_dir = args.sim_dir.resolve()
            state["simv_sha256"] = sha(args.sim_dir / "simv")
        for directory in ("software/akv/src", "software/akv/include",
                          "apps/llama_q4km_operator", "apps/akv_d256_reuse_smoke"):
            for path in (ROOT / directory).rglob("*"):
                if (path.is_file() and path.name != "data.S" and
                        path.suffix in (".c", ".h", ".S", ".py")):
                    destination = out / "source" / path.relative_to(ROOT)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, destination)
        state["source_sha256"] = {str(p.relative_to(out / "source")): sha(p)
                                  for p in sorted((out / "source").rglob("*"))
                                  if p.is_file()}
        write_json(out / "stage.json", state)
        command(["git", "diff", "--binary", "HEAD"], out / "tracked.patch")
        if args.mode == "capture":
            rc = capture_model(out)
        elif args.mode == "smoke":
            rc = run_smoke(out, args.sim_dir)
        else:
            rc = run_benchmark(out, args)
    except Exception as error:
        state["error"] = str(error)
        rc = 1
    state.update(status="PASS" if rc == 0 else "FAIL", return_code=rc,
                 finished_at=datetime.now(timezone.utc).isoformat())
    write_json(out / "stage.json", state)
    return rc


def run_benchmark(out, args):
    env = {"Q4KM_CAPTURE_ROOT": str(args.capture.resolve()),
           "LLAMA_ATTN_RUN_ROOT": str(out),
           "LLAMA_ATTN_SIM_DIR": str(args.sim_dir.resolve()),
           "LLAMA_ATTN_ARA_TIMEOUT": "10800",
           "LLAMA_ATTN_AKV_PERF_MODE": "detail"}
    rc = command(["bash", ROOT / "hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh",
                  args.mode, str(args.kv), "--ara-only"],
                 out / "worker.log", env, timeout=11100)
    if rc == 0:
        write_json(out / "metrics.json", collect(out, args.mode, args.kv))
    return rc


if __name__ == "__main__":
    sys.exit(main())
