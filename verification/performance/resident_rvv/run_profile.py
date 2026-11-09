#!/usr/bin/env python3
"""Build passive probes on sealed RTL, then replay the accepted ELF exactly once."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CHAIN = HERE.parent / "chain_profile"
sys.path.insert(0, str(CHAIN))
from build_soc import OUT, digest, execute, require, save, verify
from run_case import checked_soc, checked_software

ACCEPTED = OUT / "akv_pair_integration_vcs_20261107_01"
SOFTWARE = OUT / "akv_pair_integration_build_20261107_01"
SOC = OUT / "chain_soc_admitted_20261107_01"
SOURCE = OUT / "chain_soc_20261107_01"
ELF_SHA = "eea222d18cdff8b7e7353b66beebad87bd6385b1b66a6c303aec6e8bf2179ef0"
IMAGE_SHA = "3ed8bc6b761d49664162b9f3b45e525e5c051923618950cbdb2b38ea403486a6"
FIRST, END = 125000, 162000


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def combine(pins, extra):
    for path, value in extra.items():
        require(path not in pins or pins[path] == value, "Conflicting pin: " + path)
        pins[path] = value


def same_measurement(actual, reference):
    # Only evidence location/digest changes when a passive log gains probe lines.
    ignore = {"log", "log_sha256"}
    return ({k: v for k, v in actual.items() if k not in ignore} ==
            {k: v for k, v in reference.items() if k not in ignore})


def probe_rows(work):
    import csv
    result = {}
    for name in ("akv", "lane0", "lane1", "lane2", "lane3"):
        path = work / ("resident." + name + ".csv")
        count = 0
        with path.open() as stream:
            for row in csv.DictReader(stream):
                require(int(row["cycle"]) == FIRST + count, "Probe cycle discontinuity")
                require(all(re.fullmatch("[0-9]+" if key != "insn" else "[0-9a-f]{8}", value)
                            for key, value in row.items()), "Unknown/malformed sampled signal")
                count += 1
        require(count == END - FIRST, "Truncated probe interval")
        result[name] = dict(rows=count, sha256=digest(path))
    return result


def main(args):
    out = args.output.resolve()
    require(out.is_relative_to(OUT.resolve()) and not out.exists(), "Fresh verification output required")
    out.mkdir()
    statusfile = out / "status.json"
    status = dict(state="PREFLIGHT", owner_pid=os.getpid(), child_pid=None,
                  started=datetime.now(timezone.utc).isoformat(), datapath_changed=False)
    save(statusfile, status)
    result = dict(state="PREFLIGHT", optimization_measured=False, datapath_changed=False)
    try:
        soc, pins = checked_soc(SOC)
        software, extra = checked_software(SOFTWARE)
        combine(pins, extra)
        accepted = json.loads((ACCEPTED / "result.json").read_text())
        require(accepted["state"] == "PASS" and accepted["independent_protocol_checked"] and
                accepted["post_pins_match"], "Missing accepted complete-call proof")
        require(software["elf_sha256"] == accepted["software_sha256"] == ELF_SHA and
                digest(soc["simv"]) == accepted["image_sha256"] == IMAGE_SHA,
                "Not the selected accepted image/software")
        owner = load(HERE.parent / "akv_pair_eval/integration/run.py", "resident_accepted_owner").load_owner()
        _, checker = owner.load_checker("qwen3_abba")
        plan_path = SOURCE / "plan.json"
        require(pins.get(str(plan_path)) == digest(plan_path), "Unsealed original build command")
        command = json.loads(plan_path.read_text())["command"]
        require(command[-2:] == ["-l", "comp.vcs.log"] and "-j8" in command,
                "Unexpected original compile command")
        require(Path(command[command.index("-f") + 1]) == SOURCE / "sources.f",
                "Not the accepted frozen file list")
        monitor = out / "cycle_monitor.sv"
        shutil.copy2(HERE / "cycle_monitor.sv", monitor)
        sim = out / "sim"
        sim.mkdir()
        shutil.copy2(Path(soc["simv"]).parent / "simulator.conf", sim / "simulator.conf")
        command = command[:-2] + [str(monitor)] + command[-2:]
        for directory in (HERE, HERE.parent / "akv_pair_eval", ROOT / "verification/ara_verify"):
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix in (".py", ".sv", ".md", ".c", ".h", ".S"):
                    combine(pins, {str(path): digest(path)})
        for path in (CHAIN / "build_soc.py", CHAIN / "run_case.py", monitor,
                     sim / "simulator.conf", ACCEPTED / "result.json",
                     ROOT / "hardware/scripts/llama_q4km_extract/check-sim-l2.sh"):
            combine(pins, {str(path): digest(path)})
        save(out / "plan.json", dict(schema="resident-passive-profile-v1",
             reference_image=IMAGE_SHA, reference_elf=ELF_SHA, configuration=soc["configuration"],
             compile_command=command, first_cycle=FIRST, end_cycle=END,
             rtl_source=SOURCE.as_posix(), source_revision=soc["revision"],
             datapath_changes=[], added_verification_source=str(monitor),
             replay="Exact accepted ABBA ELF; no firmware/prod RTL edits"))
        pins[str(out / "plan.json")] = digest(out / "plan.json")
        save(out / "source-pins.json", pins)
        verify(pins)
        if args.preflight_only:
            result.update(state="PREFLIGHT_PASS_NOT_EXECUTED")
            return
        execute(command, sim, out / "compile.log", 7200, status, statusfile, "BUILDING_PROBES")
        log = (out / "compile.log").read_text()
        simv = sim / "simv"
        require(simv.is_file() and not re.search(r"(?m)^(Error-|Error:|Fatal:)", log), "Probe build failure")
        verify(pins)
        image_pins = {str(p): digest(p) for p in sim.rglob("*") if p.is_file()}
        save(out / "build.json", dict(state="PASSIVE_PROBE_IMAGE_BUILT_NOT_EXECUTED",
             simv=str(simv), image_sha256=digest(simv), configuration=soc["configuration"],
             source_pins_sha256=digest(out / "source-pins.json"), image_pins=image_pins))
        work = out / "work"
        work.mkdir()
        env = dict(PYTHONPATH=str(ROOT / "verification"), PYTHONDONTWRITEBYTECODE="1",
                   READELF="/usr/bin/readelf", LC_ALL="C")
        os.environ.update(env)
        elf = Path(software["elf"])
        execute(["bash", ROOT / "hardware/scripts/llama_q4km_extract/check-sim-l2.sh",
                 sim, elf, "akv_v2"], work, out / "image-contract.log", 180,
                status, statusfile, "IMAGE_CONTRACT")
        run = [simv, "-no_save", "-l", work / "run.vcs.log", "+PRELOAD=" + str(elf),
               "+TESTCASE=resident_rvv_profile", "+NO_FSDB", "+NO_INSTR_TRACE",
               "+VECTOR_TRACE=" + str(work / "vector_trace.csv"),
               "+COMMIT_TRACE=" + str(work / "commit.csv"), "+AKV_PERF", "+AKV_SUMMARY",
               "+ARA_CONTRACT_TRACE_LIMIT=2000000", "+ARA_UVM_TRACE_LIMIT=2000000",
               "+RESIDENT_TRACE=" + str(work / "resident"),
               "+RESIDENT_FIRST=" + str(FIRST), "+RESIDENT_END=" + str(END)]
        start = time.monotonic()
        execute(run, work, work / "console.log", 10800, status, statusfile, "RUNNING_PROFILE")
        wall = time.monotonic() - start
        measured = checker.check_run(work / "run.vcs.log", SOFTWARE)
        vector = checker.check_vector_workcounts(work / "vector_trace.csv", SOFTWARE)
        require(measured["state"] == "PASS", "Numerical/work acceptance failed")
        require(same_measurement(measured, accepted["measured"]) and
                vector == accepted["vector_command_work"],
                "Passive replay differs in timing/output/CSR/work from accepted reference")
        execute([sys.executable, "-B", "-m", "ara_verify.uvm_dut", "--require-events",
                 "--require-backend", "--require-axi", "--require-axi-write", "--vector-trace",
                 work / "vector_trace.csv", "--log", work / "run.vcs.log", "--simv", simv,
                 "--elf", elf, "--output", work / "uvm_result.json"],
                work, work / "checker.log", 600, status, statusfile, "PROTOCOL_CHECK")
        proof = json.loads((work / "uvm_result.json").read_text())
        require(proof["status"] == "PASS" and proof["issues"] == [] and
                proof["elf_sha256"] == ELF_SHA and
                proof["log_sha256"] == digest(work / "run.vcs.log") and
                proof["vector_trace_sha256"] == digest(work / "vector_trace.csv"),
                "Independent protocol check failed")
        samples = probe_rows(work)
        verify(pins)
        verify(image_pins)
        result.update(state="PASSIVE_REPLAY_PASS", exact_reference_timing_and_outputs=True,
            independent_protocol_checked=True, post_pins_match=True, measured=measured,
            vector_command_work=vector, sample_files=samples, wall_seconds=wall,
            image_sha256=digest(simv), software_sha256=ELF_SHA,
            artifacts={str(p): digest(p) for p in work.iterdir() if p.is_file()})
    except BaseException as exc:
        result.update(state="FAIL", error=repr(exc))
        raise
    finally:
        save(out / "result.json", result)
        status.update(state=result["state"], child_pid=None,
                      finished=datetime.now(timezone.utc).isoformat())
        save(statusfile, status)
    print(json.dumps(dict(state=result["state"], output=str(out))), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")

    def interrupted(sig, _frame):
        raise InterruptedError("Signal " + str(sig))

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    main(parser.parse_args())
