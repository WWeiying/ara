#!/usr/bin/env python3
"""Run a bounded real Attention pair on one already-accepted VCS image."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification/qbs"))
from run_half_scale_soc import atomic_json, digest, hashes, image_files, script_files
from run_tile_context_engine import run_command
from run_refill_overlap_probe import numeric_fields, PERF_FIELDS, SUMMARY_FIELDS, COUNTERS


def check_log(text, overlap):
    rows = re.findall(r"^AKV_REFILL_ATTENTION overlap=([01]) native=1 kv=128 outputs=1536 "
                      r"cycles=(\d+) fcsr=(\d+) vcsr=5 checksum=([0-9a-f]{16}) errors=0\s*$",
                      text, re.M)
    if (len(rows) != 1 or int(rows[0][0]) != overlap or
            int(rows[0][1]) <= 0 or not 0 <= int(rows[0][2]) <= 31 or
            text.count("Core Test *** SUCCESS") != 1):
        raise ValueError("Missing/failed Attention numerical or CSR result")
    perf = [numeric_fields(line.removeprefix("[AKV_PERF] "), PERF_FIELDS)
            for line in text.splitlines() if line.startswith("[AKV_PERF] ")]
    summary = [numeric_fields(line.removeprefix("[AKV_PERF_SUMMARY] "), SUMMARY_FIELDS)
               for line in text.splitlines() if line.startswith("[AKV_PERF_SUMMARY] ")]
    if len(summary) != 1 or len(perf) != 774:
        raise ValueError("Missing/extra hardware commands")
    for i, row in enumerate(perf, 1):
        if (row["seq"] != i or row["success"] != 1 or
                any(row[k] for k in ("fault", "validation_fault", "read_fault", "validation_error"))):
            raise ValueError("Failed/nonsequential AKV command")
    totals = summary[0]
    observed = {k: (max(r[k] for r in perf) if k == "read_outstanding_max" else
                    sum(r[k] for r in perf)) for k in COUNTERS}
    observed.update(records=774, success_records=774, fault_records=0,
                    validation_fault_records=0)
    if totals != observed:
        raise ValueError("Summary differs from per-command accounting")
    expected = dict(records=774, success_records=774, fault_records=0,
                    validation_fault_records=0, v2_full=2, v2_refill=2,
                    release=2, v2_column_load=512, v2_row_load=256,
                    v2_column_panel=0, v2_rejected=0, full=0, refill=0,
                    q_external_bytes=3072, kv_external_bytes=131072,
                    replay_bytes=131072, read_ranges=526,
                    read_payload_bytes=134272, v2_bank_conflict_cycles=0)
    if any(totals[k] != v for k, v in expected.items()):
        raise ValueError("Attention shape, work or traffic changed")
    return dict(overlap=overlap, cycles=int(rows[0][1]), fcsr=int(rows[0][2]),
                vcsr=5, checksum=rows[0][3], hardware_totals=totals)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--integration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=10800)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 10800:
        parser.error("Each simulation is bounded to at most three hours")
    build, integration = args.build.resolve(strict=True), args.integration.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state="PREFLIGHT", pid=os.getpid(), child_pid=None, completed=[])
    def save():
        atomic_json(out / "status.json", state)
    def started(pid):
        state["child_pid"] = pid
        save()
    save()
    try:
        report = json.loads((build / "build.json").read_text())
        inherited = json.loads((build / "manifest.json").read_text())
        gate = json.loads((integration / "status.json").read_text())
        simv = integration / "build/sim/simv"
        if (report["state"] != "BUILT_NOT_EXECUTED" or
                digest(build / "manifest.json") != report["manifest_sha256"] or
                hashes(map(Path, inherited)) != inherited or
                hashes(map(Path, report["generated_sha256"])) != report["generated_sha256"] or
                gate["state"] != "PASS" or
                digest(integration / "probe/result.json") != gate["probe_result_sha256"]):
            raise ValueError("Build or image acceptance gate drift")
        image = hashes(image_files(simv))
        pins = {**inherited, **image, **report["generated_sha256"],
                **hashes([Path(__file__), ROOT / "verification/akv/run_refill_overlap_probe.py",
                    ROOT / "verification/qbs/run_tile_context_engine.py", *script_files(),
                    ROOT / "hardware/scripts/llama_q4km_extract/check-sim-l2.sh",
                    build / "manifest.json", build / "build.json", integration / "status.json",
                    integration / "probe/result.json"])}
        for variant in report["variants"].values():
            elf = Path(variant["elf"])
            if digest(elf) != variant["elf_sha256"]:
                raise ValueError("ELF drift")
            pins[str(elf)] = digest(elf)
        atomic_json(out / "manifest.json", pins)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "verification")
        results = []
        for overlap in (0, 1):
            if hashes(map(Path, pins)) != pins:
                raise ValueError("Input drift before dispatch")
            state.update(state="RUNNING", overlap=overlap)
            save()
            work = out / f"schedule{overlap}"
            work.mkdir()
            elf = work / "input.elf"
            shutil.copy2(report["variants"][str(overlap)]["elf"], elf)
            contract = ["bash", str(ROOT / "hardware/scripts/llama_q4km_extract/check-sim-l2.sh"),
                        str(simv.parent), str(elf), "akv_v2"]
            if run_command(contract, work / "image-contract.log", 180, env, started):
                raise RuntimeError("Image/configuration contract mismatch")
            command = [str(simv), "-no_save", "-l", str(work / "run.vcs.log"),
                       "+PRELOAD=" + str(elf), f"+TESTCASE=akv_refill_attention_{overlap}",
                       "+NO_FSDB", "+NO_INSTR_TRACE", "+AKV_PERF", "+AKV_SUMMARY",
                       "+ARA_CONTRACT_TRACE_LIMIT=100000", "+ARA_UVM_TRACE_LIMIT=100000",
                       "+VECTOR_TRACE=" + str(work / "vector_trace.csv")]
            atomic_json(work / "command.json", command)
            # The simulator uses absolute log/ELF/trace paths; no shared outputs.
            rc = run_command(command, work / "console.log", args.timeout, env, started)
            if rc:
                raise RuntimeError(f"VCS schedule{overlap} exited {rc}")
            state.update(state="CHECKING", child_pid=None)
            save()
            command = [sys.executable, "-m", "ara_verify.uvm_dut", "--require-events",
                       "--require-backend", "--require-axi", "--require-axi-write",
                       "--vector-trace", str(work / "vector_trace.csv"),
                       "--log", str(work / "run.vcs.log"), "--simv", str(simv),
                       "--elf", str(elf), "--output", str(work / "uvm_result.json")]
            if run_command(command, work / "checker.log", 180, env, started):
                raise RuntimeError("Independent UVM boundary check failed")
            uvm = json.loads((work / "uvm_result.json").read_text())
            if (uvm["status"] != "PASS" or uvm.get("issues") or
                    uvm["elf_sha256"] != digest(elf) or
                    uvm["log_sha256"] != digest(work / "run.vcs.log")):
                raise ValueError("Protocol result/input identity mismatch")
            result = check_log((work / "run.vcs.log").read_text(), overlap)
            result["evidence_sha256"] = hashes([work / name for name in
                ("input.elf", "run.vcs.log", "vector_trace.csv", "uvm_result.json")])
            atomic_json(work / "result.json", result)
            results.append(result)
            state["completed"].append(overlap)
            save()
        if (hashes(map(Path, pins)) != pins or
                len({(r["checksum"], r["fcsr"], r["vcsr"]) for r in results}) != 1):
            raise ValueError("Provenance, output bytes or architectural FP/vector status changed")
        atomic_json(out / "result.json", dict(state="PASS", trials=results,
            attention_speedup=results[0]["cycles"] / results[1]["cycles"],
            cycle_reduction_percent=100 * (1-results[1]["cycles"] / results[0]["cycles"]),
            scope="Complete real captured Decode Attention, paired schedule0/1 on same RTL; not model speedup"))
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        state["child_pid"] = None
        save()


if __name__ == "__main__":
    main()
