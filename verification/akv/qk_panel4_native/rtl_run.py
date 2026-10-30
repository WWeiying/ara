#!/usr/bin/env python3
"""Own one bounded VCS score gate; never build or modify the sealed image."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

from rtl_build import ROOT, HERE, sha, cases
from rtl_check import check_output

sys.path.insert(0, str(ROOT / "verification/akv"))
sys.path.insert(0, str(ROOT / "verification/qbs"))
from run_refill_overlap_probe import numeric_fields, COUNTERS, PERF_FIELDS, SUMMARY_FIELDS
from run_half_scale_soc import atomic_json, hashes, image_files, script_files

EXPECTED = dict(pairs=8, runs=16, outputs=3240, tailwords=2904, full=16, release=16,
                column_single=1024, column_panel4=256, logical_columns=2048, commands=1312)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_perf(text, expected):
    require(expected == EXPECTED, "Build expected workload changed")
    records, summaries, active = [], [], None
    next_run = 0
    for line in text.splitlines():
        if line.startswith("RTL_QK_BEGIN "):
            require(active is None and next_run < 16, "Duplicate/outside run BEGIN")
            match = re.fullmatch(r"RTL_QK_BEGIN case=(\d+) mode=([01]) kvhead=(\d+) tile=(\d+) vl=(\d+) stride=(\d+)", line)
            require(match is not None, "Malformed BEGIN")
            require((int(match[1]), int(match[2])) == (next_run // 2, next_run % 2), "Run order mismatch")
            active = [int(match[2]), 0]
        elif "[AKV_PERF]" in line:
            require(line.startswith("[AKV_PERF] ") and active is not None, "PERF outside numeric run")
            r = numeric_fields(line[len("[AKV_PERF] "):], PERF_FIELDS)
            mode, index = active
            columns = 32 if mode else 128
            require(index < columns + 2, "Excess command")
            command = 4 if index == 0 else (3 if index == columns + 1 else 6)
            col = int(command == 6)
            count = (4 if mode else 1) * col
            wanted = dict(seq=len(records) + 1, command=command, success=1, fault=0,
                validation_fault=0, validation_error=0, read_fault=0,
                context_ready=int(command != 3), full=0, refill=0, load=0,
                release=int(command == 3), v2_full=int(command == 4), v2_refill=0,
                v2_row_load=0, v2_column_load=col, v2_column_panel=col * mode,
                v2_logical_column=count, v2_k_view_bank_cycles=8 * col,
                v2_bank_conflict_cycles=0, v2_rejected=0,
                q_external_bytes=1536 if command == 4 else 0,
                kv_external_bytes=32768 if command == 4 else 0,
                replay_bytes=128 * count, read_ranges=135 if command == 4 else 0,
                read_payload_bytes=34368 if command == 4 else 0)
            require(all(r[k] == v for k, v in wanted.items()),
                    f"Command work/lifecycle/fault mismatch at seq {len(records)+1}")
            require(r["id"] < 8 and r["busy_cycles"] > 0 and r["read_outstanding_max"] <= 2,
                    "Invalid VID/cycles/outstanding bound")
            if command == 4:
                require(r["ar"] >= 135 and r["r_beats"] >= r["ar"] and r["read_outstanding_max"] > 0,
                        "FULL missing external traffic")
            else:
                require(all(r[k] == 0 for k in ("ar", "r_beats", "translations",
                        "read_outstanding_max", "read_outstanding_occ_sum")),
                        "Local command performed external reads")
            active[1] += 1
            records.append(r)
        elif line.startswith("RTL_QK_END "):
            require(active is not None and active[1] == (34 if active[0] else 130),
                    "Missing command before numeric END")
            next_run += 1
            active = None
        elif "[AKV_PERF_SUMMARY]" in line:
            require(line.startswith("[AKV_PERF_SUMMARY] ") and active is None and next_run == 16,
                    "Malformed/premature hardware summary")
            summaries.append(numeric_fields(line[len("[AKV_PERF_SUMMARY] "):], SUMMARY_FIELDS))
    require(active is None and next_run == 16 and len(records) == 1312 and len(summaries) == 1,
            "Incomplete/extra run or hardware evidence")
    require("[QBS_PERF]" not in text, "Unexpected QBS work")
    total = {k: (max(r[k] for r in records) if k == "read_outstanding_max" else
                  sum(r[k] for r in records)) for k in COUNTERS}
    total.update(records=1312, success_records=1312, fault_records=0, validation_fault_records=0)
    require(summaries[0] == total, "Summary differs from per-command accounting")
    require(total["v2_full"] == 16 and total["release"] == 16 and
            total["v2_column_load"] - total["v2_column_panel"] == 1024 and
            total["v2_column_panel"] == 256 and total["v2_logical_column"] == 2048,
            "Aggregate work mismatch")
    return total


def checked_build(build):
    report = json.loads((build / "build.json").read_text())
    require(report["state"] == "BUILT_NOT_EXECUTED" and report["execution"] == "NOT_RUN" and
            report["post_pins_match"] and report["expected"] == EXPECTED,
            "Not the focused reviewed build")
    require(report["cases"] == [dict(c, fcsr=1) for c in cases()], "Unexpected capture shapes/flags")
    require(sha(build / "source-pins.json") == report["source_pins_sha256"], "Source receipt drift")
    pins = json.loads((build / "source-pins.json").read_text())
    for path, digest in report["artifact_sha256"].items():
        require(path not in pins or pins[path] == digest, "Conflicting build pins")
        pins[path] = digest
    require(all(sha(p) == digest for p, digest in pins.items()), "Build source/artifact drift")
    require(sha(report["elf"]) == report["elf_sha256"], "ELF drift")
    pins[str(build / "build.json")] = sha(build / "build.json")
    return report, pins


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run(args):
    require(1 <= args.timeout <= 10800, "VCS timeout must be 1..10800 seconds")
    build, simv = args.build.resolve(strict=True), args.simv.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    work = out / "work"
    work.mkdir()
    state = dict(state="PREFLIGHT", pid=os.getpid(), child_pid=None,
                 started=datetime.now(timezone.utc).isoformat(), timeout_seconds=args.timeout,
                 service=os.environ.get("SYSTEMD_EXEC_PID"), simv=str(simv), build=str(build))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "verification"))
    env.pop("LLAMA_ATTN_SIM_L2_BYTES", None)
    env.pop("LD_PRELOAD", None)
    pins, result, accepted_image = None, None, None

    def save():
        atomic_json(out / "status.json", state)

    def execute(argv, log, timeout, phase):
        argv = list(map(str, argv))
        atomic_json(out / (phase + "-command.json"), dict(argv=argv, cwd=str(work)))
        with log.open("x") as stream:
            child = subprocess.Popen(argv, cwd=work, env=env, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            state.update(state=phase.upper(), child_pid=child.pid)
            if phase == "running":
                state["simulator_pid"] = child.pid
            save()
            try:
                code = child.wait(timeout=timeout)
            except BaseException:
                stop_group(child)
                raise
            finally:
                state["child_pid"] = None
                save()
        require(code == 0, f"{phase} returned {code}")

    manifest = simv.parent / "vcs_source_manifest.json"

    def manifest_check(stage):
        execute([sys.executable, "-B", "-m", "ara_verify.vcs_source_manifest",
                 "--output", manifest, "--check"], out / (stage + ".log"), 300, stage)

    def interrupted(signum, _frame):
        raise InterruptedError(f"Signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    save()
    try:
        report, pins = checked_build(build)
        require(str(simv) == report["simv"], "Unexpected simulator path")
        acceptance_path = ROOT / "verification/qbs/results/qbacc-soc-20261023.json"
        acceptance = json.loads(acceptance_path.read_text())
        accepted_root = Path(acceptance["worker"])
        accepted_result_path = accepted_root / "result.json"
        require(acceptance["state"] == "PASS" and sha(accepted_result_path) == acceptance["result_sha256"],
                "Accepted image receipt chain changed")
        accepted_result = json.loads(accepted_result_path.read_text())
        require(accepted_result["state"] == "PASS" and accepted_result["neighbors"] == 2,
                "Image lacks accepted probe and neighbor evidence")
        accepted_image_path = accepted_root / "image-pins.json"
        require(str(accepted_image_path) in accepted_result["evidence_sha256"], "Receipt omits image pins")
        for path, digest in accepted_result["evidence_sha256"].items():
            require(sha(path) == digest, "Acceptance evidence drift")
            require(path not in pins or pins[path] == digest, "Acceptance pin conflict")
            pins[path] = digest
        accepted_image = json.loads(accepted_image_path.read_text())
        require(hashes(image_files(simv)) == accepted_image, "Actual image differs from accepted receipt")
        pins[str(acceptance_path)] = sha(acceptance_path)
        pins[str(accepted_result_path)] = sha(accepted_result_path)
        config = {}
        for line in (simv.parent / "simulator.conf").read_text().splitlines():
            k, v = line.split("=", 1)
            require(k not in config, "Duplicate simulator configuration")
            config[k] = v
        require(all(config.get(k) == v for k, v in dict(nr_lanes="4", vlen="1024",
                    akv_enabled="1", akv_v2_enabled="1", sim_l2_mb="16",
                    sim_l2_bytes="16777216", verify_axi_delay="0").items()), "Incompatible image")
        source = json.loads(manifest.read_text())
        require(source["schema_version"] == 1 and Path(source["repo_root"]).resolve() == ROOT,
                "Wrong image source root/schema")
        for row in source["files"]:
            require(row["path"] not in pins or pins[row["path"]] == row["sha256"], "Conflicting image source pin")
            pins[row["path"]] = row["sha256"]
        files = [*image_files(simv), *script_files(), Path(__file__), HERE / "rtl_run_test.py",
                 HERE / "rtl_check.py", HERE / "rtl_build.py", sys.executable,
                 ROOT / "verification/akv/run_refill_overlap_probe.py"]
        for path, digest in hashes(map(Path, files)).items():
            require(path not in pins or pins[path] == digest, "Conflicting worker pin")
            pins[path] = digest
        require(all(sha(p) == digest for p, digest in pins.items()), "Preflight source/image drift")
        manifest_check("manifest-before")
        elf = work / "input.elf"
        shutil.copy2(report["elf"], elf)
        require(sha(elf) == report["elf_sha256"], "ELF copy drift")
        pins[str(elf)] = sha(elf)
        atomic_json(out / "pins-before.json", pins)
        before_sha = sha(out / "pins-before.json")
        require(all(sha(p) == digest for p, digest in pins.items()), "Pre-launch identity drift")
        log = work / "run.vcs.log"
        execute([simv, "-no_save", "-l", log, "+PRELOAD=" + str(elf),
                 "+TESTCASE=akv_qk_panel4_rtl", "+NO_FSDB", "+NO_INSTR_TRACE",
                 "+AKV_PERF", "+AKV_SUMMARY", "+VECTOR_TRACE=" + str(work / "vector_trace.csv"),
                 "+ARA_CONTRACT_TRACE_LIMIT=2000000", "+ARA_UVM_TRACE_LIMIT=2000000"],
                work / "console.log", args.timeout, "running")
        text = log.read_text()
        numeric = check_output(text, report["cases"], (build / "golden.bin").read_bytes())
        totals = check_perf(text, report["expected"])
        execute([sys.executable, "-B", "-m", "ara_verify.uvm_dut", "--require-events",
                 "--require-backend", "--require-axi", "--require-axi-write",
                 "--vector-trace", work / "vector_trace.csv", "--log", log,
                 "--simv", simv, "--elf", elf, "--output", out / "uvm_result.json"],
                out / "uvm-check.log", 600, "checking-uvm")
        uvm = json.loads((out / "uvm_result.json").read_text())
        design = {str(p): sha(p) for p in image_files(simv)
                  if p.name not in ("simulator.conf", "vcs_source_manifest.json")}
        require(uvm["status"] == "PASS" and not uvm["issues"] and
                uvm["elf_sha256"] == sha(elf) and uvm["log_sha256"] == sha(log) and
                uvm["vector_trace_sha256"] == sha(work / "vector_trace.csv") and
                uvm["sim_image_sha256"] == design, "UVM result/provenance mismatch")
        require(sha(out / "pins-before.json") == before_sha, "Start pin receipt drift")
        result = dict(state="CHECKED_PENDING_PINS", numeric=numeric, hardware_totals=totals,
                      scope="Actual RTL score-only correctness, no whole-Attention/performance claim",
                      elf_sha256=sha(elf), sim_image_sha256=design)
    except BaseException as exc:
        state.update(state="TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "FAIL", error=repr(exc))
    finally:
        terminal = state["state"]
        try:
            if pins is not None:
                manifest_check("manifest-after")
                if accepted_image is not None:
                    require(hashes(image_files(simv)) == accepted_image, "Image inventory/content drift")
                after = {p: sha(p) for p in pins}
                atomic_json(out / "pins-after.json", after)
                require(after == pins, "Final source/image/artifact identity drift")
                require(json.loads((out / "pins-before.json").read_text()) == pins, "Start pins drift")
                if result is not None:
                    result["state"] = "PASS"
                    result["evidence_sha256"] = {str(p): sha(p) for p in (
                        work / "run.vcs.log", work / "console.log", work / "vector_trace.csv",
                        out / "uvm_result.json", out / "pins-before.json", out / "pins-after.json")}
                    terminal = "PASS"
        except BaseException as exc:
            terminal = "FAIL"
            state["pin_error"] = repr(exc)
        state.update(state=terminal, child_pid=None, terminal=True,
                     finished=datetime.now(timezone.utc).isoformat())
        if terminal != "PASS":
            result = dict(state=terminal, error=state.get("error"), pin_error=state.get("pin_error"))
        atomic_json(out / "result.json", result)
        save()
        atomic_json(out / "artifact-hashes.json", {str(p): sha(p) for p in out.rglob("*")
                    if p.is_file() and p.name != "artifact-hashes.json"})
    print(json.dumps(state, sort_keys=True), flush=True)
    return 0 if state["state"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=ROOT / "verification/out/akv-qk-panel4-rtl-gate-build-20261023-01")
    parser.add_argument("--simv", type=Path, default=ROOT / "verification/out/qbacc-soc-20261023-02/build/sim/simv")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=10800)
    raise SystemExit(run(parser.parse_args()))
