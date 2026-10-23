#!/usr/bin/env python3
"""Fixed-address real Attention ABBA, with original protocol/numerical checks."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification/qbs"))
from run_half_scale_soc import atomic_json, digest, hashes, image_files, script_files
from run_tile_context_engine import run_command
from run_refill_overlap_probe import numeric_fields, PERF_FIELDS, SUMMARY_FIELDS, COUNTERS
from run_refill_attention_soc import check_log as check_trial


def check_log(text):
    if (text.count("Core Test *** SUCCESS") != 1 or
        text.splitlines().count("AKV_REFILL_ABBA_PASS trials=4 outputs_per_trial=1536") != 1):
        raise ValueError("Incomplete ABBA execution")
    trials, rows, summaries, active, records = [], [], [], False, []
    for line in text.splitlines():
        if line.startswith("AKV_REFILL_TRIAL_BEGIN"):
            i = len(trials)
            if active or i >= 4 or line != f"AKV_REFILL_TRIAL_BEGIN trial={i} overlap={int(i in (1,2))}":
                raise ValueError("ABBA order or nesting changed")
            active, records = True, []
        elif line.startswith("[AKV_PERF] "):
            if not active:
                raise ValueError("Command outside a trial")
            row = numeric_fields(line.removeprefix("[AKV_PERF] "), PERF_FIELDS)
            if row["seq"] != len(rows) + 1:
                raise ValueError("Missing/repeated global command")
            rows.append(row); records.append(row)
        elif line.startswith("AKV_REFILL_ATTENTION"):
            if not active or len(records) != 774:
                raise ValueError("Incomplete or duplicate trial")
            # Normalize sequence numbers only after proving the global stream.
            # Derive local subtotals, then check them against the *raw* final
            # hardware summary below. No per-trial hardware summary is claimed.
            local = []
            for i, row in enumerate(records, 1):
                normalized = dict(row, seq=i)
                local.append("[AKV_PERF] " + " ".join(f"{k}={v}" for k,v in normalized.items()))
            totals = {k: (max(r[k] for r in records) if k == "read_outstanding_max" else
                          sum(r[k] for r in records)) for k in COUNTERS}
            totals.update(records=774, success_records=774, fault_records=0, validation_fault_records=0)
            local.append("[AKV_PERF_SUMMARY] " + " ".join(f"{k}={v}" for k,v in totals.items()))
            # The actual final core success was checked once above; this is a
            # schema adapter for the already-accepted single-trial validator.
            local.extend((line, "Core Test *** SUCCESS"))
            trials.append(check_trial("\n".join(local), int(len(trials) in (1,2))))
            active = False
        elif line.startswith("[AKV_PERF_SUMMARY] "):
            summaries.append(numeric_fields(line.removeprefix("[AKV_PERF_SUMMARY] "), SUMMARY_FIELDS))
    if active or len(trials) != 4 or len(summaries) != 1 or len(rows) != 3096:
        raise ValueError("Incomplete ABBA/hardware records")
    total = {k: (max(r[k] for r in rows) if k == "read_outstanding_max" else
                 sum(r[k] for r in rows)) for k in COUNTERS}
    total.update(records=3096, success_records=3096, fault_records=0, validation_fault_records=0)
    if total != summaries[0]:
        raise ValueError("Global hardware accounting differs from trial subtotals")
    if len({(r["checksum"],r["fcsr"],r["vcsr"]) for r in trials}) != 1:
        raise ValueError("Numerical or FP/vector status changed")
    traffic = "ar r_beats q_external_bytes kv_external_bytes replay_bytes read_ranges read_payload_bytes".split()
    if any(len({r["hardware_totals"][k] for r in trials}) != 1 for k in traffic):
        raise ValueError("Fixed-address trial traffic differs")
    sums = {str(mode): sum(r["cycles"] for r in trials if r["overlap"] == mode) for mode in (0,1)}
    return dict(state="PASS", trials=trials, sums=sums,
                attention_speedup=sums["0"]/sums["1"],
                cycle_reduction_percent=100*(1-sums["1"]/sums["0"]),
                scope="Fixed-address same-ELF real Attention ABBA; not full model performance")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "integration", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    build, integration = args.build.resolve(strict=True), args.integration.resolve(strict=True)
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    state = dict(state="PREFLIGHT", pid=os.getpid(), child_pid=None)
    def save(): atomic_json(out / "status.json", state)
    def started(pid): state.update(child_pid=pid); save()
    save()
    try:
        report = json.loads((build / "build.json").read_text())
        pins = json.loads((build / "manifest.json").read_text())
        simv = integration / "build/sim/simv"
        gate = json.loads((integration / "status.json").read_text())
        if (report["state"] != "READY" or digest(build / "manifest.json") != report["manifest_sha256"] or
            hashes(map(Path,pins)) != pins or digest(Path(report["elf"])) != report["elf_sha256"] or
            gate["state"] != "PASS" or digest(integration / "probe/result.json") != gate["probe_result_sha256"]):
            raise ValueError("Build/image acceptance drift")
        here = Path(__file__).parent
        pins.update(hashes([Path(__file__), *image_files(simv), *script_files(),
            here / "run_refill_attention_soc.py", here / "run_refill_overlap_probe.py",
            ROOT / "verification/qbs/run_tile_context_engine.py", build / "manifest.json",
            build / "build.json", integration / "status.json", integration / "probe/result.json"]))
        atomic_json(out / "manifest.json", pins)
        work = out / "work"; work.mkdir()
        elf, log = Path(report["elf"]), work / "run.vcs.log"
        env = os.environ.copy(); env["PYTHONPATH"] = str(ROOT / "verification")
        command = [str(simv), "-no_save", "-l", str(log), "+PRELOAD=" + str(elf),
                   "+TESTCASE=akv_refill_attention_abba", "+NO_FSDB", "+NO_INSTR_TRACE",
                   "+AKV_PERF", "+AKV_SUMMARY", "+VECTOR_TRACE=" + str(work / "vector_trace.csv"),
                   "+COMMIT_TRACE=" + str(work / "commit_trace.csv"),
                   "+ARA_CONTRACT_TRACE_LIMIT=100000", "+ARA_UVM_TRACE_LIMIT=100000"]
        atomic_json(out / "command.json", command); state["state"] = "RUNNING"; save()
        if run_command(command, work / "console.log", 10800, env, started):
            raise RuntimeError("VCS failed or exceeded three-hour bound")
        state["state"] = "CHECKING"; save()
        command = [sys.executable, "-m", "ara_verify.uvm_dut", "--require-events", "--require-backend",
                   "--require-axi", "--require-axi-write", "--vector-trace", str(work / "vector_trace.csv"),
                   "--log", str(log), "--simv", str(simv), "--elf", str(elf),
                   "--output", str(work / "uvm_result.json")]
        if run_command(command, work / "checker.log", 300, env, started):
            raise RuntimeError("UVM boundary checks failed")
        result = check_log(log.read_text())
        if hashes(map(Path,pins)) != pins:
            raise ValueError("Execution input drift")
        result["evidence_sha256"] = hashes([log, work / "vector_trace.csv", work / "commit_trace.csv",
                                           work / "uvm_result.json", out / "manifest.json"])
        atomic_json(out / "result.json", result)
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc)); raise
    finally:
        state["child_pid"] = None; save()


if __name__ == "__main__": main()
