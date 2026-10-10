#!/usr/bin/env python3
"""Isolated seed509 validation. Launch only after the dispatcher patch is ready."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from ara_verify.artifacts import sha256, simulation_image
from run_coverage_checkpoint import check_service, save

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
OUT = ROOT / "verification/out"
REFERENCE = OUT / "merged-store-fp16-image-20260926-01"
FAILED = OUT / "coverage-checkpoint-20260926-02/functional/short-memory-509"
AXPY = OUT / "merged-store-fp16-smoke-20260926-01/axpy"
CASE = "ara_dsa_rvv1_short_memory_cross_0"
SEGMENTS = ("vlseg", "vssseg", "vsseg", "vsuxseg", "vsegment_emul_edges",
            "vwhole_vstart_edges", "villegal_segment_recovery")
UVM = ("ara_cvxif_if.sv", "ara_cvxif_uvm_pkg.sv", "ara_acc_contract_monitor.sv",
       "ara_cvxif_dut_bind.sv")
PYTHON = sys.executable
DISPATCHER_SHA256 = "0a18ac4521ca8f25257fbbb1d88643bf51a52d27c98f2d52142d4553b5124edb"


def read(path):
    return json.loads(path.read_text())


def cycles(path):
    values = re.findall(r"^\[PERF\] total_cycles\s*:\s*(\d+)\s*$",
                        path.read_text(errors="replace"), re.M)
    if len(values) != 1 or int(values[0]) <= 0:
        raise ValueError(f"expected one positive AXPY total_cycles: {path}")
    return int(values[0])


def vcs_argv(image):
    lines = (image / "sim/simv.daidir/vcs_rebuild").read_text().splitlines()
    commands = [shlex.split(line) for line in lines if line.startswith("vcs ")]
    if len(commands) != 1 or commands[0][-1] != "2>&1":
        raise ValueError("unrecognized recorded VCS build command")
    return [word.replace(str(image), "<IMAGE>") for word in commands[0][:-1]]


def compile_command(output):
    return ["make", "-C", str(ROOT / "hardware"), "compile", "config=default",
            "nr_lanes=4", "vlen=1024", "qbs=1", "akv=1", "akv_v2=1", "sim_l2_mb=2",
            "mc=0", "code_coverage=0", "fail_on_assert=0", "store_b_ab_baseline=0",
            "no_fsdb=1", "verify_axi_delay=1", "verify_uvm_cvxif=1",
            "verify_source_manifest=1", f"buildpath={output / 'build'}",
            f"sim_dir={output / 'sim'}",
            "verify_extra_sources=" + " ".join(str(ROOT / "verification/uvm" / name)
                                                for name in UVM)]


def run(command, log, timeout=1800):
    log.parent.mkdir(parents=True, exist_ok=True)
    save(log.with_suffix(".command.json"), {"command": [str(x) for x in command],
                                           "cwd": str(ROOT), "timeout_s": timeout})
    print(json.dumps([str(x) for x in command]), flush=True)
    with log.open("w") as stream:
        subprocess.run([str(x) for x in command], cwd=ROOT, check=True, timeout=timeout,
                       stdout=stream, stderr=subprocess.STDOUT)


def freeze(output):
    original = FAILED / "tests" / CASE
    inputs = read(original / "inputs.json")
    seed = original / "input.elf"
    if sha256(seed) != inputs["binary"]["sha256"]:
        raise RuntimeError("seed509 ELF no longer matches original evidence")
    if simulation_image(REFERENCE / "sim/simv") != inputs["simv"]["image_sha256"]:
        raise RuntimeError("reference image differs from the failing seed509 image")
    spike = Path(inputs["spike"]["path"])
    if sha256(spike) != inputs["spike"]["sha256"]:
        raise RuntimeError("Spike differs from original seed509 reference")
    axpy_report = read(AXPY / "uvm_result.json")
    if cycles(AXPY / "run.vcs.log") != 2810 or axpy_report["status"] != "PASS":
        raise RuntimeError("AXPY baseline is not the retained 2810-cycle PASS")
    if sha256(AXPY / "input.elf") != axpy_report["elf_sha256"] or \
            sha256(REFERENCE / "sim/simv") != axpy_report["simv_sha256"]:
        raise RuntimeError("AXPY ELF/image differs from the retained baseline")
    # Permit only the authorized dispatcher change relative to this image's sources.
    dispatcher = ROOT / "hardware/src/ara_dispatcher.sv"
    if sha256(dispatcher) != DISPATCHER_SHA256:
        raise RuntimeError("dispatcher differs from Franklin's frozen patch")
    changed = [row["path"] for row in read(REFERENCE / "sim/vcs_source_manifest.json")["files"]
               if sha256(Path(row["path"])) != row["sha256"]]
    if changed != [str(dispatcher)]:
        raise RuntimeError(f"expected only the dispatcher patch, found changed sources: {changed}")
    files = [SCRIPT, dispatcher, spike, FAILED / "summary.json", original / "inputs.json",
             AXPY / "run.vcs.log", AXPY / "uvm_result.json",
             REFERENCE / "sim/vcs_source_manifest.json", REFERENCE / "sim/simulator.conf",
             REFERENCE / "sim/simv.daidir/vcs_rebuild"]
    frozen = {}
    sources = {"seed509": seed, "axpy": AXPY / "input.elf",
               **{name: ROOT / "apps/bin" / f"rv64uv-ara-{name}" for name in SEGMENTS}}
    for name, source in sources.items():
        target = output / "inputs" / f"{name}.elf"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256(source) != sha256(target):
            raise RuntimeError(f"input changed while freezing: {source}")
        files.extend((source, target))
        frozen[name] = str(target)
    summary = output / "inputs/seed509-summary.json"
    save(summary, [{"name": CASE, "profile": "ara_dsa_rvv1_short_memory_cross",
                    "seed": 509, "status": "FAIL", "elf": frozen["seed509"]}])
    files.append(summary)
    record = {"files": {str(path): sha256(path) for path in files},
              "reference_image": simulation_image(REFERENCE / "sim/simv"),
              "spike": str(spike), "inputs": frozen, "seed_summary": str(summary),
              "baseline_cycles": 2810, "compile_argv": vcs_argv(REFERENCE),
              "original_failure": str(original)}
    save(output / "inputs.json", record)
    return record


def check_frozen(output):
    record = read(output / "inputs.json")
    for path, expected in record["files"].items():
        if sha256(Path(path)) != expected:
            raise RuntimeError(f"frozen input changed: {path}")
    if simulation_image(REFERENCE / "sim/simv") != record["reference_image"]:
        raise RuntimeError("original image changed")
    image_record = output / "image.json"
    if image_record.exists() and simulation_image(output / "sim/simv") != read(image_record):
        raise RuntimeError("candidate image changed")
    return record


def check_manifest(output, log):
    run([PYTHON, "-m", "ara_verify.vcs_source_manifest", "--output",
         output / "sim/vcs_source_manifest.json", "--check"], log, 120)


def job(output, name):
    record = check_frozen(output)
    simv = output / "sim/simv"
    result = output / "results" / name
    check_manifest(output, output / "logs" / f"{name}-sources-before.log")
    verify = [PYTHON, ROOT / "verification/verify.py"]
    if name == "seed509":
        run(verify + ["replay-failed-rvv", "--summary", record["seed_summary"],
            "--case", CASE, "--simv", simv, "--spike", record["spike"],
            "--spike-isa", "rv64gcv_zvfh_zvl1024b", "--jobs", "1", "--timeout", "1800",
            "--spike-timeout", "120", "--watchdog-cycles", "250000", "--output", result],
            output / "logs/seed509-replay.log", 2100)
        run(verify + ["audit", "--run", result, "--require-trace", "--require-vector",
            "--require-full-match", "--output", result / "independent_audit.json"],
            output / "logs/seed509-audit.log", 300)
        rows = read(result / "summary.json")
        if len(rows) != 1 or rows[0]["status"] != "PASS" or \
                rows[0]["comparison"]["status"] != "TERMINAL_MATCH" or \
                rows[0]["vector_commit"]["status"] != "PASS":
            raise RuntimeError("seed509 did not achieve complete scalar/vector PASS")
    elif name == "axpy":
        run(["bash", ROOT / "verification/uvm/run_real_dut_case.sh", simv,
             record["inputs"][name], "seed509_axpy", result], output / "logs/axpy.log", 1000)
        measured = cycles(result / "work/run.vcs.log")
        report = {"status": "PASS" if measured <= 2810 else "FAIL",
                  "baseline_cycles": 2810, "candidate_cycles": measured,
                  "delta_cycles": measured - 2810,
                  "elf_sha256": sha256(Path(record["inputs"][name])),
                  "baseline_log": str(AXPY / "run.vcs.log")}
        save(result / "cycle_comparison.json", report)
        if report["status"] != "PASS":
            raise RuntimeError(f"AXPY cycle regression: {measured} > 2810")
    else:
        run(verify + ["run", "--test", "rvv:" + name, "--simv", simv, "--skip-build",
            "--commit-trace", "--jobs", "1", "--timeout", "900", "--output", result],
            output / "logs" / f"{name}.log", 1100)
        captured = result / "tests" / ("rvv_" + name) / "input.elf"
        if sha256(captured) != sha256(Path(record["inputs"][name])):
            raise RuntimeError(f"directed input differs from frozen ELF: {name}")
        run(verify + ["audit", "--run", result, "--require-trace",
            "--output", result / "independent_audit.json"],
            output / "logs" / f"{name}-audit.log", 300)
    check_frozen(output)
    check_manifest(output, output / "logs" / f"{name}-sources-after.log")


def schedule(output, phase, names, workers):
    plan = [{"name": name, "cwd": str(ROOT),
             "command": [PYTHON, str(SCRIPT), "--patch-ready", "--output", str(output),
                         "--job", name]} for name in names]
    plan_path = output / f"{phase}-plan.json"
    save(plan_path, plan)
    run([PYTHON, ROOT / "verification/run_failfast_checkpoint.py", "--plan", plan_path,
         "--jobs", str(workers), "--output", output / f"{phase}-scheduler"],
        output / "logs" / f"{phase}-scheduler.log", 3000)


def execute(output):
    output = output.resolve()
    if output == OUT.resolve() or not output.is_relative_to(OUT.resolve()):
        raise ValueError("output must be a new directory under verification/out")
    output.mkdir(parents=True, exist_ok=False)
    state = {"status": "RUNNING", "phase": "preflight", "rtl_edits": False,
             "workers_max": 5, "coverage_build": False}
    save(output / "validation.json", state)
    try:
        check_service()
        record = freeze(output)
        state["phase"] = "compile"
        save(output / "validation.json", state)
        run(compile_command(output), output / "compile.log", 1800)
        if vcs_argv(output) != record["compile_argv"]:
            raise RuntimeError("candidate VCS compile flags differ from reference")
        if (output / "sim/simulator.conf").read_bytes() != (REFERENCE / "sim/simulator.conf").read_bytes():
            raise RuntimeError("candidate simulator configuration differs from reference")
        if (output / "build/vcs/bender_script_default").read_bytes() != \
                (REFERENCE / "build/vcs/bender_script_default").read_bytes():
            raise RuntimeError("candidate Bender source list/defines differ from reference")
        save(output / "image.json", simulation_image(output / "sim/simv"))
        check_frozen(output)
        for phase, names, workers in (("seed509", ["seed509"], 1),
                                      ("regression", [*SEGMENTS, "axpy"], 5)):
            state["phase"] = phase
            save(output / "validation.json", state)
            schedule(output, phase, names, workers)
        check_frozen(output)
        check_manifest(output, output / "logs/final-sources.log")
        state.update(status="PASS", phase="complete")
        save(output / "validation.json", state)
    except Exception as error:
        state.update(status="STOPPED", reason=f"{type(error).__name__}: {error}",
                     policy="stop on first failure; no retries or automatic repair")
        save(output / "validation.json", state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT / "seed509-fix-20260926-01")
    parser.add_argument("--patch-ready", action="store_true",
                        help="explicit acknowledgement that the authorized patch is ready")
    parser.add_argument("--job", choices=("seed509", "axpy", *SEGMENTS), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.patch_ready:
        parser.error("do not launch until patch ready; then pass --patch-ready")
    os.environ["PYTHONPATH"] = str(ROOT / "verification")
    os.environ["ARA_VCS_TIMEOUT_SECONDS"] = "900"
    os.environ["ARA_CONTRACT_TRACE_LIMIT"] = "100000"
    os.environ["ARA_UVM_TRACE_LIMIT"] = "100000"
    if args.job:
        job(args.output.resolve(), args.job)
    else:
        execute(args.output)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"VALIDATION_STOP: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
