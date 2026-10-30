#!/usr/bin/env python3
"""Prepare a pinned storage unit; execution requires a reviewed manifest hash."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ACCEPTED = ROOT / "verification/out/akv-legacy-repacker-unit-20261024-03"
REPACKER = ROOT / "verification/akv/storage_adapter/akv_legacy_repacker.sv"
REPACKER_SHA = "78ce01557cfdc226b1d6102f88e47afbfef45f54b7735206b88f73e3f45f0a3b"
MEMORY = Path("/home/wangwy/ara/backend/library/mem")
EXPECTED = dict(legacy_rows=105, latency_checks=105, legacy_writes=1361,
                direct_writes=2048, row_checks=2704, column_checks=72, aborts=9,
                q_direct_overlap=2, q_bytes=2048, kv_bytes=32768)
MARKER = "UNIFIED_STORAGE_PASS " + " ".join(f"{k}={v}" for k, v in EXPECTED.items())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pins(paths):
    return {str(p): sha(p) for p in sorted(set(map(Path, paths)))}


def verify(identity):
    if not identity or pins(identity) != identity:
        raise ValueError("Input identity changed or missing")


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def accepted_inputs(directory=ACCEPTED, repacker=REPACKER):
    report_path, sources_path = directory / "result.json", directory / "source-pins.json"
    report = json.loads(report_path.read_text())
    sources = json.loads(sources_path.read_text())
    if report.get("state") != "PASS" or sources.get(str(repacker)) != REPACKER_SHA:
        raise ValueError("Accepted repacker provenance mismatch")
    evidence = report["evidence"]
    if evidence.get(str(sources_path)) != sha(sources_path):
        raise ValueError("Accepted result does not pin its source manifest")
    for name in ("compile.log", "positive.log", "simv"):
        if str(directory / name) not in evidence:
            raise ValueError("Incomplete accepted evidence")
    verify(sources)
    verify(evidence)
    return [report_path, sources_path, *map(Path, sources), *map(Path, evidence)]


def source_graph(sram):
    sources = [ROOT / "hardware/include/akv_pkg.sv"]
    if sram == "tc":
        sources.append(ROOT / "hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv")
    elif sram == "macro":
        for depth in (64, 96, 128):
            name = f"ts1n28hpcpuhdsvtb{depth}x256m1swbso_170a"
            model = MEMORY / name / "VERILOG" / (name + "_tt1v25c.v")
            if not re.search(rf"module\s+TS1N28HPCPUHDSVTB{depth}X256M1SWBSO\s*\(",
                             model.read_text()):
                raise ValueError("Wrong SRAM model")
            sources.append(model)
    else:
        raise ValueError("Unknown SRAM profile")
    sources += [ROOT / "hardware/src/vlsu/akv/akv_context.sv",
                ROOT / "hardware/src/vlsu/akv/akv_v2_context.sv", REPACKER,
                HERE / "akv_q_store.sv", HERE / "akv_unified_context.sv",
                HERE / "unified_storage_tb.sv"]
    # This deliberately small graph has no include files. Refuse silent expansion.
    for source in sources:
        if re.search(r"^\s*`include\b", source.read_text(), re.M):
            raise ValueError(f"New dependency needs explicit pinning: {source}")
    return sources


def check_log(text, exit_code):
    records = [line for line in text.splitlines() if "UNIFIED_STORAGE_PASS" in line]
    if (exit_code != 0 or records != [MARKER] or
            re.search(r"Fatal:|Error(?:-|:)|Assertion.*fail|UNIT_.*(?:TIMEOUT|MISMATCH)",
                      text, re.I)):
        raise ValueError("Storage unit did not pass strictly")
    return dict(EXPECTED)


def run(command, output, name, timeout):
    save(output / f"{name}.command.json", command)
    with (output / f"{name}.log").open("w") as log:
        child = subprocess.Popen(command, cwd=output, stdout=log, stderr=log,
                                 start_new_session=True)
        try:
            code = child.wait(timeout=timeout)
            save(output / f"{name}.exit.json", {"exit_code": code})
            return code
        finally:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


def prepare(output, sram):
    output.mkdir(parents=True, exist_ok=False)
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("VCS unavailable (no compiler invoked)")
    vcs = Path(vcs)
    compiler = vcs.resolve().parents[1] / "linux64/bin/vcs1"
    sources = source_graph(sram)
    identity = pins([*sources, *accepted_inputs(), vcs, vcs.resolve(), compiler,
                     ROOT / "config/sram.mk", ROOT / "hardware/src/vlsu/akv/akv_engine.sv",
                     *HERE.glob("*.py"), HERE / "README.md"])
    command = [str(vcs), "-full64", "-sverilog", "-timescale=1ns/1ps"]
    if sram == "macro":
        # Functional real-macro model, not an SDF/timing or PPA claim.
        command += ["+define+TARGET_SRAM_MC", "+nospecify", "+notimingcheck"]
    command += [*map(str, sources), "-top", "unified_storage_tb", "-o", str(output / "simv")]
    manifest = dict(state="PREPARED_NOT_EXECUTED", output=str(output), sram=sram,
                    source_pins=identity, compile_command=command,
                    compile_timeout_seconds=300, simulation_timeout_seconds=60,
                    expected=EXPECTED, production_integrated=False, ppa_measured=False)
    save(output / "manifest.json", manifest)
    save(output / "status.json", {"state": "PREPARED_NOT_EXECUTED"})
    return sha(output / "manifest.json")


def execute(output, reviewed):
    manifest_path = output / "manifest.json"
    if sha(manifest_path) != reviewed:
        raise ValueError("Reviewed manifest identity mismatch")
    manifest = json.loads(manifest_path.read_text())
    if manifest["output"] != str(output):
        raise ValueError("Do not move prepared outputs")
    if json.loads((output / "status.json").read_text())["state"] != "PREPARED_NOT_EXECUTED":
        raise ValueError("Refuse repeat/partial execution; inspect existing result")
    identity = {**manifest["source_pins"], str(manifest_path): reviewed}
    try:
        verify(identity)
        save(output / "status.json", {"state": "BUILDING", "pid": os.getpid()})
        if run(manifest["compile_command"], output, "compile", 300):
            raise RuntimeError("VCS compilation failed")
        verify(identity)
        save(output / "status.json", {"state": "RUNNING", "pid": os.getpid()})
        code = run([str(output / "simv")], output, "unit", 60)
        counts = check_log((output / "unit.log").read_text(), code)
        verify(identity)
        result = dict(state="PASS", counts=counts, sram=manifest["sram"],
                      manifest_sha256=reviewed, post_pins_match=True,
                      production_integrated=False, ppa_measured=False,
                      evidence=pins([output / name for name in
                                     ("manifest.json", "compile.log", "unit.log", "simv",
                                      "compile.command.json", "compile.exit.json",
                                      "unit.command.json", "unit.exit.json")]))
        save(output / "result.json", result)
        save(output / "status.json", {"state": "PASS"})
    except BaseException as exc:
        state = "TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "FAIL"
        result = {"state": state, "error": repr(exc)}
        save(output / "result.json", result)
        save(output / "status.json", result)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sram", choices=("tc", "macro"), default="tc")
    parser.add_argument("--execute-reviewed", metavar="MANIFEST_SHA256")
    args = parser.parse_args()
    def terminated(*_):
        raise InterruptedError("SIGTERM")
    signal.signal(signal.SIGTERM, terminated)
    if args.execute_reviewed:
        execute(args.output.resolve(), args.execute_reviewed)
    else:
        print("PREPARED_NOT_EXECUTED manifest_sha256=" + prepare(args.output.resolve(), args.sram))


if __name__ == "__main__":
    main()
