#!/usr/bin/env python3
"""Check opt-in GGML D256 admission with isolated real-model runs.

QBS uses the QEMU instruction model; AKV uses the GGML functional executor.
This tests dispatch and model numerics, not native AKV performance. Native
evidence is collected separately with run_d256_online_order.py.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from run_portability_stage2 import ROOT, QEMU, command, sha, specs, write_json


def plans():
    models = {m["id"]: m for m in specs()}
    gemma = models["gemma3_1b_q4km"]
    qwen = models["qwen25_1p5b_q4km"]
    short = "The answer is"
    long = "Explain how a vector processor uses local data reuse." + " Data reuse matters." * 32
    return [
        dict(name="gemma_enabled", model=gemma, enabled=True, prompt=short),
        dict(name="gemma_default", model=gemma, enabled=False, prompt=short),
        dict(name="qwen_existing", model=qwen, enabled=True, prompt=short),
        dict(name="gemma_long_enabled", model=gemma, enabled=True, prompt=long),
    ]


def decode_evidence(text):
    active = False
    executions, fallbacks = [], []
    for line in text.splitlines():
        if line.startswith("AKV_TOKEN_RUN_BEGIN="):
            active = line.strip() == "AKV_TOKEN_RUN_BEGIN=QBS_AKV_V2"
        if line.startswith("AKV_TOKEN_RUN_EXIT="):
            active = False
        if active and line.startswith(("GGML_RISCV_AKV_EXEC mode=decode ",
                                        "GGML_RISCV_AKV_FALLBACK mode=decode ")):
            fields = dict(item.split("=", 1) for item in line.split()[1:] if "=" in item)
            (executions if line.startswith("GGML_RISCV_AKV_EXEC ") else fallbacks).append(fields)
    return executions, fallbacks


def require_admission(text, plan):
    executions, fallbacks = decode_evidence(text)
    gemma = plan["model"]["id"].startswith("gemma")
    if gemma and not plan["enabled"]:
        if executions or not fallbacks or any(f["reason"] != "shape" for f in fallbacks):
            raise RuntimeError("default Gemma Decode must retain shape fallback")
    else:
        dimension = "256" if gemma else "128"
        if not executions or fallbacks:
            raise RuntimeError("expected every Decode node to execute, without fallback")
        if any(e.get("head_dim") != dimension or e.get("execution") != "functional"
               or e.get("kernel") != "v2" or e.get("d256") != str(int(gemma))
               for e in executions):
            raise RuntimeError("unexpected dimension, execution mode, or D256 admission")
    return {"decode_executed": len(executions), "decode_fallback": len(fallbacks),
            "active_kv": sorted({int(e["active_kv"]) for e in executions}),
            "execution": "GGML functional AKV; QEMU native QBS"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--llama-src", type=Path, required=True)
    parser.add_argument("--llama-binary", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, default=QEMU)
    args = parser.parse_args()
    out, llama = args.output.resolve(), args.llama_src.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = {"status": "RUNNING", "pid": os.getpid(), "cases": {},
             "started_at": datetime.now(timezone.utc).isoformat(),
             "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    cohort = plans()
    for plan in cohort:
        state["cases"][plan["name"]] = {"status": "PENDING"}
    write_json(out / "plan.json", cohort)
    write_json(out / "status.json", state)
    rc = 1
    try:
        binary = out / "llama-simple"
        shutil.copy2(args.llama_binary, binary)
        state["llama_src"] = str(llama)
        state["llama_binary_sha256"] = sha(binary)
        state["qemu_sha256"] = sha(args.qemu)
        state["llama_adapter_sha256"] = sha(llama / "ggml/src/ggml-cpu/arch/riscv/akv.cpp")
        command(["git", "diff", "--binary", "HEAD"], out / "hardware.patch")
        command(["git", "diff", "--binary", "HEAD"], out / "llama.patch", cwd=llama)
        init = ROOT / "hardware/scripts/akv/akv-token-init.c"
        init_sha = sha(init)
        shutil.copy2(init, out / init.name)
        for plan in cohort:
            if sha(binary) != state["llama_binary_sha256"] or sha(init) != init_sha:
                raise RuntimeError("binary or guest launcher changed; refusing mixed inputs")
            if sha(args.qemu) != state["qemu_sha256"]:
                raise RuntimeError("QEMU binary changed during cohort")
            name, model = plan["name"], plan["model"]
            if sha(model["model"]) != model["expected_sha256"]:
                raise RuntimeError(f"model hash mismatch: {name}")
            if sha(model["qemu"]["disk"]) != model["qemu"]["disk_sha256"]:
                raise RuntimeError(f"model disk hash mismatch: {name}")
            run = out / name
            run.mkdir()
            mode = "combined-fallback" if name == "gemma_default" else "combined"
            env = {
                "AKV_LLAMA_SRC": str(llama), "AKV_LLAMA_BINARY": str(binary),
                "AKV_QEMU_BINARY": str(args.qemu), "AKV_MODEL_MODE": mode,
                "AKV_MODEL_D256": str(int(plan["enabled"])), "AKV_MODEL_PORTABLE": "1",
                "AKV_MODEL_TOKENS": "3", "AKV_MODEL_PROMPT": plan["prompt"],
                "AKV_MODEL_DISK": model["qemu"]["disk"],
                "AKV_MODEL_GUEST_PATH": model["qemu"]["guest_path"],
                "AKV_QEMU_MEMORY": model["qemu"]["memory"], "AKV_RUN_DIR": str(run),
                "AKV_MODEL_DIGEST": "MUL_MAT,FLASH_ATTN_EXT", "AKV_MODEL_DYNAMIC_ONLY": "1",
                "AKV_UPDATE_LATEST": "0",
            }
            record = {"status": "RUNNING", "environment": env,
                      "started_at": datetime.now(timezone.utc).isoformat()}
            state["current"] = name
            state["cases"][name] = record
            write_json(out / "status.json", state)
            rc = command(["bash", ROOT / "hardware/scripts/akv/run-qemu-model-check.sh"],
                         run / "worker.log", env, timeout=10800)
            record.update(return_code=rc, status="PASS" if rc == 0 else "FAIL",
                          finished_at=datetime.now(timezone.utc).isoformat())
            if rc == 0:
                record.update(require_admission((run / "qemu.log").read_text(errors="replace"), plan))
            write_json(run / "stage.json", record)
            write_json(out / "status.json", state)
            if rc:
                break
        state["status"] = "PASS" if rc == 0 else "FAIL"
    except Exception as error:
        state.update(status="FAIL", error=str(error))
        rc = 1
        current = state.get("current")
        if current:
            state["cases"][current].update(status="FAIL", error=str(error), return_code=rc)
    for record in state["cases"].values():
        if record["status"] == "PENDING":
            record["status"] = "SKIPPED_AFTER_FAILURE"
    state.update(return_code=rc, finished_at=datetime.now(timezone.utc).isoformat())
    write_json(out / "status.json", state)
    return rc


if __name__ == "__main__":
    sys.exit(main())
